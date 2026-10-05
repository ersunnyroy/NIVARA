"""Top-10 daily opportunity pipeline.

Steps (mirrors the product spec): load universe → liquidity/data exclusions → market regime → per-stock
technical/momentum/volume/RS/fundamental/sector/news/F&O/risk-reward → reject poor setups → rank (with a
per-sector cap) → store an immutable snapshot (versions, weights, data timestamps) → outcomes are tracked
separately. If market data is missing or stale nothing is fabricated: the run is recorded with status
`data_unavailable` / `data_stale` and no recommendations.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.config import LEVELS_VERSION, MODEL_VERSION, SCORING_VERSION, load_config, validate_weights
from app.analytics.evaluate import Evaluation, ExternalInputs, evaluate
from app.analytics.sector import BENCHMARK, INDUSTRY_TO_INDEX, rs_percentiles, stock_relative_strength
from app.core.timeutil import ist_datetime, utcnow
from app.market_calendar.calendar import CLOSE, MarketCalendar, load_calendar
from app.models import (
    OHLCV,
    EventCalendar,
    MarketRegime,
    NewsItem,
    Recommendation,
    RecommendationOutcome,
    ScanRun,
    SectorStrength,
    Signal,
    Stock,
    TaxRule,
)
from app.news.classify import news_component
from app.services.fno_service import fno_component
from app.services.fundamentals_service import fundamental_view
from app.services.market import compute_and_store_regime
from app.services.prices import bars_bulk, index_series
from app.technical.indicators import INDICATOR_VERSION

log = logging.getLogger(__name__)


def _freshness(db: Session, cal: MarketCalendar, now: datetime | None = None) -> tuple[date | None, bool, str]:
    last = db.scalar(select(func.max(OHLCV.date)))
    if last is None:
        return None, False, "No market data has been ingested"
    st = cal.status(now)
    expected = date.fromisoformat(st["last_completed_eod_session"])
    if not cal.holidays_loaded:
        return last, last >= expected - timedelta(days=4), "Holiday calendar not loaded; freshness approximate"
    if last < expected:
        missed = cal.sessions_between(last, expected)
        return last, False, f"Latest data is for {last}, expected {expected} ({missed} session(s) behind)"
    return last, True, f"Data current as of {last} close"


def _eligible(db: Session, as_of: date, excl: dict) -> tuple[list[Stock], Counter]:
    universe = excl.get("universe_index", "nifty500")
    stocks = [s for s in db.scalars(select(Stock).where(Stock.exchange_code == "NSE", Stock.is_active.is_(True)))
              if universe == "all" or universe in (s.index_memberships or [])]
    rej: Counter = Counter()
    out = []
    allowed = set(excl.get("allowed_series", ["EQ"]))
    for s in stocks:
        if s.series and s.series not in allowed:
            rej["series_not_allowed"] += 1
            continue
        if s.is_suspended:
            rej["suspended"] += 1
            continue
        if excl.get("exclude_surveillance") and s.surveillance_flags:
            rej["surveillance"] += 1
            continue
        out.append(s)
    return out, rej


def run_scan(db: Session, as_of: date | None = None, trigger: str = "scheduled", now: datetime | None = None,
             persist: bool = True) -> ScanRun:
    cfg = load_config(db)
    weights = validate_weights(cfg["scoring_weights"])
    risk, excl, scan_cfg = cfg["risk_limits"], cfg["exclusions"], cfg["scanner"]
    cal = load_calendar(db)
    last, fresh, fresh_note = _freshness(db, cal, now)
    as_of = as_of or last
    tax_ver = db.scalar(select(TaxRule.rule_set_version).limit(1))
    target_session = cal.next_trading_day(as_of) if as_of else None
    run = ScanRun(session_date=target_session or date.today(), generated_at=utcnow(),
                  data_as_of=ist_datetime(as_of, CLOSE.hour, CLOSE.minute) if as_of else None,
                  status="running", model_version=MODEL_VERSION, scoring_version=SCORING_VERSION,
                  indicator_version=INDICATOR_VERSION, levels_version=LEVELS_VERSION, tax_rule_version=tax_ver,
                  weights=weights, trigger=trigger, notes=[fresh_note], data_quality={"fresh": fresh})
    if as_of is None:
        run.status = "data_unavailable"
        run.notes = ["DATA UNAVAILABLE — no market data; no recommendations generated"]
        return _save(db, run, persist)
    if not fresh and trigger not in ("backfill", "replay"):
        run.status = "data_stale"
        run.notes = [f"DATA STALE — recommendation disabled. {fresh_note}"]
        return _save(db, run, persist)

    # Only a regime computed for this exact session may be used (a later one would leak future data).
    regime = db.scalar(select(MarketRegime).where(MarketRegime.session_date == as_of)
                       .order_by(MarketRegime.id.desc()).limit(1)) or compute_and_store_regime(db, as_of)
    run.regime_id = regime.id if regime else None
    regime_label = regime.regime if regime else "NEUTRAL"
    if regime is None:
        run.notes.append("Market regime unavailable (index history missing) — treated as NEUTRAL, confidence reduced")

    stocks, rej = _eligible(db, as_of, excl)
    run.universe_size = len(stocks) + sum(rej.values())
    frames = bars_bulk(db, [s.id for s in stocks], as_of, lookback_days=560)
    bench = index_series(db, [BENCHMARK], as_of, 400).get(BENCHMARK)

    # Liquidity / data-quality exclusions.
    candidates: list[tuple[Stock, object]] = []
    for s in stocks:
        df = frames.get(s.id)
        if df is None or df.empty or df.index[-1].date() != as_of:
            rej["no_bar_for_session"] += 1
            continue
        if len(df) < int(excl["min_history_days"]):
            rej["insufficient_history"] += 1
            continue
        close = float(df["close"].iloc[-1])
        if close < float(excl["min_price"]):
            rej["penny_stock"] += 1
            continue
        turn = df["turnover"].iloc[-21:-1].mean() if "turnover" in df else None
        if turn is None or turn != turn or turn / 1e7 < float(excl["min_avg_turnover_cr"]):
            rej["illiquid"] += 1
            continue
        rets = df["close"].pct_change().iloc[-60:].abs() * 100
        if (rets > float(excl["max_abs_gap_pct_unadjusted"])).any():
            rej["abnormal_move_unreliable_data"] += 1
            continue
        candidates.append((s, df))

    # Cross-sectional relative strength.
    rs_ex = {s.symbol: stock_relative_strength(df["close"], bench) for s, df in candidates} if bench is not None else {}
    rs_rate = rs_percentiles(rs_ex) if rs_ex else {}
    sectors = {r.index_name: r for r in db.scalars(select(SectorStrength).where(SectorStrength.date == as_of))}
    as_of_dt = ist_datetime(as_of, CLOSE.hour, CLOSE.minute)
    news_rows = db.scalars(select(NewsItem).where(NewsItem.published_at >= as_of_dt - timedelta(days=14),
                                                  NewsItem.published_at <= as_of_dt,
                                                  NewsItem.stock_id.is_not(None))).all()
    news_by: dict[int, list] = {}
    for n in news_rows:
        news_by.setdefault(n.stock_id, []).append(n)
    events = {}
    for e in db.scalars(select(EventCalendar).where(EventCalendar.event_date > as_of,
                                                    EventCalendar.event_date <= as_of + timedelta(days=21))):
        if "result" in e.purpose.lower():
            events.setdefault(e.stock_id, e.event_date)

    evals: list[tuple[Stock, Evaluation]] = []
    for s, df in candidates:
        idx_name = INDUSTRY_TO_INDEX.get(s.industry or "")
        sec = sectors.get(idx_name) if idx_name else None
        fv = fundamental_view(db, s.id, s.symbol, as_of, float(df["close"].iloc[-1]))
        ev_date = events.get(s.id)
        ext = ExternalInputs(
            rs_rating=rs_rate.get(s.symbol), rs_excess=rs_ex.get(s.symbol),
            fundamentals=(fv["score"], fv["reasons"], fv["cautions"],
                          None if fv["score"] is not None else "; ".join(fv["missing"][:2]) or "Insufficient fundamental data"),
            sector=(sec.score, sec.index_name) if sec else (None, None),
            news=news_component(news_by.get(s.id, []), as_of_dt),
            fno=fno_component(db, s.symbol, s.is_fno, as_of), is_fno=s.is_fno,
            regime=regime_label, regime_confidence=regime.confidence if regime else None,
            upcoming_results_in_sessions=cal.sessions_between(as_of, ev_date) if ev_date else None,
            data_fresh=fresh,
        )
        try:
            ev = evaluate(s.symbol, df, as_of, ext, weights, risk, excl)
        except Exception as e:
            log.warning("evaluate failed for %s: %s", s.symbol, e)
            rej["evaluation_error"] += 1
            continue
        evals.append((s, ev))

    run.eligible_count = len(evals)
    min_score = float(scan_cfg.get("min_score", 55))
    ranked = sorted([x for x in evals if not x[1].rejected and x[1].score and x[1].score.total >= min_score],
                    key=lambda x: (-x[1].score.total, -x[1].confidence))
    for _s, ev in evals:
        if ev.rejected:
            for r in ev.rejection_reasons:
                rej["rejected: " + r.split("(")[0].split(":")[0].strip()[:60]] += 1
        elif ev.score and ev.score.total < min_score:
            rej["below_min_score"] += 1

    # Diversify: cap names per sector.
    top: list[tuple[Stock, Evaluation]] = []
    per_sector: Counter = Counter()
    for s, ev in ranked:
        key = s.industry or "Unknown"
        if per_sector[key] >= int(scan_cfg.get("max_per_sector", 3)):
            continue
        per_sector[key] += 1
        top.append((s, ev))
        if len(top) >= int(scan_cfg.get("top_n", 10)):
            break
    run.rejection_counts = dict(rej)
    run.status = "ok" if top else "ok_no_candidates"
    if not top:
        run.notes.append("No stock passed all filters today — no recommendation is better than a forced one.")
    db.add(run)
    db.flush()
    if persist:
        for s, ev in evals:
            db.add(Signal(run_id=run.id, stock_id=s.id, session_date=run.session_date,
                          score=ev.score.total if ev.score else 0.0, setup=ev.levels.setup if ev.levels else None,
                          components={"score": ev.score.breakdown() if ev.score else None,
                                      "confidence": ev.confidence, "action": ev.action},
                          rejected=ev.rejected, rejection_reasons=ev.rejection_reasons))
        track = closed_outcomes(db)
        for rank, (s, ev) in enumerate(top, 1):
            db.add(_recommendation(run, rank, s, ev, regime_label, track, risk, as_of))
    db.commit()
    return run


def closed_outcomes(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(RecommendationOutcome).where(
        RecommendationOutcome.status.in_(["target1", "target2", "target3", "stopped", "expired"]))) or 0


def _suitability(ev: Evaluation, track: int, min_track: int, missing_weight: float) -> str:
    if ev.action != "BUY" or ev.confidence < 55:
        return "observation"
    if ev.confidence >= 70 and missing_weight <= 15 and track >= min_track:
        return "live_consideration"
    return "paper_trading"


def _recommendation(run: ScanRun, rank: int, s: Stock, ev: Evaluation, regime: str, track: int, risk: dict,
                    as_of: date) -> Recommendation:
    lv, sc = ev.levels, ev.score
    missing = [{"component": c.label, "reason": c.missing_reason} for c in sc.components if c.fraction is None]
    suit = _suitability(ev, track, int(risk.get("min_track_record_for_live", 30)), sc.missing_weight)
    notes = list(ev.confidence_notes)
    if suit == "paper_trading" and track < int(risk.get("min_track_record_for_live", 30)):
        notes.append(f"Capped at paper-trading: model track record has {track} closed outcomes "
                     f"(< {risk.get('min_track_record_for_live')} required)")
    sources = ["NSE CM bhavcopy (EOD, official)", "NSE index closes (EOD, official)"]
    if not any(m["component"] == "Fundamentals" for m in missing):
        sources.append("NSE XBRL financial results")
    if not any(m["component"] == "F&O" for m in missing):
        sources.append("NSE F&O bhavcopy (EOD)")
    sources.append("NSE corporate announcements (RSS)")
    return Recommendation(
        run_id=run.id, session_date=run.session_date, generated_at=run.generated_at, data_as_of=run.data_as_of,
        rank=rank, stock_id=s.id, action=ev.action, suitability=suit, score=sc.total,
        score_breakdown=sc.breakdown(), confidence=ev.confidence, setup=lv.setup, strategy=lv.strategy,
        cmp=ev.cmp, aggressive_entry=lv.aggressive_entry, entry_low=lv.entry_low, entry_high=lv.entry_high,
        conservative_low=lv.conservative_low, conservative_high=lv.conservative_high,
        no_chase_above=lv.no_chase_above, stop=lv.stop, trailing_stop_after_t1=lv.trailing_stop_after_t1,
        target1=lv.target1, target2=lv.target2, target3=lv.target3, risk_pct=lv.risk_pct,
        reward_pcts=lv.reward_pcts, rr=lv.rr_t2, holding_min_sessions=lv.holding_min,
        holding_max_sessions=lv.holding_max, why=ev.why[:6], why_not=ev.why_not[:6], invalidation=ev.invalidation,
        methodology={**lv.methodology, "confidence_notes": notes, "price_action": _slim_pa(ev.price_action),
                     "indicators": {k: ev.indicators.get(k) for k in KEY_INDICATORS}},
        data_sources=sources, missing_components=missing, market_regime=regime, sector=s.industry,
        model_version=run.model_version, scoring_version=run.scoring_version,
        indicator_version=run.indicator_version, levels_version=run.levels_version,
        tax_rule_version=run.tax_rule_version,
    )


KEY_INDICATORS = ["close", "ema_20", "ema_50", "ema_200", "rsi_14", "macd", "macd_signal", "adx", "atr_14", "atr_pct",
                  "rel_volume", "delivery_pct", "hv_20", "high_52w", "low_52w", "supertrend", "bb_upper", "bb_lower"]


def _slim_pa(pa: dict) -> dict:
    return {"structure": pa.get("structure"), "supports": pa.get("supports", [])[:3],
            "resistances": pa.get("resistances", [])[:3],
            "patterns": {k: v for k, v in pa.get("patterns", {}).items() if v.get("detected")}}


def _save(db: Session, run: ScanRun, persist: bool) -> ScanRun:
    if persist:
        db.add(run)
        db.commit()
    return run



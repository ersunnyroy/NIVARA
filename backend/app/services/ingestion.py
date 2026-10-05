"""Pull data from providers and persist it with provenance. Every job is idempotent (upserts)."""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import today_ist, utcnow
from app.data import registry
from app.data.adjustments import detect_adjustments
from app.data.providers.base import DataUnavailable, NotConfigured, ProviderError
from app.models import (
    OHLCV,
    CorporateAction,
    EventCalendar,
    FinancialResult,
    FnoFuture,
    IndexOHLCV,
    InstitutionalFlow,
    MarketHoliday,
    NewsItem,
    OptionChainRow,
    PriceAdjustment,
    Sector,
    Shareholding,
    Stock,
)
from app.news.classify import CLASSIFIER_VERSION, classify, dedupe_hash
from app.repositories.upsert import upsert
from app.services.jobs import job

log = logging.getLogger(__name__)

INDEX_LISTS = ("nifty50", "niftynext50", "nifty100", "nifty200", "nifty500")


def _stock_map(db: Session) -> dict[str, int]:
    return dict(db.execute(select(Stock.symbol, Stock.id).where(Stock.exchange_code == "NSE")).all())


# ---------------------------------------------------------------- reference
def ingest_securities(db: Session) -> dict:
    """EQUITY_L master + NIFTY constituents (industry → sector) + F&O lot sizes."""
    with job(db, "securities", "nse_securities") as j:
        md = registry.market_data()
        res = md.securities()
        rows = []
        for s in res.data:
            rows.append({"symbol": s.symbol, "exchange_code": "NSE", "name": s.name, "isin": s.isin, "series": s.series,
                         "listing_date": s.listing_date, "face_value": s.face_value, "is_active": True,
                         "index_memberships": [], "surveillance_flags": [], "meta": {}, "is_fno": False})
        upsert(db, Stock, rows, ["symbol", "exchange_code"],
               ["name", "isin", "series", "listing_date", "face_value", "is_active"])
        db.commit()
        j.rows = len(rows)
        # constituents
        sectors = {s.name: s.id for s in db.scalars(select(Sector))}
        members: dict[str, list[str]] = defaultdict(list)
        industry: dict[str, str] = {}
        warnings = []
        for idx in INDEX_LISTS:
            try:
                for sec in registry.market_data().index_constituents(idx).data:
                    members[sec.symbol].append(idx)
                    if sec.industry:
                        industry[sec.symbol] = sec.industry
            except ProviderError as e:
                warnings.append(f"{idx}: {e}")
        lots: dict[str, int] = {}
        try:
            lots = registry.fno().lot_sizes().data
        except ProviderError as e:
            warnings.append(f"lot sizes: {e}")
        for st in db.scalars(select(Stock).where(Stock.exchange_code == "NSE")):
            st.index_memberships = members.get(st.symbol, [])
            ind = industry.get(st.symbol)
            if ind:
                st.industry = ind
                if ind not in sectors:
                    sec = Sector(name=ind, index_name=None)
                    db.add(sec)
                    db.flush()
                    sectors[ind] = sec.id
                st.sector_id = sectors[ind]
            st.is_fno = st.symbol in lots
            st.fno_lot_size = lots.get(st.symbol)
        db.commit()
        j.details = {"securities": len(rows), "index_members": len(members), "fno": len(lots), "warnings": warnings}
        j.status = "partial" if warnings else "ok"
        return j.details


def ingest_holidays(db: Session) -> dict:
    with job(db, "holidays", "nse_holidays") as j:
        res = registry.calendar().holidays()
        rows = [{"exchange_code": "NSE", "date": h.date, "segment": h.segment, "description": h.description,
                 "is_special_session": False, "source": "nse"} for h in res.data]
        upsert(db, MarketHoliday, rows, ["exchange_code", "date", "segment"], ["description"])
        j.rows = len(rows)
        j.details = {"holidays": len(rows)}
        return j.details


# ---------------------------------------------------------------- EOD prices
def ingest_eod(db: Session, session: date, create_missing: bool = True) -> dict:
    """Daily bars (all NSE equities) + index closes for one session."""
    out: dict = {"session": session.isoformat()}
    with job(db, f"eod:{session}", "nse_cm_bhavcopy") as j:
        res = registry.market_data().daily_bars(session)
        smap = _stock_map(db)
        missing = [b for b in res.data if b.symbol not in smap]
        if missing and create_missing:
            upsert(db, Stock, [{"symbol": b.symbol, "exchange_code": "NSE", "name": b.symbol, "isin": b.isin,
                                "series": b.series, "is_active": True, "index_memberships": [],
                                "surveillance_flags": [], "meta": {"created_from": "bhavcopy"}, "is_fno": False}
                               for b in missing], ["symbol", "exchange_code"], [])
            db.flush()
            smap = _stock_map(db)
        now = utcnow()
        rows = []
        for b in res.data:
            sid = smap.get(b.symbol)
            if sid is None or b.series not in (None, "EQ", "BE", "BZ", "SM", "ST", "SZ"):
                continue
            rows.append({"stock_id": sid, "date": b.date, "open": b.open, "high": b.high, "low": b.low,
                         "close": b.close, "prev_close": b.prev_close, "volume": int(b.volume or 0),
                         "turnover": b.turnover, "trades": b.trades, "delivery_qty": b.delivery_qty,
                         "delivery_pct": b.delivery_pct, "source": res.provenance.source, "retrieved_at": now})
        upsert(db, OHLCV, rows, ["stock_id", "date"])
        db.commit()
        n_adj = derive_adjustments(db, session, {r["stock_id"]: r for r in rows})
        out["missing_session_suspected"] = n_adj == -1
        n_adj = max(n_adj, 0)
        j.rows = len(rows)
        j.details = {"bars": len(rows), "adjustments": n_adj, "warnings": res.warnings,
                     "data_as_of_dt": res.provenance.data_timestamp}
        out.update(bars=len(rows), adjustments=n_adj, warnings=res.warnings)
    try:
        out["indices"] = ingest_indices(db, session)
    except ProviderError as e:
        out["indices_error"] = str(e)
    return out


def ingest_indices(db: Session, session: date) -> int:
    with job(db, f"indices:{session}", "nse_indices") as j:
        res = registry.market_data().index_bars(session)
        now = utcnow()
        rows = [{"index_name": b.index_name, "date": b.date, "open": b.open, "high": b.high, "low": b.low,
                 "close": b.close, "change_pct": b.change_pct, "volume": b.volume, "turnover_cr": b.turnover_cr,
                 "pe": b.pe, "pb": b.pb, "div_yield": b.div_yield, "source": res.provenance.source,
                 "retrieved_at": now} for b in res.data if b.close is not None]
        upsert(db, IndexOHLCV, rows, ["index_name", "date"])
        j.rows = len(rows)
        j.details = {"indices": len(rows), "data_as_of_dt": res.provenance.data_timestamp}
        return len(rows)


def derive_adjustments(db: Session, session: date, todays: dict[int, dict]) -> int:
    """Split/bonus factors from the exchange-adjusted previous close (see app/data/adjustments.py)."""
    prev = dict(db.execute(
        select(OHLCV.stock_id, func.max(OHLCV.date)).where(OHLCV.date < session).group_by(OHLCV.stock_id)
    ).all())
    if not prev:
        return 0
    prev_close: dict[int, float] = {}
    # Fetch the last close before `session` for each stock that traded today.
    ids = [sid for sid in todays if sid in prev]
    for chunk_start in range(0, len(ids), 1000):
        part = ids[chunk_start : chunk_start + 1000]
        for sid, d, c in db.execute(select(OHLCV.stock_id, OHLCV.date, OHLCV.close).where(OHLCV.stock_id.in_(part))
                                    .where(OHLCV.date < session).where(OHLCV.date >= session - timedelta(days=15))):
            if d == prev[sid]:
                prev_close[sid] = c
    # Only compare against the immediately preceding session in our store; if that session is missing for
    # everyone (a backfill gap) the comparison is meaningless, so skip.
    global_prev = max(prev.values())
    candidates = []
    for sid, row in todays.items():
        pc_exchange, last_close = row.get("prev_close"), prev_close.get(sid)
        if not pc_exchange or not last_close or prev[sid] != global_prev:
            continue
        for ex_date, factor in detect_adjustments([(prev[sid], last_close, None), (session, row["close"], pc_exchange)]):
            candidates.append((sid, ex_date, factor, pc_exchange, last_close))
    if len(candidates) > max(25, 0.05 * len(todays)):
        log.warning("adjustment detection skipped: %d candidates looks systemic (data gap?)", len(candidates))
        return -1  # signals a missing session between our last stored date and `session`
    n = 0
    now = utcnow()
    for sid, ex_date, factor, pc_exchange, last_close in candidates:
        upsert(db, PriceAdjustment, [{"stock_id": sid, "ex_date": ex_date, "factor": factor,
                                      "method": "exchange_prev_close", "created_at": now,
                                      "note": f"NSE previous close {pc_exchange} vs our last close {last_close}"}],
               ["stock_id", "ex_date"], ["factor", "note"])
        n += 1
    db.commit()
    return n


def corporate_action_factor(action_type: str, ratio_from: float | None, ratio_to: float | None) -> float | None:
    """Price factor applied to bars before the ex-date.
    split: face value ratio_from → ratio_to (₹10 → ₹2 ⇒ 0.2); bonus a:b (a new per b held) ⇒ b / (a + b)."""
    if not ratio_from or not ratio_to or ratio_from <= 0 or ratio_to <= 0:
        return None
    if action_type == "split":
        return ratio_to / ratio_from
    if action_type == "bonus":
        return ratio_to / (ratio_from + ratio_to)
    return None


def derive_adjustments_from_actions(db: Session, tolerance: float = 0.35) -> dict:
    """Record split/bonus adjustment factors from exchange corporate-action records.

    The current NSE bhavcopy does not adjust the previous close on ex-dates, so the published actions are the
    authoritative source. Each factor is cross-checked against the observed close-to-close ratio across the
    ex-date; a mismatch beyond ±35% is not applied (logged for review) because the record may be mis-dated.
    Only ex-dates that have already passed are applied (point-in-time)."""
    applied, skipped, unverifiable = 0, [], 0
    now = utcnow()
    # Combine all split/bonus records sharing an ex-date (de-duplicating repeated filings of the same action).
    groups: dict[tuple[int, date], dict[tuple, CorporateAction]] = defaultdict(dict)
    for ca in db.scalars(select(CorporateAction).where(CorporateAction.action_type.in_(["split", "bonus"]),
                                                       CorporateAction.ex_date.is_not(None),
                                                       CorporateAction.ex_date <= today_ist())):
        groups[(ca.stock_id, ca.ex_date)][(ca.action_type, ca.ratio_from, ca.ratio_to)] = ca
    for (stock_id, ex_date), acts in groups.items():
        factors = [corporate_action_factor(*k) for k in acts]
        if any(f is None for f in factors):
            continue
        f = math.prod(factors)
        if abs(f - 1) < 1e-6:
            continue
        before = db.scalar(select(OHLCV.close).where(OHLCV.stock_id == stock_id, OHLCV.date < ex_date)
                           .order_by(OHLCV.date.desc()).limit(1))
        on = db.scalar(select(OHLCV.close).where(OHLCV.stock_id == stock_id, OHLCV.date >= ex_date)
                       .order_by(OHLCV.date).limit(1))
        note = "; ".join(ca.subject for ca in acts.values()) + f" (combined factor {f:.4f})"
        if before and on:
            observed = on / before
            if abs(math.log(observed / f)) > math.log(1 + tolerance):
                skipped.append(f"{stock_id}:{ex_date}: observed {observed:.3f} vs factor {f:.3f}")
                continue
            note += f"; observed close ratio {observed:.3f}"
        else:
            unverifiable += 1
            note += "; not price-verified (no bars around ex-date)"
        upsert(db, PriceAdjustment, [{"stock_id": stock_id, "ex_date": ex_date, "factor": f,
                                      "method": "corporate_action", "note": note[:1000], "created_at": now}],
               ["stock_id", "ex_date"], ["factor", "method", "note"])
        applied += 1
    db.commit()
    if skipped:
        log.warning("corporate-action factors not applied (price mismatch): %s", skipped[:10])
    return {"applied": applied, "skipped_mismatch": len(skipped), "unverifiable": unverifiable,
            "examples_skipped": skipped[:10]}


def _discover_special_sessions(db: Session, session: date) -> int:
    """Exchanges occasionally trade on a weekend/holiday (e.g. Budget day, Muhurat). When `session`'s published
    previous closes disagree with our last stored closes, probe the closed days in between for a bhavcopy."""
    last = db.scalar(select(func.max(OHLCV.date)).where(OHLCV.date < session))
    found = 0
    d = (last or session - timedelta(days=4)) + timedelta(days=1)
    while d < session:
        try:
            ingest_eod(db, d)
        except DataUnavailable:
            d += timedelta(days=1)
            continue
        upsert(db, MarketHoliday, [{"exchange_code": "NSE", "date": d, "segment": "CM", "is_special_session": True,
                                    "description": "Special trading session (discovered from published bhavcopy)",
                                    "session_open": "09:15", "session_close": "15:30", "source": "inferred"}],
               ["exchange_code", "date", "segment"], ["is_special_session", "description", "session_open",
                                                      "session_close"])
        db.commit()
        found += 1
        d += timedelta(days=1)
    if found:
        ingest_eod(db, session)  # recompute derived data now that the gap is filled
    return found


def backfill_eod(db: Session, start: date, end: date, calendar=None) -> dict:
    """Download every session in [start, end] (cached on disk, polite rate). Missing days are skipped."""
    from app.market_calendar.calendar import load_calendar

    cal = calendar or load_calendar(db)
    done, skipped, errors = 0, [], []
    d = start
    while d <= end:
        if cal.is_trading_day(d):
            try:
                res = ingest_eod(db, d)
                done += 1
                if res.get("missing_session_suspected"):
                    done += _discover_special_sessions(db, d)
            except DataUnavailable as e:
                skipped.append(f"{d}: {e}")
                if d < today_ist() - timedelta(days=3):
                    # No official bhavcopy for a past weekday ⇒ the exchange was closed (holiday master only
                    # covers the current year). Record it so historical session arithmetic stays correct.
                    upsert(db, MarketHoliday, [{"exchange_code": "NSE", "date": d, "segment": "CM",
                                                "description": "Holiday (inferred: no official bhavcopy published)",
                                                "is_special_session": False, "source": "inferred"}],
                           ["exchange_code", "date", "segment"], [])
                    db.commit()
            except ProviderError as e:
                errors.append(f"{d}: {e}")
        d += timedelta(days=1)
    return {"sessions_ingested": done, "skipped": skipped[-20:], "errors": errors[-20:]}


# ---------------------------------------------------------------- flows / corporate / events
def ingest_flows(db: Session) -> dict:
    with job(db, "flows", "nse_flows") as j:
        res = registry.flows().institutional_flows()
        now = utcnow()
        rows = [{"date": f.date, "category": "FII" if f.category.upper().startswith("FII") else "DII",
                 "buy_value_cr": f.buy_value_cr, "sell_value_cr": f.sell_value_cr, "net_value_cr": f.net_value_cr,
                 "source": res.provenance.source + " (provisional)", "retrieved_at": now} for f in res.data]
        upsert(db, InstitutionalFlow, rows, ["date", "category"])
        j.rows = len(rows)
        j.details = {"rows": len(rows)}
        return j.details


def ingest_corporate_actions(db: Session, start: date, end: date) -> dict:
    with job(db, "corporate_actions", "nse_corporate_actions") as j:
        res = registry.corporate_actions().corporate_actions(start, end)
        smap = _stock_map(db)
        now = utcnow()
        rows = []
        for c in res.data:
            sid = smap.get(c.symbol)
            if sid is None:
                continue
            rows.append({"stock_id": sid, "ex_date": c.ex_date, "record_date": c.record_date,
                         "action_type": c.action_type, "subject": c.subject[:500], "ratio_from": c.ratio_from,
                         "ratio_to": c.ratio_to, "amount": c.amount, "source": res.provenance.source,
                         "retrieved_at": now, "raw": c.raw})
        upsert(db, CorporateAction, rows, ["stock_id", "ex_date", "subject"])
        db.commit()
        j.rows = len(rows)
        j.details = {"rows": len(rows), "adjustments": derive_adjustments_from_actions(db)}
        return j.details


def ingest_event_calendar(db: Session) -> dict:
    with job(db, "event_calendar", "nse_event_calendar") as j:
        res = registry.corporate_actions().event_calendar()
        smap = _stock_map(db)
        now = utcnow()
        rows = [{"stock_id": smap[e.symbol], "event_date": e.event_date, "purpose": e.purpose[:255],
                 "description": e.description, "source": res.provenance.source, "retrieved_at": now}
                for e in res.data if e.symbol in smap]
        upsert(db, EventCalendar, rows, ["stock_id", "event_date", "purpose"], ["description", "retrieved_at"])
        j.rows = len(rows)
        j.details = {"rows": len(rows)}
        return j.details


# ---------------------------------------------------------------- news
def _match_symbol(company: str | None, names: dict[str, tuple[int, str]]) -> tuple[int | None, str | None]:
    if not company:
        return None, None
    key = _norm(company)
    hit = names.get(key)
    return (hit[0], hit[1]) if hit else (None, None)


def _norm(name: str) -> str:
    n = name.lower().replace("&", "and")
    for suffix in (" limited", " ltd.", " ltd", "."):
        n = n.replace(suffix, "")
    return " ".join(n.split())


def ingest_news(db: Session) -> dict:
    """Primary-source exchange announcements (+ optional secondary RSS). Classified deterministically."""
    names = {_norm(n): (i, s) for i, s, n in db.execute(select(Stock.id, Stock.symbol, Stock.name))}
    by_symbol = {s: i for _, (i, s) in names.items()}
    total, errors = 0, []
    for prov in registry.news():
        key = "nse_announcements" if prov.name.startswith("nse") else "rss_secondary"
        try:
            with job(db, f"news:{prov.name}", key) as j:
                res = prov.latest()
                now = utcnow()
                rows = []
                for a in res.data:
                    sid, sym = (by_symbol.get(a.symbol), a.symbol) if a.symbol in by_symbol else \
                        _match_symbol(a.company, names)
                    text = f"{a.headline} {a.body or ''}"
                    c = classify(text, a.source_tier)
                    rows.append({
                        "stock_id": sid, "symbol": sym, "company": a.company, "source": a.source,
                        "source_tier": a.source_tier, "headline": a.headline[:2000], "body": a.body, "url": a.url,
                        "published_at": a.published_at, "retrieved_at": now, "event_type": c.event_type,
                        "sentiment": c.sentiment, "sentiment_label": c.sentiment_label, "impact": c.impact,
                        "horizon": c.horizon, "confidence": c.confidence,
                        "is_verified": a.source_tier == "primary", "classifier": CLASSIFIER_VERSION,
                        "dedupe_hash": dedupe_hash(a.source, a.headline, a.published_at, a.url), "raw": a.raw,
                    })
                upsert(db, NewsItem, rows, ["dedupe_hash"], [])
                j.rows = len(rows)
                j.details = {"items": len(rows)}
                total += len(rows)
        except (ProviderError, NotConfigured) as e:
            errors.append(f"{prov.name}: {e}")
    return {"items": total, "errors": errors}


# ---------------------------------------------------------------- F&O
def ingest_fno(db: Session, session: date) -> dict:
    with job(db, f"fno:{session}", "nse_fo_bhavcopy") as j:
        res = registry.fno().fo_bhavcopy(session)
        futures, options = res.data
        now = utcnow()
        frows = [{"underlying": f.underlying, "date": f.date, "expiry": f.expiry, "instrument": f.instrument,
                  "open": f.open, "high": f.high, "low": f.low, "close": f.close, "settle": f.settle,
                  "underlying_price": f.underlying_price, "oi": f.oi, "change_oi": f.change_oi, "volume": f.volume,
                  "lot_size": f.lot_size, "source": res.provenance.source, "retrieved_at": now} for f in futures]
        upsert(db, FnoFuture, frows, ["underlying", "date", "expiry"])
        # Keep only the two nearest expiries of the option chain to bound storage.
        exp_by_u: dict[str, list[date]] = defaultdict(list)
        for o in options:
            if o.expiry not in exp_by_u[o.underlying]:
                exp_by_u[o.underlying].append(o.expiry)
        keep = {u: set(sorted(e)[:2]) for u, e in exp_by_u.items()}
        orows = [{"underlying": o.underlying, "date": o.date, "expiry": o.expiry, "strike": o.strike,
                  "option_type": o.option_type, "close": o.close, "settle": o.settle,
                  "underlying_price": o.underlying_price, "oi": o.oi, "change_oi": o.change_oi, "volume": o.volume,
                  "iv": None, "source": res.provenance.source} for o in options if o.expiry in keep[o.underlying]]
        upsert(db, OptionChainRow, orows, ["underlying", "date", "expiry", "strike", "option_type"])
        j.rows = len(frows) + len(orows)
        j.details = {"futures": len(frows), "options": len(orows), "data_as_of_dt": res.provenance.data_timestamp}
        return {"futures": len(frows), "options": len(orows)}


# ---------------------------------------------------------------- fundamentals
def ingest_fundamentals(db: Session, symbols: list[str], max_filings: int = 9) -> dict:
    """Result filings (XBRL) + shareholding for the given symbols. Slow by design (polite rate)."""
    prov = registry.fundamentals()
    smap = _stock_map(db)
    stats = {"symbols": 0, "results": 0, "shareholding": 0, "errors": []}
    with job(db, "fundamentals", "nse_results") as j:
        for sym in symbols:
            sid = smap.get(sym)
            if sid is None:
                continue
            try:
                filings = prov.result_filings(sym).data
            except ProviderError as e:
                stats["errors"].append(f"{sym}: {e}")
                continue
            have = {(pe, c) for pe, c in db.execute(select(FinancialResult.period_end, FinancialResult.consolidated)
                                                     .where(FinancialResult.stock_id == sid))}
            consolidated_any = any(f.consolidated for f in filings)
            chosen = [f for f in filings if f.consolidated == consolidated_any and f.xbrl_url]
            chosen.sort(key=lambda f: f.period_end, reverse=True)
            for f in chosen[:max_filings]:
                if (f.period_end, f.consolidated) in have:
                    continue
                try:
                    st = prov.financial_statement(f).data
                except ProviderError as e:
                    stats["errors"].append(f"{sym} {f.period_end}: {e}")
                    continue
                db.add(FinancialResult(
                    stock_id=sid, period_type=f.period_type, period_start=st.period_start or f.period_start,
                    period_end=f.period_end, consolidated=f.consolidated, is_bank=st.is_bank or f.is_bank,
                    audited=f.audited, broadcast_at=f.broadcast_at, revenue=st.revenue, other_income=st.other_income,
                    total_income=st.total_income, total_expenses=st.total_expenses, finance_costs=st.finance_costs,
                    depreciation=st.depreciation, pbt=st.pbt, tax=st.tax, pat=st.pat, pat_owners=st.pat_owners,
                    ebitda=st.ebitda, ebit=st.ebit, eps_basic=st.eps_basic, eps_diluted=st.eps_diluted,
                    paid_up_capital=st.paid_up_capital, face_value=st.face_value, debt_equity=st.debt_equity,
                    interest_coverage=st.interest_coverage, source="NSE XBRL filing", source_url=f.xbrl_url,
                    retrieved_at=utcnow(), raw={},
                ))
                stats["results"] += 1
            try:
                for s in prov.shareholding(sym).data[:8]:
                    upsert(db, Shareholding, [{
                        "stock_id": sid, "period_end": s.period_end, "promoter_pct": s.promoter_pct,
                        "public_pct": s.public_pct, "promoter_pledged_pct": s.promoter_pledged_pct,
                        "fii_pct": s.fii_pct, "dii_pct": s.dii_pct, "mf_pct": s.mf_pct,
                        "broadcast_at": s.broadcast_at, "source": "NSE shareholding pattern",
                        "source_url": s.xbrl_url, "retrieved_at": utcnow()}], ["stock_id", "period_end"])
                    stats["shareholding"] += 1
            except ProviderError as e:
                stats["errors"].append(f"{sym} shareholding: {e}")
            stats["symbols"] += 1
            db.commit()
        j.rows = stats["results"]
        j.details = {k: v for k, v in stats.items() if k != "errors"} | {"errors": stats["errors"][-20:]}
        j.status = "partial" if stats["errors"] else "ok"
    return stats


def last_ohlcv_date(db: Session) -> date | None:
    return db.scalar(select(func.max(OHLCV.date)))


def latest_index_date(db: Session) -> date | None:
    return db.scalar(select(func.max(IndexOHLCV.date)))


def data_age(db: Session) -> dict[str, datetime | None]:
    return {"ohlcv": last_ohlcv_date(db), "indices": latest_index_date(db)}

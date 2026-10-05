"""Plain-language "Simple view" for everyday users.

Translates the engine's outputs into everyday words. It adds no new predictions: every number shown comes from
the scanner, the fundamentals engine, the market-regime model or the stock's own price history, and every idea
shows both the possible gain and the possible loss. Intraday ideas are only possible with live prices.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import date

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.data import registry
from app.models import AppSetting, Recommendation, ScanRun, Stock
from app.schemas.dto import j
from app.services.fundamentals_service import fundamental_view
from app.services.market import latest_regime
from app.services.outcomes_service import CLOSED, TRADED
from app.services.prices import bars_bulk, current_prices
from app.technical.indicators import ema

CACHE_VERSION = "simple-v2"

MOOD = {
    "STRONG BULLISH": ("Very positive", "Most stocks are rising and investors are confident."),
    "BULLISH": ("Positive", "More stocks are rising than falling."),
    "NEUTRAL": ("Mixed", "The market has no clear direction right now."),
    "BEARISH": ("Weak", "More stocks are falling than rising."),
    "STRONG BEARISH": ("Very weak", "Most stocks are falling and nervousness in the market is high."),
}
MOOD_ADVICE = {
    "STRONG BULLISH": "Good conditions for new buying, but still follow the stop-loss on every trade.",
    "BULLISH": "Reasonable conditions for careful buying.",
    "NEUTRAL": "Be selective; buy only the strongest ideas and keep some cash aside.",
    "BEARISH": "Be careful. Keep most money aside and buy only small amounts, if at all.",
    "STRONG BEARISH": "Not a good time for new short-term buying. Most ideas below are marked 'Wait'.",
}

GOOD = {
    "technical": "The price has been moving up steadily",
    "momentum": "Buying interest is strong right now",
    "volume": "More shares than usual are being bought",
    "relative_strength": "It has done better than most other stocks recently",
    "fundamentals": "The company's business numbers look healthy",
    "sector": "Its industry is doing well right now",
    "news": "Recent company news has been positive",
    "fno": "Futures & options traders are positioned for a rise",
    "risk_reward": "The possible gain is well above the possible loss",
}
BAD = {
    "technical": "The price trend is not clearly upward",
    "momentum": "Buying interest is weak",
    "fundamentals": "The company's business numbers are weak or incomplete",
    "sector": "Its industry is going through a weak phase",
    "news": "There has been some negative company news",
}

GLOSSARY = [
    {"term": "Buy zone", "meaning": "The price range in which buying makes sense. Buying above it means paying too much."},
    {"term": "Stop-loss", "meaning": "A price at which you sell to keep a loss small if the idea goes wrong. Always set it."},
    {"term": "Target", "meaning": "A price at which you can sell to book profit. It is a goal, not a promise."},
    {"term": "Do not buy above", "meaning": "If the price is already above this, the remaining profit is too small for the risk."},
    {"term": "Short term", "meaning": "Ideas meant to be held for a few days to a few weeks."},
    {"term": "Long term", "meaning": "Companies you might hold for a year or more, based on business quality."},
    {"term": "Intraday", "meaning": "Buying and selling on the same day. Very risky and needs live prices."},
    {"term": "Market mood", "meaning": "Whether most stocks are rising or falling overall. Weak mood = buy less."},
    {"term": "Confidence", "meaning": "How strongly the system's checks agree. Even 'High' can be wrong."},
]


def _conf_label(c: float | None) -> str:
    if c is None:
        return "Unknown"
    return "High" if c >= 70 else "Medium" if c >= 55 else "Low"


def _weeks(min_s: int, max_s: int) -> str:
    lo, hi = max(1, round(min_s / 5)), max(1, math.ceil(max_s / 5))
    if hi <= 1:
        return "about a week"
    return f"about {lo}–{hi} weeks" if lo != hi else f"about {lo} weeks"


def _similar_ideas(db: Session, conf: float) -> dict | None:
    """How past ideas in the same confidence band turned out (live + replayed history)."""
    band = (0, 55) if conf < 55 else (55, 70) if conf < 70 else (70, 101)
    recs = db.scalars(select(Recommendation).where(Recommendation.confidence >= band[0],
                                                   Recommendation.confidence < band[1])).unique().all()
    traded = [r.outcome for r in recs if r.outcome and r.outcome.status in TRADED and r.outcome.return_pct is not None]
    closed = [r.outcome for r in recs if r.outcome and r.outcome.status in CLOSED]
    if len(traded) < 20:
        return None
    n = len(traded)
    return {
        "ideas": len(closed), "bought": n,
        "reached_first_target_pct": round(100 * sum(1 for o in traded if o.t1_hit_date) / n),
        "hit_stop_loss_pct": round(100 * sum(1 for o in traded if o.status == "stopped") / n),
        "made_money_pct": round(100 * sum(1 for o in traded if o.return_pct > 0) / n),
        "average_result_pct": round(float(np.mean([o.return_pct for o in traded])), 2),
        "note": "Based on past ideas with similar confidence (including ideas replayed on past data). "
                "Past results do not guarantee future results.",
    }


def _short_term(db: Session, regime_label: str | None) -> dict:
    run = db.scalar(select(ScanRun).where(ScanRun.status.in_(["ok", "ok_no_candidates"]))
                    .order_by(ScanRun.generated_at.desc()).limit(1))
    if run is None:
        return {"status": "data_unavailable", "message": "No ideas yet. The system has not run its daily scan.",
                "items": []}
    recs = db.scalars(select(Recommendation).where(Recommendation.run_id == run.id)
                      .order_by(Recommendation.rank)).unique().all()
    prices = current_prices(db, [r.stock_id for r in recs])
    items = []
    for r in recs:
        comps = {c["key"]: c for c in (r.score_breakdown or {}).get("components", [])}
        good = [GOOD[k] for k, c in sorted(comps.items(), key=lambda kv: -(kv[1].get("fraction") or 0))
                if c.get("fraction") is not None and c["fraction"] >= 0.7 and k in GOOD][:4]
        risks = []
        cp = prices.get(r.stock_id)
        price = cp.price if cp and cp.price else r.cmp
        if price > r.no_chase_above:
            risks.append(f"The price has already gone up. Wait for it to come back to ₹{r.entry_low:,.2f}–₹{r.entry_high:,.2f}.")
        if any("Results due" in w for w in (r.why_not or [])):
            risks.append("The company will announce results soon. The price can jump or fall sharply around that day.")
        if regime_label in ("BEARISH", "STRONG BEARISH"):
            risks.append("The overall market is weak, which can pull even good stocks down.")
        risks += [BAD[k] + "." for k, c in comps.items()
                  if c.get("fraction") is not None and c["fraction"] < 0.4 and k in BAD][:2]
        risks.append("Any stock can fall suddenly on unexpected news. Never invest money you cannot afford to lose.")
        mid = (r.entry_low + r.entry_high) / 2
        if r.action == "BUY":
            what, tone = "Can buy in the buy zone", "buy"
        elif r.action == "WAIT":
            what, tone = "Wait — don't buy yet", "wait"
        else:
            what, tone = "Avoid for now", "avoid"
        items.append({
            "symbol": r.stock.symbol, "company": r.stock.name, "industry": r.sector, "what_to_do": what, "tone": tone,
            "price_now": price, "price_as_of": j(cp.as_of) if cp else j(r.data_as_of),
            "price_kind": cp.kind if cp else "eod_close",
            "buy_zone": [r.entry_low, r.entry_high], "do_not_buy_above": r.no_chase_above,
            "stop_loss": r.stop, "possible_loss_pct": round(100 * (r.stop / mid - 1), 1),
            "targets": [{"price": t, "gain_pct": round(100 * (t / mid - 1), 1)} for t in (r.target1, r.target2) if t],
            "holding_time": _weeks(r.holding_min_sessions, r.holding_max_sessions),
            "confidence": _conf_label(r.confidence), "confidence_score": round(r.confidence),
            "why": good or ["Passed the system's trend, risk and data-quality checks"],
            "what_could_go_wrong": risks[:4],
            "similar_past_ideas": _similar_ideas(db, r.confidence),
            "simple_plan": (f"If you buy between ₹{r.entry_low:,.2f} and ₹{r.entry_high:,.2f}, sell if the price closes below "
                            f"₹{r.stop:,.2f} (a loss of about {abs(100 * (r.stop / mid - 1)):.1f}%). Consider booking "
                            f"profit near ₹{r.target1:,.2f} (+{100 * (r.target1 / mid - 1):.1f}%)."),
            "recommendation_id": r.id,
        })
    order = {"buy": 0, "wait": 1, "avoid": 2}
    items.sort(key=lambda x: order[x["tone"]])
    return {"status": "ok", "for_session": j(run.session_date), "data_as_of": j(run.data_as_of), "items": items,
            "how_much": "Risk only a small part of your money on any one idea — many investors limit the possible "
                        "loss on a single trade to 1% of their total investment money."}


def _plain_valuation(pe: float | None) -> str | None:
    if pe is None:
        return None
    if pe < 15:
        return f"Priced low compared to its profits (P/E {pe:.0f})"
    if pe < 30:
        return f"Fairly priced compared to its profits (P/E {pe:.0f})"
    if pe < 50:
        return f"Expensive compared to its profits (P/E {pe:.0f})"
    return f"Very expensive compared to its profits (P/E {pe:.0f})"


def _yearly_range(close) -> dict | None:
    """Distribution of 1-year (≈250-session) price changes in the stock's own available history."""
    c = close.dropna()
    if len(c) < 300:
        return None
    r = (c.iloc[250:].to_numpy() / c.iloc[:-250].to_numpy() - 1) * 100
    biggest_fall = float(((c / c.cummax()) - 1).min() * 100)
    return {"worst_pct": round(float(np.percentile(r, 5)), 1), "typical_pct": round(float(np.median(r)), 1),
            "biggest_fall_pct": round(biggest_fall, 1),
            "best_pct": round(float(np.percentile(r, 95)), 1), "years_of_data": round(len(c) / 250, 1),
            "note": ("How much the price changed over 1-year periods in the data we have. This is history, not a forecast"
                     + (" — and only a short history, so a bad stretch may not be included yet." if len(c) < 1250 else "."))}


def _long_term(db: Session, as_of: date, regime_label: str | None) -> dict:
    universe = [s for s in db.scalars(select(Stock).where(Stock.is_active.is_(True)))
                if "nifty100" in (s.index_memberships or [])]
    frames = bars_bulk(db, [s.id for s in universe], as_of, lookback_days=1100)
    rows = []
    for s in universe:
        df = frames.get(s.id)
        if df is None or len(df) < 120:
            continue
        price = float(df["close"].iloc[-1])
        fv = fundamental_view(db, s.id, s.symbol, as_of, price)
        if fv.get("score") is None or (fv.get("completeness") or 0) < 0.5:
            continue
        rows.append((fv["score"], s, df, fv, price))
    rows.sort(key=lambda x: -x[0])
    per_sector: Counter = Counter()
    items = []
    for score, s, df, fv, price in rows:
        if score < 55 or per_sector[s.industry] >= 2:
            continue
        per_sector[s.industry] += 1
        m = {k: (v or {}).get("value") for k, v in fv["metrics"].items()}
        e200 = float(ema(df["close"], 200).iloc[-1]) if len(df) >= 200 else None
        good, care = [], []
        if m.get("earnings_growth_yoy") is not None:
            g = m["earnings_growth_yoy"]
            (good if g > 0 else care).append(f"Profits {'grew' if g > 0 else 'fell'} {abs(g):.0f}% compared to last year")
        if m.get("revenue_growth_yoy") is not None and m["revenue_growth_yoy"] > 8:
            good.append(f"Sales grew {m['revenue_growth_yoy']:.0f}% compared to last year")
        if m.get("debt_equity") is not None:
            de = m["debt_equity"]
            (good if de < 0.5 else care).append("Low debt" if de < 0.5 else f"Carries noticeable debt (debt/equity {de:.1f})")
        if m.get("promoter_holding") and m["promoter_holding"] >= 50:
            good.append(f"Founders/promoters own {m['promoter_holding']:.0f}% of the company")
        if m.get("promoter_pledge") and m["promoter_pledge"] > 5:
            care.append(f"Promoters have pledged {m['promoter_pledge']:.0f}% of their shares")
        val = _plain_valuation(m.get("pe"))
        if val:
            (care if "xpensive" in val else good).append(val)
        if e200:
            if price >= e200:
                good.append("The long-term price trend is upward")
            else:
                care.append("The price is in a long-term downtrend right now — cheaper, but it may keep falling for a while")
        if regime_label in ("BEARISH", "STRONG BEARISH"):
            care.append("The overall market is weak; prices may fall further before recovering")
        rng = _yearly_range(df["close"])
        r = fv.get("result_analysis") or {}
        items.append({
            "symbol": s.symbol, "company": s.name, "industry": s.industry,
            "business_quality": "Strong" if score >= 70 else "Good", "business_score": round(score),
            "price_now": price, "price_as_of": df.index[-1].strftime("%Y-%m-%d"),
            "latest_results": r.get("classification"), "latest_results_quarter": r.get("fiscal_quarter"),
            "why": good[:5], "things_to_watch": care[:4], "past_yearly_range": rng,
            "how_to_buy": ("Consider buying in small parts over 3–6 months instead of all at once."
                           + (" With the market weak, going slowly matters more." if regime_label in ("BEARISH", "STRONG BEARISH") else "")),
            "data_note": "Business numbers come from the company's official quarterly filings with NSE.",
        })
        if len(items) >= 8:
            break
    return {"status": "ok" if items else "data_unavailable",
            "message": None if items else "Not enough company financial data yet (run the fundamentals job).",
            "items": items,
            "how_it_works": ("Picked from the 100 largest companies by business strength: profit and sales growth, "
                             "debt, valuation and promoter holding. There is no target price for long-term ideas — "
                             "results depend on how the business performs over years.")}


def _intraday(db: Session) -> dict:
    if registry.realtime_quotes() is None:
        return {"status": "needs_live_data",
                "message": ("Intraday (same-day) ideas need live prices during market hours. This app currently uses "
                            "official end-of-day prices only, so it will not suggest intraday trades rather than guess."),
                "how_to_enable": "An admin can connect a broker data feed (Upstox or Zerodha Kite) in the .env file.",
                "warning": ("Intraday trading is very risky. A SEBI study (July 2024) found that about 7 out of 10 "
                            "individual intraday traders made losses in FY 2022-23.")}
    return {"status": "not_available",
            "message": "Live prices are connected, but intraday idea generation is not built yet.",
            "warning": ("Intraday trading is very risky. A SEBI study (July 2024) found that about 7 out of 10 "
                        "individual intraday traders made losses in FY 2022-23.")}


def simple_view(db: Session, refresh: bool = False) -> dict:
    run = db.scalar(select(ScanRun).order_by(ScanRun.generated_at.desc()).limit(1))
    regime = latest_regime(db)
    from app.services.live_market import live_market

    live = live_market(db)
    key = (f"simple_cache:{CACHE_VERSION}:{run.id if run else 0}:{regime.id if regime else 0}:"
           f"{live['as_of'] if live else 'eod'}")
    cached = db.get(AppSetting, key)
    if cached and not refresh:
        return cached.value
    label = regime.regime if regime else None
    mood = None
    if regime:
        word, sentence = MOOD[regime.regime]
        mood = {"label": word, "explanation": sentence, "advice": MOOD_ADVICE[regime.regime],
                "suggested_max_invested_pct": regime.recommended_exposure_pct,
                "as_of": j(regime.data_as_of), "regime": regime.regime}
    as_of = regime.session_date if regime else (run.session_date if run else date.today())
    out = j({
        "generated_at": utcnow(), "market_mood": mood, "today_intraday": _intraday(db),
        "this_week": _short_term(db, label), "long_term": _long_term(db, as_of, label), "glossary": GLOSSARY,
        "disclaimer": ("These are ideas from an automated research tool, not advice. No profit is guaranteed — you can "
                       "lose money. Decide only after your own research; consider a SEBI-registered adviser."),
    })
    if cached is None:
        db.add(AppSetting(key=key, value=out, updated_at=utcnow()))
    else:
        cached.value, cached.updated_at = out, utcnow()
    db.commit()
    return out


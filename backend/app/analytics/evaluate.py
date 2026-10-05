"""Evaluate one stock as of one session — the single code path shared by the live scanner and the
backtester, so backtests measure exactly what the live system would have produced.

Point-in-time contract: `bars` must contain only sessions <= as_of (the caller truncates), and every
external input (fundamentals, news, F&O, sector) must have been computed from data public at as_of.
`assert_point_in_time` enforces the bar part.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.analytics.levels import Levels, SetupContext, compute_levels
from app.analytics.scoring import ScoreResult, build_score, confidence_from
from app.technical.indicators import compute_all, latest_values
from app.technical.patterns import analyze_price_action


class LookAheadError(AssertionError):
    pass


def assert_point_in_time(bars: pd.DataFrame, as_of: date) -> None:
    if len(bars) and pd.Timestamp(bars.index.max()).date() > as_of:
        raise LookAheadError(f"bars extend past as_of={as_of}: last bar {bars.index.max()}")


@dataclass(slots=True)
class ExternalInputs:
    rs_rating: float | None = None
    rs_excess: dict | None = None
    fundamentals: tuple = (None, [], [], "Fundamental data not available")
    sector: tuple = (None, None)
    news: tuple = (50.0, [], [], None)
    fno: tuple = (None, [], [], "Not an F&O stock")
    is_fno: bool = False
    regime: str = "NEUTRAL"
    regime_confidence: float | None = None
    upcoming_results_in_sessions: int | None = None
    data_fresh: bool = True


@dataclass(slots=True)
class Evaluation:
    symbol: str
    as_of: date
    cmp: float
    indicators: dict
    price_action: dict
    levels: Levels | None
    score: ScoreResult | None
    confidence: float
    confidence_notes: list[str]
    action: str  # BUY | WAIT | AVOID
    rejected: bool
    rejection_reasons: list[str] = field(default_factory=list)
    why: list[str] = field(default_factory=list)
    why_not: list[str] = field(default_factory=list)
    invalidation: str = ""


def _rising(s: pd.Series, n: int = 10) -> bool | None:
    s = s.dropna()
    if len(s) < n + 1:
        return None
    return bool(s.iloc[-1] > s.rolling(n).mean().iloc[-1])


def evaluate(symbol: str, bars: pd.DataFrame, as_of: date, ext: ExternalInputs, weights: dict,
             risk_cfg: dict, excl_cfg: dict) -> Evaluation:
    assert_point_in_time(bars, as_of)
    ind_df = compute_all(bars)
    ind = latest_values(ind_df)
    pa = analyze_price_action(bars)
    cmp = float(bars["close"].iloc[-1])
    reasons: list[str] = []

    atr_v = ind.get("atr_14")
    if atr_v is None or ind.get("ema_200") is None:
        return Evaluation(symbol, as_of, cmp, ind, pa, None, None, 0.0, [], "AVOID", True,
                          ["Insufficient history for indicators (need ~200 sessions)"])

    ctx = SetupContext(
        cmp=cmp, atr=float(atr_v), ema20=ind.get("ema_20"), ema50=ind.get("ema_50"),
        supports=pa["supports"], resistances=pa["resistances"], last_swing_low=pa.get("last_swing_low"),
        high_52w=ind.get("high_52w"), hv_20=ind.get("hv_20"), patterns=pa["patterns"], regime=ext.regime,
    )
    lv = compute_levels(ctx, risk_cfg)
    reasons += lv.rejections

    score = build_score(
        weights, ind, pa,
        obv_rising=_rising(ind_df["obv"]), ad_rising=_rising(ind_df["ad_line"]),
        rs_rating=ext.rs_rating, rs_excess=ext.rs_excess, fundamentals=ext.fundamentals, sector=ext.sector,
        news=ext.news, fno=ext.fno, rr_t2=lv.rr_t2, risk_pct=lv.risk_pct,
    )
    optional = {"fno"} if not ext.is_fno else set()
    conf, conf_notes = confidence_from(score, ext.regime, ext.regime_confidence, ext.data_fresh, optional)

    # Hard filters → reject (not ranked).
    rsi_v = ind.get("rsi_14")
    if ind.get("ema_200") and cmp < ind["ema_200"] and ext.regime in ("BEARISH", "STRONG BEARISH"):
        reasons.append("Below 200-EMA in a bearish market regime")
    if rsi_v is not None and rsi_v > 82:
        reasons.append(f"Overextended (RSI {rsi_v:.0f} > 82)")
    pats = pa["patterns"]
    if pats.get("breakdown", {}).get("detected"):
        reasons.append("Fresh breakdown below 20-day low")
    rejected = bool(reasons)

    why, why_not = [], []
    for c in sorted(score.components, key=lambda c: -(c.points or 0)):
        why += c.reasons
        why_not += c.cautions
    if ext.upcoming_results_in_sessions is not None:
        why_not.insert(0, f"Results due in ~{ext.upcoming_results_in_sessions} session(s): event risk / gap risk")
    if lv.rr_t2 < 2.0:
        why_not.append(f"Reward:risk to T2 only 1:{lv.rr_t2:.1f}")
    if ext.regime in ("BEARISH", "STRONG BEARISH"):
        why_not.append(f"Market regime {ext.regime}: broad selling can override stock-specific setups")
    if not why_not:
        why_not.append("General market risk: gaps, news and liquidity can invalidate any technical setup")

    action = "BUY"
    blackout = int(excl_cfg.get("results_blackout_sessions", 2))
    if rejected:
        action = "AVOID"
    elif cmp > lv.no_chase_above:
        action = "WAIT"
        why_not.insert(0, f"Price ₹{cmp:.2f} is above the do-not-chase level ₹{lv.no_chase_above:.2f} — wait for a pullback")
    elif ext.upcoming_results_in_sessions is not None and ext.upcoming_results_in_sessions <= blackout:
        action = "WAIT"
    elif ext.regime == "STRONG BEARISH":
        action = "WAIT"

    invalidation = (f"Setup becomes invalid on a daily close below ₹{lv.stop:.2f}"
                    + (f", or a close back below the breakout level ₹{pats['breakout']['level']:.2f} within 3 sessions"
                       if pats.get("breakout", {}).get("detected") else "")
                    + (f", or if price opens above ₹{lv.no_chase_above:.2f} (do not chase)") + ".")
    return Evaluation(symbol, as_of, cmp, ind, pa, lv, score, conf, conf_notes, action, rejected, reasons,
                      why[:8], why_not[:8], invalidation)


def frame_from_rows(rows) -> pd.DataFrame:
    """Build the canonical OHLCV frame from ORM rows / dicts sorted by date."""
    recs = [
        {"date": pd.Timestamp(r.date), "open": r.open, "high": r.high, "low": r.low, "close": r.close,
         "volume": float(r.volume or 0), "turnover": r.turnover, "delivery_pct": r.delivery_pct}
        for r in rows
    ]
    if not recs:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame.from_records(recs).set_index("date").sort_index()
    for c in ("open", "high", "low", "close", "volume", "turnover", "delivery_pct"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["delivery_pct"] = df["delivery_pct"].replace({np.nan: np.nan})
    return df

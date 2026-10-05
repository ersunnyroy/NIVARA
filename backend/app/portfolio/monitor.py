"""Bought-stock monitoring: deterministic action rules for an open long position.

Actions: HOLD, ADD ONLY ON DIP, PARTIAL PROFIT, TRAIL STOP, EXIT, WAIT. Rules are evaluated in priority
order (risk first) and every triggered rule contributes a reason that cites the numbers. The AI layer may
explain these, but never overrides them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MONITOR_VERSION = "monitor-1.0"


@dataclass(slots=True)
class PositionState:
    symbol: str
    quantity: float
    avg_cost: float
    cmp: float
    stop: float | None
    target1: float | None
    target2: float | None
    trailing_stop: float | None = None
    levels_source: str = "user"  # user | recommendation | system_suggested | none
    ema20: float | None = None
    ema50: float | None = None
    atr: float | None = None
    rsi: float | None = None
    supertrend_dir: float | None = None
    macd_below_signal: bool | None = None
    regime: str | None = None
    worst_recent_news: float | None = None  # min sentiment of high/medium-impact items in last 5 days
    negative_news_headline: str | None = None
    current_score: float | None = None
    best_alternative_score: float | None = None
    upcoming_results_sessions: int | None = None
    data_as_of: str | None = None


@dataclass(slots=True)
class MonitorResult:
    action: str
    severity: str  # info | warning | critical
    reasons: list[str]
    sell_signals: list[dict] = field(default_factory=list)  # [{code, reason}]
    suggested_trailing_stop: float | None = None
    partial_exit_pct: int | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    distance_to_stop_pct: float | None = None
    distance_to_target_pct: float | None = None
    version: str = MONITOR_VERSION


def _pct(a: float, b: float) -> float:
    return 100.0 * (a / b - 1.0)


def evaluate_position(p: PositionState) -> MonitorResult:
    pnl = (p.cmp - p.avg_cost) * p.quantity
    pnl_pct = _pct(p.cmp, p.avg_cost)
    eff_stop = max(x for x in (p.stop, p.trailing_stop) if x is not None) if (p.stop or p.trailing_stop) else None
    d_stop = None if eff_stop is None else 100.0 * (p.cmp - eff_stop) / p.cmp
    tgt = p.target1 if p.target1 and p.cmp < p.target1 else p.target2
    d_tgt = None if not tgt else 100.0 * (tgt - p.cmp) / p.cmp
    signals: list[dict] = []
    reasons: list[str] = []

    def sig(code: str, reason: str) -> None:
        signals.append({"code": code, "reason": reason})
        reasons.append(reason)

    # --- exit conditions (risk first) ---
    if eff_stop is not None and p.cmp <= eff_stop:
        sig("stop_hit", f"Price ₹{p.cmp:.2f} is at/below the stop ₹{eff_stop:.2f} — setup invalidated")
    tech_bad = sum([
        bool(p.ema50 and p.cmp < p.ema50),
        bool(p.supertrend_dir is not None and p.supertrend_dir < 0),
        bool(p.macd_below_signal),
    ])
    if tech_bad >= 3:
        sig("technical_deterioration",
            f"Technical deterioration: below 50-EMA (₹{p.ema50:.2f}), Supertrend bearish, MACD below signal")
    if p.worst_recent_news is not None and p.worst_recent_news <= -0.4:
        sig("negative_event", f"Negative event: {p.negative_news_headline or 'high-impact negative news'}")
    if p.regime in ("BEARISH", "STRONG BEARISH") and pnl_pct < 0:
        sig("regime_changed", f"Market regime is {p.regime} and the position is under water ({pnl_pct:+.1f}%)")
    if d_stop is not None and d_tgt is not None and d_stop > 0 and d_tgt / d_stop < 0.5:
        sig("rr_deteriorated", f"Remaining reward ({d_tgt:.1f}%) is less than half the risk to stop ({d_stop:.1f}%)")
    if (p.current_score is not None and p.best_alternative_score is not None
            and p.current_score < 45 and p.best_alternative_score - p.current_score >= 30):
        sig("better_opportunity", f"Holding scores {p.current_score:.0f}/100 vs {p.best_alternative_score:.0f} "
                                  "for today's best idea — capital may be better deployed")

    t1_hit = p.target1 is not None and p.cmp >= p.target1
    t2_hit = p.target2 is not None and p.cmp >= p.target2
    if t2_hit:
        sig("target2_reached", f"Target 2 ₹{p.target2:.2f} reached")
    elif t1_hit:
        sig("target1_reached", f"Target 1 ₹{p.target1:.2f} reached")

    # Suggested trailing stop once in profit: max(existing, breakeven, close − 2×ATR, 20-EMA − 0.5×ATR).
    trail = None
    if pnl_pct > 0 and p.atr:
        cands = [p.avg_cost if t1_hit else None, p.cmp - 2.0 * p.atr,
                 (p.ema20 - 0.5 * p.atr) if p.ema20 else None, p.trailing_stop, p.stop]
        trail = round(max(c for c in cands if c is not None), 2)
        if eff_stop is not None and trail <= eff_stop:
            trail = None

    codes = {s["code"] for s in signals}
    partial = None
    if "stop_hit" in codes or ("negative_event" in codes and pnl_pct < 0) or len(codes & {
            "technical_deterioration", "regime_changed", "rr_deteriorated"}) >= 2:
        action, severity = "EXIT", "critical"
    elif "target2_reached" in codes:
        action, severity, partial = "PARTIAL PROFIT", "warning", 50
        reasons.append("Book a further portion at Target 2 and trail the rest")
    elif "target1_reached" in codes:
        action, severity, partial = "PARTIAL PROFIT", "warning", 30
        reasons.append("Book ~30% at Target 1; trail the remainder")
    elif codes & {"technical_deterioration", "regime_changed", "rr_deteriorated", "better_opportunity", "negative_event"}:
        action, severity = ("TRAIL STOP" if pnl_pct > 0 else "WAIT"), "warning"
    elif trail is not None and pnl_pct >= 3:
        action, severity = "TRAIL STOP", "info"
        reasons.append(f"In profit {pnl_pct:+.1f}%: raise stop to ₹{trail:.2f}")
    elif (pnl_pct < 0 and eff_stop is not None and d_stop is not None and d_stop > 2 and p.ema50 and p.cmp > p.ema50
          and p.regime not in ("BEARISH", "STRONG BEARISH")):
        action, severity = "ADD ONLY ON DIP", "info"
        reasons.append(f"Trend intact above 50-EMA; consider adding only near support/stop zone, never below ₹{eff_stop:.2f}")
    else:
        action, severity = "HOLD", "info"
        reasons.append("No exit condition triggered; setup intact")

    if p.upcoming_results_sessions is not None and p.upcoming_results_sessions <= 3:
        reasons.append(f"Results in ~{p.upcoming_results_sessions} session(s): consider event risk")
    if p.levels_source == "none":
        reasons.append("No stop/target set — add them to enable full monitoring")
        if action == "HOLD":
            action = "WAIT"
    elif p.levels_source == "system_suggested":
        reasons.append("Stop/targets are system-suggested from current data (not your own levels)")

    return MonitorResult(action, severity, reasons, signals, trail, partial, round(pnl, 2), round(pnl_pct, 2),
                         None if d_stop is None else round(d_stop, 2), None if d_tgt is None else round(d_tgt, 2))

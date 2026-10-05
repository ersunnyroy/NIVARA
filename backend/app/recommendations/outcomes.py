"""Recommendation outcome simulation on daily bars (also used by the backtester).

Rules (documented and conservative):
* Entry window: the first `entry_window` sessions starting at the recommendation's target session.
  Fill when the bar trades inside the preferred zone: at the open if it opens inside the zone, at
  `entry_high` if it opens above and trades down into the zone, at the open if it gaps below the zone
  but above the stop. A gap open at/below the stop → `invalidated` (never entered).
* After entry, each bar checks the stop BEFORE targets (if a bar touches both, we assume the stop hit
  first). Gap through the stop exits at the open.
* After Target 1 the stop moves up to `trailing_stop_after_t1` (if higher). Position exits fully at
  Target 2 (base case). Target 3 hits are recorded for statistics if reached on the exit bar or earlier.
* If no exit within `holding_max` sessions after entry, exit at that session's close (`expired`).
* MFE/MAE are measured from the fill price using bar highs/lows while the trade is open.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass(slots=True)
class TradePlan:
    entry_low: float
    entry_high: float
    stop: float
    target1: float
    target2: float | None
    target3: float | None
    trailing_after_t1: float | None
    holding_max: int
    entry_window: int = 3


@dataclass(slots=True)
class Outcome:
    status: str = "pending"  # pending | not_triggered | invalidated | open | target1 | target2 | stopped | expired
    entry_date: date | None = None
    entry_price: float | None = None
    exit_date: date | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    t1_hit_date: date | None = None
    t2_hit_date: date | None = None
    t3_hit_date: date | None = None
    stop_hit_date: date | None = None
    mfe_pct: float | None = None
    mae_pct: float | None = None
    return_pct: float | None = None
    sessions_held: int | None = None
    last_evaluated_date: date | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def closed(self) -> bool:
        return self.status in ("not_triggered", "invalidated", "target1", "target2", "stopped", "expired")


def simulate(plan: TradePlan, bars: pd.DataFrame) -> Outcome:
    """`bars`: daily OHLC from the recommendation's target session onwards (index = dates, ascending)."""
    o = Outcome()
    if bars.empty:
        return o
    stop = plan.stop
    hi_since = lo_since = None
    held = 0
    for ts, b in bars.iterrows():
        d = ts.date() if hasattr(ts, "date") else ts
        o.last_evaluated_date = d
        op, hi, lo, cl = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
        if o.entry_price is None:
            idx = bars.index.get_loc(ts)
            if idx >= plan.entry_window:
                o.status = "not_triggered"
                o.notes.append(f"Price did not trade in the entry zone within {plan.entry_window} sessions")
                return o
            if op <= plan.stop:
                o.status = "invalidated"
                o.notes.append(f"Opened at ₹{op:.2f}, at/below the stop, before entry")
                return o
            if plan.entry_low <= op <= plan.entry_high:
                fill = op
            elif op > plan.entry_high and lo <= plan.entry_high:
                fill = plan.entry_high
            elif op < plan.entry_low:
                fill = op
            else:
                continue
            o.entry_date, o.entry_price, o.status = d, fill, "open"
            hi_since, lo_since = hi, lo
            # Same-bar exit checks after entry (stop first).
        else:
            held += 1
            hi_since, lo_since = max(hi_since, hi), min(lo_since, lo)
        o.mfe_pct = round(100 * (hi_since / o.entry_price - 1), 3)
        o.mae_pct = round(100 * (lo_since / o.entry_price - 1), 3)
        if lo <= stop:
            px = min(op, stop) if held > 0 else stop
            if o.t1_hit_date is None:
                o.stop_hit_date = d
            return _close(o, d, px, "target1" if o.t1_hit_date else "stopped",
                          "trailing stop after T1" if o.t1_hit_date else "stop loss", held)
        if o.t1_hit_date is None and hi >= plan.target1:
            o.t1_hit_date = d
            if plan.trailing_after_t1 and plan.trailing_after_t1 > stop:
                stop = plan.trailing_after_t1
        if plan.target2 and hi >= plan.target2:
            o.t2_hit_date = d
            if plan.target3 and hi >= plan.target3:
                o.t3_hit_date = d
            px = max(op, plan.target2) if held > 0 else plan.target2
            return _close(o, d, px, "target2", "target 2", held)
        if held >= plan.holding_max:
            return _close(o, d, cl, "target1" if o.t1_hit_date else "expired", "time exit (max holding)", held)
    return o


def _close(o: Outcome, d: date, px: float, status: str, reason: str, held: int) -> Outcome:
    o.exit_date, o.exit_price, o.status, o.exit_reason = d, round(px, 2), status, reason
    o.return_pct = round(100 * (px / o.entry_price - 1), 3)
    o.sessions_held = held
    return o


def win(o: Outcome) -> bool | None:
    if o.return_pct is None:
        return None
    return o.return_pct > 0

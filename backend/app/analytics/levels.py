"""Entry, stop-loss, target and position-sizing engines (long side).

Every level carries a `method` string explaining exactly how it was derived. Levels are rounded to
the ₹0.05 tick (stops rounded down, entries/targets rounded to nearest).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from app.analytics.config import DEFAULTS, LEVELS_VERSION

TICK = 0.05


def rtick(x: float, mode: str = "nearest") -> float:
    q = x / TICK
    q = math.floor(q + 1e-9) if mode == "down" else math.ceil(q - 1e-9) if mode == "up" else round(q)
    return round(q * TICK, 2)


@dataclass(slots=True)
class SetupContext:
    cmp: float
    atr: float
    ema20: float | None
    ema50: float | None
    supports: list[dict]  # nearest first, each {price, touches, strength}
    resistances: list[dict]  # nearest first
    last_swing_low: float | None
    high_52w: float | None
    hv_20: float | None  # annualised decimal
    patterns: dict  # name -> Detection dict
    regime: str = "NEUTRAL"


@dataclass(slots=True)
class Levels:
    setup: str
    strategy: str
    aggressive_entry: float
    entry_low: float
    entry_high: float
    conservative_low: float
    conservative_high: float
    no_chase_above: float
    stop: float
    trailing_stop_after_t1: float
    target1: float
    target2: float
    target3: float
    risk_pct: float
    reward_pcts: list[float]
    rr_t1: float
    rr_t2: float
    holding_min: int
    holding_max: int
    methodology: dict = field(default_factory=dict)
    valid: bool = True
    rejections: list[str] = field(default_factory=list)

    def asdict(self) -> dict:
        return asdict(self)


def classify_setup(ctx: SetupContext) -> tuple[str, str]:
    p = ctx.patterns
    det = lambda n: bool(p.get(n, {}).get("detected"))
    if det("retest") and det("breakout") is False:
        return "Bullish breakout + retest", "breakout"
    if det("breakout"):
        vol = p["breakout"].get("details", {}).get("volume_confirmed")
        return ("Fresh breakout (volume confirmed)" if vol else "Breakout (volume unconfirmed)"), "breakout"
    if det("flag"):
        return "Bull flag continuation", "pattern"
    if det("triangle") and p["triangle"].get("details", {}).get("type") == "ascending":
        return "Ascending triangle", "pattern"
    if det("double_bottom") and p["double_bottom"].get("details", {}).get("confirmed"):
        return "Double bottom (neckline cleared)", "pattern"
    if ctx.ema20 and ctx.ema50 and ctx.cmp > ctx.ema50 and abs(ctx.cmp - ctx.ema20) <= 0.75 * ctx.atr:
        return "Pullback to 20-EMA in uptrend", "pullback"
    if det("consolidation"):
        return "Tight consolidation near highs" if ctx.high_52w and ctx.cmp >= 0.9 * ctx.high_52w else \
            "Consolidation (base building)", "momentum"
    return "Trend continuation", "momentum"


def compute_levels(ctx: SetupContext, risk_cfg: dict | None = None) -> Levels:
    risk_cfg = risk_cfg or DEFAULTS["risk_limits"]
    a = max(ctx.atr, ctx.cmp * 0.003)
    cmp = ctx.cmp
    setup, strategy = classify_setup(ctx)
    meth: dict[str, str] = {"version": LEVELS_VERSION, "atr": f"ATR(14) = ₹{a:.2f}"}
    p = ctx.patterns

    # ---------- ENTRY ----------
    ref_level: float | None = None
    if strategy == "breakout":
        ref_level = (p.get("retest", {}).get("level") if p.get("retest", {}).get("detected")
                     else p.get("breakout", {}).get("level"))
    elif strategy == "pattern":
        for n in ("flag", "triangle", "double_bottom"):
            if p.get(n, {}).get("detected") and p[n].get("level"):
                ref_level = p[n]["level"]
                break
    if ref_level and ref_level < cmp + a:
        entry_low = min(cmp, ref_level)
        entry_high = min(cmp, ref_level + 0.5 * a) if cmp > ref_level else ref_level + 0.25 * a
        entry_high = max(entry_high, entry_low + 0.1 * a)
        cons_high, cons_low = ref_level, ref_level - 0.4 * a
        meth["entry"] = (f"Preferred zone anchored on the {setup.lower()} level ₹{ref_level:.2f} up to +0.5×ATR; "
                         f"conservative zone is a retest of that level")
    else:
        support = ctx.ema20 if (ctx.ema20 and ctx.ema20 < cmp) else None
        sup_lvls = [s["price"] for s in ctx.supports if s["price"] < cmp]
        if sup_lvls and (support is None or sup_lvls[0] > support):
            support = sup_lvls[0]
        if support and cmp - support <= 1.5 * a:
            entry_low, entry_high = support, min(cmp, support + 0.6 * a)
            meth["entry"] = f"Preferred zone from nearest support/20-EMA ₹{support:.2f} up to +0.6×ATR"
        else:
            entry_low, entry_high = cmp - 0.5 * a, cmp
            meth["entry"] = "No support within 1.5×ATR: preferred zone is CMP down to −0.5×ATR"
        cons_high = entry_low - 0.2 * a
        cons_low = cons_high - 0.5 * a
        if ctx.ema50 and ctx.ema50 < cons_high and cons_high - ctx.ema50 < 1.5 * a:
            cons_low = min(cons_low, ctx.ema50)
    entry_mid = (entry_low + entry_high) / 2.0

    # ---------- STOP ----------
    k = float(risk_cfg.get("atr_stop_multiple", 2.0)) * (1.15 if ctx.regime in ("BEARISH", "STRONG BEARISH") else 1.0)
    atr_stop = entry_mid - k * a
    structural: list[tuple[float, str]] = []
    if ctx.last_swing_low and ctx.last_swing_low < entry_low:
        structural.append((ctx.last_swing_low - 0.25 * a, f"below recent swing low ₹{ctx.last_swing_low:.2f} − 0.25×ATR"))
    sup_below = [s for s in ctx.supports if s["price"] < entry_low]
    if sup_below:
        structural.append((sup_below[0]["price"] - 0.25 * a, f"below support ₹{sup_below[0]['price']:.2f} − 0.25×ATR"))
    if ref_level and ref_level <= entry_low + 1e-9:
        structural.append((ref_level - 1.0 * a, f"1×ATR below breakout level ₹{ref_level:.2f}"))
    chosen = None
    for price, why in sorted(structural, key=lambda t: -t[0]):  # tightest valid structural stop first
        dist = entry_mid - price
        if 1.0 * a <= dist <= 3.5 * a:
            chosen = (price, why)
            break
    if chosen:
        stop, meth["stop"] = chosen[0], f"Structural stop {chosen[1]} (distance within 1–3.5×ATR)"
    else:
        stop, meth["stop"] = atr_stop, f"Volatility stop: entry mid − {k:.2f}×ATR (no structural level within 1–3.5×ATR)"
    stop = rtick(stop, "down")
    risk = entry_mid - stop
    risk_pct = 100.0 * risk / entry_mid

    # ---------- TARGETS ----------
    res = sorted({round(r["price"], 2) for r in ctx.resistances if r["price"] > entry_high})
    if ctx.high_52w and ctx.high_52w > entry_high:
        res = sorted(set(res) | {round(ctx.high_52w, 2)})
    t1 = next((r for r in res if entry_mid + 1.0 * risk <= r <= entry_mid + 2.0 * risk), None)
    meth["target1"] = (f"First resistance ₹{t1:.2f} between 1R and 2R" if t1 else "1.5R projection (no resistance in 1–2R)")
    t1 = t1 or entry_mid + 1.5 * risk
    t2 = next((r for r in res if r >= t1 + 0.5 * risk and r <= entry_mid + 3.5 * risk), None)
    meth["target2"] = (f"Next resistance ₹{t2:.2f} (≥ T1 + 0.5R, ≤ 3.5R)" if t2 else "2.5R projection (no resistance in range)")
    t2 = t2 or max(entry_mid + 2.5 * risk, t1 + 0.75 * risk)
    measured = None
    if p.get("flag", {}).get("detected"):
        pole = p["flag"]["details"].get("pole_gain_pct")
        if pole:
            measured = entry_mid * (1 + pole / 100.0)
    elif p.get("consolidation", {}).get("detected"):
        box = p["consolidation"]["details"]
        if box.get("box_high") and box.get("box_low"):
            measured = box["box_high"] + (box["box_high"] - box["box_low"])
    t3_candidates = [entry_mid + 3.5 * risk]
    if measured and measured > t2:
        t3_candidates.append(measured)
    beyond = [r for r in res if r > t2 + 0.5 * risk]
    if beyond:
        t3_candidates.append(beyond[0])
    t3 = max(min(t3_candidates), t2 + 0.5 * risk)
    meth["target3"] = "Aggressive: min(3.5R, pattern measured move, next resistance beyond T2), at least T2 + 0.5R"
    t1, t2, t3 = rtick(t1), rtick(t2), rtick(t3)

    # Expected-move sanity check (1σ over the max holding horizon).
    hold_min = max(2, math.ceil((t1 - entry_mid) / (0.6 * a)))
    hold_max = min(40, max(hold_min + 3, math.ceil((t2 - entry_mid) / (0.35 * a))))
    if ctx.hv_20:
        sigma = entry_mid * ctx.hv_20 * math.sqrt(hold_max / 252.0)
        meth["expected_move"] = (f"1σ move over {hold_max} sessions ≈ ₹{sigma:.2f} (HV20 {100 * ctx.hv_20:.1f}%); "
                                 f"T2 is {(t2 - entry_mid) / sigma:.2f}σ away" if sigma > 0 else "n/a")
    meth["holding"] = "Sessions to T1 at 0.6×ATR/day progress (min) and to T2 at 0.35×ATR/day (max), heuristic"

    rr_t1 = (t1 - entry_mid) / risk if risk > 0 else 0.0
    rr_t2 = (t2 - entry_mid) / risk if risk > 0 else 0.0
    min_rr = float(risk_cfg.get("min_rr_t2", 1.8))
    # Do-not-chase: price above which reward:risk to T2 falls below the minimum.
    no_chase = (t2 + min_rr * stop) / (1.0 + min_rr)
    no_chase = min(no_chase, entry_high + 1.0 * a)
    meth["no_chase"] = (f"Above ₹{no_chase:.2f} the reward:risk to Target 2 falls below 1:{min_rr} "
                        f"(capped at preferred-zone high + 1×ATR)")
    trail = max(entry_mid, t1 - 2.0 * a)
    meth["trailing"] = "After Target 1: max(entry mid / breakeven, T1 − 2×ATR); then trail below rising 20-EMA"

    rejections = []
    if risk <= 0:
        rejections.append("Invalid stop (not below entry)")
    if risk_pct > float(risk_cfg.get("max_risk_pct_per_setup", 8.0)):
        rejections.append(f"Risk {risk_pct:.1f}% exceeds max {risk_cfg.get('max_risk_pct_per_setup')}%")
    if rr_t2 < min_rr:
        rejections.append(f"Reward:risk to T2 {rr_t2:.2f} below minimum {min_rr}")

    return Levels(
        setup=setup, strategy=strategy,
        aggressive_entry=rtick(cmp), entry_low=rtick(entry_low), entry_high=rtick(entry_high),
        conservative_low=rtick(min(cons_low, cons_high)), conservative_high=rtick(max(cons_low, cons_high)),
        no_chase_above=rtick(no_chase, "down"), stop=stop, trailing_stop_after_t1=rtick(trail, "down"),
        target1=t1, target2=t2, target3=t3,
        risk_pct=round(risk_pct, 2),
        reward_pcts=[round(100.0 * (t / entry_mid - 1.0), 2) for t in (t1, t2, t3)],
        rr_t1=round(rr_t1, 2), rr_t2=round(rr_t2, 2), holding_min=hold_min, holding_max=hold_max,
        methodology=meth, valid=not rejections, rejections=rejections,
    )


@dataclass(slots=True)
class PositionSize:
    capital: float
    risk_pct: float
    entry: float
    stop: float
    risk_per_share: float
    max_loss: float
    quantity: int
    capital_required: float
    capped_by: str | None
    potential_profits: list[float]
    notes: list[str]


def position_size(capital: float, risk_pct: float, entry: float, stop: float, targets: list[float] | None = None,
                  max_position_pct: float | None = None) -> PositionSize:
    """Quantity = floor(capital × risk% ÷ (entry − stop)), optionally capped by a max position size."""
    if entry <= 0 or stop <= 0 or stop >= entry:
        raise ValueError("Stop must be positive and below entry for a long position")
    if capital <= 0 or not (0 < risk_pct <= 100):
        raise ValueError("Capital must be positive and risk % in (0, 100]")
    rps = entry - stop
    budget = capital * risk_pct / 100.0
    qty = math.floor(budget / rps + 1e-9)
    capped_by, notes = None, []
    if qty * entry > capital:
        qty, capped_by = math.floor(capital / entry), "capital"
        notes.append("Quantity reduced: risk-based size would exceed available capital")
    if max_position_pct:
        cap_qty = math.floor(capital * max_position_pct / 100.0 / entry)
        if cap_qty < qty:
            qty, capped_by = cap_qty, "max_position_pct"
            notes.append(f"Quantity reduced to respect the {max_position_pct}% single-stock limit")
    notes.append("Excludes brokerage/taxes and gap risk: losses can exceed the planned amount if price gaps past the stop.")
    return PositionSize(
        capital=capital, risk_pct=risk_pct, entry=entry, stop=stop, risk_per_share=round(rps, 2),
        max_loss=round(qty * rps, 2), quantity=qty, capital_required=round(qty * entry, 2), capped_by=capped_by,
        potential_profits=[round(qty * (t - entry), 2) for t in (targets or [])], notes=notes,
    )

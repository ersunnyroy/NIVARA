"""F&O analytics: OI buildup, futures basis, option-chain statistics, implied volatility and a
long-side swing score.

Design rules (apply to every function here):

* Pure and deterministic -- no DB, no network, no clock reads. Callers pass in everything.
* Never invent numbers. When an input is missing the output field is ``None`` and a ``missing`` /
  ``notes`` list says why.
* Every result is a plain dataclass (``dataclasses.asdict`` gives JSON-serialisable output) with a
  human-readable ``reasons`` / ``explanation`` list that cites the inputs used.
* OI is one input among many; every buildup interpretation carries :data:`OI_CAVEAT`.

All tunable thresholds are module-level constants below.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from typing import Any

from scipy.optimize import brentq
from scipy.stats import norm

from app.core.timeutil import IST
from app.data.types import FuturesRow, OptionRow

# --------------------------------------------------------------------------------------------
# Thresholds (tunable)
# --------------------------------------------------------------------------------------------

#: |price change %| below this is treated as "no move" for buildup classification.
BUILDUP_PRICE_THRESHOLD_PCT = 0.5
#: |OI change %| below this is treated as "no move" for buildup classification.
BUILDUP_OI_THRESHOLD_PCT = 2.0
#: Volume / 20-day average volume above this confirms the move (raises confidence).
VOLUME_CONFIRM_RATIO = 1.2
#: |price change %| at/above this counts as a "large" price move (raises confidence).
STRONG_PRICE_MOVE_PCT = 2.0
#: |OI change %| at/above this counts as a "large" OI move (raises confidence).
STRONG_OI_MOVE_PCT = 8.0
#: Look-back (trading days) for the average-volume denominator of the volume ratio.
VOLUME_AVG_DAYS = 20
#: Minimum prior trading days required before a volume ratio is reported.
VOLUME_AVG_MIN_DAYS = 10
#: When the near-month expiry is this many calendar days away (or fewer) we are in the rollover
#: window: the next month is reported too and buildup uses OI combined across all expiries.
ROLLOVER_DAYS = 2

#: Default annual risk-free rate (continuously compounded, decimal) for option pricing.
DEFAULT_RISK_FREE_RATE = 0.065
#: Volatility search bracket for brentq.
IV_LOWER = 0.001
IV_UPPER = 5.0
#: Contract expiry time (IST) used to compute time-to-expiry.
EXPIRY_TIME_IST = time(15, 30)
#: Minimum IV history observations for an IV percentile.
MIN_IV_HISTORY = 20

#: Number of strikes reported in the call-resistance / put-support / OI-change top lists.
TOP_N_STRIKES = 3

# fno_score thresholds (LONG-side swing setup). Score starts at FNO_SCORE_BASE and is clamped 0..100.
FNO_SCORE_BASE = 50.0
#: Points per buildup type, by confidence.
BUILDUP_POINTS: dict[str, dict[str, float]] = {
    "long_buildup": {"low": 10.0, "medium": 15.0, "high": 20.0},
    "short_covering": {"low": 5.0, "medium": 8.0, "high": 10.0},
    "neutral": {"low": 0.0, "medium": 0.0, "high": 0.0},
    "long_unwinding": {"low": -5.0, "medium": -8.0, "high": -10.0},
    "short_buildup": {"low": -10.0, "medium": -15.0, "high": -20.0},
}
#: PCR (by OI) range considered "healthy" for a long setup.
PCR_HEALTHY_LOW = 0.8
PCR_HEALTHY_HIGH = 1.3
PCR_HEALTHY_POINTS = 5.0
#: PCR above/below these is treated as a contrarian extreme -> caution.
PCR_EXTREME_HIGH = 1.6
PCR_EXTREME_LOW = 0.5
PCR_EXTREME_POINTS = -5.0
#: Distance (% of spot) from spot up to the call-resistance strike.
ROOM_LARGE_PCT = 5.0  # >= this: plenty of room
ROOM_LARGE_POINTS = 10.0
ROOM_SMALL_PCT = 2.0  # >= this (and < large): some room
ROOM_SMALL_POINTS = 5.0
ROOM_TIGHT_POINTS = -5.0  # < ROOM_SMALL_PCT: pressing against resistance
#: Spot within this % above the put-support strike counts as "support nearby".
SUPPORT_NEAR_PCT = 3.0
SUPPORT_NEAR_POINTS = 5.0
#: IV percentile above this is an "extreme IV" caution (event risk / expensive options).
IV_PCT_EXTREME = 85.0
IV_PCT_EXTREME_POINTS = -10.0

OI_CAVEAT = "OI is one input; never decide on OI alone."

BUILDUP_LABELS = {
    "long_buildup": "Long buildup",
    "short_buildup": "Short buildup",
    "short_covering": "Possible short covering",
    "long_unwinding": "Long unwinding",
    "neutral": "Neutral (moves below thresholds)",
}


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Attribute-or-key access so callers may pass dataclasses, ORM rows or dicts."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _fmt_pct(x: float) -> str:
    arrow = "↑" if x > 0 else ("↓" if x < 0 else "→")
    return f"{arrow} {abs(x):.1f}%"


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)


# --------------------------------------------------------------------------------------------
# A1. Buildup classification
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class BuildupThresholds:
    price_pct: float = BUILDUP_PRICE_THRESHOLD_PCT
    oi_pct: float = BUILDUP_OI_THRESHOLD_PCT
    volume_confirm_ratio: float = VOLUME_CONFIRM_RATIO
    strong_price_pct: float = STRONG_PRICE_MOVE_PCT
    strong_oi_pct: float = STRONG_OI_MOVE_PCT


@dataclass(slots=True)
class BuildupResult:
    buildup: str | None  # long_buildup | short_buildup | short_covering | long_unwinding | neutral | None
    confidence: str | None  # low | medium | high
    interpretation: str
    price_change_pct: float | None
    oi_change_pct: float | None
    volume_ratio: float | None
    volume_confirmed: bool | None
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    caveat: str = OI_CAVEAT


def classify_buildup(
    price_change_pct: float | None,
    oi_change_pct: float | None,
    volume_ratio: float | None = None,
    thresholds: BuildupThresholds | None = None,
) -> BuildupResult:
    """Classify the price/OI quadrant.

    * price ↑ OI ↑ -> long_buildup     * price ↓ OI ↑ -> short_buildup
    * price ↑ OI ↓ -> short_covering   * price ↓ OI ↓ -> long_unwinding
    * either move below its threshold -> neutral

    Confidence: one point each for volume confirmation (``volume_ratio`` > threshold), a large price
    move and a large OI move. 0 -> low, 1 -> medium, >=2 -> high -- but "high" requires volume
    confirmation; without it confidence is capped at medium.
    """
    th = thresholds or BuildupThresholds()
    missing: list[str] = []
    if price_change_pct is None:
        missing.append("price change % unavailable")
    if oi_change_pct is None:
        missing.append("OI change % unavailable")
    if missing:
        return BuildupResult(
            buildup=None,
            confidence=None,
            interpretation=f"Buildup not classified: {', '.join(missing)}. {OI_CAVEAT}",
            price_change_pct=price_change_pct,
            oi_change_pct=oi_change_pct,
            volume_ratio=volume_ratio,
            volume_confirmed=None,
            reasons=[],
            missing=missing,
        )

    p, o = float(price_change_pct), float(oi_change_pct)
    reasons: list[str] = []
    if abs(p) < th.price_pct or abs(o) < th.oi_pct:
        kind = "neutral"
        reasons.append(
            f"|price change| {abs(p):.2f}% vs threshold {th.price_pct}% and |OI change| {abs(o):.2f}% vs "
            f"threshold {th.oi_pct}% -> at least one move below threshold"
        )
    elif p > 0 and o > 0:
        kind = "long_buildup"
    elif p < 0 and o > 0:
        kind = "short_buildup"
    elif p > 0 and o < 0:
        kind = "short_covering"
    else:
        kind = "long_unwinding"
    if kind != "neutral":
        reasons.append(f"price change {p:+.2f}% and OI change {o:+.2f}% -> {BUILDUP_LABELS[kind]}")

    vol_confirmed: bool | None = None
    if volume_ratio is None:
        missing.append("volume ratio vs 20d average unavailable (no volume confirmation)")
    else:
        vol_confirmed = float(volume_ratio) > th.volume_confirm_ratio
        reasons.append(
            f"volume {volume_ratio:.2f}× 20d avg "
            f"({'confirms' if vol_confirmed else 'does not confirm'}; threshold {th.volume_confirm_ratio}×)"
        )

    confidence: str
    if kind == "neutral":
        confidence = "low"
    else:
        pts = 0
        if vol_confirmed:
            pts += 1
        if abs(p) >= th.strong_price_pct:
            pts += 1
            reasons.append(f"large price move (|{p:.2f}|% >= {th.strong_price_pct}%)")
        if abs(o) >= th.strong_oi_pct:
            pts += 1
            reasons.append(f"large OI move (|{o:.2f}|% >= {th.strong_oi_pct}%)")
        confidence = "low" if pts == 0 else ("medium" if pts == 1 else "high")
        if confidence == "high" and not vol_confirmed:
            confidence = "medium"
            reasons.append("confidence capped at medium without volume confirmation")

    parts = [f"Price {_fmt_pct(p)}", f"OI {_fmt_pct(o)}"]
    if volume_ratio is not None:
        parts.append(f"volume {volume_ratio:.1f}× avg")
    interpretation = f"{', '.join(parts)} → {BUILDUP_LABELS[kind]} ({confidence} confidence). {OI_CAVEAT}"
    return BuildupResult(
        buildup=kind,
        confidence=confidence,
        interpretation=interpretation,
        price_change_pct=_r(p),
        oi_change_pct=_r(o),
        volume_ratio=_r(volume_ratio),
        volume_confirmed=vol_confirmed,
        reasons=reasons,
        missing=missing,
    )


# --------------------------------------------------------------------------------------------
# A2. Futures: near-month selection & basis
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class FuturesContract:
    expiry: date
    days_to_expiry: int
    close: float
    settle: float | None
    oi: int
    change_oi: int
    volume: int
    lot_size: int | None


@dataclass(slots=True)
class FuturesAnalytics:
    underlying: str
    date: date
    near: FuturesContract | None
    next: FuturesContract | None  # only reported inside the rollover window
    in_rollover_window: bool
    oi_basis: str | None  # "near_month" | "combined_all_expiries"
    oi: int | None
    change_oi: int | None
    oi_change_pct: float | None
    volume: int | None
    spot: float | None
    basis: float | None  # fut - spot
    basis_pct: float | None  # basis / spot * 100
    annualised_basis_pct: float | None  # basis_pct * 365 / days_to_expiry (simple cost-of-carry)
    implied_carry_rate: float | None  # ln(F/S) * 365 / days (continuously compounded, decimal)
    explanation: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def _contract(row: FuturesRow, as_of: date) -> FuturesContract:
    return FuturesContract(
        expiry=row.expiry,
        days_to_expiry=(row.expiry - as_of).days,
        close=float(row.close),
        settle=row.settle,
        oi=int(row.oi or 0),
        change_oi=int(row.change_oi or 0),
        volume=int(row.volume or 0),
        lot_size=row.lot_size,
    )


def compute_basis(fut_price: float | None, spot: float | None, days_to_expiry: int | None) -> dict[str, Any]:
    """Basis = fut − spot; basis % of spot; simple annualised basis and continuously-compounded carry."""
    out: dict[str, Any] = {
        "basis": None,
        "basis_pct": None,
        "annualised_basis_pct": None,
        "implied_carry_rate": None,
        "notes": [],
    }
    if fut_price is None or spot is None or spot <= 0:
        out["notes"].append("basis needs both a futures price and a positive spot price")
        return out
    basis = fut_price - spot
    basis_pct = basis / spot * 100.0
    out["basis"] = _r(basis)
    out["basis_pct"] = _r(basis_pct)
    if days_to_expiry is None or days_to_expiry <= 0:
        out["notes"].append("annualised basis undefined on/after expiry day (days to expiry <= 0)")
    else:
        out["annualised_basis_pct"] = _r(basis_pct * 365.0 / days_to_expiry)
        if fut_price > 0:
            out["implied_carry_rate"] = _r(math.log(fut_price / spot) * 365.0 / days_to_expiry, 6)
    return out


def futures_analytics(futures_rows: Iterable[FuturesRow], as_of: date, spot: float | None) -> FuturesAnalytics:
    """Near-month selection (nearest expiry >= ``as_of``), rollover handling and basis.

    Only rows dated ``as_of`` are used. OI change % is derived from the exchange's own change-in-OI
    field: ``change_oi / (oi − change_oi)``.
    """
    rows = [r for r in futures_rows if r.date == as_of and r.expiry >= as_of]
    explanation: list[str] = []
    missing: list[str] = []
    if not rows:
        missing.append(f"no futures rows for {as_of.isoformat()} with expiry on/after that date")
        return FuturesAnalytics(
            underlying="",
            date=as_of,
            near=None,
            next=None,
            in_rollover_window=False,
            oi_basis=None,
            oi=None,
            change_oi=None,
            oi_change_pct=None,
            volume=None,
            spot=spot,
            basis=None,
            basis_pct=None,
            annualised_basis_pct=None,
            implied_carry_rate=None,
            explanation=explanation,
            missing=missing,
        )
    by_expiry: dict[date, FuturesRow] = {}
    for r in sorted(rows, key=lambda x: x.expiry):
        by_expiry.setdefault(r.expiry, r)  # first row per expiry wins (input should be unique anyway)
    expiries = sorted(by_expiry)
    near = _contract(by_expiry[expiries[0]], as_of)
    nxt = _contract(by_expiry[expiries[1]], as_of) if len(expiries) > 1 else None
    rollover = near.days_to_expiry <= ROLLOVER_DAYS
    explanation.append(f"near-month expiry {near.expiry.isoformat()} ({near.days_to_expiry} days to expiry)")

    if rollover:
        oi = sum(int(by_expiry[e].oi or 0) for e in expiries)
        chg = sum(int(by_expiry[e].change_oi or 0) for e in expiries)
        vol = sum(int(by_expiry[e].volume or 0) for e in expiries)
        oi_basis = "combined_all_expiries"
        explanation.append(
            f"rollover window (<= {ROLLOVER_DAYS} days): OI/volume combined across {len(expiries)} expiries "
            f"(OI {oi:,}, change {chg:+,})"
        )
        if nxt is None:
            explanation.append("no next-month contract available in the input")
        else:
            explanation.append(f"next-month expiry {nxt.expiry.isoformat()} close {nxt.close:.2f}, OI {nxt.oi:,}")
    else:
        oi, chg, vol = near.oi, near.change_oi, near.volume
        oi_basis = "near_month"
        nxt = None
    prev_oi = oi - chg
    oi_change_pct: float | None
    if prev_oi > 0:
        oi_change_pct = chg / prev_oi * 100.0
        explanation.append(f"OI change {chg:+,} on previous OI {prev_oi:,} = {oi_change_pct:+.2f}%")
    else:
        oi_change_pct = None
        missing.append("previous OI (oi − change_oi) is not positive; OI change % undefined")

    if spot is None:
        missing.append("spot price unavailable; basis not computed")
    b = compute_basis(near.close, spot, near.days_to_expiry)
    missing.extend(b["notes"])
    if b["basis"] is not None:
        explanation.append(
            f"basis = fut {near.close:.2f} − spot {spot:.2f} = {b['basis']:+.2f} ({b['basis_pct']:+.3f}%)"
            + (
                f", annualised {b['annualised_basis_pct']:+.2f}% over {near.days_to_expiry} days"
                if b["annualised_basis_pct"] is not None
                else ""
            )
        )
    return FuturesAnalytics(
        underlying=rows[0].underlying,
        date=as_of,
        near=near,
        next=nxt,
        in_rollover_window=rollover,
        oi_basis=oi_basis,
        oi=oi,
        change_oi=chg,
        oi_change_pct=_r(oi_change_pct),
        volume=vol,
        spot=spot,
        basis=b["basis"],
        basis_pct=b["basis_pct"],
        annualised_basis_pct=b["annualised_basis_pct"],
        implied_carry_rate=b["implied_carry_rate"],
        explanation=explanation,
        missing=missing,
    )


def futures_volume_ratio(futures_rows: Iterable[FuturesRow], as_of: date) -> tuple[float | None, str]:
    """Today's total futures volume (all expiries) / average of the previous ``VOLUME_AVG_DAYS`` dates."""
    per_day: dict[date, int] = defaultdict(int)
    for r in futures_rows:
        if r.date <= as_of:
            per_day[r.date] += int(r.volume or 0)
    if as_of not in per_day:
        return None, f"no futures volume for {as_of.isoformat()}"
    prior = sorted(d for d in per_day if d < as_of)[-VOLUME_AVG_DAYS:]
    if len(prior) < VOLUME_AVG_MIN_DAYS:
        return None, f"only {len(prior)} prior trading days of volume (< {VOLUME_AVG_MIN_DAYS}); volume ratio not computed"
    avg = sum(per_day[d] for d in prior) / len(prior)
    if avg <= 0:
        return None, "average prior volume is zero; volume ratio undefined"
    ratio = per_day[as_of] / avg
    return ratio, f"volume {per_day[as_of]:,} vs {len(prior)}-day avg {avg:,.0f} = {ratio:.2f}×"


# --------------------------------------------------------------------------------------------
# A3. Implied volatility
# --------------------------------------------------------------------------------------------


def time_to_expiry_years(as_of: date | datetime, expiry: date) -> float:
    """Calendar time from valuation to expiry (15:30 IST) in years (/365).

    A bare ``date`` is valued at that day's close (15:30 IST), so this is ``calendar_days / 365``.
    A naive ``datetime`` is interpreted as IST.
    """
    exp_dt = datetime.combine(expiry, EXPIRY_TIME_IST, IST)
    if isinstance(as_of, datetime):
        val = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=IST)
    else:
        val = datetime.combine(as_of, EXPIRY_TIME_IST, IST)
    return (exp_dt - val).total_seconds() / (365.0 * 86400.0)


def _d1d2(f_or_s: float, k: float, t: float, sigma: float, carry: float) -> tuple[float, float]:
    vs = sigma * math.sqrt(t)
    d1 = (math.log(f_or_s / k) + (carry + 0.5 * sigma * sigma) * t) / vs
    return d1, d1 - vs


def black_scholes_price(spot: float, strike: float, t: float, r: float, sigma: float, option_type: str) -> float:
    """Black-Scholes (no dividend) price of a European CE/PE on spot."""
    d1, d2 = _d1d2(spot, strike, t, sigma, r)
    disc = math.exp(-r * t)
    if option_type.upper() == "CE":
        return spot * norm.cdf(d1) - strike * disc * norm.cdf(d2)
    return strike * disc * norm.cdf(-d2) - spot * norm.cdf(-d1)


def black76_price(fut: float, strike: float, t: float, r: float, sigma: float, option_type: str) -> float:
    """Black-76 price of a European CE/PE on a futures price."""
    d1, d2 = _d1d2(fut, strike, t, sigma, 0.0)
    disc = math.exp(-r * t)
    if option_type.upper() == "CE":
        return disc * (fut * norm.cdf(d1) - strike * norm.cdf(d2))
    return disc * (strike * norm.cdf(-d2) - fut * norm.cdf(-d1))


def _lower_bound(underlying: float, strike: float, t: float, r: float, option_type: str, model: str) -> float:
    disc = math.exp(-r * t)
    if model == "black76":
        intrinsic = (underlying - strike) if option_type == "CE" else (strike - underlying)
        return max(0.0, disc * intrinsic)
    intrinsic = (underlying - strike * disc) if option_type == "CE" else (strike * disc - underlying)
    return max(0.0, intrinsic)


@dataclass(slots=True)
class IvResult:
    iv: float | None  # annualised decimal
    model: str | None  # black76 | black_scholes
    option_price: float | None
    underlying: float | None
    strike: float
    option_type: str
    t_years: float | None
    note: str | None = None


def implied_volatility(
    price: float | None,
    underlying: float | None,
    strike: float,
    t_years: float | None,
    option_type: str,
    r: float = DEFAULT_RISK_FREE_RATE,
    model: str = "black76",
) -> IvResult:
    """Solve for σ with brentq on [IV_LOWER, IV_UPPER]. ``model``: 'black76' (underlying = futures
    price) or 'black_scholes' (underlying = spot, zero dividend). Returns ``iv=None`` with a note when
    the premium is zero/missing, below the no-arbitrage lower bound, or the solver does not converge."""
    ot = option_type.upper()
    res = IvResult(None, model, price, underlying, strike, ot, t_years)
    if price is None or price <= 0:
        res.note = "zero or missing premium"
        return res
    if underlying is None or underlying <= 0 or strike <= 0:
        res.note = "missing/invalid underlying or strike"
        return res
    if t_years is None or t_years <= 0:
        res.note = "no time to expiry left"
        return res
    pricer = black76_price if model == "black76" else black_scholes_price
    lb = _lower_bound(underlying, strike, t_years, r, ot, model)
    if price < lb - 1e-9:
        res.note = f"premium {price:.4f} below intrinsic/lower bound {lb:.4f}"
        return res

    def f(sig: float) -> float:
        return pricer(underlying, strike, t_years, r, sig, ot) - price

    try:
        lo, hi = f(IV_LOWER), f(IV_UPPER)
        if lo * hi > 0:
            res.note = f"no IV in [{IV_LOWER}, {IV_UPPER}] reproduces premium {price:.4f}"
            return res
        res.iv = float(brentq(f, IV_LOWER, IV_UPPER, xtol=1e-8, maxiter=200))
    except (ValueError, RuntimeError, ZeroDivisionError, OverflowError) as exc:  # pragma: no cover - defensive
        res.note = f"IV solver did not converge: {exc}"
        res.iv = None
    return res


def option_row_iv(
    row: OptionRow,
    as_of: date | datetime,
    fut_price: float | None = None,
    spot: float | None = None,
    r: float = DEFAULT_RISK_FREE_RATE,
) -> IvResult:
    """IV for one option row: Black-76 on ``fut_price`` (pass only a same-expiry futures price) when
    available, else Black-Scholes on spot. Uses the traded close; zero-volume rows return None."""
    t = time_to_expiry_years(as_of, row.expiry)
    model = "black76" if fut_price is not None else "black_scholes"
    und = fut_price if fut_price is not None else (spot if spot is not None else row.underlying_price)
    if not row.volume:
        return IvResult(None, model, row.close, und, row.strike, row.option_type.upper(), t, "zero volume (no trade)")
    return implied_volatility(row.close, und, row.strike, t, row.option_type, r=r, model=model)


@dataclass(slots=True)
class IvPercentile:
    value: float | None  # 0..100: % of history observations strictly below current IV
    current_iv: float | None
    observations: int
    note: str | None = None


def iv_percentile(current_iv: float | None, history: Iterable[float | None] | None) -> IvPercentile:
    """% of historical daily IV observations below ``current_iv``; None if < MIN_IV_HISTORY obs."""
    hist = [float(h) for h in (history or []) if h is not None and not math.isnan(float(h))]
    if current_iv is None:
        return IvPercentile(None, None, len(hist), "current IV unavailable")
    if len(hist) < MIN_IV_HISTORY:
        return IvPercentile(
            None, current_iv, len(hist), f"insufficient IV history: {len(hist)} observations (< {MIN_IV_HISTORY})"
        )
    below = sum(1 for h in hist if h < current_iv)
    return IvPercentile(round(below / len(hist) * 100.0, 2), current_iv, len(hist), None)


# --------------------------------------------------------------------------------------------
# A4. Option chain analytics
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class StrikeOI:
    strike: float
    option_type: str
    oi: int
    change_oi: int


@dataclass(slots=True)
class OptionChainAnalytics:
    underlying: str
    date: date | None
    expiry: date | None
    underlying_price: float | None
    strikes: int
    total_ce_oi: int
    total_pe_oi: int
    total_ce_volume: int
    total_pe_volume: int
    pcr_oi: float | None
    pcr_volume: float | None
    max_pain: float | None
    call_resistance: float | None
    call_resistance_top: list[StrikeOI]
    put_support: float | None
    put_support_top: list[StrikeOI]
    call_writing_top: list[StrikeOI]  # largest positive ΔOI on CE
    put_writing_top: list[StrikeOI]  # largest positive ΔOI on PE
    oi_change_concentration: dict[str, float | None]  # share of total positive ΔOI in the top strikes
    atm_strike: float | None
    explanation: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def compute_max_pain(option_rows: Iterable[OptionRow]) -> float | None:
    """Strike minimising the total intrinsic value payable to option buyers at expiry.

    For each candidate settlement K (every listed strike): Σ_s CE_OI(s)·max(K−s,0) + PE_OI(s)·max(s−K,0).
    Ties resolve to the lowest strike. None when there is no open interest."""
    ce: dict[float, int] = defaultdict(int)
    pe: dict[float, int] = defaultdict(int)
    for r in option_rows:
        if r.option_type.upper() == "CE":
            ce[float(r.strike)] += int(r.oi or 0)
        else:
            pe[float(r.strike)] += int(r.oi or 0)
    strikes = sorted(set(ce) | set(pe))
    if not strikes or (sum(ce.values()) + sum(pe.values())) == 0:
        return None
    best_k, best_pay = None, None
    for k in strikes:
        pay = sum(oi * max(k - s, 0.0) for s, oi in ce.items()) + sum(oi * max(s - k, 0.0) for s, oi in pe.items())
        if best_pay is None or pay < best_pay:
            best_k, best_pay = k, pay
    return best_k


def nearest_strike(strikes: Iterable[float], price: float | None) -> float | None:
    """Strike nearest to ``price`` (ties -> lower strike)."""
    ss = sorted({float(s) for s in strikes})
    if not ss or price is None:
        return None
    return min(ss, key=lambda s: (abs(s - price), s))


def option_chain_analytics(
    option_rows: Iterable[OptionRow],
    underlying_price: float | None = None,
    expiry: date | None = None,
    as_of: date | None = None,
) -> OptionChainAnalytics:
    """PCR, max pain, call resistance / put support, ΔOI concentration and ATM strike for one expiry.

    If ``as_of`` is given only rows of that date are used; if ``expiry`` is None the nearest expiry
    on/after the row date is used. ``underlying_price`` falls back to the rows' own underlying price."""
    rows = list(option_rows)
    explanation: list[str] = []
    missing: list[str] = []
    if as_of is not None:
        rows = [r for r in rows if r.date == as_of]
    if expiry is None and rows:
        d0 = as_of or max(r.date for r in rows)
        future = sorted({r.expiry for r in rows if r.expiry >= d0})
        expiry = future[0] if future else None
    rows = [r for r in rows if r.expiry == expiry] if expiry is not None else []
    if underlying_price is None:
        ups = [r.underlying_price for r in rows if r.underlying_price]
        if ups:
            underlying_price = float(ups[0])
            explanation.append(f"underlying price {underlying_price:.2f} taken from the option rows")
    underlying = rows[0].underlying if rows else ""
    d = rows[0].date if rows else as_of

    ces = [r for r in rows if r.option_type.upper() == "CE"]
    pes = [r for r in rows if r.option_type.upper() == "PE"]
    ce_oi = sum(int(r.oi or 0) for r in ces)
    pe_oi = sum(int(r.oi or 0) for r in pes)
    ce_vol = sum(int(r.volume or 0) for r in ces)
    pe_vol = sum(int(r.volume or 0) for r in pes)

    if not rows:
        missing.append("no option rows for the requested date/expiry")
    pcr_oi = pe_oi / ce_oi if ce_oi > 0 else None
    pcr_vol = pe_vol / ce_vol if ce_vol > 0 else None
    if rows:
        if pcr_oi is None:
            missing.append("total CE OI is zero; PCR (OI) undefined")
        else:
            explanation.append(f"PCR (OI) = PE OI {pe_oi:,} / CE OI {ce_oi:,} = {pcr_oi:.2f}")
        if pcr_vol is None:
            missing.append("total CE volume is zero; PCR (volume) undefined")
        else:
            explanation.append(f"PCR (volume) = PE vol {pe_vol:,} / CE vol {ce_vol:,} = {pcr_vol:.2f}")

    def so(r: OptionRow) -> StrikeOI:
        return StrikeOI(float(r.strike), r.option_type.upper(), int(r.oi or 0), int(r.change_oi or 0))

    ce_top = [so(r) for r in sorted(ces, key=lambda r: (-int(r.oi or 0), r.strike)) if r.oi][:TOP_N_STRIKES]
    pe_top = [so(r) for r in sorted(pes, key=lambda r: (-int(r.oi or 0), -r.strike)) if r.oi][:TOP_N_STRIKES]
    call_res = ce_top[0].strike if ce_top else None
    put_sup = pe_top[0].strike if pe_top else None
    if call_res is not None:
        explanation.append(f"call resistance {call_res:g} (max CE OI {ce_top[0].oi:,})")
    elif rows:
        missing.append("no CE open interest; call resistance undefined")
    if put_sup is not None:
        explanation.append(f"put support {put_sup:g} (max PE OI {pe_top[0].oi:,})")
    elif rows:
        missing.append("no PE open interest; put support undefined")

    ce_add = sorted((r for r in ces if (r.change_oi or 0) > 0), key=lambda r: (-r.change_oi, r.strike))
    pe_add = sorted((r for r in pes if (r.change_oi or 0) > 0), key=lambda r: (-r.change_oi, -r.strike))
    ce_w = [so(r) for r in ce_add[:TOP_N_STRIKES]]
    pe_w = [so(r) for r in pe_add[:TOP_N_STRIKES]]
    tot_ce_add = sum(r.change_oi for r in ce_add)
    tot_pe_add = sum(r.change_oi for r in pe_add)
    conc = {
        "ce_top_share_of_oi_addition": _r(sum(x.change_oi for x in ce_w) / tot_ce_add) if tot_ce_add else None,
        "pe_top_share_of_oi_addition": _r(sum(x.change_oi for x in pe_w) / tot_pe_add) if tot_pe_add else None,
    }
    if ce_w:
        explanation.append(f"largest call writing at {ce_w[0].strike:g} (ΔOI {ce_w[0].change_oi:+,})")
    if pe_w:
        explanation.append(f"largest put writing at {pe_w[0].strike:g} (ΔOI {pe_w[0].change_oi:+,})")

    mp = compute_max_pain(rows)
    if mp is not None:
        explanation.append(f"max pain {mp:g} (strike minimising total option-buyer payout)")
    elif rows:
        missing.append("no open interest; max pain undefined")
    atm = nearest_strike((r.strike for r in rows), underlying_price)
    if atm is None and rows:
        missing.append("underlying price unavailable; ATM strike undefined")
    return OptionChainAnalytics(
        underlying=underlying,
        date=d,
        expiry=expiry,
        underlying_price=underlying_price,
        strikes=len({r.strike for r in rows}),
        total_ce_oi=ce_oi,
        total_pe_oi=pe_oi,
        total_ce_volume=ce_vol,
        total_pe_volume=pe_vol,
        pcr_oi=_r(pcr_oi),
        pcr_volume=_r(pcr_vol),
        max_pain=mp,
        call_resistance=call_res,
        call_resistance_top=ce_top,
        put_support=put_sup,
        put_support_top=pe_top,
        call_writing_top=ce_w,
        put_writing_top=pe_w,
        oi_change_concentration=conc,
        atm_strike=atm,
        explanation=explanation,
        missing=missing,
    )


@dataclass(slots=True)
class AtmIv:
    atm_strike: float | None
    atm_iv: float | None
    ce: IvResult | None
    pe: IvResult | None
    note: str | None = None


def atm_iv(
    option_rows: Iterable[OptionRow],
    as_of: date | datetime,
    spot: float | None,
    fut_price: float | None = None,
    r: float = DEFAULT_RISK_FREE_RATE,
) -> AtmIv:
    """ATM IV = mean of CE and PE IV at the strike nearest to the underlying (spot, else futures).

    Pass rows of one expiry only. ``fut_price`` must be the same-expiry futures price (Black-76);
    without it Black-Scholes on spot is used. If only one side solves, that side is used (noted)."""
    rows = list(option_rows)
    ref = spot if spot is not None else fut_price
    k = nearest_strike((x.strike for x in rows), ref)
    if k is None:
        return AtmIv(None, None, None, None, "no strikes or no underlying price")
    side: dict[str, IvResult] = {}
    for x in rows:
        if float(x.strike) == k and x.option_type.upper() in ("CE", "PE"):
            side[x.option_type.upper()] = option_row_iv(x, as_of, fut_price=fut_price, spot=spot, r=r)
    ce, pe = side.get("CE"), side.get("PE")
    ivs = [s.iv for s in (ce, pe) if s is not None and s.iv is not None]
    if not ivs:
        return AtmIv(k, None, ce, pe, "IV unavailable on both CE and PE at the ATM strike")
    note = None
    if len(ivs) == 1:
        bad = "CE" if (ce is None or ce.iv is None) else "PE"
        why = (side[bad].note if bad in side else "row missing") or "unsolved"
        note = f"only one side solved at ATM strike {k:g}; {bad} IV unavailable ({why})"
    return AtmIv(k, round(sum(ivs) / len(ivs), 6), ce, pe, note)


# --------------------------------------------------------------------------------------------
# A5. Snapshot + score
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class FnoSnapshotResult:
    underlying: str
    date: date
    is_fno: bool
    spot: float | None
    fut_price: float | None
    basis: float | None
    basis_pct: float | None
    fut_oi: int | None
    fut_oi_change_pct: float | None
    fut_volume: int | None
    pcr_oi: float | None
    pcr_volume: float | None
    max_pain: float | None
    call_resistance: float | None
    put_support: float | None
    atm_iv: float | None
    iv_percentile: float | None
    buildup: str | None
    interpretation: str | None
    details: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _price_change_for_buildup(
    futures_rows: list[FuturesRow], as_of: date, near: FuturesContract, spot: float | None, prev_snapshot: Any
) -> tuple[float | None, str]:
    """Price change %: same-contract previous close from ``futures_rows`` > previous snapshot with the same
    near expiry > spot vs previous snapshot spot. Returns (pct, explanation)."""
    prev_rows = [r for r in futures_rows if r.date < as_of and r.expiry == near.expiry]
    if prev_rows:
        prev = max(prev_rows, key=lambda r: r.date)
        if prev.close:
            pct = (near.close - prev.close) / prev.close * 100.0
            return pct, f"futures {near.expiry.isoformat()} close {near.close:.2f} vs {prev.close:.2f} on {prev.date}"
    if prev_snapshot is not None:
        prev_details = _get(prev_snapshot, "details") or {}
        prev_exp = _get(prev_details, "near_expiry")
        prev_fut = _get(prev_snapshot, "fut_price")
        if prev_fut and prev_exp is not None and str(prev_exp) == near.expiry.isoformat():
            pct = (near.close - prev_fut) / prev_fut * 100.0
            return pct, f"futures close {near.close:.2f} vs previous snapshot {prev_fut:.2f} (same expiry)"
        prev_spot = _get(prev_snapshot, "spot")
        if prev_spot and spot is not None:
            pct = (spot - prev_spot) / prev_spot * 100.0
            return pct, f"spot {spot:.2f} vs previous snapshot spot {prev_spot:.2f} (no same-contract futures close)"
    return None, "no previous price available for the price-change leg"


def fno_snapshot(
    underlying: str,
    date: date,
    futures_rows: Iterable[FuturesRow],
    option_rows: Iterable[OptionRow],
    spot: float | None,
    prev_snapshot: Any = None,
    iv_history: Iterable[float | None] | None = None,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> FnoSnapshotResult:
    """Daily per-underlying F&O analytics matching ``models.fno.FnoSnapshot`` columns.

    ``futures_rows`` may include previous dates (used for the price change and the 20-day volume
    average); ``option_rows`` should contain at least the rows dated ``date``. ``prev_snapshot`` may
    be a FnoSnapshotResult, ORM row or dict (fields: spot, fut_price, details.near_expiry)."""
    as_of = date
    frows = [r for r in futures_rows if r.underlying == underlying] if underlying else list(futures_rows)
    orows = [r for r in option_rows if r.underlying == underlying and r.date == as_of]
    missing: list[str] = []
    notes: list[str] = []
    details: dict[str, Any] = {}

    has_fut_today = any(r.date == as_of for r in frows)
    if not has_fut_today and not orows:
        return FnoSnapshotResult(
            underlying=underlying, date=as_of, is_fno=False, spot=spot, fut_price=None, basis=None,
            basis_pct=None, fut_oi=None, fut_oi_change_pct=None, fut_volume=None, pcr_oi=None,
            pcr_volume=None, max_pain=None, call_resistance=None, put_support=None, atm_iv=None,
            iv_percentile=None, buildup=None, interpretation=None, details={},
            missing=["not an F&O stock (no futures or option rows for this date)"], notes=[],
        )  # fmt: skip

    if spot is None:
        ups = [r.underlying_price for r in frows if r.date == as_of and r.underlying_price]
        ups += [r.underlying_price for r in orows if r.underlying_price]
        if ups:
            spot = float(ups[0])
            notes.append(f"spot {spot:.2f} taken from the exchange's underlying price in the F&O bhavcopy")
        else:
            missing.append("spot price unavailable")

    # ---- futures
    fa = futures_analytics(frows, as_of, spot)
    missing.extend(fa.missing)
    details["futures"] = asdict(fa)
    buildup_res: BuildupResult | None = None
    fut_price = fa.near.close if fa.near else None
    if fa.near is not None:
        details["near_expiry"] = fa.near.expiry.isoformat()
        details["days_to_expiry"] = fa.near.days_to_expiry
        details["oi_basis"] = fa.oi_basis
        pchg, pnote = _price_change_for_buildup(frows, as_of, fa.near, spot, prev_snapshot)
        vr, vnote = futures_volume_ratio(frows, as_of)
        details["price_change_source"] = pnote
        details["volume_ratio_note"] = vnote
        if vr is None:
            notes.append(vnote)
        buildup_res = classify_buildup(pchg, fa.oi_change_pct, vr)
        details["buildup"] = asdict(buildup_res)
        missing.extend(buildup_res.missing)
    else:
        missing.append("no futures contract; buildup not classified")

    # ---- options
    opt_exp: date | None = None
    if orows:
        exps = sorted({r.expiry for r in orows if r.expiry >= as_of})
        if exps:
            opt_exp = exps[0]
            if (opt_exp - as_of).days <= ROLLOVER_DAYS and len(exps) > 1:
                notes.append(
                    f"option expiry {opt_exp.isoformat()} is within {ROLLOVER_DAYS} days; chain analytics use the "
                    f"next expiry {exps[1].isoformat()}"
                )
                opt_exp = exps[1]
    chain = option_chain_analytics(orows, underlying_price=spot, expiry=opt_exp, as_of=as_of) if opt_exp else None
    iv_res: AtmIv | None = None
    ivp: IvPercentile | None = None
    if chain is None:
        missing.append("no option chain for this date")
    else:
        details["option_chain"] = asdict(chain)
        missing.extend(chain.missing)
        same_exp_fut = next(
            (float(r.close) for r in frows if r.date == as_of and r.expiry == opt_exp and r.close), None
        )
        chain_rows = [r for r in orows if r.expiry == opt_exp]
        iv_res = atm_iv(chain_rows, as_of, spot, fut_price=same_exp_fut, r=risk_free_rate)
        details["atm_iv"] = asdict(iv_res)
        details["iv_model"] = "black76 (same-expiry futures)" if same_exp_fut is not None else "black_scholes (spot)"
        if iv_res.note:
            notes.append(iv_res.note)
        if iv_res.atm_iv is None:
            missing.append("ATM IV unavailable")
        ivp = iv_percentile(iv_res.atm_iv, iv_history)
        details["iv_percentile"] = asdict(ivp)
        if ivp.value is None and ivp.note:
            missing.append(ivp.note)

    interp_parts: list[str] = []
    if buildup_res is not None:
        interp_parts.append(buildup_res.interpretation)
    if chain is not None and chain.pcr_oi is not None:
        interp_parts.append(f"PCR(OI) {chain.pcr_oi:.2f}")
    if chain is not None and chain.call_resistance is not None and chain.put_support is not None:
        interp_parts.append(f"call OI wall {chain.call_resistance:g}, put OI base {chain.put_support:g}")
    interpretation = " | ".join(interp_parts) if interp_parts else None
    if interpretation and len(interpretation) > 500:  # DB column is String(500)
        interpretation = interpretation[:497] + "..."

    return FnoSnapshotResult(
        underlying=underlying,
        date=as_of,
        is_fno=True,
        spot=spot,
        fut_price=fut_price,
        basis=fa.basis,
        basis_pct=fa.basis_pct,
        fut_oi=fa.oi,
        fut_oi_change_pct=fa.oi_change_pct,
        fut_volume=fa.volume,
        pcr_oi=chain.pcr_oi if chain else None,
        pcr_volume=chain.pcr_volume if chain else None,
        max_pain=chain.max_pain if chain else None,
        call_resistance=chain.call_resistance if chain else None,
        put_support=chain.put_support if chain else None,
        atm_iv=iv_res.atm_iv if iv_res else None,
        iv_percentile=ivp.value if ivp else None,
        buildup=buildup_res.buildup if buildup_res else None,
        interpretation=interpretation,
        details=_jsonable(details),
        missing=list(dict.fromkeys(missing)),
        notes=list(dict.fromkeys(notes)),
    )


def _jsonable(obj: Any) -> Any:
    """Convert dates inside nested dicts/lists to ISO strings so ``details`` is JSON-ready."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def fno_score(snapshot: Any) -> tuple[float | None, list[str], list[str]]:
    """LONG-side swing score 0..100 from an F&O snapshot (FnoSnapshotResult, ORM row or dict).

    Starts at FNO_SCORE_BASE (50 = no edge) and adds/subtracts the documented points:
    buildup (BUILDUP_POINTS by confidence), PCR band, room to call resistance, nearby put support and
    extreme IV percentile. Returns (score, reasons, missing). Non-F&O -> (None, [], ["not an F&O stock"]).
    """
    if snapshot is None or _get(snapshot, "is_fno", True) is False:
        return None, [], ["not an F&O stock"]
    keys = ("fut_price", "pcr_oi", "buildup", "call_resistance", "atm_iv")
    if all(_get(snapshot, k) is None for k in keys):
        return None, [], ["not an F&O stock"]

    score = FNO_SCORE_BASE
    reasons: list[str] = []
    missing: list[str] = []
    details = _get(snapshot, "details") or {}

    buildup = _get(snapshot, "buildup")
    conf = _get(_get(details, "buildup") or {}, "confidence") or "low"
    if buildup is None:
        missing.append("buildup unavailable")
    else:
        pts = BUILDUP_POINTS.get(buildup, {}).get(conf, 0.0)
        score += pts
        label = BUILDUP_LABELS.get(buildup, buildup)
        reasons.append(f"{label} ({conf} confidence): {pts:+.0f}. {OI_CAVEAT}")

    pcr = _get(snapshot, "pcr_oi")
    if pcr is None:
        missing.append("PCR (OI) unavailable")
    elif pcr > PCR_EXTREME_HIGH or pcr < PCR_EXTREME_LOW:
        score += PCR_EXTREME_POINTS
        reasons.append(
            f"PCR(OI) {pcr:.2f} outside {PCR_EXTREME_LOW}–{PCR_EXTREME_HIGH}: contrarian extreme, caution "
            f"{PCR_EXTREME_POINTS:+.0f}"
        )
    elif PCR_HEALTHY_LOW <= pcr <= PCR_HEALTHY_HIGH:
        score += PCR_HEALTHY_POINTS
        reasons.append(f"PCR(OI) {pcr:.2f} in healthy {PCR_HEALTHY_LOW}–{PCR_HEALTHY_HIGH} range: {PCR_HEALTHY_POINTS:+.0f}")
    else:
        reasons.append(f"PCR(OI) {pcr:.2f}: no adjustment")

    spot = _get(snapshot, "spot")
    cr = _get(snapshot, "call_resistance")
    if spot is None or cr is None:
        missing.append("spot or call resistance unavailable (room-to-move not assessed)")
    else:
        room = (cr - spot) / spot * 100.0
        if room < 0:
            reasons.append(f"spot {spot:.2f} above max-CE-OI strike {cr:g} (resistance exceeded): no adjustment")
        elif room >= ROOM_LARGE_PCT:
            score += ROOM_LARGE_POINTS
            reasons.append(f"call resistance {cr:g} is {room:.1f}% above spot: room to move {ROOM_LARGE_POINTS:+.0f}")
        elif room >= ROOM_SMALL_PCT:
            score += ROOM_SMALL_POINTS
            reasons.append(f"call resistance {cr:g} is {room:.1f}% above spot: some room {ROOM_SMALL_POINTS:+.0f}")
        else:
            score += ROOM_TIGHT_POINTS
            reasons.append(f"call resistance {cr:g} only {room:.1f}% above spot: limited room {ROOM_TIGHT_POINTS:+.0f}")

    ps = _get(snapshot, "put_support")
    if spot is not None and ps is not None:
        gap = (spot - ps) / spot * 100.0
        if 0 <= gap <= SUPPORT_NEAR_PCT:
            score += SUPPORT_NEAR_POINTS
            reasons.append(f"put support {ps:g} is {gap:.1f}% below spot: nearby support {SUPPORT_NEAR_POINTS:+.0f}")

    ivp = _get(snapshot, "iv_percentile")
    if ivp is None:
        missing.append("IV percentile unavailable")
    elif ivp > IV_PCT_EXTREME:
        score += IV_PCT_EXTREME_POINTS
        reasons.append(
            f"IV percentile {ivp:.0f} > {IV_PCT_EXTREME:.0f}: extreme IV / event risk, caution {IV_PCT_EXTREME_POINTS:+.0f}"
        )
    else:
        reasons.append(f"IV percentile {ivp:.0f}: no adjustment")

    score = max(0.0, min(100.0, score))
    return round(score, 2), reasons, missing

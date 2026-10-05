"""Fundamental metrics (TTM from quarterly filings) and a transparent 0-100 fundamental score.

Rules:

* Pure functions; never invent numbers. A metric that cannot be computed from the inputs is
  ``value=None`` with a ``note`` explaining why (e.g. balance-sheet data not in the quarterly feed).
* Consolidated statements are preferred; consolidated and standalone are never mixed.
* The score is a weighted mean of category scores; categories without data are excluded and the
  remaining weights re-normalised. ``completeness`` is the share of total component weight that had
  data. Below MIN_COMPLETENESS the score is None ("insufficient fundamental data").

All thresholds/weights are module-level constants below.
"""
from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise
from typing import Any

import numpy as np

from app.data.types import FinancialStatement, ShareholdingRecord

# --------------------------------------------------------------------------------------------
# Constants (tunable)
# --------------------------------------------------------------------------------------------

SOURCE_XBRL = "derived from NSE XBRL filings"
SOURCE_XBRL_REPORTED = "reported in NSE XBRL filing"
SOURCE_SHP = "NSE shareholding pattern filing"
SOURCE_INPUT = "caller-supplied input"

NOT_IN_FEED = "requires balance sheet / cash-flow data — not in quarterly filing feed"

#: Gap (days) between consecutive quarter ends considered "consecutive".
QUARTER_GAP_DAYS = (80, 100)
#: A statement whose period_start→period_end spans more than this is not a quarter (ignored).
MAX_QUARTER_SPAN_DAYS = 100
#: Tolerance when finding the shareholding record ~1 year before the latest (days around 365).
SHP_YOY_TOLERANCE_DAYS = 45

#: Category weights (sum to 1). Components inside a category share its weight equally for
#: completeness; the category score is the mean of its available component scores.
CATEGORY_WEIGHTS: dict[str, float] = {
    "growth": 0.25,
    "profitability": 0.20,
    "balance_sheet": 0.20,
    "valuation": 0.20,
    "ownership": 0.15,
}
CATEGORY_COMPONENTS: dict[str, tuple[str, ...]] = {
    "growth": ("revenue_growth_yoy", "earnings_growth_yoy"),
    "profitability": ("ebitda_margin", "pat_margin", "roe", "roce"),
    "balance_sheet": ("debt_equity", "interest_coverage", "promoter_pledge"),
    "valuation": ("pe_vs_sector", "pe_vs_history", "peg"),
    "ownership": ("promoter_holding", "promoter_trend"),
}
#: If the share of component weight with data is below this, the score is None.
MIN_COMPLETENESS = 0.3

# Piecewise-linear scoring curves: (x points, score points); values outside are clamped.
CURVE_REVENUE_GROWTH = ([-10.0, 0.0, 10.0, 20.0, 30.0], [0.0, 30.0, 60.0, 85.0, 100.0])  # % YoY
CURVE_EARNINGS_GROWTH = ([-20.0, 0.0, 15.0, 25.0, 40.0], [0.0, 30.0, 65.0, 85.0, 100.0])  # % YoY
CURVE_EBITDA_MARGIN = ([0.0, 10.0, 20.0, 30.0], [10.0, 45.0, 75.0, 100.0])  # % (absolute)
CURVE_PAT_MARGIN = ([0.0, 5.0, 10.0, 20.0, 25.0], [0.0, 45.0, 65.0, 90.0, 100.0])  # % (absolute)
#: Margin vs sector median (percentage-point difference) -- used instead when a sector median exists.
CURVE_MARGIN_VS_SECTOR_PP = ([-10.0, 0.0, 10.0], [10.0, 50.0, 90.0])
CURVE_RETURN_RATIO = ([0.0, 10.0, 15.0, 20.0, 25.0], [0.0, 40.0, 65.0, 85.0, 100.0])  # ROE / ROCE %
CURVE_DEBT_EQUITY = ([0.0, 0.5, 1.0, 2.0, 3.0], [100.0, 80.0, 55.0, 20.0, 0.0])  # x
CURVE_INTEREST_COVERAGE = ([1.0, 1.5, 3.0, 5.0, 10.0], [0.0, 20.0, 55.0, 80.0, 100.0])  # x
CURVE_PLEDGE = ([0.0, 5.0, 20.0, 50.0], [100.0, 75.0, 35.0, 0.0])  # % of promoter holding pledged
CURVE_PE_VS_SECTOR = ([0.5, 0.8, 1.0, 1.3, 2.0], [100.0, 80.0, 60.0, 35.0, 0.0])  # PE / sector median PE
CURVE_PEG = ([0.5, 1.0, 1.5, 2.0, 3.0], [100.0, 75.0, 50.0, 30.0, 0.0])
CURVE_PROMOTER_HOLDING = ([0.0, 25.0, 40.0, 50.0, 65.0, 75.0], [40.0, 50.0, 65.0, 80.0, 90.0, 100.0])  # %
CURVE_PROMOTER_TREND_PP = ([-5.0, -2.0, 0.0, 1.0, 3.0], [0.0, 25.0, 55.0, 75.0, 100.0])  # change, pp
#: Score for a company with no promoter group (professionally managed) -- neutral.
NO_PROMOTER_SCORE = 50.0
#: Minimum own-history PE observations for the PE-vs-history component.
MIN_PE_HISTORY = 8
#: Minimum peers with a value for a sector median to be reported.
MIN_SECTOR_PEERS = 3
#: Metrics for which sector medians are computed.
SECTOR_MEDIAN_METRICS = (
    "pe",
    "ebitda_margin",
    "pat_margin",
    "revenue_growth_yoy",
    "earnings_growth_yoy",
    "roe",
    "roce",
    "debt_equity",
)


# --------------------------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class Metric:
    name: str
    value: float | None
    unit: str  # INR | INR/share | % | x | pp | shares
    source: str | None
    period_end: date | None
    note: str | None = None


@dataclass(slots=True)
class FundamentalMetrics:
    symbol: str | None
    basis: str | None  # consolidated | standalone
    is_bank: bool
    latest_period_end: date | None
    price: float | None
    metrics: dict[str, Metric] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def value(self, name: str) -> float | None:
        m = self.metrics.get(name)
        return None if m is None else m.value


@dataclass(slots=True)
class ComponentScore:
    name: str
    value: float | None  # the input value scored
    score: float | None  # 0..100
    reason: str


@dataclass(slots=True)
class CategoryScore:
    name: str
    weight: float  # nominal weight
    effective_weight: float  # re-normalised weight actually applied (0 if excluded)
    score: float | None
    components: list[ComponentScore] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FundamentalScore:
    score: float | None
    completeness: float
    breakdown: dict[str, CategoryScore]
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------------------


def _pat(st: FinancialStatement) -> float | None:
    return st.pat_owners if st.pat_owners is not None else st.pat


def _eps(st: FinancialStatement) -> float | None:
    return st.eps_basic if st.eps_basic is not None else st.eps_diluted


def _consecutive(sts: list[FinancialStatement]) -> bool:
    """``sts`` sorted newest first: every gap is one quarter."""
    lo, hi = QUARTER_GAP_DAYS
    return all(lo <= (a.period_end - b.period_end).days <= hi for a, b in pairwise(sts))


def _sum(vals: list[float | None]) -> float | None:
    return None if any(v is None for v in vals) else float(sum(vals))  # type: ignore[arg-type]


def _growth_pct(cur: float | None, prior: float | None) -> tuple[float | None, str | None]:
    if cur is None or prior is None:
        return None, "missing current or prior TTM value"
    if prior <= 0:
        return None, f"prior TTM value {prior:,.2f} is not positive; growth % undefined"
    return (cur - prior) / prior * 100.0, None


def compute_metrics(
    statements: Iterable[FinancialStatement],
    price: float | None,
    shares_outstanding: float | None = None,
    shareholding: ShareholdingRecord | Iterable[ShareholdingRecord] | None = None,
) -> FundamentalMetrics:
    """Derive TTM and valuation metrics from quarterly statements (+ optional shareholding).

    TTM = sum of the latest 4 consecutive quarters (else None). YoY growth = TTM vs prior TTM (needs 8
    consecutive quarters). P/E = price / TTM EPS (None if EPS <= 0). Shares outstanding: caller value,
    else paid-up capital / face value of the latest statement."""
    notes: list[str] = []
    all_sts = list(statements)
    qs: list[FinancialStatement] = []
    for s in all_sts:
        if s.period_start is not None and (s.period_end - s.period_start).days > MAX_QUARTER_SPAN_DAYS:
            continue
        qs.append(s)
    if len(qs) != len(all_sts):
        notes.append(f"{len(all_sts) - len(qs)} non-quarterly statement(s) ignored")
    cons = [s for s in qs if s.consolidated]
    chosen = cons if cons else [s for s in qs if not s.consolidated]
    basis = ("consolidated" if cons else "standalone") if chosen else None
    if cons and len(cons) != len(qs):
        notes.append("standalone statements ignored (consolidated preferred; bases never mixed)")
    by_end: dict[date, FinancialStatement] = {}
    for s in chosen:
        by_end[s.period_end] = s
    sts = [by_end[k] for k in sorted(by_end, reverse=True)]  # newest first
    latest = sts[0] if sts else None
    latest_end = latest.period_end if latest else None
    is_bank = bool(latest.is_bank) if latest else False
    symbol = latest.symbol if latest else None

    out = FundamentalMetrics(symbol, basis, is_bank, latest_end, price, notes=notes)
    M = out.metrics

    def put(name: str, value: float | None, unit: str, source: str | None, pe: date | None, note: str | None = None):
        M[name] = Metric(name, None if value is None else round(float(value), 6), unit, source if value is not None
                         else None, pe, note)  # fmt: skip

    # ---- TTM
    last4 = sts[:4]
    have4 = len(last4) == 4 and _consecutive(last4)
    ttm_note = None
    if not have4:
        ttm_note = (
            f"TTM requires 4 consecutive quarters; have {len(last4)}"
            if len(last4) < 4
            else "TTM requires 4 consecutive quarters; latest 4 are not consecutive"
        )
    ttm: dict[str, float | None] = {}
    getters = {
        "revenue": lambda s: s.revenue,
        "ebitda": lambda s: s.ebitda,
        "pat": _pat,
        "eps": _eps,
        "ebit": lambda s: s.ebit,
        "finance_costs": lambda s: s.finance_costs,
    }
    for k, fn in getters.items():
        ttm[k] = _sum([fn(s) for s in last4]) if have4 else None
    for k, unit in (("revenue", "INR"), ("ebitda", "INR"), ("pat", "INR"), ("eps", "INR/share")):
        note = ttm_note
        if have4 and ttm[k] is None:
            note = f"one or more of the last 4 quarters did not report {k}"
        put(f"ttm_{k}", ttm[k], unit, SOURCE_XBRL, latest_end, note)
    if is_bank:
        M["ttm_ebitda"].note = (M["ttm_ebitda"].note or "") + " (EBITDA not meaningful for banks)"

    # ---- growth (TTM vs prior TTM)
    prev4 = sts[4:8]
    have8 = have4 and len(prev4) == 4 and _consecutive(sts[:8])
    g_note = None if have8 else f"YoY TTM growth needs 8 consecutive quarters; have {len(sts[:8])}"
    for name, key in (("revenue_growth_yoy", "revenue"), ("earnings_growth_yoy", "pat"), ("eps_growth_yoy", "eps")):
        if not have8:
            put(name, None, "%", None, latest_end, g_note)
            continue
        prior = _sum([getters[key](s) for s in prev4])
        val, why = _growth_pct(ttm[key], prior)
        put(name, val, "%", SOURCE_XBRL, latest_end, why)

    # ---- margins (TTM)
    rev = ttm["revenue"]
    for name, key in (("ebitda_margin", "ebitda"), ("pat_margin", "pat")):
        if ttm[key] is None or rev is None or rev <= 0:
            put(name, None, "%", None, latest_end, ttm_note or f"needs TTM {key} and positive TTM revenue")
        else:
            put(name, ttm[key] / rev * 100.0, "%", SOURCE_XBRL, latest_end)

    # ---- shares, market cap, valuation
    if shares_outstanding is not None:
        put("shares_outstanding", shares_outstanding, "shares", SOURCE_INPUT, None)
    elif latest is not None and latest.paid_up_capital and latest.face_value:
        put("shares_outstanding", latest.paid_up_capital / latest.face_value, "shares", SOURCE_XBRL, latest_end,
            "paid-up equity capital / face value")  # fmt: skip
    else:
        put("shares_outstanding", None, "shares", None, latest_end, "no share count: needs paid-up capital & face value")
    shares = M["shares_outstanding"].value
    if price is None:
        put("market_cap", None, "INR", None, None, "price unavailable")
    elif shares is None:
        put("market_cap", None, "INR", None, None, "shares outstanding unavailable")
    else:
        put("market_cap", price * shares, "INR", SOURCE_XBRL, latest_end, "price × shares outstanding")

    eps = ttm["eps"]
    if price is None:
        put("pe", None, "x", None, latest_end, "price unavailable")
    elif eps is None:
        put("pe", None, "x", None, latest_end, ttm_note or "TTM EPS unavailable")
    elif eps <= 0:
        put("pe", None, "x", None, latest_end, f"loss-making (TTM EPS {eps:.2f}); P/E undefined")
    else:
        put("pe", price / eps, "x", SOURCE_XBRL, latest_end, f"price {price:.2f} / TTM EPS {eps:.2f}")

    pe = M["pe"].value
    eg = M["eps_growth_yoy"].value
    if pe is None or eg is None:
        put("peg", None, "x", None, latest_end, "needs P/E and TTM EPS growth")
    elif eg <= 0:
        put("peg", None, "x", None, latest_end, f"EPS growth {eg:.1f}% not positive; PEG undefined")
    else:
        put("peg", pe / eg, "x", SOURCE_XBRL, latest_end, f"P/E {pe:.2f} / EPS growth {eg:.1f}%")

    put("ev_ebitda", None, "x", None, latest_end, "net debt unknown (no balance sheet in quarterly P&L filings)")
    for name, unit in (("pb", "x"), ("roe", "%"), ("roce", "%"), ("fcf", "INR"), ("ocf", "INR"), ("dividend_yield", "%")):
        put(name, None, unit, None, latest_end, NOT_IN_FEED)

    # ---- reported ratios
    if latest is not None and latest.debt_equity is not None:
        put("debt_equity", latest.debt_equity, "x", SOURCE_XBRL_REPORTED, latest_end, "DebtEquityRatio as reported")
    else:
        put("debt_equity", None, "x", None, latest_end, NOT_IN_FEED)
    if latest is not None and latest.interest_coverage is not None:
        put("interest_coverage", latest.interest_coverage, "x", SOURCE_XBRL_REPORTED, latest_end,
            "InterestServiceCoverageRatio as reported")  # fmt: skip
    elif is_bank:
        put("interest_coverage", None, "x", None, latest_end, "not meaningful for banks (interest is the core cost)")
    elif ttm["ebit"] is not None and ttm["finance_costs"] is not None and ttm["finance_costs"] > 0:
        put("interest_coverage", ttm["ebit"] / ttm["finance_costs"], "x", SOURCE_XBRL, latest_end,
            "TTM EBIT / TTM finance costs")  # fmt: skip
    else:
        put("interest_coverage", None, "x", None, latest_end,
            ttm_note or "no reported ratio and finance costs are zero/unavailable")  # fmt: skip

    # ---- shareholding
    if shareholding is None:
        shp: list[ShareholdingRecord] = []
    elif isinstance(shareholding, ShareholdingRecord):
        shp = [shareholding]
    else:
        shp = list(shareholding)
    shp = sorted(shp, key=lambda r: r.period_end)
    last = shp[-1] if shp else None
    if last is None:
        for name, unit in (("promoter_holding", "%"), ("promoter_pledge", "%"),
                           ("promoter_change_qoq", "pp"), ("promoter_change_yoy", "pp")):  # fmt: skip
            put(name, None, unit, None, None, "no shareholding data provided")
    else:
        put("promoter_holding", last.promoter_pct, "%", SOURCE_SHP, last.period_end,
            None if last.promoter_pct is not None else "promoter % not reported")  # fmt: skip
        put("promoter_pledge", last.promoter_pledged_pct, "%", SOURCE_SHP, last.period_end,
            None if last.promoter_pledged_pct is not None else "pledge % not reported")  # fmt: skip
        prev = shp[-2] if len(shp) > 1 else None
        if prev is not None and prev.promoter_pct is not None and last.promoter_pct is not None:
            put("promoter_change_qoq", last.promoter_pct - prev.promoter_pct, "pp", SOURCE_SHP, last.period_end,
                f"vs {prev.period_end.isoformat()}")  # fmt: skip
        else:
            put("promoter_change_qoq", None, "pp", None, last.period_end, "no previous shareholding record")
        ya = [r for r in shp[:-1] if abs((last.period_end - r.period_end).days - 365) <= SHP_YOY_TOLERANCE_DAYS]
        if ya and ya[-1].promoter_pct is not None and last.promoter_pct is not None:
            put("promoter_change_yoy", last.promoter_pct - ya[-1].promoter_pct, "pp", SOURCE_SHP, last.period_end,
                f"vs {ya[-1].period_end.isoformat()}")  # fmt: skip
        else:
            put("promoter_change_yoy", None, "pp", None, last.period_end, "no shareholding record ~1 year earlier")

    out.missing = [f"{m.name}: {m.note}" for m in M.values() if m.value is None]
    return out


# --------------------------------------------------------------------------------------------
# Score
# --------------------------------------------------------------------------------------------


def _curve(x: float, curve: tuple[list[float], list[float]]) -> float:
    xs, ys = curve
    return round(float(np.interp(x, xs, ys)), 2)


def _metric_value(metrics: FundamentalMetrics | Mapping[str, Any], name: str) -> float | None:
    if isinstance(metrics, FundamentalMetrics):
        return metrics.value(name)
    v = metrics.get(name)
    if isinstance(v, Metric):
        return v.value
    if isinstance(v, Mapping):
        return v.get("value")
    return v


def _components(
    metrics: FundamentalMetrics, sector: Mapping[str, Any], history_pe: list[float] | None
) -> dict[str, ComponentScore]:
    """Score every available component 0..100. Absent components are omitted (reason via `skipped`)."""
    v = metrics.value
    c: dict[str, ComponentScore] = {}

    def add(name: str, value: float | None, score: float | None, reason: str) -> None:
        c[name] = ComponentScore(name, None if value is None else round(value, 4), score, reason)

    if (x := v("revenue_growth_yoy")) is not None:
        add("revenue_growth_yoy", x, _curve(x, CURVE_REVENUE_GROWTH), f"TTM revenue growth {x:+.1f}% YoY")
    if (x := v("earnings_growth_yoy")) is not None:
        add("earnings_growth_yoy", x, _curve(x, CURVE_EARNINGS_GROWTH), f"TTM PAT growth {x:+.1f}% YoY")

    for name, abs_curve in (("ebitda_margin", CURVE_EBITDA_MARGIN), ("pat_margin", CURVE_PAT_MARGIN)):
        if name == "ebitda_margin" and metrics.is_bank:
            continue
        if (x := v(name)) is None:
            continue
        med = sector.get(name)
        if med is not None:
            add(name, x, _curve(x - med, CURVE_MARGIN_VS_SECTOR_PP),
                f"TTM {name.replace('_', ' ')} {x:.1f}% vs sector median {med:.1f}% ({x - med:+.1f} pp)")  # fmt: skip
        else:
            add(name, x, _curve(x, abs_curve), f"TTM {name.replace('_', ' ')} {x:.1f}% (absolute bands; no sector median)")
    for name in ("roe", "roce"):
        if (x := v(name)) is not None:
            add(name, x, _curve(x, CURVE_RETURN_RATIO), f"{name.upper()} {x:.1f}%")

    if (x := v("debt_equity")) is not None and not metrics.is_bank:
        add("debt_equity", x, _curve(x, CURVE_DEBT_EQUITY), f"debt/equity {x:.2f}×")
    if (x := v("interest_coverage")) is not None:
        add("interest_coverage", x, _curve(x, CURVE_INTEREST_COVERAGE), f"interest coverage {x:.2f}×")
    if (x := v("promoter_pledge")) is not None:
        add("promoter_pledge", x, _curve(x, CURVE_PLEDGE), f"promoter pledge {x:.1f}%")

    pe = v("pe")
    if pe is not None:
        med = sector.get("pe")
        if med:
            ratio = pe / med
            add("pe_vs_sector", pe, _curve(ratio, CURVE_PE_VS_SECTOR),
                f"P/E {pe:.1f} vs sector median {med:.1f} ({ratio:.2f}×)")  # fmt: skip
        hist = [h for h in (history_pe or []) if h is not None and h > 0]
        if len(hist) >= MIN_PE_HISTORY:
            pct_below = sum(1 for h in hist if h < pe) / len(hist) * 100.0
            add("pe_vs_history", pe, round(100.0 - pct_below, 2),
                f"P/E {pe:.1f} above {pct_below:.0f}% of own history ({len(hist)} obs)")  # fmt: skip
    if (x := v("peg")) is not None:
        add("peg", x, _curve(x, CURVE_PEG), f"PEG {x:.2f}")

    if (x := v("promoter_holding")) is not None:
        if x == 0:
            add("promoter_holding", x, NO_PROMOTER_SCORE, "no promoter group (professionally managed): neutral")
        else:
            add("promoter_holding", x, _curve(x, CURVE_PROMOTER_HOLDING), f"promoter holding {x:.1f}%")
    trend = v("promoter_change_yoy")
    label = "YoY"
    if trend is None:
        trend, label = v("promoter_change_qoq"), "QoQ"
    if trend is not None:
        add("promoter_trend", trend, _curve(trend, CURVE_PROMOTER_TREND_PP), f"promoter holding {trend:+.2f} pp {label}")
    return c


_SKIP_REASONS = {
    "pe_vs_sector": "needs positive P/E and a sector median P/E",
    "pe_vs_history": f"needs positive P/E and >= {MIN_PE_HISTORY} own-history P/E observations",
    "promoter_trend": "needs at least two shareholding records",
}


def fundamental_score(
    metrics: FundamentalMetrics,
    sector_medians: Mapping[str, float] | None = None,
    history_pe: list[float] | None = None,
) -> FundamentalScore:
    """0-100 score. Category score = mean of available component scores; overall = weighted mean over
    categories with data (weights re-normalised). completeness = Σ weight of components with data,
    where each category's weight is split equally among its components. completeness < MIN_COMPLETENESS
    -> score None."""
    sector = dict(sector_medians or {})
    comps = _components(metrics, sector, history_pe)
    breakdown: dict[str, CategoryScore] = {}
    missing: list[str] = []
    reasons: list[str] = []
    notes: list[str] = []
    completeness = 0.0
    if metrics.is_bank:
        notes.append("bank: EBITDA margin and debt/equity excluded (not meaningful for lenders)")
    if sector_medians is None:
        notes.append("no sector medians supplied: margins scored on absolute bands, P/E vs sector skipped")

    for cat, weight in CATEGORY_WEIGHTS.items():
        names = CATEGORY_COMPONENTS[cat]
        present = [comps[n] for n in names if n in comps]
        cs = CategoryScore(cat, weight, 0.0, None, present)
        for n in names:
            if n not in comps:
                why = _SKIP_REASONS.get(n)
                m = metrics.metrics.get(n)
                if m is not None and m.note:
                    why = m.note
                if metrics.is_bank and n in ("ebitda_margin", "debt_equity"):
                    why = "not meaningful for banks"
                cs.missing.append(f"{n}: {why or 'unavailable'}")
        completeness += weight * len(present) / len(names)
        if present:
            cs.score = round(sum(p.score for p in present) / len(present), 2)  # type: ignore[misc]
        else:
            missing.append(f"{cat}: no data")
        missing.extend(f"{cat}.{x}" for x in cs.missing)
        breakdown[cat] = cs

    avail = {k: c for k, c in breakdown.items() if c.score is not None}
    wsum = sum(c.weight for c in avail.values())
    for c in avail.values():
        c.effective_weight = round(c.weight / wsum, 4) if wsum else 0.0
    completeness = round(completeness, 4)

    for c in breakdown.values():
        if c.score is None:
            continue
        reasons.append(
            f"{c.name}: {c.score:.0f}/100 (weight {c.weight:.2f} -> {c.effective_weight:.2f}) — "
            + "; ".join(f"{p.reason} -> {p.score:.0f}" for p in c.components)
        )

    if completeness < MIN_COMPLETENESS or not avail:
        missing.insert(0, f"insufficient fundamental data (completeness {completeness:.2f} < {MIN_COMPLETENESS})")
        return FundamentalScore(None, completeness, breakdown, reasons, missing, notes)
    score = sum(c.score * c.effective_weight for c in avail.values())  # type: ignore[operator]
    reasons.insert(0, f"fundamental score {score:.1f}/100 from {len(avail)} of {len(breakdown)} categories "
                      f"(completeness {completeness:.0%})")  # fmt: skip
    return FundamentalScore(round(score, 2), completeness, breakdown, reasons, missing, notes)


def sector_relative(
    metrics_by_symbol: Mapping[str, FundamentalMetrics | Mapping[str, Any]],
    sector_by_symbol: Mapping[str, str | None],
) -> dict[str, dict[str, float]]:
    """Median of SECTOR_MEDIAN_METRICS per sector (only metrics with >= MIN_SECTOR_PEERS values; P/E only
    positive values). Symbols without a sector are skipped."""
    groups: dict[str, dict[str, list[float]]] = {}
    for sym, m in metrics_by_symbol.items():
        sector = sector_by_symbol.get(sym)
        if not sector:
            continue
        g = groups.setdefault(sector, {k: [] for k in SECTOR_MEDIAN_METRICS})
        for k in SECTOR_MEDIAN_METRICS:
            val = _metric_value(m, k)
            if val is None:
                continue
            if k == "pe" and val <= 0:
                continue
            g[k].append(float(val))
    out: dict[str, dict[str, float]] = {}
    for sector, g in groups.items():
        meds = {k: round(statistics.median(vals), 4) for k, vals in g.items() if len(vals) >= MIN_SECTOR_PEERS}
        out[sector] = meds
    return out

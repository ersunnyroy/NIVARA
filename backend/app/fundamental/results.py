"""Quarterly results analysis (deterministic, no LLM).

Rules:

* Consolidated numbers are preferred. A comparison NEVER mixes consolidated and standalone figures:
  history points on a different basis from ``current`` are dropped (and counted in ``notes``).
* Values are absolute INR (as parsed from NSE XBRL). Display converts to ₹ crore (1 cr = 1e7).
* Growth on a negative or zero base is undefined -- we describe it ("turned profitable",
  "loss widened", ...) instead of printing a misleading %.
* Analyst estimates and cash-flow data are not in our feed -> ``None`` with a note. Never invented.

The classification is a transparent points table (constants below); the per-rule breakdown is returned.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.data.types import FinancialStatement

# --------------------------------------------------------------------------------------------
# Thresholds (tunable)
# --------------------------------------------------------------------------------------------

#: Window (days before current period_end) in which the previous quarter's period_end must fall.
QOQ_WINDOW_DAYS = (75, 105)
#: Tolerance (days) when matching the same quarter last year (period_end − 1 year).
YOY_MATCH_TOLERANCE_DAYS = 5

#: Other income share of PBT (%) above which (and rising) PAT growth is flagged as other-income driven.
OTHER_INCOME_SHARE_FLAG_PCT = 30.0

#: Revenue growth bands (%, applied to YoY; QoQ only if YoY unavailable): (min_growth, points), first match.
REVENUE_GROWTH_POINTS: list[tuple[float, int]] = [(20.0, 2), (10.0, 1), (0.0, 0), (-10.0, -1)]
REVENUE_GROWTH_FLOOR_POINTS = -2  # below the last band
#: PAT growth bands (%), same mechanics.
PAT_GROWTH_POINTS: list[tuple[float, int]] = [(25.0, 2), (10.0, 1), (0.0, 0), (-15.0, -1)]
PAT_GROWTH_FLOOR_POINTS = -2
#: PAT sign-change descriptions -> points (growth % undefined for these).
PAT_STATE_POINTS: dict[str, int] = {
    "turned profitable": 2,
    "loss narrowed": 1,
    "broke even": 0,
    "loss widened": -2,
    "loss unchanged": -1,
    "swung to loss": -2,
}
#: EBITDA margin YoY change (bps): >= +X -> +1, <= −X -> −1.
MARGIN_CHANGE_BPS = 150.0
MARGIN_POINTS = 1
#: Extra QoQ PAT momentum row (only when the YoY rows are used): >= +X% -> +1, <= −X% -> −1.
QOQ_PAT_MOMENTUM_PCT = 10.0
QOQ_PAT_MOMENTUM_POINTS = 1
#: Other-income flag penalty.
OTHER_INCOME_FLAG_POINTS = -1

#: Total points -> classification (first match, evaluated top-down).
CLASSIFICATION_BANDS: list[tuple[int, str]] = [
    (4, "VERY POSITIVE"),
    (2, "POSITIVE"),
    (-1, "NEUTRAL"),
    (-3, "NEGATIVE"),
]
CLASSIFICATION_FLOOR = "VERY NEGATIVE"

NO_ESTIMATES_NOTE = "No licensed analyst-estimate source configured"
NO_CASHFLOW_NOTE = "Quarterly filings in our feed do not include a cash-flow statement; cash-flow quality not assessed"
ONE_OFF_NOTE = (
    "Exceptional/one-off items are not separately captured in the filing feed; reported PAT may include them"
)

CRORE = 1e7
METRICS = ("revenue", "ebitda", "pat", "eps")


# --------------------------------------------------------------------------------------------
# Data points
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class ResultPoint:
    period_end: date
    revenue: float | None = None
    ebitda: float | None = None
    pat: float | None = None  # attributable to owners when reported, else total PAT
    eps: float | None = None  # basic EPS (diluted if basic missing)
    other_income: float | None = None
    finance_costs: float | None = None
    depreciation: float | None = None
    pbt: float | None = None
    consolidated: bool | None = None
    is_bank: bool = False
    symbol: str | None = None
    pat_source: str | None = None  # "pat_owners" | "pat"


def from_statement(st: FinancialStatement) -> ResultPoint:
    pat, src = (st.pat_owners, "pat_owners") if st.pat_owners is not None else (st.pat, "pat")
    return ResultPoint(
        period_end=st.period_end,
        revenue=st.revenue,
        ebitda=st.ebitda,
        pat=pat,
        eps=st.eps_basic if st.eps_basic is not None else st.eps_diluted,
        other_income=st.other_income,
        finance_costs=st.finance_costs,
        depreciation=st.depreciation,
        pbt=st.pbt,
        consolidated=st.consolidated,
        is_bank=st.is_bank,
        symbol=st.symbol,
        pat_source=src if pat is not None else None,
    )


def select_basis(statements: list[FinancialStatement]) -> tuple[list[ResultPoint], str, list[str]]:
    """Prefer consolidated: if any consolidated statements exist only those are used, else standalone.
    Returns (points sorted by period_end ascending, basis label, notes). One point per period_end."""
    notes: list[str] = []
    cons = [s for s in statements if s.consolidated]
    chosen = cons if cons else [s for s in statements if not s.consolidated]
    basis = "consolidated" if cons else "standalone"
    if cons and len(cons) != len(statements):
        notes.append(f"{len(statements) - len(cons)} standalone statement(s) ignored (consolidated preferred)")
    by_end: dict[date, ResultPoint] = {}
    for s in chosen:
        by_end[s.period_end] = from_statement(s)  # later duplicates override earlier
    return [by_end[k] for k in sorted(by_end)], basis, notes


# --------------------------------------------------------------------------------------------
# Output dataclasses
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class Growth:
    metric: str
    current: float | None
    base: float | None
    base_period_end: date | None
    pct: float | None
    description: str  # e.g. "+12.3%", "turned profitable", "missing base"


@dataclass(slots=True)
class MarginInfo:
    metric: str  # ebitda_margin | pat_margin
    current_pct: float | None
    prev_quarter_pct: float | None
    year_ago_pct: float | None
    change_bps_qoq: float | None
    change_bps_yoy: float | None


@dataclass(slots=True)
class ResultFlag:
    code: str
    severity: str  # info | warning
    message: str


@dataclass(slots=True)
class PointItem:
    rule: str
    input: str
    points: int


@dataclass(slots=True)
class ResultAnalysis:
    symbol: str | None
    period_end: date
    basis: str | None  # consolidated | standalone | None (unknown)
    fiscal_quarter: str
    prev_quarter_period_end: date | None
    year_ago_period_end: date | None
    qoq: dict[str, Growth]
    yoy: dict[str, Growth]
    margins: dict[str, MarginInfo]
    other_income_share_pct: float | None
    flags: list[ResultFlag]
    points: list[PointItem]
    total_points: int | None
    classification: str | None  # VERY POSITIVE | POSITIVE | NEUTRAL | NEGATIVE | VERY NEGATIVE | None
    vs_estimates: Any | None
    cash_flow_quality: Any | None
    summary_text: str
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------


def fiscal_quarter_label(period_end: date) -> str:
    """Indian FY quarter label: Apr–Jun = Q1. 2026-09-30 -> 'Q2 FY27'."""
    m = period_end.month
    fy = period_end.year + 1 if m >= 4 else period_end.year
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(m)
    if q is None:  # non-standard period end: approximate by FY month index
        q = ((m - 4) % 12) // 3 + 1
    return f"Q{q} FY{str(fy)[-2:]}"


def _year_ago(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # Feb 29
        return date(d.year - 1, 2, calendar.monthrange(d.year - 1, 2)[1])


def find_prev_quarter(current: ResultPoint, history: list[ResultPoint]) -> ResultPoint | None:
    lo, hi = QOQ_WINDOW_DAYS
    cands = [h for h in history if lo <= (current.period_end - h.period_end).days <= hi]
    return max(cands, key=lambda h: h.period_end) if cands else None


def find_year_ago(current: ResultPoint, history: list[ResultPoint]) -> ResultPoint | None:
    target = _year_ago(current.period_end)
    cands = [h for h in history if abs((h.period_end - target).days) <= YOY_MATCH_TOLERANCE_DAYS]
    return min(cands, key=lambda h: abs((h.period_end - target).days)) if cands else None


def growth(metric: str, cur: float | None, base: float | None, base_end: date | None) -> Growth:
    """% growth on a positive base; descriptive wording for zero/negative bases or sign flips."""
    if cur is None or base is None:
        what = "current value" if cur is None else "base value"
        return Growth(metric, cur, base, base_end, None, f"missing {what}")
    if base > 0:
        if cur < 0:
            return Growth(metric, cur, base, base_end, None, "swung to loss")
        pct = (cur - base) / base * 100.0
        return Growth(metric, cur, base, base_end, round(pct, 2), f"{pct:+.1f}%")
    if base == 0:
        return Growth(metric, cur, base, base_end, None, "base is zero; growth undefined")
    # negative base
    if cur > 0:
        desc = "turned profitable"
    elif cur == 0:
        desc = "broke even"
    elif cur < base:
        desc = "loss widened"
    elif cur > base:
        desc = "loss narrowed"
    else:
        desc = "loss unchanged"
    return Growth(metric, cur, base, base_end, None, desc)


def _margin(num: float | None, rev: float | None) -> float | None:
    if num is None or rev is None or rev <= 0:
        return None
    return num / rev * 100.0


def _other_income_share(p: ResultPoint | None) -> float | None:
    if p is None or p.other_income is None or p.pbt is None or p.pbt <= 0:
        return None
    return p.other_income / p.pbt * 100.0


def _band_points(value: float, bands: list[tuple[float, int]], floor: int) -> int:
    for threshold, pts in bands:
        if value >= threshold:
            return pts
    return floor


def classify_points(total: int) -> str:
    for threshold, label in CLASSIFICATION_BANDS:
        if total >= threshold:
            return label
    return CLASSIFICATION_FLOOR


def _cr(x: float | None) -> str:
    return "n/a" if x is None else f"₹{x / CRORE:,.2f} cr"


# --------------------------------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------------------------------


def analyze_result(current: ResultPoint, history: list[ResultPoint]) -> ResultAnalysis:
    """Analyse one quarter against its history (QoQ, YoY, margins, flags, classification)."""
    notes: list[str] = [ONE_OFF_NOTE]
    missing: list[str] = []
    reasons: list[str] = []

    hist = [h for h in history if h.period_end != current.period_end]
    if current.consolidated is not None:
        same = [h for h in hist if h.consolidated is None or h.consolidated == current.consolidated]
        if len(same) != len(hist):
            notes.append(
                f"{len(hist) - len(same)} history point(s) on a different consolidation basis excluded "
                "(never mix consolidated and standalone)"
            )
        hist = same
    basis = None if current.consolidated is None else ("consolidated" if current.consolidated else "standalone")

    prev = find_prev_quarter(current, hist)
    ya = find_year_ago(current, hist)
    if prev is None:
        missing.append("previous quarter not in history; QoQ unavailable")
    if ya is None:
        missing.append("same quarter last year not in history; YoY unavailable")

    qoq = {m: growth(m, getattr(current, m), getattr(prev, m) if prev else None, prev.period_end if prev else None)
           for m in METRICS}  # fmt: skip
    yoy = {m: growth(m, getattr(current, m), getattr(ya, m) if ya else None, ya.period_end if ya else None)
           for m in METRICS}  # fmt: skip
    if current.is_bank:
        notes.append("bank: EBITDA is not a meaningful measure for lenders; EBITDA-based rows are informational only")

    margins: dict[str, MarginInfo] = {}
    for name, attr in (("ebitda_margin", "ebitda"), ("pat_margin", "pat")):
        cur_m = _margin(getattr(current, attr), current.revenue)
        prev_m = _margin(getattr(prev, attr), prev.revenue) if prev else None
        ya_m = _margin(getattr(ya, attr), ya.revenue) if ya else None
        margins[name] = MarginInfo(
            metric=name,
            current_pct=None if cur_m is None else round(cur_m, 2),
            prev_quarter_pct=None if prev_m is None else round(prev_m, 2),
            year_ago_pct=None if ya_m is None else round(ya_m, 2),
            change_bps_qoq=None if cur_m is None or prev_m is None else round((cur_m - prev_m) * 100.0, 1),
            change_bps_yoy=None if cur_m is None or ya_m is None else round((cur_m - ya_m) * 100.0, 1),
        )
        if cur_m is None:
            missing.append(f"{name} unavailable (needs {attr} and positive revenue)")

    # ---- flags
    flags: list[ResultFlag] = []
    oi_share = _other_income_share(current)
    base_for_share = ya if ya is not None else prev
    base_share = _other_income_share(base_for_share)
    if oi_share is not None and oi_share > OTHER_INCOME_SHARE_FLAG_PCT:
        rising = base_share is not None and oi_share > base_share
        if rising:
            flags.append(
                ResultFlag(
                    "other_income_driven",
                    "warning",
                    f"Other income is {oi_share:.1f}% of PBT (up from {base_share:.1f}%, "
                    f"> {OTHER_INCOME_SHARE_FLAG_PCT:.0f}%): profit growth leans on non-operating income",
                )
            )
        else:
            flags.append(
                ResultFlag(
                    "high_other_income",
                    "info",
                    f"Other income is {oi_share:.1f}% of PBT (> {OTHER_INCOME_SHARE_FLAG_PCT:.0f}%)"
                    + ("" if base_share is not None else "; trend unknown (no comparable base)"),
                )
            )
    if current.pat is not None and current.pat < 0:
        flags.append(ResultFlag("loss_making", "warning", f"Net loss of {_cr(current.pat)} this quarter"))

    # ---- points table
    points: list[PointItem] = []
    use_yoy = yoy["revenue"].pct is not None or yoy["pat"].pct is not None or yoy["pat"].description in PAT_STATE_POINTS
    gset, gname = (yoy, "YoY") if use_yoy else (qoq, "QoQ")
    if not use_yoy:
        notes.append("YoY comparison unavailable; classification uses QoQ growth (seasonality risk)")

    rev_g = gset["revenue"]
    if rev_g.pct is not None:
        points.append(PointItem(f"revenue growth {gname}", rev_g.description,
                                _band_points(rev_g.pct, REVENUE_GROWTH_POINTS, REVENUE_GROWTH_FLOOR_POINTS)))  # fmt: skip
    pat_g = gset["pat"]
    if pat_g.pct is not None:
        points.append(PointItem(f"PAT growth {gname}", pat_g.description,
                                _band_points(pat_g.pct, PAT_GROWTH_POINTS, PAT_GROWTH_FLOOR_POINTS)))  # fmt: skip
    elif pat_g.description in PAT_STATE_POINTS:
        points.append(PointItem(f"PAT {gname}", pat_g.description, PAT_STATE_POINTS[pat_g.description]))

    em = margins["ebitda_margin"]
    m_change = em.change_bps_yoy if use_yoy else em.change_bps_qoq
    if m_change is not None and not current.is_bank:
        mp = MARGIN_POINTS if m_change >= MARGIN_CHANGE_BPS else (-MARGIN_POINTS if m_change <= -MARGIN_CHANGE_BPS else 0)
        points.append(PointItem(f"EBITDA margin change {gname}", f"{m_change:+.0f} bps", mp))

    if use_yoy and qoq["pat"].pct is not None:
        q = qoq["pat"].pct
        qp = (QOQ_PAT_MOMENTUM_POINTS if q >= QOQ_PAT_MOMENTUM_PCT
              else (-QOQ_PAT_MOMENTUM_POINTS if q <= -QOQ_PAT_MOMENTUM_PCT else 0))  # fmt: skip
        points.append(PointItem("PAT momentum QoQ", qoq["pat"].description, qp))

    if any(f.code == "other_income_driven" for f in flags):
        points.append(PointItem("other-income-driven profit", f"{oi_share:.1f}% of PBT", OTHER_INCOME_FLAG_POINTS))

    has_growth = any(p.rule.startswith(("revenue growth", "PAT")) for p in points)
    if has_growth:
        total: int | None = sum(p.points for p in points)
        classification: str | None = classify_points(total)
    else:
        total, classification = None, None
        missing.append("insufficient comparable history for classification (no revenue/PAT comparison)")

    for p in points:
        reasons.append(f"{p.rule}: {p.input} -> {p.points:+d}")
    if classification is not None:
        reasons.append(f"total {total:+d} points -> {classification}")
    for f in flags:
        reasons.append(f.message)

    notes.append(NO_ESTIMATES_NOTE)
    notes.append(NO_CASHFLOW_NOTE)

    label = fiscal_quarter_label(current.period_end)
    summary = _summary(current, label, basis, qoq, yoy, margins, flags, total, classification)

    return ResultAnalysis(
        symbol=current.symbol,
        period_end=current.period_end,
        basis=basis,
        fiscal_quarter=label,
        prev_quarter_period_end=prev.period_end if prev else None,
        year_ago_period_end=ya.period_end if ya else None,
        qoq=qoq,
        yoy=yoy,
        margins=margins,
        other_income_share_pct=None if oi_share is None else round(oi_share, 2),
        flags=flags,
        points=points,
        total_points=total,
        classification=classification,
        vs_estimates=None,
        cash_flow_quality=None,
        summary_text=summary,
        reasons=reasons,
        notes=notes,
        missing=missing,
    )


def _summary(
    cur: ResultPoint,
    label: str,
    basis: str | None,
    qoq: dict[str, Growth],
    yoy: dict[str, Growth],
    margins: dict[str, MarginInfo],
    flags: list[ResultFlag],
    total: int | None,
    classification: str | None,
) -> str:
    def g(m: str) -> str:
        return f"YoY {yoy[m].description}, QoQ {qoq[m].description}"

    head = f"{cur.symbol + ' ' if cur.symbol else ''}{label} (period ending {cur.period_end.isoformat()}"
    head += f", {basis})" if basis else ")"
    parts = [
        f"Revenue {_cr(cur.revenue)} ({g('revenue')})",
        f"EBITDA {_cr(cur.ebitda)} ({g('ebitda')})",
        f"PAT {_cr(cur.pat)} ({g('pat')})",
        f"EPS {'n/a' if cur.eps is None else f'₹{cur.eps:.2f}'} ({g('eps')})",
    ]
    for name, title in (("ebitda_margin", "EBITDA margin"), ("pat_margin", "PAT margin")):
        mi = margins[name]
        if mi.current_pct is not None:
            chg = "" if mi.change_bps_yoy is None else f", {mi.change_bps_yoy:+.0f} bps YoY"
            parts.append(f"{title} {mi.current_pct:.1f}%{chg}")
    text = f"{head}: " + "; ".join(parts) + "."
    if flags:
        text += " Flags: " + "; ".join(f.message for f in flags) + "."
    if classification is not None:
        text += f" Classification: {classification} ({total:+d} points)."
    else:
        text += " Classification: not assigned (insufficient comparable history)."
    return text

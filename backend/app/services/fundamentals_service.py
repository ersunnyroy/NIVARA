"""Point-in-time fundamentals: only filings broadcast at/before `as_of` are used."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import IST, ist_datetime
from app.data.types import FinancialStatement, ShareholdingRecord
from app.fundamental.results import analyze_result, select_basis
from app.fundamental.scoring import compute_metrics, fundamental_score
from app.models import FinancialResult, Shareholding


def _to_statement(r: FinancialResult, symbol: str) -> FinancialStatement:
    return FinancialStatement(
        symbol=symbol, period_start=r.period_start, period_end=r.period_end, consolidated=r.consolidated,
        is_bank=r.is_bank, revenue=r.revenue, other_income=r.other_income, total_income=r.total_income,
        total_expenses=r.total_expenses, finance_costs=r.finance_costs, depreciation=r.depreciation, pbt=r.pbt,
        tax=r.tax, pat=r.pat, pat_owners=r.pat_owners, eps_basic=r.eps_basic, eps_diluted=r.eps_diluted,
        paid_up_capital=r.paid_up_capital, face_value=r.face_value,
        # The DebtEquityRatio / InterestServiceCoverageRatio values companies tag in quarterly result XBRL are
        # inconsistent (verified: e.g. 0.004–0.04 for clearly leveraged companies), so they are not used.
        # Interest coverage is derived from filed EBIT and finance costs instead.
        debt_equity=None, interest_coverage=None,
    )


def statements_as_of(db: Session, stock_id: int, symbol: str, as_of: date) -> list[FinancialStatement]:
    cutoff = ist_datetime(as_of, 23, 59, 59)
    rows = db.scalars(select(FinancialResult).where(FinancialResult.stock_id == stock_id,
                                                    FinancialResult.period_type == "quarterly")
                      .order_by(FinancialResult.period_end)).all()
    # Point-in-time: a result is usable only once it was broadcast; unknown broadcast time → assume
    # 60 days after period end (regulatory deadline is 45 days for quarterly results).
    out = []
    for r in rows:
        if r.broadcast_at is not None:
            if r.broadcast_at.astimezone(IST) > cutoff:
                continue
        elif (as_of - r.period_end).days < 60:
            continue
        out.append(_to_statement(r, symbol))
    return out


def shareholding_as_of(db: Session, stock_id: int, symbol: str, as_of: date) -> list[ShareholdingRecord]:
    cutoff = ist_datetime(as_of, 23, 59, 59)
    rows = db.scalars(select(Shareholding).where(Shareholding.stock_id == stock_id)
                      .order_by(Shareholding.period_end.desc())).all()
    return [ShareholdingRecord(symbol=symbol, period_end=s.period_end, promoter_pct=s.promoter_pct,
                               public_pct=s.public_pct, broadcast_at=s.broadcast_at,
                               promoter_pledged_pct=s.promoter_pledged_pct, fii_pct=s.fii_pct, dii_pct=s.dii_pct,
                               mf_pct=s.mf_pct)
            for s in rows if (s.broadcast_at is None and (as_of - s.period_end).days >= 30)
            or (s.broadcast_at is not None and s.broadcast_at.astimezone(IST) <= cutoff)]


def fundamental_view(db: Session, stock_id: int, symbol: str, as_of: date, price: float | None,
                     sector_medians: dict | None = None) -> dict:
    sts = statements_as_of(db, stock_id, symbol, as_of)
    shp = shareholding_as_of(db, stock_id, symbol, as_of)
    if not sts:
        return {"score": None, "metrics": {}, "missing": ["No financial results ingested for this stock"],
                "reasons": [], "cautions": [], "result_analysis": None}
    metrics = compute_metrics(sts, price, shareholding=shp or None)
    fs = fundamental_score(metrics, sector_medians=sector_medians)
    points, basis, notes = select_basis(sts)
    analysis = None
    if points:
        analysis = analyze_result(points[-1], points[:-1])
    reasons = [r for r in fs.reasons if "weak" not in r.lower()][:4]
    cautions = [r for r in fs.reasons if any(w in r.lower() for w in ("weak", "decline", "high", "loss", "pledge"))][:3]
    if analysis and analysis.classification in ("NEGATIVE", "VERY NEGATIVE"):
        cautions.insert(0, f"Latest results ({analysis.fiscal_quarter}) classified {analysis.classification}")
    elif analysis and analysis.classification in ("POSITIVE", "VERY POSITIVE"):
        reasons.insert(0, f"Latest results ({analysis.fiscal_quarter}) classified {analysis.classification}")
    return {"score": fs.score, "completeness": fs.completeness, "metrics": {k: asdict(v) for k, v in metrics.metrics.items()},
            "breakdown": {k: asdict(v) for k, v in fs.breakdown.items()}, "missing": fs.missing + metrics.missing,
            "notes": notes + metrics.notes, "reasons": reasons, "cautions": cautions,
            "result_analysis": asdict(analysis) if analysis else None, "basis": basis}

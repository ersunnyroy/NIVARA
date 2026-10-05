from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

import pytest

from app.data.types import FinancialStatement
from app.fundamental.results import (
    NO_ESTIMATES_NOTE,
    ResultPoint,
    analyze_result,
    classify_points,
    fiscal_quarter_label,
    from_statement,
    growth,
    select_basis,
)

CR = 1e7


def pt(end: date, revenue, ebitda, pat, eps=None, other_income=0.0, pbt=None, consolidated=True):
    return ResultPoint(
        period_end=end,
        revenue=None if revenue is None else revenue * CR,
        ebitda=None if ebitda is None else ebitda * CR,
        pat=None if pat is None else pat * CR,
        eps=eps,
        other_income=other_income * CR,
        pbt=None if pbt is None else pbt * CR,
        consolidated=consolidated,
        symbol="ABC",
    )


Q_CUR = date(2026, 9, 30)
Q_PREV = date(2026, 6, 30)
Q_YA = date(2025, 9, 30)


def test_qoq_yoy_growth_and_margin_bps():
    cur = pt(Q_CUR, 1200, 240, 120, eps=12.0)
    prev = pt(Q_PREV, 1100, 209, 100, eps=10.0)
    ya = pt(Q_YA, 1000, 180, 80, eps=8.0)
    a = analyze_result(cur, [prev, ya])
    assert a.prev_quarter_period_end == Q_PREV and a.year_ago_period_end == Q_YA
    assert a.yoy["revenue"].pct == pytest.approx(20.0)
    assert a.qoq["revenue"].pct == pytest.approx(100 / 1100 * 100, abs=0.01)
    assert a.yoy["pat"].pct == pytest.approx(50.0)
    assert a.yoy["eps"].pct == pytest.approx(50.0)
    # EBITDA margin 20% vs 18% YoY -> +200 bps; vs 19% QoQ -> +100 bps
    assert a.margins["ebitda_margin"].change_bps_yoy == pytest.approx(200.0)
    assert a.margins["ebitda_margin"].change_bps_qoq == pytest.approx(100.0)
    # rev +20% (+2), PAT +50% (+2), margin +200bps (+1), QoQ PAT +20% (+1) = 6
    assert a.total_points == 6 and a.classification == "VERY POSITIVE"
    assert a.vs_estimates is None and NO_ESTIMATES_NOTE in a.notes
    assert a.cash_flow_quality is None
    assert "Revenue ₹1,200.00 cr (YoY +20.0%" in a.summary_text
    json.dumps(asdict(a), default=str)


def test_loss_to_profit_wording():
    g = growth("pat", 10.0, -5.0, Q_YA)
    assert g.pct is None and g.description == "turned profitable"
    assert growth("pat", -10.0, -5.0, Q_YA).description == "loss widened"
    assert growth("pat", -2.0, -5.0, Q_YA).description == "loss narrowed"
    assert growth("pat", -2.0, 5.0, Q_YA).description == "swung to loss"
    a = analyze_result(pt(Q_CUR, 1000, 100, 50), [pt(Q_YA, 900, 50, -20)])
    assert a.yoy["pat"].description == "turned profitable"
    assert any(p.input == "turned profitable" and p.points == 2 for p in a.points)
    assert "turned profitable" in a.summary_text


@pytest.mark.parametrize(
    ("total", "label"),
    [(6, "VERY POSITIVE"), (4, "VERY POSITIVE"), (3, "POSITIVE"), (2, "POSITIVE"), (1, "NEUTRAL"),
     (-1, "NEUTRAL"), (-2, "NEGATIVE"), (-3, "NEGATIVE"), (-4, "VERY NEGATIVE")],
)  # fmt: skip
def test_classification_boundaries(total, label):
    assert classify_points(total) == label


def test_negative_classification():
    cur = pt(Q_CUR, 850, 100, 40)
    ya = pt(Q_YA, 1000, 150, 80)
    a = analyze_result(cur, [ya])
    # rev -15% (-2), PAT -50% (-2), margin 11.76% vs 15% = -324 bps (-1) -> -5
    assert a.total_points == -5 and a.classification == "VERY NEGATIVE"


def test_other_income_flag():
    cur = pt(Q_CUR, 1000, 100, 90, other_income=50, pbt=120)  # 41.7% of PBT
    ya = pt(Q_YA, 1000, 100, 70, other_income=20, pbt=95)  # 21%
    a = analyze_result(cur, [ya])
    assert any(f.code == "other_income_driven" for f in a.flags)
    assert any(p.rule == "other-income-driven profit" and p.points == -1 for p in a.points)


def test_no_history_no_classification_and_no_mixing():
    cur = pt(Q_CUR, 1000, 100, 50)
    a = analyze_result(cur, [pt(Q_YA, 900, 90, 40, consolidated=False)])
    assert a.year_ago_period_end is None
    assert a.classification is None and a.total_points is None
    assert any("different consolidation basis" in n for n in a.notes)


def test_qoq_fallback_when_no_yoy():
    a = analyze_result(pt(Q_CUR, 1100, 110, 55), [pt(Q_PREV, 1000, 100, 50)])
    assert a.classification is not None
    assert any("QoQ" in n for n in a.notes)


def test_from_statement_and_basis():
    st = FinancialStatement(
        symbol="ABC", period_start=date(2026, 7, 1), period_end=Q_CUR, consolidated=True, is_bank=False,
        revenue=100.0, other_income=5.0, finance_costs=2.0, depreciation=3.0, pbt=20.0, pat=15.0,
        pat_owners=14.0, eps_basic=1.4,
    )  # fmt: skip
    p = from_statement(st)
    assert p.pat == 14.0 and p.pat_source == "pat_owners"
    assert p.ebitda == 20.0  # 20 + 2 + 3 - 5
    standalone = FinancialStatement("ABC", None, Q_CUR, False, False, revenue=90.0)
    pts, basis, notes = select_basis([st, standalone])
    assert basis == "consolidated" and len(pts) == 1 and notes
    assert fiscal_quarter_label(Q_CUR) == "Q2 FY27"
    assert fiscal_quarter_label(date(2027, 3, 31)) == "Q4 FY27"

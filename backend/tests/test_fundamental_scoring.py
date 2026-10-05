from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

import pytest

from app.data.types import FinancialStatement, ShareholdingRecord
from app.fundamental.scoring import (
    CATEGORY_WEIGHTS,
    MIN_COMPLETENESS,
    NOT_IN_FEED,
    FundamentalMetrics,
    Metric,
    compute_metrics,
    fundamental_score,
    sector_relative,
)

QUARTER_ENDS = [
    date(2024, 12, 31), date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30),
    date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30),
]  # fmt: skip


def st(end, revenue, pat, eps, consolidated=True, **kw):
    return FinancialStatement(
        symbol="ABC", period_start=None, period_end=end, consolidated=consolidated, is_bank=False,
        revenue=revenue, other_income=0.0, finance_costs=10.0, depreciation=20.0, pbt=pat * 1.25, pat=pat,
        eps_basic=eps, paid_up_capital=1_000_000.0, face_value=10.0, **kw,
    )  # fmt: skip


def eight_quarters():
    # prior 4: revenue 100 each, pat 10, eps 1 ; latest 4: revenue 120, pat 13, eps 1.3
    out = [st(e, 100.0, 10.0, 1.0) for e in QUARTER_ENDS[:4]]
    out += [st(e, 120.0, 13.0, 1.3) for e in QUARTER_ENDS[4:]]
    return out


def test_ttm_and_growth():
    m = compute_metrics(eight_quarters(), price=104.0)
    assert m.basis == "consolidated"
    assert m.value("ttm_revenue") == pytest.approx(480.0)
    assert m.value("ttm_eps") == pytest.approx(5.2)
    assert m.value("revenue_growth_yoy") == pytest.approx(20.0)
    assert m.value("earnings_growth_yoy") == pytest.approx(30.0)
    assert m.value("pe") == pytest.approx(20.0)
    assert m.value("peg") == pytest.approx(20.0 / 30.0)
    assert m.value("shares_outstanding") == pytest.approx(100_000.0)
    assert m.value("market_cap") == pytest.approx(104.0 * 100_000)
    assert m.metrics["pe"].source == "derived from NSE XBRL filings"
    assert m.metrics["roe"].value is None and m.metrics["roe"].note == NOT_IN_FEED
    assert m.metrics["ev_ebitda"].value is None
    # derived interest coverage = TTM EBIT / TTM finance costs = (4*(16.25+10)) / 40
    assert m.value("interest_coverage") == pytest.approx(105.0 / 40.0)
    json.dumps(asdict(m), default=str)


def test_ttm_needs_four_consecutive_quarters():
    m = compute_metrics(eight_quarters()[-3:], price=100.0)
    assert m.value("ttm_revenue") is None
    assert "4 consecutive quarters" in m.metrics["ttm_revenue"].note
    gap = [s for s in eight_quarters()[-5:] if s.period_end != date(2026, 3, 31)]  # hole in the middle
    m2 = compute_metrics(gap, price=100.0)
    assert m2.value("ttm_eps") is None
    assert m2.value("pe") is None


def test_pe_none_for_negative_eps():
    sts = [st(e, 100.0, -5.0, -0.5) for e in QUARTER_ENDS[4:]]
    m = compute_metrics(sts, price=50.0)
    assert m.value("pe") is None
    assert "loss-making" in m.metrics["pe"].note


def test_consolidated_preferred_not_mixed():
    sts = [*eight_quarters(), st(QUARTER_ENDS[-1], 999.0, 99.0, 9.9, consolidated=False)]
    m = compute_metrics(sts, price=100.0)
    assert m.value("ttm_revenue") == pytest.approx(480.0)


def test_shareholding_metrics():
    shp = [
        ShareholdingRecord("ABC", date(2025, 9, 30), 50.0, 50.0, None, promoter_pledged_pct=2.0),
        ShareholdingRecord("ABC", date(2026, 6, 30), 51.0, 49.0, None, promoter_pledged_pct=1.0),
        ShareholdingRecord("ABC", date(2026, 9, 30), 52.0, 48.0, None, promoter_pledged_pct=0.0),
    ]
    m = compute_metrics(eight_quarters(), price=104.0, shareholding=shp)
    assert m.value("promoter_holding") == 52.0
    assert m.value("promoter_change_qoq") == pytest.approx(1.0)
    assert m.value("promoter_change_yoy") == pytest.approx(2.0)


def _metrics(**values) -> FundamentalMetrics:
    fm = FundamentalMetrics("ABC", "consolidated", False, date(2026, 9, 30), 100.0)
    for k, v in values.items():
        fm.metrics[k] = Metric(k, v, "", "test", None)
    return fm


def test_completeness_and_renormalisation():
    # only growth category (2/2 components) + ownership (1/2) present
    fm = _metrics(revenue_growth_yoy=20.0, earnings_growth_yoy=25.0, promoter_holding=50.0)
    s = fundamental_score(fm)
    g, o = CATEGORY_WEIGHTS["growth"], CATEGORY_WEIGHTS["ownership"]
    assert s.completeness == pytest.approx(g + o / 2)
    # growth category = mean(85, 85) = 85 ; ownership = 80 ; weights re-normalised over g+o
    expected = (85.0 * g + 80.0 * o) / (g + o)
    assert s.score == pytest.approx(expected, abs=0.01)
    assert s.breakdown["growth"].effective_weight == pytest.approx(g / (g + o), abs=1e-4)
    assert s.breakdown["valuation"].score is None
    assert any(m.startswith("valuation: no data") for m in s.missing)


def test_insufficient_data_score_none():
    fm = _metrics(revenue_growth_yoy=20.0)  # 0.125 of weight
    s = fundamental_score(fm)
    assert s.completeness < MIN_COMPLETENESS
    assert s.score is None
    assert "insufficient fundamental data" in s.missing[0]


def test_valuation_with_sector_and_history():
    fm = _metrics(pe=20.0, peg=1.0, revenue_growth_yoy=10.0, earnings_growth_yoy=15.0)
    s = fundamental_score(fm, sector_medians={"pe": 25.0}, history_pe=[10, 12, 15, 18, 22, 25, 28, 30])
    names = [c.name for c in s.breakdown["valuation"].components]
    assert names == ["pe_vs_sector", "pe_vs_history", "peg"]
    assert s.score is not None


def test_sector_relative_medians():
    mk = lambda pe, pm: _metrics(pe=pe, pat_margin=pm)
    by_sym = {"A": mk(10.0, 5.0), "B": mk(20.0, 10.0), "C": mk(30.0, 15.0), "D": mk(-5.0, 1.0), "E": mk(15.0, 3.0)}
    sectors = {"A": "IT", "B": "IT", "C": "IT", "D": "IT", "E": "Pharma"}
    med = sector_relative(by_sym, sectors)
    assert med["IT"]["pe"] == 20.0  # negative PE excluded
    assert med["IT"]["pat_margin"] == pytest.approx(7.5)
    assert "pe" not in med["Pharma"]  # < MIN_SECTOR_PEERS

"""Tax-loss harvesting view tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from app.portfolio.lots import TxnIn, build_lots
from app.tax.common import money
from app.tax.engine import TaxProfileIn, gain_lines_for_matches
from app.tax.harvesting import HARVEST_LABEL, NOT_A_RECOMMENDATION, harvest_candidates
from app.tax.rules import RuleBook

RB = RuleBook.default()
FULL = TaxProfileIn(residency="resident", regime="new", other_taxable_income=D(2_000_000),
                    slab_rate_for_business_income=D("0.30"), carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
AS_OF = date(2025, 10, 1)


def _realized():
    led = build_lots([
        TxnIn(1, "R", "BUY", D(100), D(1000), date(2025, 4, 10)),
        TxnIn(2, "R", "SELL", D(100), D(2000), date(2025, 6, 2)),  # STCG 1,00,000
    ])
    return gain_lines_for_matches(led.matches, RB)


def _open():
    led = build_lots([
        TxnIn(10, "Y", "BUY", D(100), D(1000), date(2025, 5, 1)),  # ltp 700 -> STCL 30,000
        TxnIn(11, "W", "BUY", D(100), D(1000), date(2024, 1, 10)),  # ltp 800 -> LTCL 20,000
        TxnIn(12, "Z", "BUY", D(100), D(1000), date(2025, 5, 1)),  # ltp 1200 -> gain, not a candidate
    ])
    ltp = {"Y": D(700), "W": D(800), "Z": D(1200)}
    return [(lot, ltp[lot.symbol]) for lot in led.open_lots]


def test_harvest_candidates():
    rep = harvest_candidates(_open(), _realized(), FULL, RB, AS_OF)
    assert rep.tax_year == "2025-26"
    assert rep.label == HARVEST_LABEL and rep.note == NOT_A_RECOMMENDATION
    assert [c.symbol for c in rep.candidates] == ["Y", "W"]  # sorted by loss size; Z (gain) excluded
    y, w = rep.candidates

    # Y: STCL 30,000 offsets the realized STCG 1,00,000
    # without: 1,00,000 x 20% x 1.04 = 20,800 ; with: 70,000 x 20% x 1.04 = 14,560 ; impact -6,240
    assert y.classification == "STCG" and y.unrealized_loss == D(30000)
    assert money(y.estimated_tax_without_sale) == D("20800.00")
    assert money(y.estimated_tax_with_sale) == D("14560.00")
    assert money(y.estimated_tax_impact) == D("-6240.00")
    assert "STCG first and then LTCG" in y.potential_offset[0]
    assert y.note == NOT_A_RECOMMENDATION and y.label == HARVEST_LABEL
    assert y.realized_net_stcg_this_year == D(100000)

    # W: LTCL 20,000 cannot offset STCG -> no tax impact this year, carried forward
    assert w.classification == "LTCG" and w.long_term_loss == D(20000)
    assert w.estimated_tax_impact == 0
    assert w.carry_forward_ltcl_after == D(20000)
    assert "only against LTCG" in w.potential_offset[0]
    assert w.min_holding_days == w.max_holding_days == (AS_OF - date(2024, 1, 10)).days

    d = rep.to_dict()
    assert d["candidates"][0]["note"] == NOT_A_RECOMMENDATION
    assert rep.status == "complete"


def test_harvest_incomplete_profile_propagates():
    rep = harvest_candidates(_open(), _realized(), TaxProfileIn(), RB, AS_OF)
    assert rep.status == "incomplete" and rep.incomplete_reasons

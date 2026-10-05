"""TaxRulesEngine tests. All expected values hand-computed in comments (rates from rule set IN-2026.10)."""
from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal as D

import pytest

from app.portfolio.lots import CorpActionIn, TxnIn, build_lots
from app.tax.common import DISCLAIMER, INCOMPLETE_MESSAGE, money
from app.tax.engine import (
    UNREALIZED_LABEL,
    OpenLotPrice,
    RealizedContext,
    TaxProfileIn,
    capital_gain_for_match,
    classify,
    compute_tax_year,
    compute_tax_years,
    gain_lines_for_matches,
    net_pnl,
    unrealized_tax_estimate,
)
from app.tax.rules import RuleBook

RB = RuleBook.default()
EQ = "listed_equity_stt_paid"
_ids = itertools.count(1)

# Complete profile: resident, new regime, other income 20L (no basic-exemption shortfall, no surcharge below 50L)
FULL = TaxProfileIn(
    residency="resident", regime="new", other_taxable_income=D(2_000_000),
    slab_rate_for_business_income=D("0.30"), carried_forward_stcl=D(0), carried_forward_ltcl=D(0),
)


def trade(qty, buy_px, buy_d, sell_px, sell_d, sym="INFY", seg="delivery",
          buy_charges=0, buy_stt=0, sell_charges=0, sell_stt=0, fmv=None):
    return [
        TxnIn(next(_ids), sym, "BUY", D(qty), D(buy_px), buy_d, D(buy_charges), D(buy_stt), seg, fmv_31jan2018=fmv),
        TxnIn(next(_ids), sym, "SELL", D(qty), D(sell_px), sell_d, D(sell_charges), D(sell_stt), seg),
    ]


def lines(*trades, cas=()):
    txns = [t for tr in trades for t in tr]
    return gain_lines_for_matches(build_lots(txns, cas).matches, RB)


def total(res):
    return money(res.total_tax_estimate)


# ----------------------------------------------------------------------------------------------------------- classify

def test_stcg_ltcg_boundary():
    acq = date(2025, 1, 15)
    assert classify(acq, date(2026, 1, 15), EQ, RB) == "STCG"  # exactly 12 months -> STCG
    assert classify(acq, date(2026, 1, 16), EQ, RB) == "LTCG"  # more than 12 months
    assert classify(date(2024, 2, 29), date(2025, 2, 28), EQ, RB) == "STCG"
    assert classify(date(2024, 2, 29), date(2025, 3, 1), EQ, RB) == "LTCG"
    assert classify(acq, acq, "intraday_equity", RB) == "SPEC"


def test_boundary_through_lines():
    st = lines(trade(10, 100, date(2025, 1, 15), 110, date(2026, 1, 15)))[0]
    lt = lines(trade(10, 100, date(2025, 1, 15), 110, date(2026, 1, 16)))[0]
    assert (st.term, st.rate) == ("STCG", D("0.20"))
    assert (lt.term, lt.rate) == ("LTCG", D("0.125"))
    assert st.tax_year == "2025-26"


# --------------------------------------------------------------------------------------------------------- gains

def test_buy_price_equals_sell_price_charges_make_a_loss():
    (ln,) = lines(trade(100, 1000, date(2025, 5, 2), 1000, date(2025, 6, 2),
                        buy_charges="118.74", buy_stt=100, sell_charges="119.08", sell_stt=100))
    # capital gain: (1,00,000 - (119.08 - 100)) - (1,00,000 + (118.74 - 100)) = -19.08 - 18.74 = -37.82
    assert ln.capital_gain == D("-37.82")
    assert ln.stt == D(200)  # not deductible for capital gains
    # trading P&L deducts everything incl. STT: -118.74 - 119.08 = -237.82
    assert ln.trading_pnl == D("-237.82")
    res = compute_tax_year([ln], "2025-26", FULL, RB)
    assert res.total_tax_estimate == 0
    assert res.totals["STCG"].gross_losses == D("37.82")
    assert res.carry_forward.stcl == D("37.82")
    assert res.status == "complete"
    assert res.disclaimer == DISCLAIMER and res.label == "ESTIMATED"


def test_large_loss_set_off_against_ltcg_and_carried_forward():
    ls = lines(
        trade(1000, 2000, date(2025, 4, 10), 1000, date(2025, 9, 1), sym="LOSS"),  # STCL 10,00,000
        trade(100, 1000, date(2023, 1, 10), 4000, date(2025, 9, 1), sym="WIN"),  # LTCG 3,00,000
    )
    res = compute_tax_year(ls, "2025-26", FULL, RB)
    # STCL 10L: no STCG; set off against LTCG 3L (mandatory) -> LTCG 0, exemption unused; c/f STCL 7L
    assert res.total_tax_estimate == 0
    assert res.exemption_used == 0
    assert res.carry_forward.stcl == D(700_000)
    assert res.carry_forward.ltcl == 0
    assert any("remaining current-year STCL against LTCG" in s for s in res.set_off_log)
    assert any("8 tax years" in n for n in res.carry_forward.notes)


def test_large_profit_stcg():
    ls = lines(trade(1000, 1000, date(2025, 4, 10), 2000, date(2025, 9, 1)))
    res = compute_tax_year(ls, "2025-26", FULL, RB)
    # STCG 10,00,000 @ 20% = 2,00,000; total income 30L < 50L -> no surcharge; cess 4% = 8,000
    assert res.base_tax == D(200_000)
    assert res.surcharge == 0
    assert res.cess == D(8000)
    assert total(res) == D("208000.00")
    assert res.effective_rate == D("0.208")
    assert res.status == "complete"


def test_split_rate_year_2024_25():
    ls = lines(
        trade(100, 1000, date(2024, 4, 2), 2000, date(2024, 6, 3), sym="A"),  # STCG 1,00,000 @ 15%
        trade(100, 1000, date(2024, 4, 2), 2000, date(2024, 9, 2), sym="B"),  # STCG 1,00,000 @ 20%
        trade(100, 1000, date(2023, 1, 2), 2000, date(2024, 6, 3), sym="C"),  # LTCG 1,00,000 @ 10%
        trade(100, 1000, date(2023, 1, 2), 2500, date(2024, 9, 2), sym="D"),  # LTCG 1,50,000 @ 12.5%
    )
    res = compute_tax_year(ls, "2024-25", FULL, RB)
    by = {b.key: b for b in res.buckets}
    assert set(by) == {"STCG@15%", "STCG@20%", "LTCG@10%", "LTCG@12.5%"}
    # exemption Rs 1.25L for all of FY 2024-25, applied to the highest-rate LTCG bucket first:
    #   12.5% bucket 1,50,000 - 1,25,000 = 25,000 ; 10% bucket stays 1,00,000
    assert res.exemption_limit == D(125000) and res.exemption_used == D(125000)
    assert by["LTCG@12.5%"].taxable == D(25000)
    assert by["LTCG@10%"].taxable == D(100000)
    # base = 15,000 + 20,000 + 3,125 + 10,000 = 48,125; total income 24.5L -> no surcharge; cess 1,925
    assert res.base_tax == D(48125)
    assert res.cess == D(1925)
    assert total(res) == D("50050.00")
    assert by["STCG@15%"].legal_reference.startswith("s.111A")


def test_ltcg_exemption_125k():
    small = compute_tax_year(lines(trade(100, 1000, date(2024, 1, 10), 2000, date(2025, 6, 2))), "2025-26", FULL, RB)
    # LTCG 1,00,000 fully exempt
    assert small.total_tax_estimate == 0 and small.exemption_used == D(100000)
    big = compute_tax_year(lines(trade(100, 1000, date(2024, 1, 10), 3250, date(2025, 6, 2))), "2025-26", FULL, RB)
    # LTCG 2,25,000 - 1,25,000 = 1,00,000 @ 12.5% = 12,500; cess 500
    assert big.exemption_used == D(125000)
    assert total(big) == D("13000.00")


def test_ltcl_cannot_offset_stcg():
    ls = lines(
        trade(100, 1500, date(2023, 1, 10), 1000, date(2025, 6, 2), sym="L"),  # LTCL 50,000
        trade(100, 1000, date(2025, 4, 10), 2000, date(2025, 6, 2), sym="S"),  # STCG 1,00,000
    )
    res = compute_tax_year(ls, "2025-26", FULL, RB)
    # STCG fully taxable: 20,000 + 4% cess = 20,800; LTCL carried forward
    assert total(res) == D("20800.00")
    assert res.carry_forward.ltcl == D(50000)
    assert res.carry_forward.stcl == 0


def test_stcl_offsets_stcg_first_then_ltcg():
    ls = lines(
        trade(100, 1600, date(2025, 4, 10), 1000, date(2025, 6, 2), sym="L"),  # STCL 60,000
        trade(100, 1000, date(2025, 4, 10), 1500, date(2025, 6, 2), sym="S"),  # STCG 50,000
        trade(100, 1000, date(2023, 4, 10), 3000, date(2025, 6, 2), sym="T"),  # LTCG 2,00,000
    )
    res = compute_tax_year(ls, "2025-26", FULL, RB)
    # STCL 60k: 50k vs STCG, 10k vs LTCG -> LTCG 1,90,000 - 1,25,000 = 65,000 @ 12.5% = 8,125 ; cess 325
    assert total(res) == D("8450.00")
    assert res.set_off_log[1].startswith("Set off ₹50,000.00 current-year STCL against STCG")


def test_brought_forward_losses():
    profile = TaxProfileIn(residency="resident", regime="new", other_taxable_income=D(2_000_000),
                           carried_forward_stcl=D(30000), carried_forward_ltcl=D(200000))
    ls = lines(
        trade(100, 1000, date(2025, 4, 10), 1500, date(2025, 6, 2), sym="S"),  # STCG 50,000
        trade(100, 1000, date(2023, 4, 10), 2500, date(2025, 6, 2), sym="T"),  # LTCG 1,50,000
    )
    res = compute_tax_year(ls, "2025-26", profile, RB)
    # b/f STCL 30k vs STCG -> 20,000 ; b/f LTCL 2L vs LTCG 1.5L -> 0, 50k LTCL c/f
    # tax 20,000 x 20% = 4,000 + cess 160 = 4,160
    assert total(res) == D("4160.00")
    assert res.carry_forward.ltcl == D(50000)
    assert res.carry_forward.stcl == 0
    assert res.exemption_used == 0

    profile2 = TaxProfileIn(residency="resident", regime="new", other_taxable_income=D(2_000_000),
                            carried_forward_stcl=D(80000), carried_forward_ltcl=D(0))
    ls2 = lines(
        trade(100, 1000, date(2025, 4, 10), 1500, date(2025, 6, 2), sym="S"),  # STCG 50,000
        trade(100, 1000, date(2023, 4, 10), 3000, date(2025, 6, 2), sym="T"),  # LTCG 2,00,000
    )
    res2 = compute_tax_year(ls2, "2025-26", profile2, RB)
    # b/f STCL 80k: 50k vs STCG, 30k vs LTCG -> 1,70,000 - 1,25,000 = 45,000 @ 12.5% = 5,625 ; cess 225
    assert total(res2) == D("5850.00")


def test_surcharge_capped_at_15_percent_with_high_other_income():
    profile = TaxProfileIn(residency="resident", regime="old", other_taxable_income=D(60_000_000),
                           carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
    res = compute_tax_year(lines(trade(1000, 1000, date(2025, 4, 10), 2000, date(2025, 9, 1))), "2025-26", profile, RB)
    # total income 6.1 Cr -> slab 37%, capped at 15% for s.111A
    # base 2,00,000 ; surcharge 30,000 ; cess 4% x 2,30,000 = 9,200 ; total 2,39,200
    assert res.buckets[0].surcharge_rate == D("0.15")
    assert res.surcharge == D(30000)
    assert total(res) == D("239200.00")
    assert res.status == "complete"


def test_missing_other_income_is_incomplete():
    profile = TaxProfileIn(residency="resident", regime="new", carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
    res = compute_tax_year(lines(trade(1000, 1000, date(2025, 4, 10), 2000, date(2025, 9, 1))), "2025-26", profile, RB)
    assert res.status == "incomplete"
    assert res.message == INCOMPLETE_MESSAGE
    assert any("Other taxable income not provided" in r for r in res.incomplete_reasons)
    assert res.surcharge == 0  # CG alone 10L < 50L
    assert total(res) == D("208000.00")
    # very large gains: lower-bound surcharge still applies (other income assumed 0)
    big = compute_tax_year(lines(trade(1000, 1000, date(2025, 4, 10), 7000, date(2025, 9, 1))), "2025-26", profile, RB)
    # STCG 60L: base 12L; total income 60L > 50L -> 10% = 1.2L; cess 4% x 13.2L = 52,800 -> 13,72,800
    assert total(big) == D("1372800.00")
    assert big.status == "incomplete"


def test_missing_residency_and_regime_flagged():
    res = compute_tax_year(lines(trade(10, 100, date(2025, 4, 10), 200, date(2025, 9, 1))), "2025-26",
                           TaxProfileIn(other_taxable_income=D(2_000_000)), RB)
    assert res.status == "incomplete"
    joined = " ".join(res.incomplete_reasons)
    assert "Residency" in joined and "regime" in joined


def test_basic_exemption_shortfall_residents_only():
    ls = lines(trade(1000, 1000, date(2025, 4, 10), 1500, date(2025, 9, 1)))  # STCG 5,00,000
    resident = TaxProfileIn(residency="resident", regime="new", other_taxable_income=D(100000),
                            carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
    res = compute_tax_year(ls, "2025-26", resident, RB)
    # BEL 4L - other income 1L = 3L shortfall -> STCG taxable 2,00,000 @ 20% = 40,000 + cess 1,600
    assert res.basic_exemption_used == D(300000)
    assert total(res) == D("41600.00")
    nri = TaxProfileIn(residency="nri", regime="new", other_taxable_income=D(100000),
                       carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
    res_nri = compute_tax_year(ls, "2025-26", nri, RB)
    assert total(res_nri) == D("104000.00")  # 1,00,000 + 4,000


def test_old_regime_age_dependent_limit_flagged():
    profile = TaxProfileIn(residency="resident", regime="old", other_taxable_income=D(100000),
                           carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
    res = compute_tax_year(lines(trade(1000, 1000, date(2025, 4, 10), 1500, date(2025, 9, 1))), "2025-26", profile, RB)
    # old regime BEL 2.5L assumed -> shortfall 1.5L -> taxable 3.5L @ 20% = 70,000 + 2,800
    assert total(res) == D("72800.00")
    assert res.status == "incomplete" and any("age" in r for r in res.incomplete_reasons)


def test_grandfathering_with_and_without_fmv():
    buy_d, sell_d = date(2017, 6, 1), date(2025, 6, 2)
    with_fmv = lines(trade(100, 500, buy_d, 1000, sell_d, fmv=800))[0]
    # cost = max(50,000, min(80,000, 1,00,000)) = 80,000 -> LTCG 20,000
    assert with_fmv.term == "LTCG" and with_fmv.grandfathered
    assert with_fmv.capital_gain == D(20000)
    assert with_fmv.incomplete_reasons == []

    below = lines(trade(100, 500, buy_d, 700, sell_d, fmv=800))[0]
    # cost = max(50,000, min(80,000, 70,000)) = 70,000 -> gain 0 (grandfathering never creates a loss)
    assert below.capital_gain == 0

    fmv_low = lines(trade(100, 500, buy_d, 1000, sell_d, fmv=400))[0]
    assert fmv_low.capital_gain == D(50000) and not fmv_low.grandfathered

    no_fmv = lines(trade(100, 500, buy_d, 1000, sell_d))[0]
    assert no_fmv.capital_gain == D(50000)
    assert any("FMV" in r for r in no_fmv.incomplete_reasons)
    res = compute_tax_year([no_fmv], "2025-26", FULL, RB)
    assert res.status == "incomplete" and any("FMV" in r for r in res.incomplete_reasons)

    # FMV passed explicitly overrides the lot's value
    m = build_lots(trade(100, 500, buy_d, 1000, sell_d)).matches[0]
    assert capital_gain_for_match(m, RB, fmv_31jan2018=D(900)).capital_gain == D(10000)


def test_grandfathering_fmv_adjusted_for_split():
    txns = [
        TxnIn(next(_ids), "INFY", "BUY", D(10), D(1000), date(2017, 6, 1), fmv_31jan2018=D(2000)),
        TxnIn(next(_ids), "INFY", "SELL", D(50), D(300), date(2025, 6, 2)),
    ]
    ls = lines(txns, cas=[CorpActionIn("INFY", date(2020, 1, 15), "split", D(10), D(2))])
    # 10 -> 50 shares, FMV/share 2000 -> 400: cost = max(10,000, min(20,000, 15,000)) = 15,000 -> gain 0
    assert ls[0].quantity == 50 and ls[0].capital_gain == 0


def test_multiple_tax_years_chain_carry_forward():
    ls = lines(
        trade(100, 1500, date(2024, 6, 3), 1000, date(2024, 11, 4), sym="L"),  # 2024-25 STCL 50,000
        trade(100, 1000, date(2025, 4, 10), 1800, date(2025, 6, 2), sym="S"),  # 2025-26 STCG 80,000
    )
    y1, y2 = compute_tax_years(ls, FULL, RB)
    assert (y1.tax_year, y2.tax_year) == ("2024-25", "2025-26")
    assert y1.carry_forward.stcl == D(50000) and y1.total_tax_estimate == 0
    # 2025-26: b/f STCL 50k vs STCG 80k -> 30,000 @ 20% = 6,000 + cess 240
    assert total(y2) == D("6240.00")
    assert y2.carry_forward.stcl == 0
    # single-year call ignores other years' lines
    only = compute_tax_year(ls, "2025-26", FULL, RB)
    assert total(only) == D("16640.00") and any("other tax years" in n for n in only.notes)


def test_intraday_with_and_without_slab_rate():
    ls = lines(trade(100, 1000, date(2025, 6, 2), 1010, date(2025, 6, 2), seg="intraday",
                     buy_charges=30, sell_charges=55, sell_stt=25))
    assert ls[0].term == "SPEC"
    # speculative income deducts all charges incl. STT: 1,000 - 30 - 55 = 915
    assert ls[0].capital_gain == D(915)
    res = compute_tax_year(ls, "2025-26", FULL, RB)
    # 915 x 30% = 274.50 ; cess 10.98 ; total 285.48
    assert total(res) == D("285.48")
    assert res.status == "complete"
    no_slab = TaxProfileIn(residency="resident", regime="new", other_taxable_income=D(2_000_000),
                           carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
    res2 = compute_tax_year(ls, "2025-26", no_slab, RB)
    assert res2.status == "incomplete" and res2.total_tax_estimate == 0
    assert any("Slab rate" in r for r in res2.incomplete_reasons)


def test_speculative_loss_only_offsets_speculative_income():
    ls = lines(
        trade(100, 1000, date(2025, 6, 2), 800, date(2025, 6, 2), sym="I", seg="intraday"),  # SPEC loss 20,000
        trade(100, 1000, date(2025, 4, 10), 2000, date(2025, 6, 2), sym="S"),  # STCG 1,00,000
    )
    res = compute_tax_year(ls, "2025-26", FULL, RB)
    assert total(res) == D("20800.00")  # STCG untouched by the speculative loss
    assert res.carry_forward.speculative_loss == D(20000)
    assert any("4 tax years" in n for n in res.carry_forward.notes)


def test_speculative_surcharge_regime_caps():
    ls = lines(trade(1000, 1000, date(2025, 6, 2), 1100, date(2025, 6, 2), seg="intraday"))  # SPEC 1,00,000
    old = TaxProfileIn(residency="resident", regime="old", other_taxable_income=D(60_000_000),
                       slab_rate_for_business_income=D("0.30"), carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
    # base 30,000; surcharge 37% (no 15% cap on slab income) = 11,100; cess 4% x 41,100 = 1,644 -> 42,744
    assert total(compute_tax_year(ls, "2025-26", old, RB)) == D("42744.00")
    new = TaxProfileIn(residency="resident", regime="new", other_taxable_income=D(60_000_000),
                       slab_rate_for_business_income=D("0.30"), carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
    # new regime caps surcharge at 25%: 7,500; cess 1,500 -> 39,000
    assert total(compute_tax_year(ls, "2025-26", new, RB)) == D("39000.00")


def test_allocation_sums_to_total():
    ls = lines(
        trade(7, D("1000.33"), date(2024, 4, 2), D("2000.17"), date(2024, 6, 3), sym="A", buy_charges="3.31"),
        trade(13, 1000, date(2024, 4, 2), D("1999.99"), date(2024, 9, 2), sym="B", sell_charges="7.77"),
        trade(100, 1000, date(2023, 1, 2), 2000, date(2024, 6, 3), sym="C"),
        trade(101, 1000, date(2023, 1, 2), 2500, date(2024, 9, 2), sym="D"),
        trade(33, 1000, date(2024, 4, 2), 900, date(2024, 9, 2), sym="E"),  # STCL 3,300
        trade(9, 1000, date(2024, 6, 2), 1100, date(2024, 6, 2), sym="F", seg="intraday"),
    )
    res = compute_tax_year(ls, "2024-25", FULL, RB)
    alloc = res.allocate_to_lines()
    assert len(alloc) == len(ls)
    assert sum(a.estimated_tax for a in alloc) == money(res.total_tax_estimate)
    assert all(a.estimated_tax == 0 for a in alloc if a.capital_gain <= 0)
    assert all(a.estimated_tax > 0 for a in alloc if a.capital_gain > 0)
    d = res.to_dict()
    assert d["label"] == "ESTIMATED" and d["total_tax_estimate"] == str(money(res.total_tax_estimate))


def test_net_pnl():
    n = net_pnl(D(10000), D("237.82"), D(1500))
    assert (n.gross_pnl, n.charges, n.pnl_before_tax, n.estimated_tax, n.net_after_tax) == (
        D(10000), D("237.82"), D("9762.18"), D(1500), D("8262.18"))
    assert n.is_estimate
    unknown = net_pnl(D(10000), D(100), None)
    assert unknown.gross_pnl == D(10000) and unknown.net_after_tax is None


def test_unrealized_tax_estimate():
    led = build_lots([TxnIn(1, "X", "BUY", D(100), D(1000), date(2025, 1, 10))])
    est = unrealized_tax_estimate([OpenLotPrice(led.open_lots[0], D(1500))], date(2025, 10, 1), RB,
                                  RealizedContext(profile=FULL))
    # STCG 50,000 @ 20% = 10,000 + cess 400
    assert est.total_unrealized_gain == D(50000)
    assert money(est.estimated_tax_if_sold) == D("10400.00")
    assert est.lots[0].term == "STCG"
    assert est.informational_note == UNREALIZED_LABEL
    assert est.status == "complete"
    assert any("not estimated" in n for n in est.notes)
    # with realized STCL already this year, the incremental tax is lower
    realized = lines(trade(100, 1300, date(2025, 4, 10), 1000, date(2025, 6, 2), sym="Z"))  # STCL 30,000
    est2 = unrealized_tax_estimate([(led.open_lots[0], D(1500))], date(2025, 10, 1), RB,
                                   RealizedContext(realized, FULL))
    assert money(est2.estimated_tax_if_sold) == D("4160.00")  # (50,000 - 30,000) x 20% x 1.04


def test_unrealized_with_charges_engine():
    from app.tax.charges import ChargesEngine

    led = build_lots([TxnIn(1, "X", "BUY", D(100), D(1000), date(2025, 1, 10))])
    est = unrealized_tax_estimate([(led.open_lots[0], D(1000))], date(2025, 10, 1), RB,
                                  RealizedContext(profile=FULL), charges_engine=ChargesEngine.default())
    # sell charges excl. STT = 19.0806 -> capital loss
    assert est.total_unrealized_gain == D("-19.0806")
    assert est.estimated_tax_if_sold == 0


@pytest.mark.parametrize("bad", ["2025", "2025-27"])
def test_invalid_tax_year(bad):
    with pytest.raises(ValueError):
        compute_tax_year([], bad, FULL, RB)

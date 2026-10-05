"""Dated tax-rule look-ups."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.tax.common import add_months, inr, tax_year_bounds, tax_year_of
from app.tax.defaults import basic_exemption_limits, default_tax_rules
from app.tax.rules import RuleBook, RuleNotFoundError, TaxRuleSpec

RB = RuleBook.default()
EQ = "listed_equity_stt_paid"


@pytest.mark.parametrize(
    ("term", "d", "rate", "ref"),
    [
        ("STCG", date(2024, 7, 22), "0.15", "s.111A"),
        ("STCG", date(2024, 7, 23), "0.20", "s.111A"),
        ("STCG", date(2026, 3, 31), "0.20", "s.111A"),
        ("STCG", date(2026, 4, 1), "0.20", "s.196"),
        ("LTCG", date(2024, 7, 22), "0.10", "s.112A"),
        ("LTCG", date(2024, 7, 23), "0.125", "s.112A"),
        ("LTCG", date(2026, 4, 1), "0.125", "s.198"),
    ],
)
def test_rule_for_by_transfer_date(term, d, rate, ref):
    rule = RB.rule_for(EQ, term, d)
    assert rule.rate == D(rate)
    assert rule.legal_reference.startswith(ref)
    assert rule.source_url == "https://www.incometaxindia.gov.in/en/sale-of-shares"
    assert "reviewed" in rule.notes


def test_ltcg_rules_have_grandfather_date_and_caps():
    rule = RB.rule_for(EQ, "LTCG", date(2025, 6, 2))
    assert rule.grandfather_date == date(2018, 1, 31)
    assert rule.surcharge_cap == D("0.15")
    assert rule.cess_rate == D("0.04")
    assert [s["rate"] for s in rule.surcharge_slabs] == [D("0.10"), D("0.15"), D("0.25"), D("0.37")]
    assert rule.surcharge_rate_for(D(60_000_000)) == D("0.37")
    assert rule.surcharge_rate_for(D(5_000_000)) == 0  # "above" 50L, not at
    spec = RB.rule_for("intraday_equity", "SPEC", date(2025, 6, 2))
    assert spec.rate is None and spec.surcharge_cap is None


def test_rule_not_found():
    with pytest.raises(RuleNotFoundError):
        RB.rule_for(EQ, "STCG", date(2017, 1, 1))
    assert RB.find_rule("unlisted", "STCG", date(2025, 1, 1)) is None


def test_exemption_for_tax_year_uses_last_day():
    assert RB.exemption_for_tax_year(EQ, "2023-24") == D(100000)
    # FY 2024-25: rule effective on 31-Mar-2025 -> Rs 1.25L for the whole year (Finance (No.2) Act 2024)
    assert RB.exemption_for_tax_year(EQ, "2024-25") == D(125000)
    assert RB.exemption_for_tax_year(EQ, "2026-27") == D(125000)
    assert RB.exemption_for_tax_year("intraday_equity", "2025-26") == 0


def test_basic_exemption_limits():
    assert RB.basic_exemption_limit("new", "2024-25").limit == D(300000)
    assert RB.basic_exemption_limit("new", "2025-26").limit == D(400000)
    assert RB.basic_exemption_limit("new", "2027-28").limit == D(400000)
    old = RB.basic_exemption_limit("old", "2025-26")
    assert old.limit == D(250000) and old.age_dependent
    assert RB.basic_exemption_limit("new", "2023-24").limit is None
    json.dumps(basic_exemption_limits())


def test_version_and_coercion_from_orm_like_rows():
    assert RB.version == "IN-2026.10"
    rows = [SimpleNamespace(**r) for r in default_tax_rules()]
    rb = RuleBook(rows)
    assert rb.rule_for(EQ, "LTCG", date(2025, 1, 1)).exemption_threshold == D(125000)
    for r in default_tax_rules():
        json.dumps(r["surcharge_slabs"])
        assert TaxRuleSpec.from_dict(r).rule_set_version == "IN-2026.10"


def test_date_helpers():
    assert tax_year_of(date(2025, 3, 31)) == "2024-25"
    assert tax_year_of(date(2025, 4, 1)) == "2025-26"
    assert tax_year_of(date(1999, 4, 1)) == "1999-00"
    assert tax_year_bounds("2025-26") == (date(2025, 4, 1), date(2026, 3, 31))
    with pytest.raises(ValueError):
        tax_year_bounds("2025-27")
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert inr(D("12500000.5")) == "₹1,25,00,000.50"
    assert inr(D(-999)) == "-₹999.00"

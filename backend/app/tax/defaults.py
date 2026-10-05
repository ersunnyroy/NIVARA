"""Default, dated charge schedules and tax rules (seed data).

These are *data*, not logic: they are what gets seeded into the ``charges`` and ``tax_rules`` tables and what
the pure engines consume. All values are JSON-serialisable (Decimals written as strings; dates as ``date``).

Charge-schedule rates are percent values (``"0.1"`` = 0.1 %). Tax-rule rates are fractions (``"0.125"`` = 12.5 %).
Review whenever the Finance Act / exchange circulars / broker tariffs change.
"""
from __future__ import annotations

from datetime import date
from typing import Any

CHARGES_SOURCE_URL = "https://zerodha.com/charges"
CHARGES_RETRIEVED = "2026-10-05"
DEFAULT_SCHEDULE_NAME = "Discount broker (Zerodha-style) — verify with your broker"

TAX_RULE_SET_VERSION = "IN-2026.10"
TAX_SOURCE_URL = "https://www.incometaxindia.gov.in/en/sale-of-shares"
TAX_RULES_NOTE = (
    "Rates are stored as dated rules keyed by date of transfer and must be reviewed whenever the law changes "
    "(Finance Acts, Income-tax Act 2025). Estimates only."
)

_COMMON_EQUITY_TXN = {"NSE": "0.00307", "BSE": "0.00375"}
_SEBI_PER_CRORE = "10"
_GST_PCT = "18"


def _equity_delivery() -> dict[str, Any]:
    return {
        "brokerage": {"type": "zero"},
        "stt_buy_pct": "0.1",
        "stt_sell_pct": "0.1",
        "exchange_txn_pct": dict(_COMMON_EQUITY_TXN),
        "sebi_per_crore": _SEBI_PER_CRORE,
        "stamp_buy_pct": "0.015",
        "ipft_per_crore": "0",
        "gst_pct": _GST_PCT,
        "dp_charge_per_scrip_sell": "15.34",
    }


def _equity_intraday() -> dict[str, Any]:
    return {
        "brokerage": {"type": "percent_capped", "pct": "0.03", "cap": "20"},
        "stt_buy_pct": "0",
        "stt_sell_pct": "0.025",
        "exchange_txn_pct": dict(_COMMON_EQUITY_TXN),
        "sebi_per_crore": _SEBI_PER_CRORE,
        "stamp_buy_pct": "0.003",
        "ipft_per_crore": "0",
        "gst_pct": _GST_PCT,
        "dp_charge_per_scrip_sell": "0",
    }


def _futures(stt_sell_pct: str) -> dict[str, Any]:
    return {
        "brokerage": {"type": "percent_capped", "pct": "0.03", "cap": "20"},
        "stt_buy_pct": "0",
        "stt_sell_pct": stt_sell_pct,
        "exchange_txn_pct": {"NSE": "0.00183"},
        "sebi_per_crore": _SEBI_PER_CRORE,
        "stamp_buy_pct": "0.002",
        "ipft_per_crore": "0",
        "gst_pct": _GST_PCT,
        "dp_charge_per_scrip_sell": "0",
    }


def _options(stt_sell_pct: str) -> dict[str, Any]:
    return {
        "brokerage": {"type": "flat", "flat": "20"},
        "stt_buy_pct": "0",
        "stt_sell_pct": stt_sell_pct,
        "exchange_txn_pct": {"NSE": "0.03553"},
        "sebi_per_crore": _SEBI_PER_CRORE,
        "stamp_buy_pct": "0.003",
        "ipft_per_crore": "0",
        "gst_pct": _GST_PCT,
        "dp_charge_per_scrip_sell": "0",
    }


def _schedule(effective_from: date, effective_to: date | None, fut_stt: str, opt_stt: str, extra: str) -> dict:
    return {
        "name": DEFAULT_SCHEDULE_NAME,
        "broker": "Discount broker (generic)",
        "effective_from": effective_from,
        "effective_to": effective_to,
        "rates": {
            "stt_rounding": "rupee",
            "equity_delivery": _equity_delivery(),
            "equity_intraday": _equity_intraday(),
            "futures": _futures(fut_stt),
            "options": _options(opt_stt),
        },
        "source_url": CHARGES_SOURCE_URL,
        "retrieved": CHARGES_RETRIEVED,
        "notes": (
            f"Retrieved {CHARGES_RETRIEVED} from {CHARGES_SOURCE_URL}. Percent values (0.1 = 0.1%). "
            "IPFT set to 0 — configure if levied by your broker/exchange. DP charge is GST-inclusive, once per "
            "scrip per day on delivery sells. STT rounded to the nearest rupee (contract-note practice; "
            f"set stt_rounding='paise' to change). {extra} Verify with your broker's contract note."
        ),
        "is_default": True,
    }


def default_charge_schedules() -> list[dict[str, Any]]:
    """Two dated schedules; equity rates identical, F&O STT changes from 2026-04-01 (Union Budget 2026)."""
    return [
        _schedule(date(2024, 10, 1), date(2026, 3, 31), "0.02", "0.1",
                  "F&O STT on sell: futures 0.02%, options 0.1% of premium."),
        _schedule(date(2026, 4, 1), None, "0.05", "0.15",
                  "F&O STT on sell from 2026-04-01 (Union Budget 2026): futures 0.05%, options 0.15% of premium."),
    ]


# --- tax rules ---------------------------------------------------------------------------------------------

def _surcharge_slabs() -> list[dict[str, str]]:
    """Individual surcharge slabs on total income (fractions)."""
    return [
        {"above": "5000000", "rate": "0.10"},
        {"above": "10000000", "rate": "0.15"},
        {"above": "20000000", "rate": "0.25"},
        {"above": "50000000", "rate": "0.37"},
    ]


def _rule(
    asset_type: str,
    term: str,
    effective_from: date,
    effective_to: date | None,
    rate: str | None,
    legal_reference: str,
    tax_years: str,
    *,
    exemption: str | None = None,
    surcharge_cap: str | None = "0.15",
    grandfather_date: date | None = None,
    extra_note: str = "",
) -> dict[str, Any]:
    return {
        "rule_set_version": TAX_RULE_SET_VERSION,
        "asset_type": asset_type,
        "transaction_type": "transfer",
        "term": term,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "tax_years": tax_years,
        "holding_period_months": 12,
        "rate": rate,
        "exemption_threshold": exemption,
        "surcharge_cap": surcharge_cap,
        "surcharge_slabs": _surcharge_slabs(),
        "cess_rate": "0.04",
        "grandfather_date": grandfather_date,
        "legal_reference": legal_reference,
        "source_url": TAX_SOURCE_URL,
        "notes": f"{TAX_RULES_NOTE} {extra_note}".strip(),
    }


def default_tax_rules() -> list[dict[str, Any]]:
    """Rule set ``IN-2026.10`` for listed equity (STT paid) and intraday equity, keyed by date of transfer."""
    eq = "listed_equity_stt_paid"
    gf = date(2018, 1, 31)
    ltcg_note = (
        "LTCG when held more than 12 months. Exemption applies once per tax year. Grandfathering: cost for shares "
        "acquired on/before 31-Jan-2018 = max(actual cost, min(FMV on 31-Jan-2018, sale value))."
    )
    return [
        _rule(eq, "STCG", date(2018, 4, 1), date(2024, 7, 22), "0.15",
              "s.111A, Income-tax Act, 1961", "2018-19 to 2024-25 (transfers before 23-Jul-2024)"),
        _rule(eq, "STCG", date(2024, 7, 23), date(2026, 3, 31), "0.20",
              "s.111A, Income-tax Act, 1961 (as amended by Finance (No.2) Act, 2024)",
              "2024-25 (transfers on/after 23-Jul-2024) to 2025-26"),
        _rule(eq, "STCG", date(2026, 4, 1), None, "0.20",
              "s.196, Income-tax Act, 2025", "2026-27 onwards"),
        _rule(eq, "LTCG", date(2018, 4, 1), date(2024, 7, 22), "0.10",
              "s.112A, Income-tax Act, 1961", "2018-19 to 2024-25 (transfers before 23-Jul-2024)",
              exemption="100000", grandfather_date=gf, extra_note=ltcg_note),
        _rule(eq, "LTCG", date(2024, 7, 23), date(2026, 3, 31), "0.125",
              "s.112A, Income-tax Act, 1961 (as amended by Finance (No.2) Act, 2024)",
              "2024-25 (transfers on/after 23-Jul-2024) to 2025-26",
              exemption="125000", grandfather_date=gf,
              extra_note=ltcg_note + " The Rs 1,25,000 exemption applies to the whole of FY 2024-25."),
        _rule(eq, "LTCG", date(2026, 4, 1), None, "0.125",
              "s.198, Income-tax Act, 2025", "2026-27 onwards",
              exemption="125000", grandfather_date=gf, extra_note=ltcg_note),
        _rule("intraday_equity", "SPEC", date(2018, 4, 1), None, None,
              "Speculative business income (s.43(5) / s.73, Income-tax Act, 1961; corresponding provisions of "
              "Income-tax Act, 2025)", "2018-19 onwards", surcharge_cap=None,
              extra_note="Taxed at the user's slab rate (rate=None => slab rate required from the user). "
                         "Speculative losses only offset speculative gains; carry forward 4 years."),
    ]


def basic_exemption_limits() -> dict[str, Any]:
    """Basic exemption limits by regime (used for the residents-only shortfall adjustment u/s 111A/112A)."""
    return {
        "new": [
            {"from_tax_year": "2024-25", "to_tax_year": "2024-25", "limit": "300000"},
            {"from_tax_year": "2025-26", "to_tax_year": None, "limit": "400000"},
        ],
        "old": [
            {
                "from_tax_year": "2018-19",
                "to_tax_year": None,
                "limit": "250000",
                "age_dependent": True,
                "max_age_dependent_limit": "500000",
                "notes": "Old regime limit is age-dependent: Rs 2,50,000 below 60, Rs 3,00,000 for 60-79, "
                         "Rs 5,00,000 for 80+. Rs 2,50,000 assumed.",
            }
        ],
        "notes": "Shortfall of other income below the basic exemption limit can be adjusted against "
                 "STCG (s.111A) / LTCG (s.112A) for residents only.",
    }


def regime_surcharge_caps() -> dict[str, str | None]:
    """Maximum surcharge rate by regime (new regime caps surcharge at 25% from FY 2023-24)."""
    return {"new": "0.25", "old": None}

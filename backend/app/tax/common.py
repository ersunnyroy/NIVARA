"""Shared helpers for the pure charges / tax / lot engines.

Conventions
-----------
* Money is ``decimal.Decimal`` at full precision inside calculations; it is rounded to paise
  (0.01, ROUND_HALF_UP) only at the reporting edge (``money()`` / ``to_dict()``).
* Charge-schedule rates are *percent* values (``0.1`` means 0.1 %); tax-rule rates are *fractions*
  (``0.125`` means 12.5 %), matching the ``tax_rules`` table (cess default ``0.04``).
* Indian tax years run 1 April - 31 March and are written ``"2025-26"``.
"""
from __future__ import annotations

import calendar
import dataclasses
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)
PAISE = Decimal("0.01")
RUPEE = Decimal(1)

ESTIMATED = "ESTIMATED"
INCOMPLETE_MESSAGE = "Tax estimate incomplete — additional tax information required."
DISCLAIMER = "Estimated tax only. Verify with a qualified tax professional before filing."


def D(value: Any) -> Decimal:
    """Convert int/str/float/Decimal to Decimal without binary-float artefacts."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        raise TypeError("Cannot convert None to Decimal")
    if isinstance(value, bool):
        raise TypeError("Refusing to convert bool to Decimal")
    return Decimal(str(value))


def D_opt(value: Any) -> Decimal | None:
    return None if value is None else D(value)


def money(value: Decimal) -> Decimal:
    """Round to paise, ROUND_HALF_UP (reporting edge only)."""
    return D(value).quantize(PAISE, rounding=ROUND_HALF_UP)


def inr(value: Decimal) -> str:
    """Format as Indian rupees with lakh/crore digit grouping, e.g. ``₹1,25,000.00``."""
    q = money(value)
    sign = "-" if q < 0 else ""
    whole, frac = f"{abs(q):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}₹{whole}.{frac}"


def pct(rate: Decimal | None) -> str:
    """Format a fractional rate as a percentage string (``0.125`` -> ``12.5%``)."""
    if rate is None:
        return "slab rate"
    value = (D(rate) * HUNDRED).normalize()
    text = format(value, "f")
    return f"{text}%"


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def add_months(d: date, months: int) -> date:
    """Calendar-month addition; the day is clamped to the month end (29-Feb + 12m -> 28-Feb)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def tax_year_of(d: date) -> str:
    """Indian tax (financial) year containing ``d``: 2025-06-02 -> ``"2025-26"``."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def tax_year_bounds(tax_year: str) -> tuple[date, date]:
    """``"2025-26"`` -> (2025-04-01, 2026-03-31)."""
    try:
        start = int(tax_year.split("-")[0])
    except (ValueError, AttributeError, IndexError) as exc:
        raise ValueError(f"Invalid tax year {tax_year!r}; expected e.g. '2025-26'") from exc
    if tax_year_of(date(start, 4, 1)) != tax_year:
        raise ValueError(f"Invalid tax year {tax_year!r}; expected e.g. '2025-26'")
    return date(start, 4, 1), date(start + 1, 3, 31)


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def jsonable(obj: Any, key: str = "") -> Any:
    """Recursively convert dataclasses/Decimals/dates to JSON-friendly values.

    Decimals are rounded to paise, except values whose key contains ``rate``/``pct``/``quantity``
    (rates and share counts are reported unrounded).
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: jsonable(getattr(obj, f.name), f.name)
            for f in dataclasses.fields(obj)
            if f.repr
        }
    if isinstance(obj, Decimal):
        if any(token in key for token in ("rate", "pct", "quantity")):
            return format(obj.normalize(), "f")
        return format(money(obj), "f")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): jsonable(v, str(k)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v, key) for v in obj]
    return obj

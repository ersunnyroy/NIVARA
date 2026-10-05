"""Versioned, dated tax rules and charge schedules. Never hard-code rates elsewhere."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money

Rate = Numeric(12, 8)


class TaxRule(Base):
    __tablename__ = "tax_rules"
    __table_args__ = (UniqueConstraint("rule_set_version", "asset_type", "term", "effective_from", name="uq_tax_rule"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_set_version: Mapped[str] = mapped_column(String(32), index=True)
    asset_type: Mapped[str] = mapped_column(String(40))  # listed_equity_stt_paid | intraday_equity | ...
    transaction_type: Mapped[str] = mapped_column(String(20), default="transfer")
    term: Mapped[str] = mapped_column(String(8))  # STCG | LTCG | SPEC
    effective_from: Mapped[date] = mapped_column(Date)  # date of transfer on/after which rule applies
    effective_to: Mapped[date | None] = mapped_column(Date)
    tax_years: Mapped[str | None] = mapped_column(String(64))  # informational, e.g. "2024-25 onwards"
    holding_period_months: Mapped[int] = mapped_column(Integer, default=12)
    rate: Mapped[Decimal | None] = mapped_column(Rate)  # None => slab rate (needs user input)
    exemption_threshold: Mapped[Decimal | None] = mapped_column(Money)  # per tax year
    surcharge_cap: Mapped[Decimal | None] = mapped_column(Rate)
    surcharge_slabs: Mapped[list[Any]] = mapped_column(default=list)
    cess_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.04"))
    grandfather_date: Mapped[date | None] = mapped_column(Date)
    legal_reference: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChargeSchedule(Base):
    """Brokerage + statutory charges, dated. `rates` holds the full parameter set (see tax/charges.py)."""

    __tablename__ = "charges"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    broker: Mapped[str | None] = mapped_column(String(80))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    rates: Mapped[dict[str, Any]] = mapped_column(default=dict)
    source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TaxProfile(Base):
    """User-specific facts the tax estimate depends on. Missing facts => estimate flagged incomplete."""

    __tablename__ = "tax_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    residency: Mapped[str | None] = mapped_column(String(16))  # resident | nri
    regime: Mapped[str | None] = mapped_column(String(8))  # new | old
    other_taxable_income: Mapped[Decimal | None] = mapped_column(Money)  # excludes these capital gains
    slab_rate_for_business_income: Mapped[Decimal | None] = mapped_column(Rate)
    carried_forward: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {"STCL": x, "LTCL": y, "from_years": ...}
    broker_reported: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {"2025-26": {"stcg":..,"ltcg":..}}
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

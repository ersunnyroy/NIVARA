from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FinancialResult(Base):
    """One filed result (quarterly/annual), values in INR (absolute, not crores)."""

    __tablename__ = "financial_results"
    __table_args__ = (UniqueConstraint("stock_id", "period_end", "consolidated", "period_type", name="uq_result"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    period_type: Mapped[str] = mapped_column(String(12), default="quarterly")  # quarterly | annual
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    consolidated: Mapped[bool] = mapped_column(Boolean)
    is_bank: Mapped[bool] = mapped_column(Boolean, default=False)
    audited: Mapped[bool | None] = mapped_column(Boolean)
    # When the market could first know this number (point-in-time guard for backtests).
    broadcast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revenue: Mapped[float | None] = mapped_column(Float)
    other_income: Mapped[float | None] = mapped_column(Float)
    total_income: Mapped[float | None] = mapped_column(Float)
    total_expenses: Mapped[float | None] = mapped_column(Float)
    finance_costs: Mapped[float | None] = mapped_column(Float)
    depreciation: Mapped[float | None] = mapped_column(Float)
    pbt: Mapped[float | None] = mapped_column(Float)
    tax: Mapped[float | None] = mapped_column(Float)
    pat: Mapped[float | None] = mapped_column(Float)
    pat_owners: Mapped[float | None] = mapped_column(Float)
    ebitda: Mapped[float | None] = mapped_column(Float)
    ebit: Mapped[float | None] = mapped_column(Float)
    eps_basic: Mapped[float | None] = mapped_column(Float)
    eps_diluted: Mapped[float | None] = mapped_column(Float)
    paid_up_capital: Mapped[float | None] = mapped_column(Float)
    face_value: Mapped[float | None] = mapped_column(Float)
    debt_equity: Mapped[float | None] = mapped_column(Float)
    interest_coverage: Mapped[float | None] = mapped_column(Float)
    classification: Mapped[str | None] = mapped_column(String(20))  # VERY POSITIVE ... VERY NEGATIVE
    analysis: Mapped[dict[str, Any]] = mapped_column(default=dict)
    source: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any]] = mapped_column(default=dict)


class FundamentalSnapshot(Base):
    """Derived ratios as of a date (computed only from data public on/before `as_of`)."""

    __tablename__ = "fundamentals"
    __table_args__ = (UniqueConstraint("stock_id", "as_of", name="uq_fund_snapshot"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[date] = mapped_column(Date)
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict)  # name -> {value, source, period_end, ...}
    score: Mapped[float | None] = mapped_column(Float)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict)
    completeness: Mapped[float] = mapped_column(Float, default=0.0)  # 0-1
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Shareholding(Base):
    __tablename__ = "shareholding"
    __table_args__ = (UniqueConstraint("stock_id", "period_end", name="uq_shp"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    period_end: Mapped[date] = mapped_column(Date)
    promoter_pct: Mapped[float | None] = mapped_column(Float)
    public_pct: Mapped[float | None] = mapped_column(Float)
    promoter_pledged_pct: Mapped[float | None] = mapped_column(Float)
    fii_pct: Mapped[float | None] = mapped_column(Float)
    dii_pct: Mapped[float | None] = mapped_column(Float)
    mf_pct: Mapped[float | None] = mapped_column(Float)
    broadcast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventCalendar(Base):
    """Upcoming board meetings / results dates."""

    __tablename__ = "event_calendar"
    __table_args__ = (UniqueConstraint("stock_id", "event_date", "purpose", name="uq_event"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    purpose: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money, Qty, UTCDateTime


class Backtest(Base):
    __tablename__ = "backtests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    strategy: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    universe: Mapped[str] = mapped_column(String(40))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    splits: Mapped[dict[str, Any]] = mapped_column(default=dict)  # train/validation/test date ranges
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|completed|failed
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict)  # per split
    equity_curve: Mapped[list[Any]] = mapped_column(default=list)
    warnings: Mapped[list[Any]] = mapped_column(default=list)
    error: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_id: Mapped[int] = mapped_column(ForeignKey("backtests.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    split: Mapped[str] = mapped_column(String(12))
    signal_date: Mapped[date] = mapped_column(Date)
    entry_date: Mapped[date] = mapped_column(Date)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_price: Mapped[float | None] = mapped_column(Float)
    quantity: Mapped[Decimal] = mapped_column(Qty)
    gross_pnl: Mapped[Decimal | None] = mapped_column(Money)
    charges: Mapped[Decimal | None] = mapped_column(Money)
    net_pnl: Mapped[Decimal | None] = mapped_column(Money)
    exit_reason: Mapped[str | None] = mapped_column(String(40))
    holding_sessions: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)

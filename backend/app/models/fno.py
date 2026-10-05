from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FnoFuture(Base):
    __tablename__ = "fno_data"
    underlying: Mapped[str] = mapped_column(String(32), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    expiry: Mapped[date] = mapped_column(Date, primary_key=True)
    instrument: Mapped[str] = mapped_column(String(8))  # STF | IDF
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    settle: Mapped[float | None] = mapped_column(Float)
    underlying_price: Mapped[float | None] = mapped_column(Float)
    oi: Mapped[int] = mapped_column(BigInteger, default=0)
    change_oi: Mapped[int] = mapped_column(BigInteger, default=0)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    lot_size: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OptionChainRow(Base):
    __tablename__ = "option_chain"
    underlying: Mapped[str] = mapped_column(String(32), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    expiry: Mapped[date] = mapped_column(Date, primary_key=True)
    strike: Mapped[float] = mapped_column(Float, primary_key=True)
    option_type: Mapped[str] = mapped_column(String(2), primary_key=True)  # CE | PE
    close: Mapped[float | None] = mapped_column(Float)
    settle: Mapped[float | None] = mapped_column(Float)
    underlying_price: Mapped[float | None] = mapped_column(Float)
    oi: Mapped[int] = mapped_column(BigInteger, default=0)
    change_oi: Mapped[int] = mapped_column(BigInteger, default=0)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    iv: Mapped[float | None] = mapped_column(Float)  # computed (Black-76/BS), annualised decimal
    source: Mapped[str] = mapped_column(String(64))


class FnoSnapshot(Base):
    """Per-underlying daily F&O analytics."""

    __tablename__ = "fno_snapshots"
    underlying: Mapped[str] = mapped_column(String(32), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    spot: Mapped[float | None] = mapped_column(Float)
    fut_price: Mapped[float | None] = mapped_column(Float)
    basis: Mapped[float | None] = mapped_column(Float)
    basis_pct: Mapped[float | None] = mapped_column(Float)
    fut_oi: Mapped[int | None] = mapped_column(BigInteger)
    fut_oi_change_pct: Mapped[float | None] = mapped_column(Float)
    fut_volume: Mapped[int | None] = mapped_column(BigInteger)
    pcr_oi: Mapped[float | None] = mapped_column(Float)
    pcr_volume: Mapped[float | None] = mapped_column(Float)
    max_pain: Mapped[float | None] = mapped_column(Float)
    call_resistance: Mapped[float | None] = mapped_column(Float)
    put_support: Mapped[float | None] = mapped_column(Float)
    atm_iv: Mapped[float | None] = mapped_column(Float)
    iv_percentile: Mapped[float | None] = mapped_column(Float)
    buildup: Mapped[str | None] = mapped_column(String(24))
    interpretation: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

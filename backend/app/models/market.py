"""Reference + market data tables."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Exchange(Base):
    __tablename__ = "exchanges"
    code: Mapped[str] = mapped_column(String(8), primary_key=True)  # NSE / BSE
    name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")


class Sector(Base):
    __tablename__ = "sectors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    # The NSE sector index used to measure this sector's strength (e.g. "Nifty IT").
    index_name: Mapped[str | None] = mapped_column(String(120))


class Stock(Base, TimestampMixin):
    __tablename__ = "stocks"
    __table_args__ = (UniqueConstraint("symbol", "exchange_code", name="uq_stock_symbol_exchange"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange_code: Mapped[str] = mapped_column(ForeignKey("exchanges.code"), default="NSE")
    name: Mapped[str] = mapped_column(String(255))
    isin: Mapped[str | None] = mapped_column(String(16), index=True)
    series: Mapped[str | None] = mapped_column(String(8))
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))
    industry: Mapped[str | None] = mapped_column(String(160))
    listing_date: Mapped[date | None] = mapped_column(Date)
    face_value: Mapped[float | None] = mapped_column(Float)
    is_fno: Mapped[bool] = mapped_column(Boolean, default=False)
    fno_lot_size: Mapped[int | None] = mapped_column(Integer)
    index_memberships: Mapped[list[Any]] = mapped_column(default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    surveillance_flags: Mapped[list[Any]] = mapped_column(default=list)  # e.g. ASM/GSM stages
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)

    sector: Mapped[Sector | None] = relationship(lazy="joined")


class OHLCV(Base):
    """Daily bars, raw (unadjusted) as published by the exchange.

    Adjusted series are computed on read using `price_adjustments`.
    """

    __tablename__ = "ohlcv"
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    prev_close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    turnover: Mapped[float | None] = mapped_column(Float)  # INR
    trades: Mapped[int | None] = mapped_column(BigInteger)
    delivery_qty: Mapped[int | None] = mapped_column(BigInteger)
    delivery_pct: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IndexOHLCV(Base):
    __tablename__ = "index_ohlcv"
    index_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    turnover_cr: Mapped[float | None] = mapped_column(Float)
    pe: Mapped[float | None] = mapped_column(Float)
    pb: Mapped[float | None] = mapped_column(Float)
    div_yield: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PriceQuote(Base):
    """Latest/intraday quote snapshots from a real-time-capable provider (if configured)."""

    __tablename__ = "prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ltp: Mapped[float] = mapped_column(Float)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    prev_close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    vwap: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_delayed: Mapped[bool] = mapped_column(Boolean, default=True)


class PriceAdjustment(Base):
    """Multiplicative factor applied to all bars strictly before `ex_date` (splits, bonus, rights)."""

    __tablename__ = "price_adjustments"
    __table_args__ = (UniqueConstraint("stock_id", "ex_date", name="uq_adj_stock_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    ex_date: Mapped[date] = mapped_column(Date)
    factor: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(40))  # exchange_prev_close | corporate_action | manual
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CorporateAction(Base):
    __tablename__ = "corporate_actions"
    __table_args__ = (UniqueConstraint("stock_id", "ex_date", "subject", name="uq_ca"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    ex_date: Mapped[date | None] = mapped_column(Date, index=True)
    record_date: Mapped[date | None] = mapped_column(Date)
    action_type: Mapped[str] = mapped_column(String(32))  # dividend|split|bonus|rights|buyback|demerger|other
    subject: Mapped[str] = mapped_column(String(500))
    ratio_from: Mapped[float | None] = mapped_column(Float)
    ratio_to: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any]] = mapped_column(default=dict)


class MarketHoliday(Base):
    __tablename__ = "market_holidays"
    exchange_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    segment: Mapped[str] = mapped_column(String(16), primary_key=True, default="CM")
    description: Mapped[str] = mapped_column(String(255))
    is_special_session: Mapped[bool] = mapped_column(Boolean, default=False)
    session_open: Mapped[str | None] = mapped_column(String(8))  # for special sessions, "HH:MM"
    session_close: Mapped[str | None] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(64), default="nse")


class MarketBreadth(Base):
    __tablename__ = "market_breadth"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    universe: Mapped[str] = mapped_column(String(40), primary_key=True, default="ALL_EQ")
    advances: Mapped[int] = mapped_column(Integer)
    declines: Mapped[int] = mapped_column(Integer)
    unchanged: Mapped[int] = mapped_column(Integer)
    pct_above_20dma: Mapped[float | None] = mapped_column(Float)
    pct_above_50dma: Mapped[float | None] = mapped_column(Float)
    pct_above_200dma: Mapped[float | None] = mapped_column(Float)
    new_52w_highs: Mapped[int | None] = mapped_column(Integer)
    new_52w_lows: Mapped[int | None] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InstitutionalFlow(Base):
    __tablename__ = "institutional_flows"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    category: Mapped[str] = mapped_column(String(16), primary_key=True)  # FII | DII
    buy_value_cr: Mapped[float] = mapped_column(Float)
    sell_value_cr: Mapped[float] = mapped_column(Float)
    net_value_cr: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SectorStrength(Base):
    __tablename__ = "sector_strength"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    index_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)  # 0-100
    ret_1w: Mapped[float | None] = mapped_column(Float)
    ret_1m: Mapped[float | None] = mapped_column(Float)
    ret_3m: Mapped[float | None] = mapped_column(Float)
    rs_vs_nifty_1m: Mapped[float | None] = mapped_column(Float)
    rs_vs_nifty_3m: Mapped[float | None] = mapped_column(Float)
    trend: Mapped[str | None] = mapped_column(String(16))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class MarketRegime(Base):
    __tablename__ = "market_regimes"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    regime: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)  # -100..+100 composite
    confidence: Mapped[float] = mapped_column(Float)  # 0-100
    recommended_exposure_pct: Mapped[float] = mapped_column(Float)
    max_positions: Mapped[int] = mapped_column(Integer)
    components: Mapped[dict[str, Any]] = mapped_column(default=dict)
    missing_inputs: Mapped[list[Any]] = mapped_column(default=list)
    model_version: Mapped[str] = mapped_column(String(32))

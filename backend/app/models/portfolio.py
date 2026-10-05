"""Portfolios, transactions, FIFO tax lots, realized gains and the trade journal."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money, Qty, TimestampMixin, UTCDateTime


class Portfolio(Base, TimestampMixin):
    __tablename__ = "portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(12), default="live")  # live | paper | model
    broker: Mapped[str | None] = mapped_column(String(80))
    charge_schedule_id: Mapped[int | None] = mapped_column(ForeignKey("charges.id"))
    starting_cash: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    side: Mapped[str] = mapped_column(String(4))  # BUY | SELL
    quantity: Mapped[Decimal] = mapped_column(Qty)
    price: Mapped[Decimal] = mapped_column(Money)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    trade_time: Mapped[str | None] = mapped_column(String(8))
    segment: Mapped[str] = mapped_column(String(12), default="delivery")  # delivery | intraday
    exchange: Mapped[str] = mapped_column(String(8), default="NSE")
    broker: Mapped[str | None] = mapped_column(String(80))
    charges_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    charges_breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict)
    charges_source: Mapped[str] = mapped_column(String(20), default="estimated")  # estimated | user | broker_import
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import | paper | system
    # Fair market value on 31-Jan-2018 per share (s.112A grandfathering; only for shares bought on/before that date).
    fmv_31jan2018: Mapped[Decimal | None] = mapped_column(Money)
    external_id: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())

    stock = relationship("Stock", lazy="joined")


class PortfolioPosition(Base, TimestampMixin):
    """User-managed risk levels for a holding. Quantity/cost are always derived from lots."""

    __tablename__ = "portfolio_positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "stock_id", name="uq_position"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    stop: Mapped[float | None] = mapped_column(Float)
    target1: Mapped[float | None] = mapped_column(Float)
    target2: Mapped[float | None] = mapped_column(Float)
    trailing_stop: Mapped[float | None] = mapped_column(Float)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))
    thesis: Mapped[str | None] = mapped_column(Text)


class TaxLot(Base):
    __tablename__ = "tax_lots"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    buy_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"))  # None for bonus lots
    is_bonus: Mapped[bool] = mapped_column(default=False)
    acquired_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(Qty)
    remaining_quantity: Mapped[Decimal] = mapped_column(Qty)
    cost_per_share: Mapped[Decimal] = mapped_column(Money)
    buy_charges: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    buy_stt: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    fmv_31jan2018: Mapped[Decimal | None] = mapped_column(Money)  # grandfathering input, user-supplied


class RealizedGain(Base):
    """One FIFO match of a sell against a lot."""

    __tablename__ = "tax_calculations"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    sell_transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"))
    lot_id: Mapped[int] = mapped_column(ForeignKey("tax_lots.id", ondelete="CASCADE"))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    acquired_date: Mapped[date] = mapped_column(Date)
    sold_date: Mapped[date] = mapped_column(Date, index=True)
    purchase_value: Mapped[Decimal] = mapped_column(Money)
    sale_value: Mapped[Decimal] = mapped_column(Money)
    buy_charges: Mapped[Decimal] = mapped_column(Money)
    sell_charges: Mapped[Decimal] = mapped_column(Money)
    stt_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    capital_gain: Mapped[Decimal] = mapped_column(Money)  # per tax rules (STT not deductible)
    trading_pnl: Mapped[Decimal] = mapped_column(Money)  # after ALL charges, before income tax
    holding_days: Mapped[int] = mapped_column(Integer)
    term: Mapped[str] = mapped_column(String(8))  # STCG | LTCG | SPEC (intraday)
    tax_year: Mapped[str] = mapped_column(String(8), index=True)
    tax_rule_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rules.id"))
    flags: Mapped[list[Any]] = mapped_column(default=list)


class Trade(Base, TimestampMixin):
    """Trade journal (one round trip / idea)."""

    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="live")  # live | paper | system | user
    origin: Mapped[str] = mapped_column(String(12), default="user")  # user | system
    status: Mapped[str] = mapped_column(String(8), default="open")  # open | closed
    entry_date: Mapped[date] = mapped_column(Date)
    entry_price: Mapped[Decimal] = mapped_column(Money)
    quantity: Mapped[Decimal] = mapped_column(Qty)
    stop: Mapped[float | None] = mapped_column(Float)
    target: Mapped[float | None] = mapped_column(Float)
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_price: Mapped[Decimal | None] = mapped_column(Money)
    reason_entry: Mapped[str | None] = mapped_column(Text)
    reason_exit: Mapped[str | None] = mapped_column(Text)
    market_regime: Mapped[str | None] = mapped_column(String(20))
    score_at_entry: Mapped[float | None] = mapped_column(Float)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))
    gross_pnl: Mapped[Decimal | None] = mapped_column(Money)
    charges: Mapped[Decimal | None] = mapped_column(Money)
    tax_estimate: Mapped[Decimal | None] = mapped_column(Money)
    net_pnl: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)
    attachment_url: Mapped[str | None] = mapped_column(Text)

    stock = relationship("Stock", lazy="joined")


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    order_type: Mapped[str] = mapped_column(String(8))  # MARKET | LIMIT
    limit_price: Mapped[float | None] = mapped_column(Float)
    stop: Mapped[float | None] = mapped_column(Float)
    target: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | filled | cancelled | expired
    valid_till: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    filled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    fill_price: Mapped[float | None] = mapped_column(Float)
    fill_note: Mapped[str | None] = mapped_column(String(255))
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"))

    stock = relationship("Stock", lazy="joined")

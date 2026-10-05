"""Indicators, scanner signals, recommendations and their tracked outcomes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("component", "version", name="uq_model_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    component: Mapped[str] = mapped_column(String(40))  # scoring | indicators | regime | levels | tax_rules | model
    version: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class TechnicalSnapshot(Base):
    __tablename__ = "technical_indicators"
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    indicator_version: Mapped[str] = mapped_column(String(16), primary_key=True)
    values: Mapped[dict[str, Any]] = mapped_column(default=dict)
    patterns: Mapped[dict[str, Any]] = mapped_column(default=dict)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime())


class ScanRun(Base):
    """One execution of the Top-10 pipeline."""

    __tablename__ = "recommendation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)  # the session the ideas are FOR
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    data_as_of: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(20))  # running | ok | ok_no_candidates | data_unavailable | data_stale
    universe_size: Mapped[int] = mapped_column(Integer, default=0)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0)
    rejection_counts: Mapped[dict[str, Any]] = mapped_column(default=dict)
    regime_id: Mapped[int | None] = mapped_column(ForeignKey("market_regimes.id"))
    model_version: Mapped[str] = mapped_column(String(32))
    scoring_version: Mapped[str] = mapped_column(String(32))
    indicator_version: Mapped[str] = mapped_column(String(32))
    levels_version: Mapped[str] = mapped_column(String(32))
    tax_rule_version: Mapped[str | None] = mapped_column(String(32))
    weights: Mapped[dict[str, Any]] = mapped_column(default=dict)
    data_quality: Mapped[dict[str, Any]] = mapped_column(default=dict)
    notes: Mapped[list[Any]] = mapped_column(default=list)
    trigger: Mapped[str] = mapped_column(String(20), default="scheduled")


class Signal(Base):
    """Scored candidate for every eligible stock in a run (top-10 and the rest)."""

    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recommendation_runs.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)
    setup: Mapped[str | None] = mapped_column(String(80))
    components: Mapped[dict[str, Any]] = mapped_column(default=dict)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reasons: Mapped[list[Any]] = mapped_column(default=list)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recommendation_runs.id", ondelete="CASCADE"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    data_as_of: Mapped[datetime] = mapped_column(UTCDateTime())
    rank: Mapped[int] = mapped_column(Integer)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    action: Mapped[str] = mapped_column(String(8))  # BUY | WAIT | HOLD | SELL
    suitability: Mapped[str] = mapped_column(String(24))  # observation | paper_trading | live_consideration
    score: Mapped[float] = mapped_column(Float)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict)
    confidence: Mapped[float] = mapped_column(Float)
    setup: Mapped[str] = mapped_column(String(80))
    strategy: Mapped[str] = mapped_column(String(40))
    cmp: Mapped[float] = mapped_column(Float)
    aggressive_entry: Mapped[float | None] = mapped_column(Float)
    entry_low: Mapped[float] = mapped_column(Float)
    entry_high: Mapped[float] = mapped_column(Float)
    conservative_low: Mapped[float | None] = mapped_column(Float)
    conservative_high: Mapped[float | None] = mapped_column(Float)
    no_chase_above: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    trailing_stop_after_t1: Mapped[float | None] = mapped_column(Float)
    target1: Mapped[float] = mapped_column(Float)
    target2: Mapped[float | None] = mapped_column(Float)
    target3: Mapped[float | None] = mapped_column(Float)
    risk_pct: Mapped[float] = mapped_column(Float)
    reward_pcts: Mapped[list[Any]] = mapped_column(default=list)
    rr: Mapped[float] = mapped_column(Float)
    holding_min_sessions: Mapped[int] = mapped_column(Integer)
    holding_max_sessions: Mapped[int] = mapped_column(Integer)
    why: Mapped[list[Any]] = mapped_column(default=list)
    why_not: Mapped[list[Any]] = mapped_column(default=list)
    invalidation: Mapped[str] = mapped_column(Text)
    methodology: Mapped[dict[str, Any]] = mapped_column(default=dict)
    data_sources: Mapped[list[Any]] = mapped_column(default=list)
    missing_components: Mapped[list[Any]] = mapped_column(default=list)
    market_regime: Mapped[str | None] = mapped_column(String(20))
    sector: Mapped[str | None] = mapped_column(String(120))
    model_version: Mapped[str] = mapped_column(String(32))
    scoring_version: Mapped[str] = mapped_column(String(32))
    indicator_version: Mapped[str] = mapped_column(String(32))
    levels_version: Mapped[str] = mapped_column(String(32))
    tax_rule_version: Mapped[str | None] = mapped_column(String(32))
    ai_explanation: Mapped[dict[str, Any] | None] = mapped_column(default=None, nullable=True)

    stock = relationship("Stock", lazy="joined")
    outcome = relationship("RecommendationOutcome", uselist=False, lazy="joined", back_populates="recommendation")


class RecommendationOutcome(Base):
    __tablename__ = "recommendation_outcomes"
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | not_triggered | open | target1 | target2 | target3 | stopped | expired | invalid_data
    entry_date: Mapped[date | None] = mapped_column(Date)
    entry_price: Mapped[float | None] = mapped_column(Float)
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_price: Mapped[float | None] = mapped_column(Float)
    exit_reason: Mapped[str | None] = mapped_column(String(40))
    t1_hit_date: Mapped[date | None] = mapped_column(Date)
    t2_hit_date: Mapped[date | None] = mapped_column(Date)
    t3_hit_date: Mapped[date | None] = mapped_column(Date)
    stop_hit_date: Mapped[date | None] = mapped_column(Date)
    mfe_pct: Mapped[float | None] = mapped_column(Float)
    mae_pct: Mapped[float | None] = mapped_column(Float)
    return_pct: Mapped[float | None] = mapped_column(Float)
    sessions_held: Mapped[int | None] = mapped_column(Integer)
    last_evaluated_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[list[Any]] = mapped_column(default=list)

    recommendation = relationship("Recommendation", back_populates="outcome")

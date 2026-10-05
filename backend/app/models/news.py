from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime


class NewsItem(Base):
    __tablename__ = "news"
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id", ondelete="SET NULL"), index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), index=True)
    company: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(120))
    source_tier: Mapped[str] = mapped_column(String(20))  # primary | reputable | other
    headline: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime())
    event_type: Mapped[str] = mapped_column(String(40), default="other")
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)  # -1..1
    sentiment_label: Mapped[str] = mapped_column(String(12), default="neutral")
    impact: Mapped[str] = mapped_column(String(8), default="low")  # low | medium | high
    horizon: Mapped[str] = mapped_column(String(16), default="short")  # intraday | short | medium | long
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)  # true only for primary-source filings
    classifier: Mapped[str] = mapped_column(String(40), default="rules-v1")
    dedupe_hash: Mapped[str] = mapped_column(String(64), unique=True)
    raw: Mapped[dict[str, Any]] = mapped_column(default=dict)


class NewsSentiment(Base):
    """AI analysis of a news item, keeping FACT / INTERPRETATION / SPECULATION separate."""

    __tablename__ = "news_sentiment"
    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(16))
    facts: Mapped[list[Any]] = mapped_column(default=list)
    interpretation: Mapped[list[Any]] = mapped_column(default=list)
    speculation: Mapped[list[Any]] = mapped_column(default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    sentiment: Mapped[float | None] = mapped_column(Float)
    event_type: Mapped[str | None] = mapped_column(String(40))
    guardrail_flags: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())

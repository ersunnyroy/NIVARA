from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import JSON, DateTime, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """timestamptz that always round-trips as a timezone-aware UTC datetime (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


# JSONB on Postgres, plain JSON elsewhere (tests use SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")
Money = Numeric(20, 4)
Qty = Numeric(20, 4)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict] = {
        dict[str, Any]: JSONType,
        list[Any]: JSONType,
        Decimal: Money,
        datetime: UTCDateTime(),
    }


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

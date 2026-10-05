from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import JSON, DateTime, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB on Postgres, plain JSON elsewhere (tests use SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")
Money = Numeric(20, 4)
Qty = Numeric(20, 4)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict] = {
        dict[str, Any]: JSONType,
        list[Any]: JSONType,
        Decimal: Money,
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

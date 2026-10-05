"""Time helpers. All persisted timestamps are timezone-aware UTC; display is IST."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()


def to_ist(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def ist_datetime(d: date, hh: int = 0, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=IST)


def fy_of(d: date) -> str:
    """Indian financial / tax year label for a date, e.g. 2026-10-05 -> '2026-27'."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def fy_bounds(fy: str) -> tuple[date, date]:
    start = int(fy.split("-")[0])
    return date(start, 4, 1), date(start + 1, 3, 31)

"""Indian equity market calendar (NSE cash segment).

Handles weekends, exchange holidays, special sessions (e.g. Muhurat trading on a holiday/weekend),
pre-open, regular session and post-close. Holidays come from the exchange's holiday master (stored in
`market_holidays`); if that table is empty we say so instead of guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from app.core.timeutil import IST, now_ist

PRE_OPEN = time(9, 0)
OPEN = time(9, 15)
CLOSE = time(15, 30)
EOD_DATA_READY = time(18, 30)  # official EOD files are typically published by early evening


@dataclass(slots=True)
class SpecialSession:
    date: date
    open: time
    close: time
    description: str


@dataclass
class MarketCalendar:
    holidays: dict[date, str] = field(default_factory=dict)
    special_sessions: dict[date, SpecialSession] = field(default_factory=dict)
    holidays_loaded: bool = False

    def is_trading_day(self, d: date) -> bool:
        if d in self.special_sessions:
            return True
        if d.weekday() >= 5:
            return False
        return d not in self.holidays

    def session_hours(self, d: date) -> tuple[time, time] | None:
        if d in self.special_sessions:
            s = self.special_sessions[d]
            return s.open, s.close
        return (OPEN, CLOSE) if self.is_trading_day(d) else None

    def previous_trading_day(self, d: date) -> date:
        x = d - timedelta(days=1)
        for _ in range(30):
            if self.is_trading_day(x):
                return x
            x -= timedelta(days=1)
        raise RuntimeError("No trading day found in previous 30 days")

    def next_trading_day(self, d: date) -> date:
        x = d + timedelta(days=1)
        for _ in range(30):
            if self.is_trading_day(x):
                return x
            x += timedelta(days=1)
        raise RuntimeError("No trading day found in next 30 days")

    def trading_days(self, start: date, end: date) -> list[date]:
        out, x = [], start
        while x <= end:
            if self.is_trading_day(x):
                out.append(x)
            x += timedelta(days=1)
        return out

    def sessions_between(self, start: date, end: date) -> int:
        """Number of trading sessions strictly after start up to and including end."""
        return len(self.trading_days(start + timedelta(days=1), end)) if end > start else 0

    def status(self, now: datetime | None = None) -> dict:
        now = (now or now_ist()).astimezone(IST)
        d, t = now.date(), now.time()
        hours = self.session_hours(d)
        if hours is None:
            phase = "weekend" if d.weekday() >= 5 and d not in self.special_sessions else "holiday"
        elif t < PRE_OPEN:
            phase = "pre_market"
        elif t < hours[0]:
            phase = "pre_open"
        elif t <= hours[1]:
            phase = "open"
        else:
            phase = "post_close"
        if hours is not None and t >= EOD_DATA_READY:
            last_eod = d
        elif hours is not None and phase in ("open", "post_close", "pre_open", "pre_market"):
            last_eod = self.previous_trading_day(d)
        else:
            last_eod = self.previous_trading_day(d + timedelta(days=1))
        # The session that recommendations generated now are intended for.
        if hours is not None and t < hours[1]:
            target = d
        else:
            target = self.next_trading_day(d)
        return {
            "now_ist": now.isoformat(),
            "date": d.isoformat(),
            "phase": phase,
            "is_open": phase == "open",
            "is_trading_day": hours is not None,
            "holiday_name": self.holidays.get(d),
            "special_session": self.special_sessions.get(d).description if d in self.special_sessions else None,
            "last_completed_eod_session": last_eod.isoformat(),
            "target_session": target.isoformat(),
            "next_trading_day": self.next_trading_day(d).isoformat(),
            "holidays_loaded": self.holidays_loaded,
            "hours": {"pre_open": PRE_OPEN.isoformat("minutes"), "open": (hours or (OPEN, CLOSE))[0].isoformat("minutes"),
                      "close": (hours or (OPEN, CLOSE))[1].isoformat("minutes")},
        }


def load_calendar(db, exchange: str = "NSE") -> MarketCalendar:
    from app.models import MarketHoliday

    rows = db.query(MarketHoliday).filter(MarketHoliday.exchange_code == exchange, MarketHoliday.segment == "CM").all()
    cal = MarketCalendar(holidays_loaded=bool(rows))
    for r in rows:
        if r.is_special_session:
            o = time.fromisoformat(r.session_open or "18:00")
            c = time.fromisoformat(r.session_close or "19:00")
            cal.special_sessions[r.date] = SpecialSession(r.date, o, c, r.description)
        else:
            cal.holidays[r.date] = r.description
    return cal

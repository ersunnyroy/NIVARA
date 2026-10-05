from datetime import date, datetime, time

from app.core.timeutil import IST
from app.market_calendar.calendar import MarketCalendar, SpecialSession

CAL = MarketCalendar(holidays={date(2026, 10, 2): "Gandhi Jayanti"}, holidays_loaded=True,
                     special_sessions={date(2026, 11, 8): SpecialSession(date(2026, 11, 8), time(18, 0), time(19, 0),
                                                                         "Muhurat trading")})


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_weekend_and_holiday():
    assert not CAL.is_trading_day(date(2026, 10, 3))  # Saturday
    assert not CAL.is_trading_day(date(2026, 10, 2))  # holiday
    assert CAL.previous_trading_day(date(2026, 10, 5)) == date(2026, 10, 1)
    assert CAL.next_trading_day(date(2026, 10, 1)) == date(2026, 10, 5)


def test_phases_and_eod_session():
    s = CAL.status(at(2026, 10, 5, 8, 30))
    assert s["phase"] == "pre_market" and s["last_completed_eod_session"] == "2026-10-01"
    assert CAL.status(at(2026, 10, 5, 9, 5))["phase"] == "pre_open"
    assert CAL.status(at(2026, 10, 5, 11, 0))["is_open"] is True
    s = CAL.status(at(2026, 10, 5, 16, 0))
    assert s["phase"] == "post_close" and s["last_completed_eod_session"] == "2026-10-01"  # files not yet published
    assert CAL.status(at(2026, 10, 5, 19, 0))["last_completed_eod_session"] == "2026-10-05"
    h = CAL.status(at(2026, 10, 2, 11, 0))
    assert h["phase"] == "holiday" and h["is_open"] is False and h["holiday_name"] == "Gandhi Jayanti"
    assert CAL.status(at(2026, 10, 3, 11, 0))["phase"] == "weekend"


def test_never_open_on_closed_days_and_special_session():
    assert CAL.status(at(2026, 10, 4, 12, 0))["is_open"] is False
    sp = CAL.status(at(2026, 11, 8, 18, 30))  # Sunday Muhurat session
    assert sp["is_open"] is True and sp["special_session"] == "Muhurat trading"


def test_sessions_between():
    assert CAL.sessions_between(date(2026, 10, 1), date(2026, 10, 6)) == 2  # 5th, 6th

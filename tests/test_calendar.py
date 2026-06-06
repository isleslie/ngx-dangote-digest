from datetime import date

from ngx_digest.calendar import is_trading_day


def test_weekday_is_trading_day():
    assert is_trading_day(date(2026, 6, 5))  # Friday


def test_weekend_is_not_trading_day():
    assert not is_trading_day(date(2026, 6, 6))  # Saturday
    assert not is_trading_day(date(2026, 6, 7))  # Sunday


def test_holiday_is_not_trading_day():
    holidays = {date(2026, 6, 5)}
    assert not is_trading_day(date(2026, 6, 5), holidays=holidays)

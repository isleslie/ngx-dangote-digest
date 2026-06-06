from datetime import date

from ngx_digest.calendar import NGX_HOLIDAYS, is_trading_day


def test_weekday_is_trading_day():
    assert is_trading_day(date(2026, 6, 5))  # Friday


def test_weekend_is_not_trading_day():
    assert not is_trading_day(date(2026, 6, 6))  # Saturday
    assert not is_trading_day(date(2026, 6, 7))  # Sunday


def test_holiday_is_not_trading_day():
    holidays = {date(2026, 6, 5)}
    assert not is_trading_day(date(2026, 6, 5), holidays=holidays)


def test_populated_ngx_holidays_are_skipped():
    # Democracy Day 2026 is a Friday (a weekday) but a public holiday.
    democracy_day = date(2026, 6, 12)
    assert democracy_day.weekday() < 5  # it IS a weekday
    assert democracy_day in NGX_HOLIDAYS
    assert not is_trading_day(democracy_day)  # ...yet not a trading day


def test_default_holiday_set_is_populated():
    assert len(NGX_HOLIDAYS) >= 13  # the 2026 federal holidays are loaded

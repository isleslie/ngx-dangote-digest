"""NGX trading-day logic.

The NGX is closed on weekends and on Nigerian public holidays. Fetching on a
closed day yields stale or empty data, so the agent should skip those days
gracefully rather than error.

NOTE: the holiday set below is a *placeholder*. Nigerian public holidays
(and ad-hoc market closures) shift year to year and some are declared on
short notice. Populate this from the official NGX holiday calendar and update
it annually.
"""
from __future__ import annotations

from datetime import date

# TODO: replace with the official NGX holiday calendar for the relevant year(s).
NGX_HOLIDAYS: set[date] = set()


def is_trading_day(day: date, holidays: set[date] | None = None) -> bool:
    """True if ``day`` is a weekday and not a known market holiday."""
    if day.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    return day not in (holidays if holidays is not None else NGX_HOLIDAYS)

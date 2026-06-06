"""NGX trading-day logic.

The NGX is closed on weekends and on Nigerian public holidays. Fetching on a
closed day yields stale or empty data, so the agent should skip those days
gracefully rather than error.

NOTE: Nigerian public holidays (and ad-hoc market closures) shift year to year
and the moon-dependent Islamic ones are sometimes declared only days ahead.
Keep ``NGX_HOLIDAYS`` updated annually from the official NGX / Federal
Government calendar, and add future years as they are published.
"""
from __future__ import annotations

from datetime import date

# Federal public holidays the NGX observes. Weekend-falling holidays (e.g.
# Boxing Day 2026) are already covered by the weekday check, but are listed for
# completeness. Islamic holidays (Eid al-Fitr, Eid al-Adha, Mawlid) follow the
# lunar calendar and can move by a day on short notice — verify each year.
NGX_HOLIDAYS: set[date] = {
    # --- 2026 (official Federal Government declarations) ---
    date(2026, 1, 1),    # New Year's Day
    date(2026, 3, 19),   # Eid al-Fitr
    date(2026, 3, 20),   # Eid al-Fitr (second day)
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 6),    # Easter Monday
    date(2026, 5, 1),    # Workers' Day
    date(2026, 5, 27),   # Eid al-Adha (Id el Kabir)
    date(2026, 5, 28),   # Eid al-Adha (second day)
    date(2026, 6, 12),   # Democracy Day
    date(2026, 8, 25),   # Eid Milad un-Nabi (Mawlid)
    date(2026, 10, 1),   # Independence Day
    date(2026, 12, 25),  # Christmas Day
    date(2026, 12, 26),  # Boxing Day (Saturday)
}


def is_trading_day(day: date, holidays: set[date] | None = None) -> bool:
    """True if ``day`` is a weekday and not a known market holiday."""
    if day.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    return day not in (holidays if holidays is not None else NGX_HOLIDAYS)

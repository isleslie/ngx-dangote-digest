"""Normalized data schema for a single ticker's daily quote."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Quote:
    """One trading day of data for one ticker.

    Prices are in Nigerian naira (NGN). Any field may be ``None`` if the
    source did not provide it for that day.
    """

    ticker: str
    trade_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    prev_close: float | None
    volume: int | None

    @property
    def change(self) -> float | None:
        """Absolute price change vs the previous close."""
        if self.close is None or self.prev_close is None:
            return None
        return round(self.close - self.prev_close, 4)

    @property
    def pct_change(self) -> float | None:
        """Percentage change vs the previous close."""
        if self.close is None or not self.prev_close:
            return None
        return round((self.close - self.prev_close) / self.prev_close * 100, 4)

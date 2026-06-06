"""SQLite persistence for daily quotes.

History accumulates over time — that growing history is what makes the
eventual summary interesting, so we store every fetch rather than just the
latest snapshot. Writes are idempotent on ``(ticker, trade_date)`` so a
re-run on the same day overwrites rather than duplicates.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Quote

_SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
    ticker      TEXT    NOT NULL,
    trade_date  TEXT    NOT NULL,          -- ISO 8601 (YYYY-MM-DD)
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    prev_close  REAL,
    volume      INTEGER,
    fetched_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, trade_date)
);
"""


class QuoteStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_SCHEMA)

    def upsert(self, quote: Quote) -> None:
        self._conn.execute(
            """
            INSERT INTO quotes
                (ticker, trade_date, open, high, low, close, prev_close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, trade_date) DO UPDATE SET
                open       = excluded.open,
                high       = excluded.high,
                low        = excluded.low,
                close      = excluded.close,
                prev_close = excluded.prev_close,
                volume     = excluded.volume,
                fetched_at = datetime('now');
            """,
            (
                quote.ticker,
                quote.trade_date.isoformat(),
                quote.open,
                quote.high,
                quote.low,
                quote.close,
                quote.prev_close,
                quote.volume,
            ),
        )
        self._conn.commit()

    def upsert_many(self, quotes) -> None:
        for q in quotes:
            self.upsert(q)

    def history(self, ticker: str, limit: int = 30) -> list[dict]:
        """Most recent ``limit`` rows for a ticker, newest first."""
        rows = self._conn.execute(
            "SELECT * FROM quotes WHERE ticker = ? "
            "ORDER BY trade_date DESC LIMIT ?;",
            (ticker, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def latest(self, ticker: str) -> dict | None:
        rows = self.history(ticker, limit=1)
        return rows[0] if rows else None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "QuoteStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

import sqlite3
from datetime import date

from ngx_digest.models import Quote
from ngx_digest.storage import QuoteStore


def make_quote(close=530.0, prev=525.0, day=date(2026, 6, 5)):
    return Quote("DANGCEM", day, 520.0, 535.5, 518.0, close, prev, 1000)


def test_roundtrip(tmp_path):
    with QuoteStore(tmp_path / "t.db") as store:
        store.upsert(make_quote())
        latest = store.latest("DANGCEM")
    assert latest["close"] == 530.0
    assert latest["ticker"] == "DANGCEM"


def test_upsert_is_idempotent_on_same_day(tmp_path):
    with QuoteStore(tmp_path / "t.db") as store:
        store.upsert(make_quote(close=530.0))
        store.upsert(make_quote(close=540.0))  # same (ticker, date) -> overwrite
        hist = store.history("DANGCEM")
    assert len(hist) == 1
    assert hist[0]["close"] == 540.0


def test_history_is_newest_first(tmp_path):
    with QuoteStore(tmp_path / "t.db") as store:
        store.upsert(make_quote(day=date(2026, 6, 3)))
        store.upsert(make_quote(day=date(2026, 6, 4)))
        store.upsert(make_quote(day=date(2026, 6, 5)))
        hist = store.history("DANGCEM", limit=2)
    assert [r["trade_date"] for r in hist] == ["2026-06-05", "2026-06-04"]


def test_latest_on_empty_db_is_none(tmp_path):
    with QuoteStore(tmp_path / "t.db") as store:
        assert store.latest("DANGCEM") is None


def test_close_checkpoints_wal_so_db_is_self_contained(tmp_path):
    db = tmp_path / "t.db"
    with QuoteStore(db) as store:  # __exit__ -> close() checkpoints the WAL
        store.upsert(make_quote(close=530.0))

    # Simulate committing only the .db (as CI does): drop the WAL sidecars.
    for suffix in ("-wal", "-shm"):
        sidecar = db.with_name(db.name + suffix)
        if sidecar.exists():
            sidecar.unlink()

    # The data must still be there, read straight from the main file.
    with QuoteStore(db) as store:
        assert store.latest("DANGCEM")["close"] == 530.0


def test_market_cap_fields_roundtrip(tmp_path):
    q = Quote(
        "DANGCEM", date(2026, 6, 5), 1180.0, None, None, 1180.0, 1180.0, 1136842,
        market_cap=19_910_799_916_180.0, shares_outstanding=16_873_559_251,
    )
    with QuoteStore(tmp_path / "t.db") as store:
        store.upsert(q)
        latest = store.latest("DANGCEM")
    assert latest["market_cap"] == 19_910_799_916_180.0
    assert latest["shares_outstanding"] == 16_873_559_251


def test_migrates_old_database_in_place(tmp_path):
    db = tmp_path / "old.db"
    # Simulate a pre-enrichment database (no market_cap / shares_outstanding).
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE quotes (ticker TEXT NOT NULL, trade_date TEXT NOT NULL, "
        "open REAL, high REAL, low REAL, close REAL, prev_close REAL, "
        "volume INTEGER, fetched_at TEXT NOT NULL DEFAULT (datetime('now')), "
        "PRIMARY KEY (ticker, trade_date));"
    )
    conn.execute(
        "INSERT INTO quotes (ticker, trade_date, close) VALUES ('DANGCEM','2026-06-04',1170.0);"
    )
    conn.commit()
    conn.close()

    with QuoteStore(db) as store:  # opening must add the new columns
        store.upsert(make_quote(day=date(2026, 6, 5)))
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(quotes);")}
        old = store.latest("DANGCEM")
    assert {"market_cap", "shares_outstanding"} <= cols
    assert old["close"] == 530.0  # newest row still readable post-migration

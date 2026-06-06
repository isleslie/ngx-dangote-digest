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

from datetime import date
from pathlib import Path

from ngx_digest.fetcher import parse_quote, parse_stats_table

FIXTURE = Path(__file__).parent / "fixtures" / "sample_quote.html"


def test_parse_stats_table_lowercases_labels():
    stats = parse_stats_table(FIXTURE.read_text())
    assert stats["open"] == "520.00"
    assert stats["previous close"] == "525.00"


def test_parse_quote_extracts_all_fields():
    q = parse_quote(FIXTURE.read_text(), "DANGCEM", date(2026, 6, 5))
    assert q.open == 520.0
    assert q.high == 535.5
    assert q.low == 518.0
    assert q.close == 530.0
    assert q.prev_close == 525.0
    assert q.volume == 1_234_567  # comma stripped


def test_parse_quote_computes_change():
    q = parse_quote(FIXTURE.read_text(), "DANGCEM", date(2026, 6, 5))
    assert q.change == 5.0
    assert round(q.pct_change, 2) == 0.95


def test_parser_is_resilient_to_missing_fields():
    html = "<table><tr><th>Close</th><td>100</td></tr></table>"
    q = parse_quote(html, "NASCON", date(2026, 6, 5))
    assert q.close == 100.0
    assert q.open is None
    assert q.pct_change is None  # no prev_close -> undefined, not a crash

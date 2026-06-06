from datetime import date
from pathlib import Path

import pytest

from ngx_digest.fetcher import (
    index_equities_json,
    parse_company_profile,
    parse_equities_quote,
    parse_quote,
    parse_stats_table,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_quote.html"
NGX_FIXTURE = Path(__file__).parent / "fixtures" / "ngx_equities.json"
PROFILE_FIXTURE = Path(__file__).parent / "fixtures" / "company_profile.html"


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


# --- NGX official statistics (JSON) source, against a saved real payload ----


def test_ngx_json_index_is_keyed_by_uppercased_symbol():
    index = index_equities_json(NGX_FIXTURE.read_text())
    assert {"DANGCEM", "DANGSUGAR", "NASCON"} <= set(index)


def test_ngx_parse_extracts_all_fields():
    # DANGSUGAR is a full-range day: every OHLC field is populated.
    q = parse_equities_quote(NGX_FIXTURE.read_text(), "DANGSUGAR")
    assert q.open == 70.35
    assert q.high == 72.0
    assert q.low == 71.5
    assert q.close == 72.0
    assert q.prev_close == 70.35
    assert q.volume == 5_924_847  # exact integer, not abbreviated "5.9M"
    assert isinstance(q.volume, int)


def test_ngx_uses_payload_trade_date_not_wall_clock():
    # The endpoint serves the latest session; its TradeDate wins over the arg.
    q = parse_equities_quote(NGX_FIXTURE.read_text(), "DANGCEM", date(2030, 1, 1))
    assert q.trade_date == date(2026, 6, 5)


def test_ngx_tolerates_null_high_low():
    # On a flat day NGX returns null High/Low; that must be None, not a crash.
    q = parse_equities_quote(NGX_FIXTURE.read_text(), "DANGCEM")
    assert q.high is None
    assert q.low is None
    assert q.close == 1180.0
    assert q.prev_close == 1180.0


def test_ngx_case_insensitive_lookup():
    q = parse_equities_quote(NGX_FIXTURE.read_text(), "nascon")
    assert q.ticker == "nascon"
    assert q.close == 219.5


def test_ngx_unknown_ticker_raises():
    with pytest.raises(KeyError):
        parse_equities_quote(NGX_FIXTURE.read_text(), "NOTREAL")


# --- NGX company-profile (market cap / shares outstanding) ------------------


def test_profile_parses_market_cap_and_shares():
    prof = parse_company_profile(PROFILE_FIXTURE.read_text())
    assert prof["market_cap"] == 19_910_799_916_180.0  # ₦ commas stripped
    assert prof["shares_outstanding"] == 16_873_559_251  # ".00" -> exact int
    assert isinstance(prof["shares_outstanding"], int)


def test_profile_market_cap_equals_shares_times_close():
    # Internal-consistency check NGX itself satisfies (close = 1180.00).
    prof = parse_company_profile(PROFILE_FIXTURE.read_text())
    assert round(prof["shares_outstanding"] * 1180.0, 2) == prof["market_cap"]


def test_profile_missing_fields_are_none():
    prof = parse_company_profile("<html><body>no data here</body></html>")
    assert prof["market_cap"] is None
    assert prof["shares_outstanding"] is None

"""Fetch and parse daily quotes.

Design notes
------------
* ``parse_quote`` is deliberately separated from HTTP retrieval so you can
  unit-test parsing against saved HTML without hitting the network.
* The parser is *source-agnostic*: it reads a generic two-column stats table
  (label / value) and maps common label spellings to our schema. Most NGX
  data pages expose data in a table like this. If your chosen source differs,
  adjust ``parse_stats_table`` and/or ``_LABEL_MAP`` — run the CLI with
  ``--save-html`` first to dump the real page and inspect its structure.
* Always check a source's terms of use / robots.txt before scraping, and set
  a descriptive User-Agent (see config/tickers.yaml).
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from .models import Quote

# Maps our schema fields to the label spellings sources commonly use.
_LABEL_MAP: dict[str, tuple[str, ...]] = {
    "open": ("open", "opening price", "open price"),
    "high": ("high", "day high", "high price", "day's high"),
    "low": ("low", "day low", "low price", "day's low"),
    "close": ("close", "last", "price", "last price", "closing price", "last traded price"),
    "prev_close": ("previous close", "prev close", "previous closing price", "p. close", "prev. close"),
    "volume": ("volume", "vol", "traded volume", "shares traded", "volume traded"),
}


def _to_float(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in ("", "-", ".", "--"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_int(text: str | None) -> int | None:
    f = _to_float(text)
    return int(f) if f is not None else None


def parse_stats_table(html: str) -> dict[str, str]:
    """Flatten any 2+ column table rows into a ``{lowercased label: value}`` map."""
    soup = BeautifulSoup(html, "html.parser")
    stats: dict[str, str] = {}
    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True).lower()
            val = cells[1].get_text(strip=True)
            if key and key not in stats:
                stats[key] = val
    return stats


def _lookup(stats: dict[str, str], field: str) -> str | None:
    for label in _LABEL_MAP[field]:
        if label in stats:
            return stats[label]
    return None


def parse_quote(html: str, ticker: str, trade_date: date) -> Quote:
    stats = parse_stats_table(html)
    return Quote(
        ticker=ticker,
        trade_date=trade_date,
        open=_to_float(_lookup(stats, "open")),
        high=_to_float(_lookup(stats, "high")),
        low=_to_float(_lookup(stats, "low")),
        close=_to_float(_lookup(stats, "close")),
        prev_close=_to_float(_lookup(stats, "prev_close")),
        volume=_to_int(_lookup(stats, "volume")),
    )


# ---------------------------------------------------------------------------
# NGX official statistics source (JSON)
# ---------------------------------------------------------------------------
# Active data source. The NGX powers its public "Equities Price List" page from
# a keyless REST endpoint that returns one JSON record per listed equity:
#
#   https://doclib.ngxgroup.com/REST/api/statistics/equities/
#       ?market=&sector=&orderby=&pageSize=300&pageNo=0
#
# It is the authoritative exchange data (30-minute delayed), needs no API key,
# and is plain server-side JSON, so a single request covers every ticker. The
# parsing helpers below are deliberately HTTP-free so they can be unit-tested
# against a saved JSON fixture (see tests/fixtures/ngx_equities.json).

# Our schema field -> the NGX REST key that holds it.
_NGX_FIELD_MAP: dict[str, str] = {
    "open": "OpeningPrice",
    "high": "HighPrice",
    "low": "LowPrice",
    "close": "ClosePrice",
    "prev_close": "PrevClosingPrice",
    "volume": "Volume",
}


def _num(value) -> float | None:
    """Coerce an NGX numeric field (already a JSON number, a string, or null)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return _to_float(str(value))


def _parse_trade_date(value) -> date | None:
    """Parse the NGX ``TradeDate`` ("2026-06-05T00:00:00") into a ``date``."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def index_equities_json(payload: str | bytes | list | dict) -> dict[str, dict]:
    """Index an NGX equities-statistics payload by upper-cased ticker symbol."""
    data = payload if isinstance(payload, (list, dict)) else json.loads(payload)
    # The endpoint returns a bare list today; tolerate a wrapped object too.
    rows = data
    if isinstance(data, dict):
        for key in ("data", "Data", "result", "Result", "items"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    out: dict[str, dict] = {}
    for record in rows:
        symbol = str(record.get("Symbol", "")).strip().upper()
        if symbol and symbol not in out:
            out[symbol] = record
    return out


def quote_from_record(
    record: dict, ticker: str, trade_date: date | None = None
) -> Quote:
    """Build a :class:`Quote` from one NGX statistics record.

    The record's own ``TradeDate`` is authoritative (the endpoint only ever
    serves the latest trading session); ``trade_date`` is a fallback.
    """
    volume = _num(record.get(_NGX_FIELD_MAP["volume"]))
    return Quote(
        ticker=ticker,
        trade_date=_parse_trade_date(record.get("TradeDate"))
        or trade_date
        or date.today(),
        open=_num(record.get(_NGX_FIELD_MAP["open"])),
        high=_num(record.get(_NGX_FIELD_MAP["high"])),
        low=_num(record.get(_NGX_FIELD_MAP["low"])),
        close=_num(record.get(_NGX_FIELD_MAP["close"])),
        prev_close=_num(record.get(_NGX_FIELD_MAP["prev_close"])),
        volume=int(round(volume)) if volume is not None else None,
    )


def parse_equities_quote(
    payload: str | bytes | list | dict, ticker: str, trade_date: date | None = None
) -> Quote:
    """Parse one ticker's quote out of a full NGX statistics payload."""
    index = index_equities_json(payload)
    record = index.get(ticker.strip().upper())
    if record is None:
        raise KeyError(f"ticker {ticker!r} not found in NGX statistics payload")
    return quote_from_record(record, ticker, trade_date)


class QuoteFetcher(ABC):
    @abstractmethod
    def fetch(self, ticker: str, trade_date: date | None = None) -> Quote: ...


class HttpQuoteFetcher(QuoteFetcher):
    """Fetches each ticker from ``<base_url>/<TICKER>`` and parses the page."""

    def __init__(
        self,
        base_url: str,
        session: requests.Session | None = None,
        user_agent: str | None = None,
        timeout: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        if user_agent:
            self.session.headers["User-Agent"] = user_agent

    def url_for(self, ticker: str) -> str:
        return f"{self.base_url}/{ticker}"

    def fetch_html(self, ticker: str) -> str:
        resp = self.session.get(self.url_for(ticker), timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    def fetch(self, ticker: str, trade_date: date | None = None) -> Quote:
        return parse_quote(self.fetch_html(ticker), ticker, trade_date or date.today())


class NgxStatisticsFetcher(QuoteFetcher):
    """Fetches the NGX equities-statistics JSON once and serves every ticker.

    Unlike a per-ticker page scraper, this source returns all listed equities
    in a single response, so the payload is fetched once per run and cached;
    each ``fetch`` resolves its ticker from that cached payload.
    """

    def __init__(
        self,
        base_url: str,
        session: requests.Session | None = None,
        user_agent: str | None = None,
        timeout: int = 20,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.session = session or requests.Session()
        if user_agent:
            self.session.headers["User-Agent"] = user_agent
        self._payload: str | None = None
        self._index: dict[str, dict] | None = None

    def fetch_payload(self, refresh: bool = False) -> str:
        """Return the raw JSON payload, fetching (and caching) it once."""
        if self._payload is None or refresh:
            resp = self.session.get(self.base_url, timeout=self.timeout)
            resp.raise_for_status()
            self._payload = resp.text
            self._index = None
        return self._payload

    def index(self, refresh: bool = False) -> dict[str, dict]:
        if self._index is None or refresh:
            self._index = index_equities_json(self.fetch_payload(refresh=refresh))
        return self._index

    def fetch(self, ticker: str, trade_date: date | None = None) -> Quote:
        record = self.index().get(ticker.strip().upper())
        if record is None:
            raise KeyError(f"ticker {ticker!r} not found in NGX statistics payload")
        return quote_from_record(record, ticker, trade_date)

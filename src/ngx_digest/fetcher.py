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

import re
from abc import ABC, abstractmethod
from datetime import date

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

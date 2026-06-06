# NGX Dangote Daily Digest

A small agent that fetches daily market data for the publicly listed **Dangote**
companies on the **Nigerian Exchange (NGX)**, stores a growing history, and
(roadmap) summarizes it into a daily report.

> **Disclaimer:** This is an educational / informational portfolio project. It
> is **not financial advice**. Scraped market data can lag, be incomplete, or
> contain errors. Always verify against an official source before relying on any
> figure, and respect each data source's terms of use and `robots.txt`.

## Tracked tickers

| Ticker      | Company                    |
| ----------- | -------------------------- |
| `DANGCEM`   | Dangote Cement             |
| `DANGSUGAR` | Dangote Sugar Refinery     |
| `NASCON`    | NASCON Allied Industries   |

The Dangote Petroleum Refinery is **not yet listed** (an IPO has been announced).
The ticker list lives in [`config/tickers.yaml`](config/tickers.yaml), so adding
it later is a one-line config change — no code edits.

## Status

- [x] **Fetch & store** — retrieve, normalize, and persist daily quotes (this slice)
- [ ] Daily report renderer (Markdown / HTML + a per-ticker price chart)
- [ ] LLM summarization over recent history
- [ ] Delivery (email / chat webhook) on a schedule (cron or GitHub Actions)

## Architecture

```
config/tickers.yaml         # tickers + data-source settings
        │
        ▼
HttpQuoteFetcher  ──fetch_html──▶  parse_quote  ──▶  Quote        (src/ngx_digest/fetcher.py, models.py)
        │                                              │
        │                                              ▼
   is_trading_day?  (skip weekends/holidays)       QuoteStore  ──▶  SQLite (data/quotes.db)
   (src/ngx_digest/calendar.py)                    (src/ngx_digest/storage.py)
```

Parsing is intentionally decoupled from HTTP so it can be unit-tested against
saved HTML. The parser reads a generic two-column stats table and maps common
label spellings to the schema, so it adapts to most NGX data pages with little
or no change.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the test suite
pytest

# Fetch today's quotes into data/quotes.db
ngx-digest

# Backfill a specific day
ngx-digest --date 2026-06-04

# Fetch even on a weekend/holiday
ngx-digest --force
```

## Pointing it at a real data source

The shipped `config/tickers.yaml` uses a placeholder `base_url`. To wire up a
real source:

1. Pick a source and **read its terms of use / `robots.txt`** first. Prefer an
   official API over scraping where one exists.
2. Set `source.base_url` so that each ticker page resolves to
   `<base_url>/<TICKER>`, and set a descriptive `user_agent`.
3. Dump a real page and confirm the parser finds the fields:
   ```bash
   ngx-digest --save-html debug/ --force
   ```
   Inspect `debug/DANGCEM.html`. If the page isn't a simple stats table, adjust
   `parse_stats_table` / `_LABEL_MAP` in `src/ngx_digest/fetcher.py`.

## Trading calendar

`is_trading_day` skips weekends and a holiday set in
`src/ngx_digest/calendar.py`. **That holiday set is a placeholder** — populate it
from the official NGX calendar and update annually.

## Layout

```
ngx-dangote-digest/
├── config/tickers.yaml          # source + ticker config
├── src/ngx_digest/
│   ├── models.py                # Quote dataclass + change/pct_change
│   ├── storage.py               # SQLite layer (idempotent upsert)
│   ├── fetcher.py               # HTTP retrieval + HTML parsing
│   ├── calendar.py              # trading-day logic
│   └── cli.py                   # entrypoint
├── tests/                       # parser, storage, calendar tests + fixture
├── data/                        # SQLite db lives here (gitignored)
└── pyproject.toml
```

## License

MIT (or your choice) — add a `LICENSE` file.

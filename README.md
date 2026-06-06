# NGX Dangote Daily Digest

A small agent that fetches daily market data for the publicly listed **Dangote**
companies on the **Nigerian Exchange (NGX)**, stores a growing history in SQLite,
and renders a daily report (Markdown + HTML with sparkline charts).

> **Disclaimer:** This is an educational / informational portfolio project. It
> is **not financial advice**. Market data can lag, be incomplete, or contain
> errors. Always verify against an official source before relying on any figure,
> and respect each data source's terms of use and `robots.txt`.

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

- [x] **Fetch & store** — retrieve, normalize, and persist daily quotes
- [x] **Daily report renderer** — Markdown + HTML with a per-ticker sparkline
- [x] **Automation** — scheduled GitHub Action: DB commit-back + GitHub Pages
- [ ] LLM summarization over recent history
- [ ] Delivery (email / chat webhook)

## Data source

Quotes come from the **official NGX equities-statistics endpoint** — the keyless
JSON feed that powers NGX's public *Equities Price List*. A single request
returns one record per listed equity, so it covers every ticker at once:

```
https://doclib.ngxgroup.com/REST/api/statistics/equities/?market=&sector=&orderby=&pageSize=300&pageNo=0
```

It provides **open, high, low, close, previous close, volume** and the session's
`TradeDate`. Market cap and shares outstanding are not in that feed, so they are
enriched per ticker from the NGX **company-profile** page (also keyless,
server-rendered). The endpoints are configured in
[`config/tickers.yaml`](config/tickers.yaml).

Notes & etiquette:

- Data is **~30 minutes delayed** (NGX's stated delay).
- **Educational / non-commercial use only** — NGX asserts copyright over its
  market data; do not redistribute it commercially.
- `robots.txt`: `doclib.ngxgroup.com` has none; `ngxgroup.com` only disallows
  `/wp-admin/`. Requests are low-volume (one stats call + one profile call per
  ticker per day) with an honest `User-Agent` set in config.
- The feed serves only the **latest** session — there is no historical backfill,
  so `--date` does not fetch past days. Stored rows key on the source's own
  `TradeDate`, and the report header reflects that date.

## Architecture

```
config/tickers.yaml          # tickers + data-source settings
        │
        ▼
NgxStatisticsFetcher ─┐
CompanyProfileFetcher ─┴─ parse ─▶ Quote ─▶ QuoteStore ─▶ SQLite (data/quotes.db)
   (src/.../fetcher.py)         (models.py)   (storage.py)        │
        ▲                                                         ▼
   is_trading_day?  (skips weekends + NGX holidays)         report renderer
   (src/.../calendar.py)                                    (src/.../report.py)
                                                          ├─ Markdown → repo
                                                          └─ HTML+SVG → Pages
```

Parsing is intentionally decoupled from HTTP so it can be unit-tested against
saved fixtures (`tests/fixtures/`). Rendering is likewise split into a single
DB-touching builder and pure `render_*` functions.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the test suite
pytest

# Fetch the latest session's quotes into data/quotes.db
ngx-digest

# Fetch even on a weekend/holiday (re-fetches the latest session in place)
ngx-digest --force

# Render the digest from stored history
ngx-report                       # Markdown to stdout
ngx-report --format html --out reports/digest.html
ngx-report --days 60             # widen the trend window
```

`ngx-digest --save-html debug/` dumps the raw JSON payload and the per-ticker
profile HTML for debugging the parsers.

## What it stores

One row per `(ticker, trade_date)` in `data/quotes.db`, idempotent on re-run:

`open`, `high`, `low`, `close`, `prev_close`, `volume`, `market_cap`,
`shares_outstanding`, plus `fetched_at`. Any field may be `null` when the source
did not provide it (e.g. high/low on a flat day). `change` / `pct_change` are
derived. `close()` checkpoints the WAL so the `.db` is self-contained and safe
to commit.

## Reports

`ngx-report` renders from stored history (`--format md|html`, `--days`, `--date`,
`--out`). The chart is a dependency-free sparkline: an inline **SVG** in the HTML
report, and a **Unicode** block sparkline (`▁▃▅▇█`) in Markdown (GitHub strips
inline `<svg>` from Markdown but renders block characters).

In CI the reports live in two places:

- **Markdown** is committed to the repo — `reports/latest.md` plus a dated
  archive `reports/history/<session>.md` — so it renders on GitHub.
- **HTML** (with SVG charts) is published to **GitHub Pages**.

## Automation

[`.github/workflows/daily-digest.yml`](.github/workflows/daily-digest.yml) runs
weekdays at 15:00 UTC (16:00 WAT, after the NGX close + the data delay). Each run
fetches, commits the updated `data/quotes.db` and Markdown report back to the
repo, and deploys the HTML to Pages. It uses the built-in `GITHUB_TOKEN` — no
secrets. On a non-trading day the fetch is skipped and no empty report is
committed. A manual run (**Actions → Run workflow**) offers a **force** toggle
for end-to-end testing on a weekend.

[`.github/workflows/tests.yml`](.github/workflows/tests.yml) runs `pytest` on
every push and pull request (Python 3.10 and 3.12).

> **Pages prerequisites:** enable Pages with **Settings → Pages → Source =
> GitHub Actions**. Pages on a *private* repo requires a paid plan (or make the
> repo public); the DB + Markdown commit-back works regardless.

## Trading calendar

`is_trading_day` skips weekends and the NGX public-holiday set in
[`src/ngx_digest/calendar.py`](src/ngx_digest/calendar.py), currently populated
for **2026**. The moon-dependent Islamic holidays can shift by a day on short
notice — verify and extend the set each year against the official NGX / Federal
Government calendar.

## Layout

```
ngx-dangote-digest/
├── config/tickers.yaml          # source + ticker config
├── src/ngx_digest/
│   ├── models.py                # Quote dataclass + change/pct_change
│   ├── storage.py               # SQLite layer (idempotent upsert, WAL checkpoint)
│   ├── fetcher.py               # HTTP retrieval + parsing (stats JSON + profile)
│   ├── calendar.py              # trading-day logic + NGX holidays
│   ├── report.py                # report builder + Markdown/HTML renderers
│   └── cli.py                   # ngx-digest entrypoint
├── tests/                       # parser/storage/calendar/report tests + fixtures
├── .github/workflows/           # daily digest (+ Pages) and test CI
├── data/                        # SQLite db (committed by CI; gitignored locally)
└── pyproject.toml
```

## License

[MIT](LICENSE).

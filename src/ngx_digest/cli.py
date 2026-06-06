"""Command-line entrypoint for the fetch-and-store step.

Examples
--------
    ngx-digest                          # fetch today's quotes into data/quotes.db
    ngx-digest --date 2026-06-04        # backfill a specific day
    ngx-digest --save-html debug/       # also dump raw HTML for selector tuning
    ngx-digest --force                  # fetch even on a non-trading day
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import yaml

from .calendar import is_trading_day
from .fetcher import HttpQuoteFetcher, parse_quote
from .storage import QuoteStore


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_fetch(
    config_path: str | Path,
    db_path: str | Path,
    on_date: date | None = None,
    save_html_dir: str | None = None,
    force: bool = False,
) -> None:
    config = load_config(config_path)
    on_date = on_date or date.today()

    if not force and not is_trading_day(on_date):
        print(f"{on_date} is not an NGX trading day — skipping. Use --force to override.")
        return

    src = config["source"]
    fetcher = HttpQuoteFetcher(src["base_url"], user_agent=src.get("user_agent"))

    print(f"Fetching {len(config['tickers'])} tickers for {on_date} ...")
    with QuoteStore(db_path) as store:
        for entry in config["tickers"]:
            symbol = entry["symbol"]
            try:
                if save_html_dir:
                    html = fetcher.fetch_html(symbol)
                    out = Path(save_html_dir)
                    out.mkdir(parents=True, exist_ok=True)
                    (out / f"{symbol}.html").write_text(html, encoding="utf-8")
                    quote = parse_quote(html, symbol, on_date)
                else:
                    quote = fetcher.fetch(symbol, on_date)
                store.upsert(quote)
                print(
                    f"  {symbol:10s} close={quote.close} "
                    f"chg%={quote.pct_change} vol={quote.volume}"
                )
            except Exception as exc:  # keep going so one bad ticker doesn't abort the run
                print(f"  {symbol:10s} FAILED: {exc}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="NGX Dangote digest — fetch & store step")
    p.add_argument("--config", default="config/tickers.yaml")
    p.add_argument("--db", default="data/quotes.db")
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--save-html", dest="save_html", metavar="DIR",
                   help="dump raw HTML per ticker for selector debugging")
    p.add_argument("--force", action="store_true",
                   help="fetch even on weekends/holidays")
    args = p.parse_args(argv)

    on_date = date.fromisoformat(args.date) if args.date else date.today()
    run_fetch(args.config, args.db, on_date, args.save_html, args.force)


if __name__ == "__main__":
    main()

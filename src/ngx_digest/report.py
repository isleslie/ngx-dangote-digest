"""Render a daily digest from stored quote history.

Design notes
------------
* Rendering is split into a single DB-touching step (``build_report_data``)
  and several **pure** ``render_*`` functions (data -> string). The pure
  functions take an explicit ``as_of`` date rather than calling
  ``date.today()`` so their output is deterministic and unit-testable.
* Two sparkline renderers, both dependency-free strings:
  - ``render_sparkline_svg`` for the HTML report (renders in browsers).
  - ``render_sparkline_unicode`` for the Markdown report (GitHub strips inline
    <svg>, but block characters render anywhere — markdown, terminals).
"""
from __future__ import annotations

import argparse
import html as _html
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from .storage import QuoteStore


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TickerReport:
    ticker: str
    name: str
    latest: dict | None                       # newest stored row, or None
    closes: list[float] = field(default_factory=list)  # oldest -> newest

    @property
    def close(self) -> float | None:
        return self.latest.get("close") if self.latest else None

    @property
    def prev_close(self) -> float | None:
        return self.latest.get("prev_close") if self.latest else None

    @property
    def change(self) -> float | None:
        if self.close is None or self.prev_close is None:
            return None
        return round(self.close - self.prev_close, 4)

    @property
    def pct_change(self) -> float | None:
        if self.close is None or not self.prev_close:
            return None
        return round((self.close - self.prev_close) / self.prev_close * 100, 4)


@dataclass(frozen=True)
class ReportData:
    as_of: date
    tickers: list[TickerReport]


def build_report_data(
    store: QuoteStore,
    tickers: list[dict],
    days: int = 30,
    as_of: date | None = None,
) -> ReportData:
    """Assemble report data from the store for the configured tickers."""
    reports: list[TickerReport] = []
    for entry in tickers:
        symbol = entry["symbol"]
        history = store.history(symbol, limit=days)  # newest first
        closes = [r["close"] for r in reversed(history) if r["close"] is not None]
        reports.append(
            TickerReport(
                ticker=symbol,
                name=entry.get("name", symbol),
                latest=history[0] if history else None,
                closes=closes,
            )
        )
    # Default the header date to the data's own latest trade date, so the
    # report stays self-consistent even when generated a day after the session.
    if as_of is None:
        dates = [
            r.latest["trade_date"]
            for r in reports
            if r.latest and r.latest.get("trade_date")
        ]
        as_of = max(date.fromisoformat(d) for d in dates) if dates else date.today()
    return ReportData(as_of=as_of, tickers=reports)


# --------------------------------------------------------------------------- #
# Formatting helpers (pure)
# --------------------------------------------------------------------------- #
def _fmt_price(x: float | None) -> str:
    return "—" if x is None else f"{x:,.2f}"


def _fmt_int(x: int | None) -> str:
    return "—" if x is None else f"{int(x):,}"


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:+.2f}%"


def _fmt_naira_compact(x: float | None) -> str:
    """Abbreviate a naira figure: 19_910_799_916_180 -> '₦19.91T'."""
    if x is None:
        return "—"
    for divisor, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(x) >= divisor:
            return f"₦{x / divisor:.2f}{suffix}"
    return f"₦{x:.2f}"


# --------------------------------------------------------------------------- #
# Sparklines (pure)
# --------------------------------------------------------------------------- #
_BLOCKS = "▁▂▃▄▅▆▇█"


def render_sparkline_unicode(closes: list[float]) -> str:
    """A block-character sparkline, e.g. '▁▃▅█'. Empty if <2 points."""
    pts = [c for c in closes if c is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    last = len(_BLOCKS) - 1
    return "".join(_BLOCKS[round((c - lo) / span * last)] for c in pts)


def render_sparkline_svg(
    closes: list[float], width: int = 160, height: int = 40, pad: int = 2
) -> str:
    """An inline SVG polyline sparkline. Empty string if <2 points.

    The newest point's direction colours the line (green up, red down, grey
    flat). The highest price maps to y=pad (top), the lowest to y=height-pad.
    """
    pts = [c for c in closes if c is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    n = len(pts)
    coords = []
    for i, c in enumerate(pts):
        x = pad + (width - 2 * pad) * i / (n - 1)
        y = pad + (height - 2 * pad) * (1 - (c - lo) / span)
        coords.append(f"{x:.1f},{y:.1f}")
    points = " ".join(coords)
    color = "#16a34a" if pts[-1] > pts[0] else "#dc2626" if pts[-1] < pts[0] else "#6b7280"
    return (
        f'<svg class="sparkline" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.5" '
        f'points="{points}"/></svg>'
    )


# --------------------------------------------------------------------------- #
# Renderers (pure)
# --------------------------------------------------------------------------- #
def render_markdown(data: ReportData) -> str:
    lines = [
        f"# NGX Dangote Daily Digest — {data.as_of.isoformat()}",
        "",
        "| Ticker | Company | Close (₦) | Change | % | Volume | Mkt cap | Trend |",
        "| ------ | ------- | --------: | -----: | -: | -----: | ------: | :---- |",
    ]
    for t in data.tickers:
        vol = t.latest.get("volume") if t.latest else None
        mcap = t.latest.get("market_cap") if t.latest else None
        spark = render_sparkline_unicode(t.closes) or "—"
        lines.append(
            f"| {t.ticker} | {t.name} | {_fmt_price(t.close)} | "
            f"{_fmt_price(t.change)} | {_fmt_pct(t.pct_change)} | "
            f"{_fmt_int(vol)} | {_fmt_naira_compact(mcap)} | {spark} |"
        )
    lines += [
        "",
        "_Not financial advice. Data via NGX (~30-min delayed); verify before use._",
        "",
    ]
    return "\n".join(lines)


def render_html(data: ReportData) -> str:
    rows = []
    for t in data.tickers:
        vol = t.latest.get("volume") if t.latest else None
        mcap = t.latest.get("market_cap") if t.latest else None
        pct = t.pct_change
        cls = "up" if (pct or 0) > 0 else "down" if (pct or 0) < 0 else "flat"
        spark = render_sparkline_svg(t.closes) or "—"
        rows.append(
            "<tr>"
            f"<td class=\"ticker\">{_html.escape(t.ticker)}</td>"
            f"<td>{_html.escape(t.name)}</td>"
            f"<td class=\"num\">{_fmt_price(t.close)}</td>"
            f"<td class=\"num {cls}\">{_fmt_price(t.change)}</td>"
            f"<td class=\"num {cls}\">{_fmt_pct(pct)}</td>"
            f"<td class=\"num\">{_fmt_int(vol)}</td>"
            f"<td class=\"num\">{_fmt_naira_compact(mcap)}</td>"
            f"<td class=\"spark\">{spark}</td>"
            "</tr>"
        )
    body = "\n".join(rows)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NGX Dangote Daily Digest — {data.as_of.isoformat()}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ padding: .4rem .6rem; border-bottom: 1px solid #e5e7eb; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .ticker {{ font-weight: 600; }}
  .up {{ color: #16a34a; }} .down {{ color: #dc2626; }} .flat {{ color: #6b7280; }}
  .spark svg {{ vertical-align: middle; }}
  footer {{ margin-top: 1rem; color: #6b7280; font-size: .85rem; }}
</style>
</head>
<body>
<h1>NGX Dangote Daily Digest — {data.as_of.isoformat()}</h1>
<table>
<thead><tr>
<th>Ticker</th><th>Company</th><th>Close (₦)</th><th>Change</th>
<th>%</th><th>Volume</th><th>Mkt cap</th><th>Trend</th>
</tr></thead>
<tbody>
{body}
</tbody>
</table>
<footer>Not financial advice. Data via NGX (~30-min delayed); verify before use.</footer>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="NGX Dangote digest — report renderer")
    p.add_argument("--config", default="config/tickers.yaml")
    p.add_argument("--db", default="data/quotes.db")
    p.add_argument("--format", choices=("md", "html"), default="md")
    p.add_argument("--days", type=int, default=30, help="history window for trend")
    p.add_argument("--date", help="as-of date YYYY-MM-DD "
                   "(default: the data's latest trade date)")
    p.add_argument("--out", help="write to this file (default: stdout)")
    args = p.parse_args(argv)

    config = load_config(args.config)
    # Leave as_of as None when unspecified so the header reflects the data's
    # own latest trade date rather than the wall-clock run date.
    as_of = date.fromisoformat(args.date) if args.date else None
    with QuoteStore(args.db) as store:
        data = build_report_data(store, config["tickers"], days=args.days, as_of=as_of)

    text = render_html(data) if args.format == "html" else render_markdown(data)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.format} report to {out}")
    else:
        # The report contains ₦ and block characters; a non-UTF-8 console
        # (e.g. Windows cp1252) would otherwise raise UnicodeEncodeError.
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        print(text)


if __name__ == "__main__":
    main()

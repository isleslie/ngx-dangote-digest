from datetime import date

from bs4 import BeautifulSoup

from ngx_digest import report as report_cli
from ngx_digest.models import Quote
from ngx_digest.report import (
    ReportData,
    TickerReport,
    _fmt_naira_compact,
    _fmt_pct,
    _fmt_price,
    build_report_data,
    render_html,
    render_markdown,
    render_sparkline_svg,
    render_sparkline_unicode,
)
from ngx_digest.storage import QuoteStore


# --- formatting helpers -----------------------------------------------------


def test_formatting_helpers():
    assert _fmt_price(1180.0) == "1,180.00"
    assert _fmt_price(None) == "—"
    assert _fmt_pct(2.345) == "+2.35%"
    assert _fmt_pct(-1.1) == "-1.10%"
    assert _fmt_pct(None) == "—"
    assert _fmt_naira_compact(19_910_799_916_180.0) == "₦19.91T"
    assert _fmt_naira_compact(874_575_233_352.0) == "₦874.58B"
    assert _fmt_naira_compact(None) == "—"


# --- sparklines -------------------------------------------------------------


def test_unicode_sparkline_spans_low_to_high():
    s = render_sparkline_unicode([1.0, 2.0, 3.0, 4.0])
    assert s[0] == "▁" and s[-1] == "█"
    assert len(s) == 4


def test_unicode_sparkline_needs_two_points():
    assert render_sparkline_unicode([]) == ""
    assert render_sparkline_unicode([5.0]) == ""


def test_svg_sparkline_structure_and_scaling():
    svg = render_sparkline_svg([10.0, 20.0, 30.0], width=160, height=40, pad=2)
    soup = BeautifulSoup(svg, "html.parser")
    poly = soup.find("polyline")
    pts = [tuple(map(float, p.split(","))) for p in poly["points"].split()]
    assert len(pts) == 3
    # x spans pad..width-pad
    assert pts[0][0] == 2.0 and pts[-1][0] == 158.0
    # highest price -> top (y=pad); lowest -> bottom (y=height-pad)
    assert pts[-1][1] == 2.0   # 30.0 is the max -> top
    assert pts[0][1] == 38.0   # 10.0 is the min -> bottom


def test_svg_sparkline_colour_reflects_direction():
    assert "#16a34a" in render_sparkline_svg([1.0, 5.0])   # up = green
    assert "#dc2626" in render_sparkline_svg([5.0, 1.0])   # down = red
    assert render_sparkline_svg([7.0]) == ""               # <2 points


# --- renderers (pure, fixed data) ------------------------------------------


def _sample_data():
    return ReportData(
        as_of=date(2026, 6, 5),
        tickers=[
            TickerReport(
                "DANGSUGAR", "Dangote Sugar Refinery",
                latest={"close": 72.0, "prev_close": 70.35, "volume": 5_924_847,
                        "market_cap": 874_575_233_352.0},
                closes=[70.35, 71.0, 72.0],
            ),
            TickerReport(
                "NASCON", "NASCON Allied Industries",
                latest={"close": 219.5, "prev_close": 219.5, "volume": 678_610,
                        "market_cap": 593_182_758_327.5},
                closes=[219.5],  # too short for a sparkline
            ),
        ],
    )


def test_markdown_has_header_values_and_sparkline():
    md = render_markdown(_sample_data())
    assert "NGX Dangote Daily Digest — 2026-06-05" in md
    assert "DANGSUGAR" in md and "72.00" in md and "+2.35%" in md
    assert "₦874.58B" in md
    assert "5,924,847" in md
    # DANGSUGAR has a 3-point trend; NASCON (1 point) falls back to em dash.
    assert "▁" in md or "█" in md
    assert "Not financial advice" in md


def test_html_is_wellformed_and_complete():
    soup = BeautifulSoup(render_html(_sample_data()), "html.parser")
    body_rows = soup.select("tbody tr")
    assert len(body_rows) == 2  # one row per ticker
    first = body_rows[0]
    assert first.select_one(".ticker").get_text() == "DANGSUGAR"
    assert "+2.35%" in first.get_text()
    assert first.select_one("td.num.up") is not None  # positive change styled up
    # the up ticker embeds an SVG sparkline; the 1-point ticker does not
    assert body_rows[0].select_one("svg.sparkline") is not None
    assert body_rows[1].select_one("svg.sparkline") is None


def test_renderers_are_deterministic():
    data = _sample_data()
    assert render_markdown(data) == render_markdown(data)
    assert render_html(data) == render_html(data)


# --- data builder (DB-backed) ----------------------------------------------


def _q(symbol, day, close, prev, vol=1000, mcap=None):
    return Quote(symbol, day, None, None, None, close, prev, vol, market_cap=mcap)


def test_build_report_data_from_store(tmp_path):
    with QuoteStore(tmp_path / "r.db") as store:
        store.upsert(_q("DANGCEM", date(2026, 6, 3), 1100.0, 1090.0))
        store.upsert(_q("DANGCEM", date(2026, 6, 4), 1150.0, 1100.0))
        store.upsert(_q("DANGCEM", date(2026, 6, 5), 1180.0, 1150.0, mcap=1.0e13))
        data = build_report_data(
            store,
            [{"symbol": "DANGCEM", "name": "Dangote Cement"},
             {"symbol": "NASCON", "name": "NASCON Allied Industries"}],
            days=30,
            as_of=date(2026, 6, 5),
        )
    cem = data.tickers[0]
    assert cem.close == 1180.0
    assert cem.change == 30.0
    assert cem.closes == [1100.0, 1150.0, 1180.0]  # oldest -> newest
    # ticker with no stored rows degrades gracefully
    nascon = data.tickers[1]
    assert nascon.latest is None
    assert nascon.close is None
    assert nascon.closes == []


def test_as_of_defaults_to_latest_trade_date_in_data(tmp_path):
    with QuoteStore(tmp_path / "r.db") as store:
        store.upsert(_q("DANGCEM", date(2026, 6, 4), 1150.0, 1100.0))
        store.upsert(_q("DANGCEM", date(2026, 6, 5), 1180.0, 1150.0))
        data = build_report_data(  # no as_of passed
            store, [{"symbol": "DANGCEM", "name": "Dangote Cement"}]
        )
    assert data.as_of == date(2026, 6, 5)  # newest stored session, not today


def test_cli_header_uses_data_date_not_today(tmp_path, capsys):
    db = tmp_path / "r.db"
    with QuoteStore(db) as store:
        store.upsert(_q("DANGCEM", date(2026, 6, 5), 1180.0, 1150.0))
    cfg = tmp_path / "tickers.yaml"
    cfg.write_text(
        "source: {}\ntickers:\n  - symbol: DANGCEM\n    name: Dangote Cement\n",
        encoding="utf-8",
    )
    # No --date: the header must reflect the stored session, not the run date.
    report_cli.main(["--db", str(db), "--config", str(cfg), "--format", "md"])
    out = capsys.readouterr().out
    assert "2026-06-05" in out
    assert date.today().isoformat() not in out  # guards the old run-date bug

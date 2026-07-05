"""Unit tests for message formatting, universe parsing, and channel routing."""
from scanners.format import format_premarket, format_hourly
from scanners.premarket import GapResult
from scanners.hourly import Signal
from scanners.slack import route_channel
from scanners.config import CHANNELS
from scanners.universe import _parse_nasdaq_screener, _parse_wikipedia_sp500


# ---- formatting ----------------------------------------------------------------

def test_format_premarket_empty():
    out = format_premarket("QQQ", [], [])
    assert "QQQ" in out and "No qualifying gaps" in out


def test_format_premarket_content():
    ups = [GapResult("AAA", 5.0, 100, 105, 0)]
    downs = [GapResult("BBB", -4.0, 100, 96, 0)]
    out = format_premarket("S&P 500", ups, downs)
    assert "AAA" in out and "+5.00%" in out
    assert "BBB" in out and "-4.00%" in out


def test_format_hourly_empty():
    assert "No signals" in format_hourly("Scan-Up (buy)", [])


def test_format_hourly_content():
    sig = Signal("NVDA", "up", 104.4, 103.45, 108.4, 4.21, 2.5, 101, 2.0, 2.0)
    out = format_hourly("Scan-Up (buy)", [sig])
    assert "NVDA" in out and "104.40" in out and "108.40" in out and "BUY" in out


# ---- channel routing (priority: ETF > QQQ > S&P 500 > other) -------------------

def test_route_index_etf():
    assert route_channel("QQQ", ["AAPL"], ["AAPL"]) == CHANNELS["index_etf"]
    assert route_channel("IWM", [], []) == CHANNELS["index_etf"]


def test_route_qqq_before_sp500():
    # AAPL is in both QQQ and S&P 500 -> QQQ wins
    assert route_channel("AAPL", ["AAPL"], ["AAPL"]) == CHANNELS["qqq"]


def test_route_sp500():
    assert route_channel("XOM", ["AAPL"], ["XOM"]) == CHANNELS["sp500"]


def test_route_other():
    assert route_channel("RANDOM", ["AAPL"], ["XOM"]) == CHANNELS["other_5b"]


# ---- universe parsers (fixtures, no network) -----------------------------------

def test_parse_nasdaq_screener_filters_by_cap():
    payload = {"data": {"rows": [
        {"symbol": "BIG", "marketCap": "6000000000"},
        {"symbol": "SMALL", "marketCap": "1000000000"},
        {"symbol": "BAD", "marketCap": "n/a"},
        {"symbol": "HUGE", "marketCap": "9000000000"},
    ]}}
    syms = _parse_nasdaq_screener(payload, min_cap=5e9)
    assert syms == ["HUGE", "BIG"]   # sorted by descending cap, small/bad dropped


def test_parse_wikipedia_sp500():
    html = ('<table id="constituents"><tr><th>Symbol</th></tr>'
            '<tr><td><a href="/x">AAPL</a></td><td>Apple</td></tr>'
            '<tr><td><a href="/y">MSFT</a></td><td>Microsoft</td></tr>'
            '<tr><td><a href="/z">AAPL</a></td><td>dup</td></tr></table>')
    assert _parse_wikipedia_sp500(html) == ["AAPL", "MSFT"]

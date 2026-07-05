"""Tests for direction routing, hourly caption, and the post_signal fallback."""
from scanners import slack
from scanners.config import tier_tag, CHANNELS
from scanners.hourly import Signal
from scanners.run_hourly import _caption


def test_tier_tag_priority():
    assert tier_tag("QQQ", ["AAPL"], ["AAPL"]) == "ETF"
    assert tier_tag("AAPL", ["AAPL"], ["AAPL"]) == "QQQ"   # QQQ beats SPX
    assert tier_tag("XOM", ["AAPL"], ["XOM"]) == "SPX"
    assert tier_tag("RANDO", ["AAPL"], ["XOM"]) == "5B"


def test_caption_has_levels_and_breakeven():
    sig = Signal("GATX", "up", 170.08, 169.26, 172.49, 2.93, 1.3, 101, 0.93, 1.48,
                 breakeven_trigger=170.90)
    out = _caption(sig, "5B")
    assert "GATX" in out and "[5B]" in out and "BUY" in out
    assert "170.08" in out and "172.49" in out and "170.90" in out
    assert "breakeven" in out.lower()


def test_up_down_channels_distinct():
    assert CHANNELS["hourly_up"] != CHANNELS["hourly_down"]


def test_post_signal_falls_back_to_text(monkeypatch):
    calls = {}
    monkeypatch.setattr(slack, "post", lambda ch, text, token=None: calls.setdefault("t", (ch, text)))
    # no chart path -> must use text post
    slack.post_signal("C123", "hello", chart_path=None)
    assert calls["t"] == ("C123", "hello")
    # nonexistent chart path -> still text post
    calls.clear()
    slack.post_signal("C123", "again", chart_path="/no/such/file.png")
    assert calls["t"] == ("C123", "again")


def test_index_config_looser_than_hourly():
    from scanners.config import INDEX_30M, HOURLY
    assert INDEX_30M.rvol_min < HOURLY.rvol_min
    assert INDEX_30M.magnitude_tol > HOURLY.magnitude_tol
    assert INDEX_30M.low_near_high_frac > HOURLY.low_near_high_frac

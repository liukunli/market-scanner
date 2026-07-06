"""Unit tests for the daily-trend filter used by the hourly scan."""
from scanners.hourly import Bar
from scanners.trend import completed_daily_bars, daily_sma, trend_aligned


def mk_daily(close, date_ts):
    return Bar(ts=date_ts, open=close, high=close, low=close, close=close, volume=1000)


DAY = 86400


def test_completed_daily_bars_excludes_today():
    bars = [mk_daily(100, 0 * DAY), mk_daily(101, 1 * DAY), mk_daily(102, 2 * DAY)]
    from scanners.timeutil import local_date
    today = local_date(2 * DAY)
    out = completed_daily_bars(bars, today)
    assert len(out) == 2
    assert all(b.ts < 2 * DAY for b in out)


def test_daily_sma_requires_enough_bars():
    bars = [mk_daily(c, i * DAY) for i, c in enumerate([1, 2, 3])]
    assert daily_sma(bars, 5) is None
    assert daily_sma(bars, 3) == 2.0


def test_trend_aligned_up_requires_close_above_sma():
    bars = [mk_daily(c, i * DAY) for i, c in enumerate([90, 95, 100, 105, 110])]
    assert trend_aligned("up", bars, 5) is True   # last close 110 > sma 100
    assert trend_aligned("down", bars, 5) is False


def test_trend_aligned_down_requires_close_below_sma():
    bars = [mk_daily(c, i * DAY) for i, c in enumerate([110, 105, 100, 95, 90])]
    assert trend_aligned("down", bars, 5) is True  # last close 90 < sma 100
    assert trend_aligned("up", bars, 5) is False


def test_trend_aligned_false_when_insufficient_history():
    bars = [mk_daily(100, 0)]
    assert trend_aligned("up", bars, 50) is False
    assert trend_aligned("down", bars, 50) is False


def test_trend_aligned_false_on_empty_bars():
    assert trend_aligned("up", [], 50) is False

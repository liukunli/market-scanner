"""Unit tests for the 1-hour scan-up / scan-down signal engine."""
import pytest

from scanners.hourly import Bar, scan_up, scan_down, evaluate
from scanners.config import HOURLY


def mk(o, h, l, c, v, ts=0):
    return Bar(ts=ts, open=o, high=h, low=l, close=c, volume=v)


def baseline(n=5, vol=100.0):
    """n flat low-volume bars to establish the volume baseline."""
    return [mk(100, 101, 99, 100, vol, ts=i) for i in range(n)]


# ---- scan-up: the canonical passing setup -------------------------------------

def up_bars():
    p = mk(o=100.0, h=102.5, l=99.5, c=102.0, v=200.0, ts=100)   # green, g=2
    c = mk(o=102.4, h=104.6, l=102.3, c=104.4, v=300.0, ts=101)  # green, g=2, stacked
    return baseline() + [p, c]


def test_scan_up_triggers():
    sig = scan_up("TEST", up_bars())
    assert sig is not None
    assert sig.side == "up"
    assert sig.entry == pytest.approx(104.4)
    # stop = midpoint of current bar
    assert sig.stop_loss == pytest.approx((104.6 + 102.3) / 2)
    # take profit = entry + 2 * avg_gain (both gains == 2)
    assert sig.take_profit == pytest.approx(104.4 + 2 * 2.0)
    assert sig.risk_reward > 0
    assert sig.rvol == pytest.approx((200 + 300) / 2 / 100.0)


def test_scan_up_requires_both_green():
    bars = up_bars()
    bars[-2] = mk(102.0, 102.5, 99.5, 100.0, 200.0, ts=100)  # prev now RED
    assert scan_up("TEST", bars) is None


def test_scan_up_requires_low_near_prev_high():
    bars = up_bars()
    # drop current low far below prev high (big gap down within the pair)
    bars[-1] = mk(o=100.6, h=104.6, l=99.6, c=104.4, v=300.0, ts=101)
    assert scan_up("TEST", bars) is None


def test_scan_up_requires_same_magnitude():
    bars = up_bars()
    # current bar grows 10x the previous bar -> magnitude mismatch
    bars[-1] = mk(o=102.4, h=125.0, l=102.3, c=122.0, v=300.0, ts=101)
    assert scan_up("TEST", bars) is None


def test_scan_up_requires_rising_close():
    bars = up_bars()
    # current closes below previous close -> not continuous growth
    bars[-1] = mk(o=101.0, h=102.4, l=101.0, c=101.8, v=300.0, ts=101)
    assert scan_up("TEST", bars) is None


def test_scan_up_requires_volume_above_average():
    bars = up_bars()
    bars[-2] = mk(100.0, 102.5, 99.5, 102.0, 90.0, ts=100)
    bars[-1] = mk(102.4, 104.6, 102.3, 104.4, 90.0, ts=101)  # below baseline avg 100
    assert scan_up("TEST", bars) is None


def test_too_few_bars_returns_none():
    assert scan_up("TEST", up_bars()[-2:]) is None  # only 2 bars < min_bars


# ---- scan-down: mirror image ---------------------------------------------------

def down_bars():
    p = mk(o=100.0, h=100.5, l=97.5, c=98.0, v=200.0, ts=100)    # red, g=2
    c = mk(o=97.6, h=97.7, l=95.4, c=95.6, v=300.0, ts=101)      # red, g=2, stacked down
    return baseline() + [p, c]


def test_scan_down_triggers():
    sig = scan_down("TEST", down_bars())
    assert sig is not None
    assert sig.side == "down"
    assert sig.entry == pytest.approx(95.6)
    assert sig.stop_loss == pytest.approx((97.7 + 95.4) / 2)
    assert sig.take_profit == pytest.approx(95.6 - 2 * 2.0)
    assert sig.risk_reward > 0


def test_scan_down_requires_both_red():
    bars = down_bars()
    bars[-2] = mk(98.0, 100.5, 97.5, 100.0, 200.0, ts=100)  # prev now GREEN
    assert scan_down("TEST", bars) is None


def test_scan_down_requires_high_near_prev_low():
    bars = down_bars()
    bars[-1] = mk(o=99.4, h=100.4, l=95.4, c=95.6, v=300.0, ts=101)  # high back near prev high
    assert scan_down("TEST", bars) is None


def test_up_setup_does_not_trigger_down():
    assert scan_down("TEST", up_bars()) is None


def test_down_setup_does_not_trigger_up():
    assert scan_up("TEST", down_bars()) is None


def test_invalid_side_raises():
    with pytest.raises(ValueError):
        evaluate("TEST", up_bars(), "sideways", HOURLY)


def test_zero_range_bar_returns_none():
    bars = baseline() + [mk(100, 100, 100, 100, 200, ts=100),
                         mk(100, 100, 100, 100, 300, ts=101)]
    assert scan_up("TEST", bars) is None

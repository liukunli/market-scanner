"""Unit tests for the breakeven-moving-stop outcome simulation."""
from scanners.backtest import simulate
from scanners.hourly import Bar


def mk(o, h, l, c, ts=0):
    return Bar(ts=ts, open=o, high=h, low=l, close=c, volume=100)


# For all cases below: LONG, entry=100, stop=99, target=104, breakeven_trigger=101.
ENTRY, STOP, TARGET, BE = 100.0, 99.0, 104.0, 101.0


def series(*forward):
    # index 0 = signal bar; forward bars follow
    return [mk(100, 100, 100, 100)] + list(forward)


def test_target_hit():
    bars = series(mk(101, 104.5, 100.5, 104))     # reaches target
    assert simulate(bars, 0, "up", ENTRY, STOP, TARGET, BE, horizon=2)[0] == "target"


def test_plain_stop_before_breakeven_armed():
    # first bar dips straight to the stop without ever reaching the BE trigger
    bars = series(mk(100, 100.5, 98.5, 99.5))
    out, px, armed = simulate(bars, 0, "up", ENTRY, STOP, TARGET, BE, horizon=2)
    assert out == "stop" and px == STOP and armed is False


def test_breakeven_saves_the_trade():
    # bar 1 reaches BE trigger (high 101.5) but not target -> stop armed to entry;
    # bar 2 pulls back to 100 (entry) -> exits at breakeven, NOT a loss
    bars = series(mk(100, 101.5, 100.2, 101.0),
                  mk(101, 101.2, 99.5, 99.8))
    out, px, armed = simulate(bars, 0, "up", ENTRY, STOP, TARGET, BE, horizon=3)
    assert out == "breakeven" and px == ENTRY and armed is True


def test_breakeven_then_target():
    # arms on bar 1, then bar 2 runs to target
    bars = series(mk(100, 101.2, 100.1, 101.0),
                  mk(101, 104.2, 100.8, 104.0))
    assert simulate(bars, 0, "up", ENTRY, STOP, TARGET, BE, horizon=3)[0] == "target"


def test_open_when_nothing_hit():
    bars = series(mk(100, 100.4, 99.6, 100.1))
    assert simulate(bars, 0, "up", ENTRY, STOP, TARGET, BE, horizon=2)[0] == "open"


def test_short_breakeven():
    # SHORT: entry=100, stop=101, target=96, BE trigger=99
    bars = series(mk(100, 100, 100, 100),
                  mk(100, 100.2, 98.5, 99.0),   # reaches BE (low 98.5<=99) -> arm
                  mk(99, 100.5, 99.0, 100.2))   # pops back to entry -> breakeven
    out, px, armed = simulate(bars, 0, "down", 100.0, 101.0, 96.0, 99.0, horizon=3)
    assert out == "breakeven" and px == 100.0 and armed is True

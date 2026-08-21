"""Unit tests for the 0DTE/1DTE options backtest framework (dte_lab)."""
import math

import pytest

from dte_lab import blackscholes as bs
from dte_lab import volatility as vol
from dte_lab.engine import BacktestConfig, DayResult, run, _stop_adjusted_pnl
from dte_lab.metrics import equity_curve, max_drawdown, summarize
from dte_lab.strategy import IronCondorConfig, IronCondorStrategy, Leg, TradeSetup
from scanners.hourly import Bar


# ---- blackscholes ----------------------------------------------------------

def test_call_price_matches_known_reference():
    # Hull's textbook example: S=42, K=40, T=0.5, r=0.10, sigma=0.20 -> call ~= 4.76
    price = bs.call_price(42, 40, 0.5, 0.10, 0.20)
    assert price == pytest.approx(4.76, abs=0.01)


def test_put_call_parity():
    S, K, T, r, sigma = 100, 105, 0.1, 0.03, 0.25
    c = bs.call_price(S, K, T, r, sigma)
    p = bs.put_price(S, K, T, r, sigma)
    assert c - p == pytest.approx(S - K * math.exp(-r * T), abs=1e-9)


def test_call_delta_bounds_and_atm():
    # deep ITM call -> delta near 1, deep OTM -> near 0, ATM -> ~0.5-ish
    assert bs.call_delta(100, 50, 0.1, 0.03, 0.2) > 0.99
    assert bs.call_delta(100, 200, 0.1, 0.03, 0.2) < 0.01
    assert 0.4 < bs.call_delta(100, 100, 0.1, 0.03, 0.2) < 0.6


def test_strike_for_delta_round_trips():
    S, T, r, sigma = 500.0, 0.02, 0.045, 0.15
    for target in (0.10, 0.16, 0.25):
        k_call = bs.strike_for_delta(S, T, r, sigma, target, "call")
        assert bs.call_delta(S, k_call, T, r, sigma) == pytest.approx(target, abs=1e-6)
        assert k_call > S  # OTM call strike is above spot

        k_put = bs.strike_for_delta(S, T, r, sigma, target, "put")
        assert bs.put_delta(S, k_put, T, r, sigma) == pytest.approx(-target, abs=1e-6)
        assert k_put < S  # OTM put strike is below spot


def test_intrinsic_value():
    assert bs.intrinsic_value(105, 100, "call") == 5
    assert bs.intrinsic_value(95, 100, "call") == 0
    assert bs.intrinsic_value(95, 100, "put") == 5
    assert bs.intrinsic_value(105, 100, "put") == 0


# ---- volatility -------------------------------------------------------------

def test_realized_vol_zero_for_flat_prices():
    closes = [100.0] * 25
    assert vol.realized_vol(closes, window=20) == 0.0


def test_realized_vol_positive_for_moving_prices():
    closes = [100.0 * (1.01 if i % 2 == 0 else 0.99) for i in range(25)]
    assert vol.realized_vol(closes, window=20) > 0


def test_iv_estimate_applies_multiplier():
    closes = [100.0 * (1.01 if i % 2 == 0 else 0.99) for i in range(25)]
    rv = vol.realized_vol(closes, window=20)
    assert vol.iv_estimate(closes, window=20, iv_rv_multiplier=1.5) == pytest.approx(rv * 1.5)


def test_realized_vol_raises_on_insufficient_history():
    with pytest.raises(ValueError):
        vol.realized_vol([100.0, 101.0], window=20)


# ---- strategy: iron condor ---------------------------------------------------

def test_iron_condor_builds_symmetric_credit_structure():
    strat = IronCondorStrategy(IronCondorConfig(short_delta=0.16, wing_width=5.0))
    setup = strat.build(spot=500.0, iv=0.15, t_years=0.02, rate=0.045)
    assert setup is not None
    assert len(setup.legs) == 4
    call_short = next(l for l in setup.legs if l.option_type == "call" and l.side == "short")
    call_long = next(l for l in setup.legs if l.option_type == "call" and l.side == "long")
    put_short = next(l for l in setup.legs if l.option_type == "put" and l.side == "short")
    put_long = next(l for l in setup.legs if l.option_type == "put" and l.side == "long")
    assert call_long.strike - call_short.strike == pytest.approx(5.0)
    assert put_short.strike - put_long.strike == pytest.approx(5.0)
    assert put_short.strike < 500.0 < call_short.strike
    assert setup.credit_per_share > 0
    assert setup.max_loss_per_share == pytest.approx(5.0 - setup.credit_per_share)


def test_iron_condor_skips_when_credit_too_thin():
    # a huge min-credit floor makes every trade "not worth the risk"
    strat = IronCondorStrategy(IronCondorConfig(min_credit_frac_of_width=0.99))
    setup = strat.build(spot=500.0, iv=0.10, t_years=0.01, rate=0.045)
    assert setup is None


def test_trade_setup_settlement_pnl_max_profit_inside_short_strikes():
    legs = (
        Leg("call", 505, "short"), Leg("call", 510, "long"),
        Leg("put", 495, "short"), Leg("put", 490, "long"),
    )
    setup = TradeSetup(legs=legs, credit_per_share=2.0, max_loss_per_share=3.0)
    # spot settles between the short strikes -> everything expires worthless, keep full credit
    assert setup.settlement_pnl_per_share(500.0) == pytest.approx(2.0)


def test_trade_setup_settlement_pnl_max_loss_beyond_long_strike():
    legs = (
        Leg("call", 505, "short"), Leg("call", 510, "long"),
        Leg("put", 495, "short"), Leg("put", 490, "long"),
    )
    setup = TradeSetup(legs=legs, credit_per_share=2.0, max_loss_per_share=3.0)
    # spot blows through the call side entirely -> max loss = width - credit
    assert setup.settlement_pnl_per_share(520.0) == pytest.approx(2.0 - 5.0)


# ---- engine: stop-loss ---------------------------------------------------------

def _condor_setup(credit=2.0, max_loss=3.0):
    legs = (
        Leg("call", 505, "short"), Leg("call", 510, "long"),
        Leg("put", 495, "short"), Leg("put", 490, "long"),
    )
    return TradeSetup(legs=legs, credit_per_share=credit, max_loss_per_share=max_loss)


def test_stop_adjusted_pnl_no_breach_settles_at_close():
    setup = _condor_setup()
    # low/high stay inside the short strikes the whole day -> no stop, settle at close
    pnl = _stop_adjusted_pnl(setup, low=498.0, high=502.0, close=500.0, stop_loss_multiple=2.0)
    assert pnl == pytest.approx(setup.settlement_pnl_per_share(500.0))


def test_stop_adjusted_pnl_caps_loss_at_stop_even_if_close_recovers():
    setup = _condor_setup(credit=2.0, max_loss=3.0)
    # day's low blows past the long put strike (full max loss, -3.0), but price
    # recovers by the close -> a real stop-loss trader (1x credit here, tighter
    # than the 3.0 max loss) was already out and missed the recovery, so pnl
    # must be capped at -stop_multiple*credit, not the close.
    pnl = _stop_adjusted_pnl(setup, low=489.0, high=500.5, close=500.0, stop_loss_multiple=1.0)
    assert pnl == pytest.approx(-1.0 * setup.credit_per_share)
    assert pnl > -setup.max_loss_per_share  # stop is tighter than the theoretical max loss


def test_stop_adjusted_pnl_none_disables_stop():
    setup = _condor_setup(credit=2.0, max_loss=3.0)
    pnl = _stop_adjusted_pnl(setup, low=489.0, high=500.5, close=489.0, stop_loss_multiple=None)
    # no stop -> full close-based settlement, i.e. max loss
    assert pnl == pytest.approx(-setup.max_loss_per_share)


def test_stop_loss_sizes_up_positions_vs_no_stop():
    """A tighter effective risk (stop) should let the engine afford more
    contracts than sizing against the full theoretical max loss."""
    bars = []
    day0_ts = 1_700_000_000
    for i in range(30):
        price = 500.0 + (1.0 if i % 2 == 0 else -1.0)
        ts = day0_ts + i * 86400
        bars.append(Bar(ts=ts, open=500.0, high=price, low=price, close=price, volume=1000))
    strat = IronCondorStrategy(IronCondorConfig(short_delta=0.16, wing_width=10.0,
                                                 min_credit_frac_of_width=0.0))
    with_stop = BacktestConfig(strategy=strat, dte=0, starting_capital=100_000,
                               risk_pct_per_trade=0.02, vol_window=5, stop_loss_multiple=0.5)
    without_stop = BacktestConfig(strategy=strat, dte=0, starting_capital=100_000,
                                  risk_pct_per_trade=0.02, vol_window=5, stop_loss_multiple=None)
    contracts_with = [r.contracts for r in run(bars, with_stop) if r.contracts > 0]
    contracts_without = [r.contracts for r in run(bars, without_stop) if r.contracts > 0]
    assert contracts_with and contracts_without
    assert min(contracts_with) > min(contracts_without)


# ---- engine ---------------------------------------------------------------------

def _flat_bars(n: int, price: float = 500.0, day0_ts: int = 1_700_000_000) -> list[Bar]:
    """n daily bars, dead flat (zero realized vol) except for a deliberate jump
    on the last bar so the strategy actually has something to price against."""
    bars = []
    for i in range(n):
        ts = day0_ts + i * 86400
        bars.append(Bar(ts=ts, open=price, high=price, low=price, close=price, volume=1000))
    return bars


def test_engine_skips_days_with_zero_realized_vol():
    # flat closes -> realized_vol=0 -> iv_estimate=0, which Black-Scholes can't
    # price (sigma must be > 0) - the engine must skip these days, not raise.
    bars = _flat_bars(30)
    assert vol.iv_estimate([b.close for b in bars], window=20) == 0.0  # sanity check
    strat = IronCondorStrategy()
    config = BacktestConfig(strategy=strat, dte=0, starting_capital=10_000, vol_window=20)
    results = run(bars, config)
    assert results
    assert all(r.contracts == 0 and r.pnl == 0.0 for r in results)
    assert results[-1].equity_after == config.starting_capital


def test_engine_compounds_equity_on_wins():
    """Underlying stays pinned at the entry price on every settlement day, so
    every iron condor should expire at max profit (full credit kept)."""
    n = 30
    bars = []
    day0_ts = 1_700_000_000
    for i in range(n):
        # small daily wiggle so realized vol is nonzero (strategy can price),
        # but always settling back near the same level so shorts stay OTM
        price = 500.0 + (1.0 if i % 2 == 0 else -1.0)
        ts = day0_ts + i * 86400
        bars.append(Bar(ts=ts, open=500.0, high=price, low=price, close=price, volume=1000))
    # min_credit_frac_of_width=0 because this test only checks the PnL/equity
    # math, not the separately-tested credit-floor filter; at this tiny
    # same-day time-to-expiry a 10-wide condor's credit wouldn't clear the
    # default 10% floor.
    strat = IronCondorStrategy(IronCondorConfig(short_delta=0.16, wing_width=10.0,
                                                 min_credit_frac_of_width=0.0))
    # capital sized so 2% risk actually affords >=1 contract of a ~10-wide condor
    config = BacktestConfig(strategy=strat, dte=0, starting_capital=100_000,
                            risk_pct_per_trade=0.02, vol_window=5)
    results = run(bars, config)
    assert results
    traded = [r for r in results if r.contracts > 0]
    assert traded, "expected at least one trade to size up given ample equity"
    for r in traded:
        assert r.pnl >= 0  # settle price (~500±1) never reaches the short strikes
    assert results[-1].equity_after >= config.starting_capital


def test_day_result_records_equity_before_and_after():
    r = DayResult(date="2026-01-05", spot_entry=500.0, spot_settle=500.0, iv=0.15,
                 setup=None, contracts=0, pnl=0.0, equity_before=10_000.0, equity_after=10_000.0)
    assert r.equity_after - r.equity_before == 0.0


# ---- metrics --------------------------------------------------------------

def _mk_result(date, equity_before, pnl):
    return DayResult(date=date, spot_entry=500.0, spot_settle=500.0, iv=0.15,
                     setup=None, contracts=1 if pnl else 0, pnl=pnl,
                     equity_before=equity_before, equity_after=equity_before + pnl)


def test_equity_curve_and_drawdown_tracking():
    results = [
        _mk_result("2026-01-01", 100.0, 20.0),   # equity 120, new peak
        _mk_result("2026-01-02", 120.0, -30.0),  # equity 90, -25% from peak
        _mk_result("2026-01-03", 90.0, 10.0),    # equity 100, still below peak
    ]
    curve = equity_curve(results)
    assert [p.equity for p in curve] == [120.0, 90.0, 100.0]
    assert curve[0].drawdown_pct == 0.0
    assert curve[1].drawdown_pct == pytest.approx(-0.25)
    dd_pct, dd_date = max_drawdown(curve)
    assert dd_pct == pytest.approx(-0.25)
    assert dd_date == "2026-01-02"


def test_summarize_counts_trades_and_returns():
    results = [
        _mk_result("2026-01-01", 100.0, 20.0),
        _mk_result("2026-01-02", 120.0, 0.0),   # skipped day (pnl=0 -> contracts=0)
        _mk_result("2026-01-03", 120.0, -10.0),
    ]
    summary = summarize(results)
    assert summary["days"] == 3
    assert summary["trades"] == 2
    assert summary["skipped_days"] == 1
    assert summary["win_rate"] == pytest.approx(0.5)
    assert summary["start_equity"] == 100.0
    assert summary["end_equity"] == 110.0
    assert summary["total_return_pct"] == pytest.approx(10.0)

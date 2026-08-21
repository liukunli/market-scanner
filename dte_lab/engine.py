"""Day-by-day backtest engine: fetch daily bars, price a strategy's structure
at entry via Black-Scholes, settle it against the actual closing price on
the expiration day (subject to an intraday stop-loss approximated from the
day's High/Low - see `_stop_adjusted_pnl`), and compound an account equity
curve.

Simplifications (see README.md for the full list):
  * Only the day's Open/High/Low/Close are available - no intraday path, so
    the stop-loss check is an approximation: it looks at the intrinsic-value
    PnL implied by the day's high and low (in addition to the close) and, if
    either would have breached the stop, caps the loss there instead of
    riding it to the (possibly worse, or recovered) close. Real path
    dependence (e.g. touched the stop then reversed) can't be reproduced.
  * IV is a realized-vol-based proxy (dte_lab.volatility), not a market quote.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from scanners.hourly import Bar
from scanners.timeutil import local_date

from . import volatility as vol
from .strategy import Strategy, TradeSetup

CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True)
class DayResult:
    date: str
    spot_entry: float
    spot_settle: float
    iv: float
    setup: TradeSetup | None
    contracts: int
    pnl: float
    equity_before: float
    equity_after: float


@dataclass(frozen=True)
class BacktestConfig:
    strategy: Strategy
    dte: int = 0                    # 0 = same-day expiry, 1 = next-day expiry
    starting_capital: float = 50_000.0
    risk_pct_per_trade: float = 0.02  # fraction of current equity risked per trade
    rate: float = 0.045             # annualized risk-free rate used in BS pricing
    vol_window: int = 20
    iv_rv_multiplier: float = 1.25  # see dte_lab/volatility.py - results are
    # extremely sensitive to this number (it's assuming a vol risk premium,
    # not discovering one from data), so treat any single value as a
    # scenario to stress-test against, not a validated edge.
    same_day_t_fraction: float = 0.30  # remaining fraction of the entry day's
    # session at trade-open, expressed as a fraction of one trading day (e.g.
    # entering mid-morning on a 0DTE leaves ~30% of the day's time value left)
    stop_loss_multiple: float | None = None  # exit if paper loss reaches this
    # many multiples of the credit received (e.g. 2.0 means "close if you're
    # down 2x the premium you collected"). Off by default: empirically, on a
    # thin-credit far-OTM condor (the default IronCondorConfig), an active
    # stop converts winners that dip and recover into locked-in losses more
    # often than it saves real blowups - it made SPY 0DTE backtests *worse*
    # at every tested tightness. Worth enabling for wider-credit/closer-to-
    # the-money structures where the stop threshold sits further from
    # ordinary daily noise; run with and without --stop-loss-multiple set to
    # compare before trusting either for a given configuration.


def _settlement_index(entry_idx: int, dte: int) -> int:
    return entry_idx + dte


def _stop_adjusted_pnl(setup: TradeSetup, low: float, high: float, close: float,
                       stop_loss_multiple: float | None) -> float:
    """PnL per share at settlement, capped by an intraday stop-loss.

    Evaluates the structure's intrinsic-value PnL at the day's low, high, and
    close; if the worst of those breaches `stop_loss_multiple * credit`, the
    position is treated as closed at the stop rather than at the close (it
    can't do worse than the stop, and doesn't get to keep any later
    recovery). Works for any TradeSetup, not just iron condors.
    """
    if stop_loss_multiple is None:
        return setup.settlement_pnl_per_share(close)
    stop_floor = -stop_loss_multiple * setup.credit_per_share
    worst = min(setup.settlement_pnl_per_share(low),
               setup.settlement_pnl_per_share(high),
               setup.settlement_pnl_per_share(close))
    if worst <= stop_floor:
        return max(worst, stop_floor)
    return setup.settlement_pnl_per_share(close)


def run(bars: Sequence[Bar], config: BacktestConfig) -> list[DayResult]:
    """Run the backtest over daily `bars` (from scanners.yahoo.bars(..., interval="1d")).

    Needs at least `vol_window + 1` prior closes before the first tradeable
    day, plus `dte` extra days after each entry day to settle against.
    """
    results: list[DayResult] = []
    equity = config.starting_capital
    t_years = (config.dte + config.same_day_t_fraction) / vol.TRADING_DAYS_PER_YEAR

    start = config.vol_window + 1
    end = len(bars) - config.dte
    for i in range(start, end):
        entry_bar = bars[i]
        settle_bar = bars[_settlement_index(i, config.dte)]
        prior_closes = [b.close for b in bars[: i]]

        iv = vol.iv_estimate(prior_closes, config.vol_window, config.iv_rv_multiplier)
        equity_before = equity
        # zero/degenerate vol (e.g. a dead-flat price run) can't be priced by
        # Black-Scholes (sigma must be > 0) - skip rather than let it raise.
        setup = config.strategy.build(entry_bar.open, iv, t_years, config.rate) if iv > 0 else None

        if setup is None:
            results.append(DayResult(local_date(entry_bar.ts), entry_bar.open, settle_bar.close,
                                     iv, None, 0, 0.0, equity_before, equity_before))
            continue

        # Size against the loss a stop-loss discipline actually realizes, not
        # the theoretical worst case the stop exists to prevent.
        effective_loss_per_share = setup.max_loss_per_share
        if config.stop_loss_multiple is not None:
            effective_loss_per_share = min(
                effective_loss_per_share, config.stop_loss_multiple * setup.credit_per_share)

        risk_dollars = equity * config.risk_pct_per_trade
        max_loss_per_contract = effective_loss_per_share * CONTRACT_MULTIPLIER
        contracts = int(risk_dollars // max_loss_per_contract)
        if contracts < 1 or max_loss_per_contract > equity:
            results.append(DayResult(local_date(entry_bar.ts), entry_bar.open, settle_bar.close,
                                     iv, setup, 0, 0.0, equity_before, equity_before))
            continue

        pnl_per_share = _stop_adjusted_pnl(setup, settle_bar.low, settle_bar.high,
                                          settle_bar.close, config.stop_loss_multiple)
        pnl = pnl_per_share * CONTRACT_MULTIPLIER * contracts
        equity += pnl
        results.append(DayResult(local_date(entry_bar.ts), entry_bar.open, settle_bar.close,
                                 iv, setup, contracts, pnl, equity_before, equity))

    return results

"""Day-by-day backtest engine: fetch daily bars, price a strategy's structure
at entry via Black-Scholes, settle it against the actual closing price on
the expiration day, and compound an account equity curve.

Simplifications (see README.md for the full list):
  * Entry/settlement use daily Open/Close only - no intraday path, so a
    0DTE/1DTE position is never stopped out or closed early; it's always
    held to expiration and settled against the close.
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
    iv_rv_multiplier: float = 1.15
    same_day_t_fraction: float = 0.30  # remaining fraction of the entry day's
    # session at trade-open, expressed as a fraction of one trading day (e.g.
    # entering mid-morning on a 0DTE leaves ~30% of the day's time value left)


def _settlement_index(entry_idx: int, dte: int) -> int:
    return entry_idx + dte


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

        risk_dollars = equity * config.risk_pct_per_trade
        max_loss_per_contract = setup.max_loss_per_share * CONTRACT_MULTIPLIER
        contracts = int(risk_dollars // max_loss_per_contract)
        if contracts < 1 or max_loss_per_contract > equity:
            results.append(DayResult(local_date(entry_bar.ts), entry_bar.open, settle_bar.close,
                                     iv, setup, 0, 0.0, equity_before, equity_before))
            continue

        pnl_per_share = setup.settlement_pnl_per_share(settle_bar.close)
        pnl = pnl_per_share * CONTRACT_MULTIPLIER * contracts
        equity += pnl
        results.append(DayResult(local_date(entry_bar.ts), entry_bar.open, settle_bar.close,
                                 iv, setup, contracts, pnl, equity_before, equity))

    return results

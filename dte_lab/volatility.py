"""IV proxy: trailing realized volatility of the underlying, scaled up.

There is no historical options-chain data in this package, so implied
volatility can't be observed directly. This estimates it from the
underlying's own trailing daily closes (annualized stdev of log returns),
then applies a fixed multiplier to approximate the volatility risk premium
(implied vol trades above realized vol on average - historically VIX has
averaged roughly 20-30% above trailing realized SPX vol, which is where the
default of 1.25 comes from). This is still a blunt, non-regime-aware,
unverified-for-this-package assumption, and results are extremely sensitive
to it - see README.md before trusting a backtest run with a different value.
"""
from __future__ import annotations

import math
from typing import Sequence

TRADING_DAYS_PER_YEAR = 252


def realized_vol(closes: Sequence[float], window: int = 20) -> float:
    """Annualized stdev of daily log returns over the trailing `window` bars.

    `closes` should already exclude any day the caller is about to trade
    (no look-ahead) - pass closes up to and including the prior day only.
    """
    if len(closes) < window + 1:
        raise ValueError(f"need at least {window + 1} closes, got {len(closes)}")
    tail = closes[-(window + 1):]
    log_returns = [math.log(tail[i] / tail[i - 1]) for i in range(1, len(tail))]
    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)


def iv_estimate(closes: Sequence[float], window: int = 20, iv_rv_multiplier: float = 1.25) -> float:
    return realized_vol(closes, window) * iv_rv_multiplier

"""Higher-timeframe (daily) trend filter for the hourly signal engine.

Only accept a scan-up signal when the prior COMPLETED trading day's close
sits above its SMA(N), and a scan-down signal when it sits below - this
filters out counter-trend continuation fakeouts. Backtested on the QQQ-100
over 6mo of data (SMA 50): cuts resolved trade count roughly in half but
improves avg R/trade in both an in-sample and an out-of-sample split (still
negative out-of-sample, but less so) - see TREND_SMA_PERIOD in config.py.

Pure, no I/O: callers are responsible for fetching daily bars and excluding
today's in-progress session (see completed_daily_bars below).
"""
from __future__ import annotations

from typing import Optional, Sequence

from .hourly import Bar
from .timeutil import local_date


def completed_daily_bars(daily_bars: Sequence[Bar], today: str) -> list[Bar]:
    """Daily bars strictly before `today` (excludes an in-progress session bar)."""
    return [b for b in daily_bars if local_date(b.ts) < today]


def daily_sma(daily_bars: Sequence[Bar], period: int) -> Optional[float]:
    if len(daily_bars) < period:
        return None
    return sum(b.close for b in daily_bars[-period:]) / period


def trend_aligned(side: str, daily_bars: Sequence[Bar], period: int) -> bool:
    """True if `side` matches the most recent completed day's close vs its SMA(period).

    `daily_bars` must already exclude today's in-progress session (see
    completed_daily_bars) to avoid look-ahead. Returns False (conservatively
    exclude) when there isn't enough history to compute the SMA.
    """
    if not daily_bars:
        return False
    sma = daily_sma(daily_bars, period)
    if sma is None:
        return False
    close = daily_bars[-1].close
    return close > sma if side == "up" else close < sma

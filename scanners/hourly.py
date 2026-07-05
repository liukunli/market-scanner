"""1-hour scan-up / scan-down signal engine.

Pure, deterministic, no I/O — every function takes plain data and returns plain
data, so it is fully unit-testable without touching the network.

Signal definition (scan-up), using the last two COMPLETED 1h bars
    p = previous bar, c = current bar:

    1. continuous growth   both bars green (close > open) and c.close > p.close
    2. low near prev high  c.low >= p.high - low_near_high_frac * p.range
    3. minimal drawback    (p.close - c.low) / p.range <= max_drawback_frac
    4. same magnitude      |g_c - g_p| / max(g_c, g_p) <= magnitude_tol,  g = close-open
    5. relative volume     avg(p.vol, c.vol) / avg(prior N bars) >= rvol_min

Trade levels:
    entry       = c.close
    stop_loss   = midpoint of current bar = (c.high + c.low) / 2
    take_profit = entry + tp_bars * gbar,  gbar = (g_p + g_c) / 2   (mirror for shorts)

scan-down is the exact mirror (red bars, falling, current high near prev low, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import fmean
from typing import Optional, Sequence

from .config import HourlyConfig, HOURLY


@dataclass(frozen=True)
class Bar:
    ts: int          # epoch seconds (bar start)
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def range(self) -> float:
        return self.high - self.low


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str                # "up" (long) or "down" (short)
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    rvol: float
    bar_ts: int              # ts of the current (signal) bar
    prev_gain: float         # g_p
    curr_gain: float         # g_c

    def to_dict(self) -> dict:
        return asdict(self)


def _relative_volume(bars: Sequence[Bar], cfg: HourlyConfig) -> Optional[float]:
    """avg volume of the last two bars / avg volume of the N bars preceding them."""
    baseline = bars[-(cfg.vol_lookback + 2):-2]
    if not baseline:
        return None
    base = fmean(b.volume for b in baseline)
    if base <= 0:
        return None
    return fmean((bars[-2].volume, bars[-1].volume)) / base


def _same_magnitude(g_p: float, g_c: float, tol: float) -> bool:
    denom = max(abs(g_p), abs(g_c))
    if denom <= 0:
        return False
    return abs(g_c - g_p) / denom <= tol


def evaluate(symbol: str, bars: Sequence[Bar], side: str,
             cfg: HourlyConfig = HOURLY) -> Optional[Signal]:
    """Return a Signal if the last two bars satisfy the `side` pattern, else None."""
    if side not in ("up", "down"):
        raise ValueError("side must be 'up' or 'down'")
    if len(bars) < cfg.min_bars:
        return None

    p, c = bars[-2], bars[-1]
    if p.range <= 0 or c.range <= 0:
        return None

    rvol = _relative_volume(bars, cfg)
    if rvol is None or rvol < cfg.rvol_min:
        return None

    if side == "up":
        g_p, g_c = p.close - p.open, c.close - c.open
        both_trending = g_p > 0 and g_c > 0 and c.close > p.close
        near = c.low >= p.high - cfg.low_near_high_frac * p.range
        drawback = (p.close - c.low) / p.range <= cfg.max_drawback_frac
    else:  # down
        g_p, g_c = p.open - p.close, c.open - c.close
        both_trending = g_p > 0 and g_c > 0 and c.close < p.close
        near = c.high <= p.low + cfg.low_near_high_frac * p.range
        drawback = (c.high - p.close) / p.range <= cfg.max_drawback_frac

    if not (both_trending and near and drawback
            and _same_magnitude(g_p, g_c, cfg.magnitude_tol)):
        return None

    entry = c.close
    stop_loss = (c.high + c.low) / 2.0
    gbar = (g_p + g_c) / 2.0
    if side == "up":
        take_profit = entry + cfg.tp_bars * gbar
        risk = entry - stop_loss
        reward = take_profit - entry
    else:
        take_profit = entry - cfg.tp_bars * gbar
        risk = stop_loss - entry
        reward = entry - take_profit

    if risk <= 0:
        return None
    risk_reward = reward / risk

    return Signal(
        symbol=symbol, side=side, entry=round(entry, 4),
        stop_loss=round(stop_loss, 4), take_profit=round(take_profit, 4),
        risk_reward=round(risk_reward, 3), rvol=round(rvol, 3),
        bar_ts=c.ts, prev_gain=round(g_p, 4), curr_gain=round(g_c, 4),
    )


def scan_up(symbol: str, bars: Sequence[Bar], cfg: HourlyConfig = HOURLY) -> Optional[Signal]:
    return evaluate(symbol, bars, "up", cfg)


def scan_down(symbol: str, bars: Sequence[Bar], cfg: HourlyConfig = HOURLY) -> Optional[Signal]:
    return evaluate(symbol, bars, "down", cfg)

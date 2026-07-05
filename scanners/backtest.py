"""Replay the hourly signal engine over historical bars and score each trade.

For every bar on the target day we evaluate scan-up / scan-down using only the
data available up to that bar (no look-ahead), then walk forward up to
`horizon` bars to see whether the trade hit its take-profit or its stop first.

Assumptions (documented so results are honest):
  * If a single forward bar's range spans BOTH stop and target, we count the
    STOP as hit first (conservative / worst-case fill).
  * If neither is hit within `horizon` bars, the trade is marked-to-market at
    the close of the last bar in the window ("open").
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional, Sequence

from .config import HourlyConfig, HOURLY
from .hourly import Bar, evaluate

ET = datetime.timezone(datetime.timedelta(hours=-4))  # EDT


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: str
    bar_ts: int
    entry: float
    stop: float
    target: float
    risk: float
    outcome: str        # "target" | "stop" | "open"
    exit_price: float
    r_multiple: float   # realized PnL / initial risk


def _bar_day(b: Bar) -> str:
    return datetime.datetime.fromtimestamp(b.ts, ET).strftime("%Y-%m-%d")


def simulate(bars: Sequence[Bar], i: int, side: str, entry: float, stop: float,
             target: float, breakeven_trigger: float, horizon: int):
    """Walk forward with a breakeven-moving stop.

    Bar-by-bar (no intrabar ticks available), each bar is checked in this order:
      1. adverse extreme vs the CURRENT effective stop (worst-case tie-break),
      2. favorable extreme vs the target,
      3. if the in-favor move reached `breakeven_trigger` and we survived the
         bar, move the effective stop up to entry for all later bars.
    Returns (outcome, exit_price, breakeven_armed) where outcome is one of
    "target" | "stop" | "breakeven" | "open".
    """
    eff_stop = stop
    armed = False
    for j in range(i + 1, min(i + 1 + horizon, len(bars))):
        b = bars[j]
        if side == "up":
            if b.low <= eff_stop:
                return ("breakeven" if armed else "stop"), eff_stop, armed
            if b.high >= target:
                return "target", target, armed
            if not armed and b.high >= breakeven_trigger:
                armed, eff_stop = True, entry
        else:
            if b.high >= eff_stop:
                return ("breakeven" if armed else "stop"), eff_stop, armed
            if b.low <= target:
                return "target", target, armed
            if not armed and b.low <= breakeven_trigger:
                armed, eff_stop = True, entry
    last = bars[min(i + horizon, len(bars) - 1)]
    return "open", last.close, armed


def backtest_symbol(symbol: str, bars: Sequence[Bar], target_day: str,
                    cfg: HourlyConfig = HOURLY, horizon: Optional[int] = None):
    """Return the list of Trades generated on `target_day` for one symbol."""
    horizon = horizon or cfg.tp_bars
    trades = []
    for i in range(cfg.min_bars - 1, len(bars)):
        if _bar_day(bars[i]) != target_day:
            continue
        window = bars[: i + 1]
        for side in ("up", "down"):
            sig = evaluate(symbol, window, side, cfg)
            if not sig:
                continue
            risk = abs(sig.entry - sig.stop_loss)
            oc, exit_price, _ = simulate(bars, i, side, sig.entry, sig.stop_loss,
                                         sig.take_profit, sig.breakeven_trigger, horizon)
            if side == "up":
                pnl = exit_price - sig.entry
            else:
                pnl = sig.entry - exit_price
            r = pnl / risk if risk > 0 else 0.0
            trades.append(Trade(
                symbol=symbol, side=side, bar_ts=sig.bar_ts, entry=sig.entry,
                stop=sig.stop_loss, target=sig.take_profit, risk=round(risk, 4),
                outcome=oc, exit_price=round(exit_price, 4), r_multiple=round(r, 3)))
    return trades


def summarize(trades: Sequence[Trade]) -> dict:
    n = len(trades)
    wins = [t for t in trades if t.outcome == "target"]
    losses = [t for t in trades if t.outcome == "stop"]
    breakevens = [t for t in trades if t.outcome == "breakeven"]
    opens = [t for t in trades if t.outcome == "open"]
    total_r = sum(t.r_multiple for t in trades)
    return {
        "signals": n,
        "targets": len(wins),
        "stops": len(losses),
        "breakeven": len(breakevens),
        "open": len(opens),
        "win_rate": round(len(wins) / n, 3) if n else 0.0,
        "total_R": round(total_r, 2),
        "avg_R": round(total_r / n, 3) if n else 0.0,
    }

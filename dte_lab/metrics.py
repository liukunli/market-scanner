"""Equity-curve derived stats: running peak, drawdown %, and a summary block."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .engine import DayResult


@dataclass(frozen=True)
class EquityPoint:
    date: str
    equity: float
    peak: float
    drawdown_pct: float  # negative or zero, e.g. -0.271 for a 27.1% drawdown


def equity_curve(results: Sequence[DayResult]) -> list[EquityPoint]:
    out = []
    peak = results[0].equity_before if results else 0.0
    for r in results:
        peak = max(peak, r.equity_after)
        dd = (r.equity_after - peak) / peak if peak > 0 else 0.0
        out.append(EquityPoint(r.date, r.equity_after, peak, dd))
    return out


def max_drawdown(curve: Sequence[EquityPoint]) -> tuple[float, str | None]:
    if not curve:
        return 0.0, None
    worst = min(curve, key=lambda p: p.drawdown_pct)
    return worst.drawdown_pct, worst.date


def summarize(results: Sequence[DayResult]) -> dict:
    traded = [r for r in results if r.contracts > 0]
    curve = equity_curve(results)
    dd_pct, dd_date = max_drawdown(curve)
    wins = [r for r in traded if r.pnl > 0]
    start_equity = results[0].equity_before if results else 0.0
    end_equity = results[-1].equity_after if results else 0.0
    return {
        "days": len(results),
        "trades": len(traded),
        "skipped_days": len(results) - len(traded),
        "win_rate": round(len(wins) / len(traded), 3) if traded else 0.0,
        "start_equity": round(start_equity, 2),
        "end_equity": round(end_equity, 2),
        "total_return_pct": round((end_equity / start_equity - 1) * 100, 2) if start_equity else 0.0,
        "max_drawdown_pct": round(dd_pct * 100, 2),
        "max_drawdown_date": dd_date,
    }

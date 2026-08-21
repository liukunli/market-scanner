"""3-panel backtest chart: compounding equity curve (+ running peak and
drawdown shading), daily PnL bars, and a drawdown % band underneath.

CLI:
    python3 -m scripts.backtest_options --symbol SPY --dte 0 --out chart.png
"""
from __future__ import annotations

import datetime
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .engine import DayResult
from .metrics import equity_curve, max_drawdown

UP, DOWN = "#1a9850", "#d73027"          # CVD-safe green / red, matches scanners/visualize.py
PEAK_C, DD_FILL, DD_LINE = "#6b7280", "#fadbd8", "#d73027"
INK, GRID = "#1b1f24", "#e5e7eb"


def _parse_date(s: str) -> datetime.date:
    return datetime.date.fromisoformat(s)


def plot_backtest(results: Sequence[DayResult], symbol: str, strategy_name: str,
                  dte: int, out_path: str) -> None:
    if not results:
        raise ValueError("no results to plot")

    curve = equity_curve(results)
    dates = [_parse_date(p.date) for p in curve]
    equity = [p.equity for p in curve]
    peak = [p.peak for p in curve]
    dd_pct = [p.drawdown_pct * 100 for p in curve]
    daily_pnl = [r.pnl for r in results]
    dd_value, dd_date = max_drawdown(curve)

    fig, (ax_eq, ax_pnl, ax_dd) = plt.subplots(
        3, 1, figsize=(16, 12), sharex=True,
        gridspec_kw={"height_ratios": [3, 1.4, 1.4], "hspace": 0.08})

    dte_label = "0DTE" if dte == 0 else f"{dte}DTE"
    fig.suptitle(f"{strategy_name} ({symbol}, {dte_label}) — Backtest PnL Curve "
                f"({dates[0].isoformat()} to {dates[-1].isoformat()})",
                fontsize=14, y=0.93)

    # --- equity panel ---
    ax_eq.plot(dates, equity, color=UP, lw=1.4, label="Account Equity (compounding)")
    ax_eq.plot(dates, peak, color=PEAK_C, lw=1.0, ls="--", label="Running Peak")
    ax_eq.fill_between(dates, equity, peak, where=[e < p for e, p in zip(equity, peak)],
                       color=DD_FILL, alpha=0.7, label="Drawdown Region")
    if dd_date is not None:
        dd_dt = _parse_date(dd_date)
        dd_eq = equity[dates.index(dd_dt)]
        ax_eq.annotate(f"Max Drawdown {dd_value * 100:.1f}%\n({dd_date})",
                       xy=(dd_dt, dd_eq), xytext=(20, 40), textcoords="offset points",
                       color=DD_LINE, fontsize=9,
                       arrowprops=dict(arrowstyle="->", color=DD_LINE, lw=1))
    ax_eq.set_ylabel("Account Equity ($)")
    ax_eq.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax_eq.grid(color=GRID, lw=0.6)

    # --- daily PnL panel ---
    colors = [UP if p >= 0 else DOWN for p in daily_pnl]
    ax_pnl.bar(dates, daily_pnl, color=colors, width=1.0)
    ax_pnl.axhline(0, color=INK, lw=0.6)
    ax_pnl.set_ylabel("Daily PnL ($)")
    ax_pnl.grid(color=GRID, lw=0.6)

    # --- drawdown % panel ---
    ax_dd.fill_between(dates, dd_pct, 0, color=DD_FILL, edgecolor=DD_LINE, lw=0.8)
    ax_dd.set_ylabel("Drawdown %")
    ax_dd.set_xlabel("Date")
    ax_dd.grid(color=GRID, lw=0.6)

    fig.autofmt_xdate()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

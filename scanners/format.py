"""Render scanner results into Slack message text (pure, testable)."""
from __future__ import annotations

import datetime
from typing import Sequence

from .hourly import Signal
from .premarket import GapResult

ET = datetime.timezone(datetime.timedelta(hours=-4))  # EDT (adjust to -5 in winter)


def _fmt_ts(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts, ET).strftime("%Y-%m-%d %H:%M ET")


def format_premarket(universe: str, ups: Sequence[GapResult],
                     downs: Sequence[GapResult]) -> str:
    lines = [f"📊 *Pre-Market Gap Scanner — {universe}*"]
    if not ups and not downs:
        lines.append("_No qualifying gaps._")
        return "\n".join(lines)

    if ups:
        lines.append("\n📈 *Top Gap-Ups*")
        for r in ups:
            lines.append(f"• {r.symbol}  +{r.gap_pct:.2f}%  "
                         f"({r.prev_close:.2f} → {r.premarket_price:.2f})")
    if downs:
        lines.append("\n📉 *Top Gap-Downs*")
        for r in downs:
            lines.append(f"• {r.symbol}  {r.gap_pct:.2f}%  "
                         f"({r.prev_close:.2f} → {r.premarket_price:.2f})")
    return "\n".join(lines)


def format_hourly(title: str, signals: Sequence[Signal]) -> str:
    lines = [f"⏱️ *1-Hour {title}*"]
    if not signals:
        lines.append("_No signals this bar._")
        return "\n".join(lines)

    arrow = "🟢 BUY" if signals[0].side == "up" else "🔴 SELL/SHORT"
    lines.append(f"{arrow}  •  bar close {_fmt_ts(signals[0].bar_ts)}")
    for s in signals:
        lines.append(
            f"\n*{s.symbol}*  entry `{s.entry:.2f}`  "
            f"stop `{s.stop_loss:.2f}`  target `{s.take_profit:.2f}`  "
            f"(R:R {s.risk_reward:.2f}, rvol {s.rvol:.2f})"
        )
    return "\n".join(lines)

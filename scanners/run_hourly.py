"""Entrypoint: 1-hour scan-up / scan-down over all US > $5B stocks + index ETFs.

Signals route by DIRECTION: scan-up -> #one-hour-signals-up, scan-down ->
#one-hour-signals-down. Each signal posts its candlestick chart with a caption;
if charting (matplotlib) is unavailable it degrades to a text-only message.

Invoked by the Claude routine at each bar close during the trading window
(10:30, 11:30, 12:30, 13:30, 14:30, 15:30, 16:00 ET):
    python3 -m scanners.run_hourly
"""
from __future__ import annotations

import os
import tempfile
import time

from . import universe, yahoo, slack
from .config import CHANNELS, INDEX_ETFS, HOURLY, tier_tag
from .hourly import scan_up, scan_down
from .signal_export import build_record


def _caption(sig, tag: str) -> str:
    arrow = "🟢 BUY" if sig.side == "up" else "🔴 SHORT"
    word = "Up" if sig.side == "up" else "Down"
    return (f"{arrow}  *1-Hour Scan-{word}*  `[{tag}]`  *{sig.symbol}*\n"
            f"entry `{sig.entry:.2f}`  stop `{sig.stop_loss:.2f}`  "
            f"target `{sig.take_profit:.2f}`  (R:R {sig.risk_reward:.2f}, "
            f"rvol {sig.rvol:.2f})\n"
            f"↳ move stop → entry `{sig.entry:.2f}` once price hits "
            f"`{sig.breakeven_trigger:.2f}` (breakeven, no-loss)")


def _render_chart(symbol, bars, side, outdir) -> str | None:
    """Render this signal's chart; return path or None if charting unavailable."""
    try:
        from .visualize import render_signal  # lazy: matplotlib optional
        rec = build_record(symbol, bars, len(bars) - 1, side, HOURLY,
                           context=10, forward_show=0)
        if not rec:
            return None
        path = os.path.join(outdir, f"{symbol}_{side}.png")
        render_signal(rec, path)
        return path
    except Exception:
        return None


def run(post_signal=slack.post_signal) -> dict:
    now = time.time()
    qqq = universe.qqq_constituents(now)
    sp500 = universe.sp500_constituents(now)
    symbols = list(dict.fromkeys(list(INDEX_ETFS) + universe.us_5b_universe(now)))
    bars_by = yahoo.fetch_all(symbols, yahoo.hourly_bars)

    outdir = tempfile.mkdtemp(prefix="signals_")
    counts = {"up": 0, "down": 0}
    for sym, bars in bars_by.items():
        if not bars:
            continue
        for side, channel in (("up", CHANNELS["hourly_up"]),
                              ("down", CHANNELS["hourly_down"])):
            sig = scan_up(sym, bars, HOURLY) if side == "up" \
                else scan_down(sym, bars, HOURLY)
            if not sig:
                continue
            tag = tier_tag(sym, qqq, sp500)
            chart = _render_chart(sym, bars, side, outdir)
            post_signal(channel, _caption(sig, tag), chart)
            counts[side] += 1
    return counts


if __name__ == "__main__":
    print(run())

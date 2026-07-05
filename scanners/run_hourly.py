"""Entrypoint: 1-hour scan-up / scan-down over all US > $5B stocks + index ETFs.

Invoked by the Claude routine at each bar close during the trading window
(10:30, 11:30, 12:30, 13:30, 14:30, 15:30, 16:00 ET):
    python3 -m scanners.run_hourly
"""
from __future__ import annotations

import time
from collections import defaultdict

from . import universe, yahoo, slack
from .config import CHANNELS, INDEX_ETFS, HOURLY
from .format import format_hourly
from .hourly import scan_up, scan_down


def run(post=slack.post) -> dict:
    now = time.time()
    qqq = universe.qqq_constituents(now)
    sp500 = universe.sp500_constituents(now)
    symbols = list(dict.fromkeys(list(INDEX_ETFS) + universe.us_5b_universe(now)))

    bars_by_symbol = yahoo.fetch_all(symbols, yahoo.hourly_bars)

    # group signals by destination channel, per side
    buckets = defaultdict(lambda: {"up": [], "down": []})
    for sym, bars in bars_by_symbol.items():
        if not bars:
            continue
        channel = slack.route_channel(sym, qqq, sp500)
        up = scan_up(sym, bars, HOURLY)
        if up:
            buckets[channel]["up"].append(up)
        down = scan_down(sym, bars, HOURLY)
        if down:
            buckets[channel]["down"].append(down)

    summary = {}
    for channel, sides in buckets.items():
        for side, sigs in sides.items():
            if not sigs:
                continue
            sigs.sort(key=lambda s: -s.risk_reward)
            title = "Scan-Up (buy)" if side == "up" else "Scan-Down (short)"
            post(channel, format_hourly(title, sigs))
            summary[(channel, side)] = len(sigs)
    return summary


if __name__ == "__main__":
    print(run())

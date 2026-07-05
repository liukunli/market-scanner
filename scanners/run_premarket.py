"""Entrypoint: pre-market gap scan over QQQ, S&P 500, and all US > $5B.

Invoked by the Claude routine ~9:00 AM ET on trading days:
    python3 -m scanners.run_premarket
"""
from __future__ import annotations

import time

from . import universe, yahoo, slack
from .config import CHANNELS, PREMARKET
from .format import format_premarket
from .premarket import Quote, scan


def _quotes_for(symbols) -> list[Quote]:
    results = yahoo.fetch_all(symbols, yahoo.premarket_quote)
    quotes = []
    for sym, r in results.items():
        if not r:
            continue
        prev_close, price, vol = r
        quotes.append(Quote(symbol=sym, prev_close=prev_close,
                            premarket_price=price, premarket_volume=vol))
    return quotes


def run(post=slack.post) -> dict:
    now = time.time()
    universes = {
        ("QQQ", CHANNELS["qqq"]): universe.qqq_constituents(now),
        ("S&P 500", CHANNELS["sp500"]): universe.sp500_constituents(now),
        ("US > $5B", CHANNELS["other_5b"]): universe.us_5b_universe(now),
    }
    summary = {}
    for (label, channel), syms in universes.items():
        ups, downs = scan(_quotes_for(syms), PREMARKET)
        text = format_premarket(label, ups, downs)
        post(channel, text)
        summary[label] = (len(ups), len(downs))
    return summary


if __name__ == "__main__":
    print(run())

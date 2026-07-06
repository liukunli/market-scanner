"""Entrypoint: pre-market gap scan over QQQ, S&P 500, and all US > $5B.

Invoked by the Claude routine ~9:00 AM ET on trading days:
    python3 -m scanners.run_premarket
"""
from __future__ import annotations

import time

from . import universe, yahoo, slack
from .config import CHANNELS, PREMARKET, POST_THROTTLE_SECONDS
from .format import format_premarket
from .premarket import Quote, scan
from .timeutil import today_local


def _safe_post(channel, text) -> str | None:
    """Post, returning an error string on failure (never raises) so run() can
    surface it in the returned summary instead of only printing a warning."""
    error = None
    try:
        slack.post(channel, text)
    except Exception as e:  # noqa: BLE001 - never let one post abort the run
        error = str(e)
        print(f"[warn] post to {channel} failed: {error}")
    time.sleep(POST_THROTTLE_SECONDS)
    return error


def run() -> dict:
    now = time.time()
    today = today_local(now)
    session = yahoo.latest_session_date()
    if session != today:
        print(f"[skip] no live session today (latest={session}, today={today})")
        return {"skipped": True, "latest_session": session}

    qqq = set(universe.qqq_constituents(now))
    sp500 = set(universe.sp500_constituents(now))
    five_b = universe.us_5b_universe(now)

    # fetch every unique symbol ONCE, then slice per universe (was 3x overlap)
    all_syms = list(dict.fromkeys(list(qqq) + list(sp500) + list(five_b)))
    raw = yahoo.fetch_all(all_syms, yahoo.premarket_quote)
    quotes = {s: Quote(symbol=s, prev_close=r[0], premarket_price=r[1],
                      premarket_volume=r[2])
              for s, r in raw.items() if r}

    universes = [("QQQ", CHANNELS["qqq"], qqq),
                 ("S&P 500", CHANNELS["sp500"], sp500),
                 ("US > $5B", CHANNELS["other_5b"], set(five_b))]
    summary = {}
    for label, channel, members in universes:
        qs = [quotes[s] for s in members if s in quotes]
        ups, downs = scan(qs, PREMARKET)
        post_error = _safe_post(channel, format_premarket(label, ups, downs))
        summary[label] = {"ups": len(ups), "downs": len(downs), "post_error": post_error}
    return summary


if __name__ == "__main__":
    print(run())

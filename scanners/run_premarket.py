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

    universe_fetchers = [("QQQ", CHANNELS["qqq"], universe.qqq_constituents),
                        ("S&P 500", CHANNELS["sp500"], universe.sp500_constituents),
                        ("US > $5B", CHANNELS["other_5b"], universe.us_5b_universe)]
    members, fetch_errors = {}, {}
    for label, _channel, fetch_fn in universe_fetchers:
        try:
            members[label] = set(fetch_fn(now))
        except universe.UniverseFetchError as e:
            print(f"[error] {label} universe fetch failed, skipping scan/post: {e}")
            fetch_errors[label] = str(e)

    # fetch every unique symbol ONCE, then slice per universe (was 3x overlap)
    all_syms = list(dict.fromkeys(s for ms in members.values() for s in ms))
    raw = yahoo.fetch_all(all_syms, yahoo.premarket_quote)
    quotes = {s: Quote(symbol=s, prev_close=r[0], premarket_price=r[1],
                      premarket_volume=r[2])
              for s, r in raw.items() if r}

    summary = {}
    for label, channel, _fetch_fn in universe_fetchers:
        if label in fetch_errors:
            summary[label] = {"fetch_error": fetch_errors[label]}
            continue
        qs = [quotes[s] for s in members[label] if s in quotes]
        ups, downs = scan(qs, PREMARKET)
        post_error = _safe_post(channel, format_premarket(label, ups, downs))
        summary[label] = {"ups": len(ups), "downs": len(downs), "post_error": post_error}
    return summary


if __name__ == "__main__":
    print(run())

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
from .config import (CHANNELS, INDEX_ETFS, HOURLY, tier_tag,
                     MAX_SIGNALS_PER_DIRECTION, POST_THROTTLE_SECONDS)
from .hourly import scan_up, scan_down
from .signal_export import build_record
from .timeutil import today_et


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
    today = today_et(now)
    session = yahoo.latest_session_date()
    if session != today:
        print(f"[skip] no live session today (latest={session}, today={today})")
        return {"skipped": True, "latest_session": session}

    qqq = universe.qqq_constituents(now)
    sp500 = universe.sp500_constituents(now)
    symbols = list(dict.fromkeys(list(INDEX_ETFS) + universe.us_5b_universe(now)))
    bars_by = yahoo.fetch_all(symbols, yahoo.hourly_bars)

    # collect signals per direction, then rank + cap to control noise / rate limits
    found = {"up": [], "down": []}
    for sym, bars in bars_by.items():
        if not bars:
            continue
        for side in ("up", "down"):
            sig = scan_up(sym, bars, HOURLY) if side == "up" \
                else scan_down(sym, bars, HOURLY)
            if sig:
                found[side].append((sig, sym, bars))

    outdir = tempfile.mkdtemp(prefix="signals_")
    counts = {}
    for side, channel in (("up", CHANNELS["hourly_up"]),
                          ("down", CHANNELS["hourly_down"])):
        ranked = sorted(found[side], key=lambda t: -t[0].risk_reward)
        selected = ranked[:MAX_SIGNALS_PER_DIRECTION]
        for sig, sym, bars in selected:
            tag = tier_tag(sym, qqq, sp500)
            chart = _render_chart(sym, bars, side, outdir)
            try:
                post_signal(channel, _caption(sig, tag), chart)
            except Exception as e:  # noqa: BLE001 - one bad post must not abort
                print(f"[warn] post {sym} {side} failed: {e}")
            time.sleep(POST_THROTTLE_SECONDS)
        counts[side] = {"posted": len(selected), "found": len(found[side])}
    return counts


if __name__ == "__main__":
    print(run())

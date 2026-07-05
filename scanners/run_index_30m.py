"""Entrypoint: 30-minute scan of the index ETFs (QQQ, SPY, IWM), long + short.

Same 2-bar momentum mechanism as the hourly scan, on 30-minute bars. For each
signal the take-profit is expressed as an OPTION struck at the target price
(CALL for long, PUT for short) — the scanner recommends the nearest-strike
front-expiry contract and its premium.

Invoked by the Claude routine every 30 min during the trading window:
    python3 -m scanners.run_index_30m
"""
from __future__ import annotations

import os
import tempfile
import time

from . import yahoo, slack, options
from .config import CHANNELS, INDEX_ETFS, INDEX_30M, POST_THROTTLE_SECONDS
from .hourly import scan_up, scan_down
from .signal_export import build_record


def _caption(sig, opt) -> str:
    arrow = "🟢 BUY" if sig.side == "up" else "🔴 SHORT"
    word = "Up" if sig.side == "up" else "Down"
    verb = "buy CALL" if sig.side == "up" else "buy PUT"
    lines = [
        f"{arrow}  *30m Scan-{word}*  `[INDEX]`  *{sig.symbol}*",
        (f"entry `{sig.entry:.2f}`  stop `{sig.stop_loss:.2f}`  "
         f"target `{sig.take_profit:.2f}`  (R:R {sig.risk_reward:.2f}, "
         f"rvol {sig.rvol:.2f})"),
        (f"↳ move stop → entry `{sig.entry:.2f}` once price hits "
         f"`{sig.breakeven_trigger:.2f}` (breakeven, no-loss)"),
        f"🎯 TP option: {verb} — {options.describe(opt)}",
    ]
    return "\n".join(lines)


def _render_chart(symbol, bars, side, outdir):
    try:
        from .visualize import render_signal
        rec = build_record(symbol, bars, len(bars) - 1, side, INDEX_30M,
                           context=12, forward_show=0)
        if not rec:
            return None
        path = os.path.join(outdir, f"{symbol}_{side}_30m.png")
        render_signal(rec, path)
        return path
    except Exception:
        return None


def run(post_signal=slack.post_signal) -> dict:
    now = time.time()
    from .timeutil import today_local
    if yahoo.latest_session_date() != today_local(now):
        print("[skip] no live session today")
        return {"skipped": True}

    channel = CHANNELS["index_options"]
    outdir = tempfile.mkdtemp(prefix="index30_")
    counts = {"up": 0, "down": 0}
    for sym in INDEX_ETFS:
        bars = yahoo.half_hour_bars(sym)
        if not bars:
            continue
        for side in ("up", "down"):
            sig = scan_up(sym, bars, INDEX_30M) if side == "up" \
                else scan_down(sym, bars, INDEX_30M)
            if not sig:
                continue
            opt = options.option_for_signal(sym, sig.take_profit, side)
            chart = _render_chart(sym, bars, side, outdir)
            try:
                post_signal(channel, _caption(sig, opt), chart)
            except Exception as e:  # noqa: BLE001
                print(f"[warn] post {sym} {side} failed: {e}")
            time.sleep(POST_THROTTLE_SECONDS)
            counts[side] += 1
    return counts


if __name__ == "__main__":
    print(run())

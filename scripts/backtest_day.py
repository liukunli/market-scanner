"""Ad-hoc CLI: replay a scanner's signal engine over one historical trading day.

Usage:
    python3 -m scripts.backtest_day --day 2026-07-01 --scan index_30m
    python3 -m scripts.backtest_day --day 2026-07-01 --scan hourly --symbols QQQ,SPY,IWM
"""
from __future__ import annotations

import argparse
import sys

from scanners import yahoo
from scanners.backtest import backtest_symbol, summarize
from scanners.config import HOURLY, INDEX_30M

SCANS = {
    "index_30m": (INDEX_30M, yahoo.half_hour_bars),
    "hourly": (HOURLY, yahoo.hourly_bars),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True, help="target trading day, YYYY-MM-DD")
    ap.add_argument("--scan", choices=SCANS, default="index_30m")
    ap.add_argument("--symbols", default="QQQ,SPY,IWM")
    ap.add_argument("--lookback", default="2mo", help="Yahoo range param for bar fetch")
    args = ap.parse_args()

    cfg, fetch_bars = SCANS[args.scan]
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    all_trades = []
    for sym in symbols:
        bars = fetch_bars(sym, lookback=args.lookback)
        if not bars:
            print(f"[warn] no bars for {sym}", file=sys.stderr)
            continue
        trades = backtest_symbol(sym, bars, args.day, cfg=cfg)
        all_trades.extend(trades)
        print(f"\n=== {sym} ({len(trades)} signals) ===")
        for t in trades:
            print(f"  {t.side:>4} entry={t.entry:<8.2f} stop={t.stop:<8.2f} "
                  f"target={t.target:<8.2f} -> {t.outcome:<9} R={t.r_multiple:+.2f}")

    print(f"\n=== TOTAL ({args.scan}, {args.day}) ===")
    print(summarize(all_trades))


if __name__ == "__main__":
    main()

"""Ad-hoc CLI: replay a scanner's signal engine over historical trading day(s).

Usage:
    python3 -m scripts.backtest_day --day 2026-07-01 --scan index_30m
    python3 -m scripts.backtest_day --days 30 --scan index_30m --symbols QQQ,SPY,IWM
    python3 -m scripts.backtest_day --day 2026-07-01 --scan hourly --symbols QQQ,SPY,IWM
"""
from __future__ import annotations

import argparse
import sys
import time

from scanners import yahoo
from scanners.backtest import backtest_symbol, summarize
from scanners.config import HOURLY, INDEX_30M
from scanners.timeutil import local_date

SCANS = {
    "index_30m": (INDEX_30M, yahoo.half_hour_bars),
    "hourly": (HOURLY, yahoo.hourly_bars),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="single target trading day, YYYY-MM-DD")
    ap.add_argument("--days", type=int, help="replay the last N calendar days instead of one --day")
    ap.add_argument("--scan", choices=SCANS, default="index_30m")
    ap.add_argument("--symbols", default="QQQ,SPY,IWM")
    ap.add_argument("--lookback", default="45d", help="Yahoo range param for bar fetch")
    args = ap.parse_args()
    if not args.day and not args.days:
        ap.error("pass --day YYYY-MM-DD or --days N")

    cfg, fetch_bars = SCANS[args.scan]
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    all_trades = []
    per_symbol = {}
    for sym in symbols:
        bars = fetch_bars(sym, lookback=args.lookback)
        if not bars:
            print(f"[warn] no bars for {sym}", file=sys.stderr)
            continue
        if args.days:
            cutoff = time.time() - args.days * 86400
            target_days = sorted({local_date(b.ts) for b in bars if b.ts >= cutoff})
        else:
            target_days = [args.day]

        trades = []
        for day in target_days:
            trades.extend(backtest_symbol(sym, bars, day, cfg=cfg))
        all_trades.extend(trades)
        per_symbol[sym] = trades
        print(f"\n=== {sym} ({len(trades)} signals over {len(target_days)} day(s)) ===")
        for t in trades:
            print(f"  {local_date(t.bar_ts)} {t.side:>4} entry={t.entry:<8.2f} "
                  f"stop={t.stop:<8.2f} target={t.target:<8.2f} -> "
                  f"{t.outcome:<9} R={t.r_multiple:+.2f}")
        print(f"  summary: {summarize(trades)}")

    label = f"last {args.days}d" if args.days else args.day
    print(f"\n=== TOTAL ({args.scan}, {label}) ===")
    print(summarize(all_trades))


if __name__ == "__main__":
    main()

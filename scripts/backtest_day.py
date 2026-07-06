"""Ad-hoc CLI: replay a scanner's signal engine over historical trading day(s).

Usage:
    python3 -m scripts.backtest_day --day 2026-07-01 --scan index_30m
    python3 -m scripts.backtest_day --days 30 --scan index_30m --symbols QQQ,SPY,IWM
    python3 -m scripts.backtest_day --day 2026-07-01 --scan hourly --symbols QQQ,SPY,IWM
    python3 -m scripts.backtest_day --days 30 --scan hourly --symbols QQQ,SPY,IWM --trend-filter
"""
from __future__ import annotations

import argparse
import sys
import time

from scanners import yahoo
from scanners.backtest import backtest_symbol, summarize
from scanners.config import HOURLY, INDEX_30M, TREND_SMA_PERIOD
from scanners.timeutil import local_date
from scanners.trend import completed_daily_bars, trend_aligned

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
    ap.add_argument("--trend-filter", action="store_true",
                    help="apply the daily SMA(TREND_SMA_PERIOD) trend filter from scanners.trend "
                         "(matches production run_hourly.py behavior)")
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
        daily_bars = yahoo.bars(sym, interval="1d", lookback="1y") if args.trend_filter else None

        if args.days:
            cutoff = time.time() - args.days * 86400
            target_days = sorted({local_date(b.ts) for b in bars if b.ts >= cutoff})
        else:
            target_days = [args.day]

        trades = []
        for day in target_days:
            day_trades = backtest_symbol(sym, bars, day, cfg=cfg)
            if args.trend_filter:
                prior = completed_daily_bars(daily_bars, day)
                day_trades = [t for t in day_trades
                             if trend_aligned(t.side, prior, TREND_SMA_PERIOD)]
            trades.extend(day_trades)
        all_trades.extend(trades)
        per_symbol[sym] = trades
        print(f"\n=== {sym} ({len(trades)} signals over {len(target_days)} day(s)) ===")
        for t in trades:
            print(f"  {local_date(t.bar_ts)} {t.side:>4} entry={t.entry:<8.2f} "
                  f"stop={t.stop:<8.2f} target={t.target:<8.2f} -> "
                  f"{t.outcome:<9} R={t.r_multiple:+.2f}")
        print(f"  summary: {summarize(trades)}")

    label = f"last {args.days}d" if args.days else args.day
    filt = " +trend-filter" if args.trend_filter else ""
    print(f"\n=== TOTAL ({args.scan}{filt}, {label}) ===")
    print(summarize(all_trades))


if __name__ == "__main__":
    main()

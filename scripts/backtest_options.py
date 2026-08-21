"""CLI: backtest a 0DTE/1DTE options strategy and render the PnL curve chart.

Usage:
    python3 -m scripts.backtest_options --symbol SPY --dte 0 --lookback 2y
    python3 -m scripts.backtest_options --symbol QQQ --dte 1 --capital 25000 \\
        --short-delta 0.12 --wing-width 6 --out qqq_1dte.png
"""
from __future__ import annotations

import argparse
import json

from scanners import yahoo
from dte_lab.engine import BacktestConfig, run
from dte_lab.metrics import summarize
from dte_lab.strategy import IronCondorConfig, IronCondorStrategy
from dte_lab.visualize import plot_backtest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="SPY")
    ap.add_argument("--dte", type=int, default=0, help="0 = same-day expiry, 1 = next-day")
    ap.add_argument("--lookback", default="2y", help="Yahoo range param for daily bars")
    ap.add_argument("--capital", type=float, default=50_000.0)
    ap.add_argument("--risk-pct", type=float, default=0.02, help="fraction of equity risked per trade")
    ap.add_argument("--short-delta", type=float, default=0.16)
    ap.add_argument("--wing-width", type=float, default=5.0)
    ap.add_argument("--iv-rv-multiplier", type=float, default=1.15)
    ap.add_argument("--out", default=None, help="chart PNG path (default: {symbol}_{dte}dte.png)")
    args = ap.parse_args()

    bars = yahoo.bars(args.symbol, interval="1d", lookback=args.lookback)
    if not bars:
        raise SystemExit(f"no daily bars for {args.symbol}")

    strategy = IronCondorStrategy(IronCondorConfig(
        short_delta=args.short_delta, wing_width=args.wing_width))
    config = BacktestConfig(
        strategy=strategy, dte=args.dte, starting_capital=args.capital,
        risk_pct_per_trade=args.risk_pct, iv_rv_multiplier=args.iv_rv_multiplier)

    results = run(bars, config)
    summary = summarize(results)
    print(json.dumps(summary, indent=2))

    out_path = args.out or f"{args.symbol.lower()}_{args.dte}dte.png"
    plot_backtest(results, args.symbol, "Iron Condor", args.dte, out_path)
    print(f"chart -> {out_path}")


if __name__ == "__main__":
    main()

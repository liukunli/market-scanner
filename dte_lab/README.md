# dte_lab — 0DTE / 1DTE options strategy backtesting

A strategy framework for defined-risk options structures on daily-expiry
underlyings (SPY/QQQ/IWM and similar), with iron condor as the first
strategy plugged in. Produces a compounding equity curve, daily PnL, and a
drawdown chart from a single CLI call.

## This is a pricing model, not a replay of real fills

**There is no historical options-chain data anywhere in this package.**
Every option price is a Black-Scholes estimate. Concretely:

- **Spot** comes from real daily OHLC (`scanners.yahoo.bars`).
- **Implied volatility** is *not* observed — it's a proxy: trailing
  realized volatility of the underlying's own closes, scaled by a fixed
  multiplier (`iv_rv_multiplier`, default 1.25, from the historical
  VIX-over-realized-SPX-vol premium) to approximate the volatility risk
  premium. This is a blunt, non-regime-aware assumption — it won't spike
  ahead of an FOMC print or an earnings gap the way real IV does, and it
  won't capture the term-structure difference between a 0DTE option's IV
  and 1-month IV.
  **This one number dominates every backtest result far more than any
  strategy parameter does** — a sweep across delta/wing-width/multiplier on
  SPY 0DTE swung total 2-year return from -49% to +169% *purely* from
  moving the multiplier 1.15 → 1.6, because it's assuming an edge (the
  credit is priced off the inflated IV, settlement is priced off the real
  historical path), not discovering one. Treat any backtest run with a
  hand-picked multiplier as "here's what happens if this much vol premium
  is real," not as evidence of a working strategy.
- **Option prices** (and the delta-targeted strike selection) are pure
  Black-Scholes given that spot + IV. No bid/ask spread, no slippage, no
  commissions.
- **No real intraday path.** Only the day's Open/High/Low/Close are
  available. An optional stop-loss (`stop_loss_multiple`, e.g. 2.0 = exit
  at 2x the credit received) is *approximated* by checking whether the
  structure's intrinsic-value PnL at the day's high or low would have
  breached it, and if so capping the loss there instead of the close. This
  can't reproduce real path dependence (a move that breaches and
  un-breaches *between* the sampled high/low/close points isn't visible).
  **Off by default** (`stop_loss_multiple=None`, hold to expiration):
  tested against the default IronCondorConfig (16-delta, 5-wide) on SPY
  0DTE, an active stop made results *worse* at every tightness tested,
  converging back to the no-stop baseline as it loosened. The credit
  collected on a thin, far-OTM structure is small relative to its width,
  so a credit-multiple stop sits close to ordinary daily noise — it
  converts positions that dip and recover by the close into locked-in
  losses more often than it prevents real blowups. It may earn its keep on
  a wider-credit/closer-to-the-money structure; verify with and without it
  for any given configuration rather than assuming it helps.
- **Position sizing** risks a fixed fraction of current equity
  (`risk_pct_per_trade`) per trade, sized against the *effective* loss
  (the stop-loss level, when it's tighter than the structure's theoretical
  Black-Scholes max loss) — this is what drives the compounding equity
  curve.

Read backtest output as *"what this strategy should have earned under
Black-Scholes pricing and this vol assumption"*, not as a historical
record of achievable fills. Before trading anything derived from this,
validate against real quoted option prices.

## Layout

| Module | Responsibility |
|--------|----------------|
| `blackscholes.py` | European option pricing, delta, delta-targeted strike selection (stdlib only) |
| `volatility.py` | realized-vol-based IV proxy |
| `strategy.py` | `Strategy` ABC + `Leg`/`TradeSetup`; `IronCondorStrategy` is the first implementation |
| `engine.py` | day-by-day backtest loop: entry pricing, settlement, compounding equity |
| `metrics.py` | running peak / drawdown %, summary stats |
| `visualize.py` | 3-panel PnL chart (equity + drawdown shading, daily PnL bars, drawdown % band) |

## Run

```bash
python3 -m scripts.backtest_options --symbol SPY --dte 0 --lookback 2y
python3 -m scripts.backtest_options --symbol QQQ --dte 1 --capital 25000 \
    --short-delta 0.12 --wing-width 6 --out qqq_1dte.png
```

## Adding a new strategy

Implement `Strategy.build(spot, iv, t_years, rate) -> TradeSetup | None`,
returning `None` to skip a day (e.g. thin credit, degenerate pricing). The
engine and chart are strategy-agnostic — everything downstream of `build()`
just consumes `TradeSetup.legs` and `settlement_pnl_per_share()`.

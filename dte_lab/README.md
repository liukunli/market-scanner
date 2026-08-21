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
  multiplier (`iv_rv_multiplier`, default 1.15) to approximate the
  volatility risk premium. This is a blunt, non-regime-aware assumption —
  it won't spike ahead of an FOMC print or an earnings gap the way real IV
  does, and it won't capture the term-structure difference between a 0DTE
  option's IV and 1-month IV.
- **Option prices** (and the delta-targeted strike selection) are pure
  Black-Scholes given that spot + IV. No bid/ask spread, no slippage, no
  commissions.
- **Settlement is close-to-close.** A position is always held to
  expiration and settled against the actual closing price that day — there
  is no intraday path, so nothing is ever stopped out or closed early
  intra-day. Real 0DTE traders typically manage risk with intraday stops;
  this model can't represent that, which likely makes its drawdowns worse
  and more concentrated than a stop-managed strategy would see.
- **Position sizing** risks a fixed fraction of current equity
  (`risk_pct_per_trade`) per trade, based on the structure's Black-Scholes
  max loss — this is what drives the compounding equity curve.

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

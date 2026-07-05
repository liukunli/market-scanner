# market-scanner

Pre-market **gap** and 1-hour **momentum** scanners over Yahoo Finance data,
posting signals to Slack. Designed to be driven by a scheduled Claude routine
(or any cron), but every entrypoint also runs standalone.

Runtime dependencies: **Python 3.9+ standard library only** (no pip install
needed to run). `pytest` is used for the test suite.

## Universes

| Scan | Universe |
|------|----------|
| Pre-market gap | QQQ (Nasdaq-100), S&P 500, all US stocks with market cap > $5B |
| 1-hour up/down | all US > $5B + index ETFs QQQ / SPY / IWM |

## Package layout

| Module | Responsibility |
|--------|----------------|
| `scanners/config.py` | thresholds, channel IDs, universe defs (tune here) |
| `scanners/yahoo.py` | Yahoo Finance client (daily / hourly / pre-post bars) |
| `scanners/universe.py` | constituent lists with a once-per-day disk cache |
| `scanners/premarket.py` | pre-market gap logic (pure) |
| `scanners/hourly.py` | 1-hour scan-up / scan-down engine (pure) |
| `scanners/format.py` | Slack message rendering |
| `scanners/slack.py` | posting + channel routing |
| `scanners/run_premarket.py` | entrypoint — 3 gap scans |
| `scanners/run_hourly.py` | entrypoint — hourly up/down |
| `scripts/slack_notify.py` | standalone Slack poster (webhook or bot token) |

## Signal — 1-hour scan-up

Last two completed 1h bars `p` (prev), `c` (curr). **BUY** when all hold:

1. both green and `c.close > p.close`  (continuous growth)
2. `c.low ≥ p.high − 0.15·p.range`  (low near prior high)
3. `(p.close − c.low)/p.range ≤ 0.20`  (minimal drawback)
4. `|g_c − g_p| / max(g_c,g_p) ≤ 0.40`, `g = close−open`  (same magnitude)
5. `avg(p.vol,c.vol)/avg(20 prior bars) ≥ 1.2`  (relative volume)

- **entry** = `c.close`   **stop** = `(c.high+c.low)/2`   **target** = `entry + 2·(g_p+g_c)/2`

Scan-down is the mirror image. Thresholds live in `scanners/config.HourlyConfig`.

## Channel routing (priority)

index ETF (QQQ/SPY/IWM) → `#signals-index-etf`; else QQQ constituent →
`#signals-qqq`; else S&P 500 → `#signals-sp500`; else → `#signals-other-5b`.
Channel IDs are set in `scanners/config.py`.

## Run

```bash
export SLACK_BOT_TOKEN="xoxb-..."      # bot token with chat:write, joined to the channels
python3 -m scanners.run_premarket      # ~9:00 AM ET
python3 -m scanners.run_hourly         # each bar close, 09:30–16:00 ET
```

## Test

```bash
python3 -m pytest tests/ -q            # 30 tests, fully mocked, no network
```

## Scheduling

A Claude cloud routine runs the entrypoints on a cron. Times are UTC; for EDT
(summer): pre-market `0 13 * * 1-5`, hourly `30 14-19 * * 1-5` + `0 20 * * 1-5`.
Shift crons back 1 hour for EST (winter).

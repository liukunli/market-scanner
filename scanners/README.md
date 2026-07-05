# Yahoo → Scanner → Slack

Pre-market gap and 1-hour momentum scanners over Yahoo Finance data, posting
signals to Slack. Designed to be driven by a scheduled Claude routine.

## Layout

| Module | Responsibility |
|--------|----------------|
| `config.py` | thresholds, channel IDs, universe defs (edit here to tune) |
| `yahoo.py` | Yahoo Finance client (daily / hourly / pre-post bars) |
| `universe.py` | constituent lists (QQQ, S&P 500, all US > $5B) with daily cache |
| `premarket.py` | pre-market gap logic (pure) |
| `hourly.py` | 1-hour scan-up / scan-down signal engine (pure) |
| `format.py` | Slack message rendering |
| `slack.py` | posting + channel routing |
| `run_premarket.py` | entrypoint: 3 gap scans (QQQ / S&P 500 / >$5B) |
| `run_hourly.py` | entrypoint: hourly up/down over >$5B + index ETFs |

## Signal — 1-hour scan-up

Last two completed 1h bars `p` (prev), `c` (curr). BUY when **all** hold:

1. both green and `c.close > p.close`
2. `c.low ≥ p.high − 0.15·p.range`  (low near prior high)
3. `(p.close − c.low)/p.range ≤ 0.20`  (minimal drawback)
4. `|g_c − g_p| / max(g_c,g_p) ≤ 0.40`, `g = close−open`  (same magnitude)
5. `avg(p.vol,c.vol)/avg(20 prior bars) ≥ 1.2`  (relative volume)

- **entry** = `c.close`   **stop** = `(c.high+c.low)/2`   **target** = `entry + 2·(g_p+g_c)/2`

Scan-down is the mirror. Thresholds live in `config.HourlyConfig`.

## Channel routing (priority)

`index ETF (QQQ/SPY/IWM)` → `#signals-index-etf`; else QQQ constituent →
`#signals-qqq`; else S&P 500 → `#signals-sp500`; else → `#signals-other-5b`.

## Run

```bash
export SLACK_BOT_TOKEN="xoxb-..."
python3 -m scanners.run_premarket     # ~9:00 AM ET
python3 -m scanners.run_hourly        # each bar close during 09:30–16:00 ET
```

## Test

```bash
python3 -m pytest tests/ -q
```

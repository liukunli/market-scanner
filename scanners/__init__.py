"""Yahoo Finance → scanner → Slack alerting package.

Modules:
    config     tunable thresholds, channel routing, universes
    yahoo      Yahoo Finance data client (daily / hourly / pre-post bars)
    universe   constituent lists (QQQ, S&P 500, all US > $5B) with disk cache
    premarket  pre-market gap scanner (pure logic)
    hourly     1-hour scan-up / scan-down signal engine (pure logic)
    format     Slack message rendering
    slack      posting + channel routing
    run_premarket / run_hourly   entrypoints invoked by the Claude routine
"""
__all__ = [
    "config",
    "yahoo",
    "universe",
    "premarket",
    "hourly",
    "format",
    "slack",
]

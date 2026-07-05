"""Tunable configuration: thresholds, channel routing, universe definitions."""
from dataclasses import dataclass

# Timezone used for all displayed timestamps (auto-handles PST/PDT via zoneinfo).
DISPLAY_TZ = "America/Los_Angeles"

# Slack bot token fallback. The SLACK_BOT_TOKEN env var takes precedence (see
# slack.py); this hardcoded value is used only when the env var is unset.
# NOTE: committed secret — treat as public and rotate if leaked.
SLACK_BOT_TOKEN = "xoxb-11547443072976-11512889034259-uOAAdZfzpnmRt5rM2JCzu8RR"

# --- Index ETFs treated as their own focus tier ---------------------------------
INDEX_ETFS = ("QQQ", "SPY", "IWM")

# --- Slack channel IDs (active channels in the "trading" workspace) -------------
CHANNELS = {
    # index 30-min signals with option targets (QQQ / SPY / IWM):
    "index_options": "C0BF99KNPEW",  # #options-qqq-spy-iwm
    # pre-market gap tiers:
    "qqq": "C0BETQ3FV3R",           # #signals-qqq         (Nasdaq-100 constituents)
    "sp500": "C0BF2TKPNJF",         # #signals-sp500       (S&P 500 constituents)
    "other_5b": "C0BF95NT1R8",      # #signals-other-5b    (other US > $5B)
    # 1-hour momentum signals route by DIRECTION:
    "hourly_up": "C0BF5R1ARJ9",     # #one-hour-signals-up   (scan-up / BUY)
    "hourly_down": "C0BF9531XFU",   # #one-hour-signals-down (scan-down / SHORT)
}

# Tier tag shown on each hourly line (focus: index ETF > QQQ > S&P 500 > other).
def tier_tag(symbol: str, qqq, sp500) -> str:
    if symbol in INDEX_ETFS:
        return "ETF"
    if symbol in set(qqq):
        return "QQQ"
    if symbol in set(sp500):
        return "SPX"
    return "5B"


@dataclass(frozen=True)
class HourlyConfig:
    """Thresholds for the 1-hour scan-up / scan-down signal engine.

    All fractions are relative to the *previous* bar's range unless noted.
    """
    low_near_high_frac: float = 0.15   # current low must sit within this frac of prev high
    max_drawback_frac: float = 0.20    # retrace of current low below prev close, as frac of prev range
    magnitude_tol: float = 0.40        # |g_c - g_p| / max(g_c, g_p) must be <= this
    rvol_min: float = 1.2              # avg(vol of 2 bars) / avg(prior N bars) must be >= this
    vol_lookback: int = 20             # N bars used for the average-volume baseline
    tp_bars: int = 2                   # project take-profit this many bars of same magnitude ahead
    min_bars: int = 3                  # minimum bars required to evaluate (2 signal + >=1 baseline)
    breakeven_trigger_frac: float = 0.5  # once price moves this fraction of the current bar's
                                         # range in-favor, the stop is moved to entry (breakeven)


@dataclass(frozen=True)
class PremarketConfig:
    """Thresholds for the pre-market gap scanner."""
    min_abs_gap_pct: float = 0.0       # ignore |gap| below this (0 = no filter)
    min_premarket_volume: int = 0      # ignore names with pre-market volume below this
    top_n: int = 20                    # how many names per direction to report


HOURLY = HourlyConfig()

# Index 30-min scan (QQQ/SPY/IWM) — looser gates, calibrated on 60d of 30m bars
# to fire ~0.5-1 signal/day per ticker (QQQ 0.80, SPY 0.67, IWM 0.82). The stock
# hourly scan stays strict (HOURLY above).
INDEX_30M = HourlyConfig(
    rvol_min=0.8,
    magnitude_tol=0.7,
    low_near_high_frac=0.35,
    max_drawback_frac=0.35,
)

PREMARKET = PremarketConfig()

# --- routine safeguards ---------------------------------------------------------
MAX_SIGNALS_PER_DIRECTION = 15   # cap hourly posts/charts per run (ranked by R:R)
POST_THROTTLE_SECONDS = 1.1      # spacing between Slack posts to avoid 429s

"""Tunable configuration: thresholds, channel routing, universe definitions."""
from dataclasses import dataclass

# --- Index ETFs treated as their own focus tier ---------------------------------
INDEX_ETFS = ("QQQ", "SPY", "IWM")

# --- Slack channel IDs (created in the "trading" workspace) ---------------------
CHANNELS = {
    "index_etf": "C0BF2TKURLK",     # #signals-index-etf   (QQQ / SPY / IWM ETF signals)
    "qqq": "C0BETQ3FV3R",           # #signals-qqq         (Nasdaq-100 constituents)
    "sp500": "C0BF2TKPNJF",         # #signals-sp500       (S&P 500 constituents)
    "other_5b": "C0BF95NT1R8",      # #signals-other-5b    (other US > $5B)
    "premarket_rollup": "C0BF94H8Y90",  # #alerts-premarket-gap (pre-market summary)
}


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


@dataclass(frozen=True)
class PremarketConfig:
    """Thresholds for the pre-market gap scanner."""
    min_abs_gap_pct: float = 0.0       # ignore |gap| below this (0 = no filter)
    min_premarket_volume: int = 0      # ignore names with pre-market volume below this
    top_n: int = 20                    # how many names per direction to report


HOURLY = HourlyConfig()
PREMARKET = PremarketConfig()

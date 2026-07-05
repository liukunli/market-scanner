"""Pre-market gap scanner (pure logic).

A "gap" is the pre-market price relative to the previous regular-session close:
    gap_pct = (premarket_price - prev_close) / prev_close * 100

Runs identically over any universe (QQQ / S&P 500 / all US > $5B); the caller
supplies the rows and the universe label.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Sequence

from .config import PremarketConfig, PREMARKET


@dataclass(frozen=True)
class Quote:
    symbol: str
    prev_close: float
    premarket_price: float
    premarket_volume: float = 0.0


@dataclass(frozen=True)
class GapResult:
    symbol: str
    gap_pct: float
    prev_close: float
    premarket_price: float
    premarket_volume: float

    def to_dict(self) -> dict:
        return asdict(self)


def compute_gap(prev_close: float, premarket_price: float) -> Optional[float]:
    if not prev_close or prev_close <= 0 or premarket_price <= 0:
        return None
    return (premarket_price - prev_close) / prev_close * 100.0


def scan(quotes: Sequence[Quote], cfg: PremarketConfig = PREMARKET):
    """Return (gap_ups, gap_downs), each sorted by descending magnitude."""
    results = []
    for q in quotes:
        gap = compute_gap(q.prev_close, q.premarket_price)
        if gap is None:
            continue
        if abs(gap) < cfg.min_abs_gap_pct:
            continue
        if q.premarket_volume < cfg.min_premarket_volume:
            continue
        results.append(GapResult(
            symbol=q.symbol, gap_pct=round(gap, 3), prev_close=q.prev_close,
            premarket_price=q.premarket_price, premarket_volume=q.premarket_volume,
        ))

    ups = sorted((r for r in results if r.gap_pct > 0), key=lambda r: -r.gap_pct)
    downs = sorted((r for r in results if r.gap_pct < 0), key=lambda r: r.gap_pct)
    return ups[:cfg.top_n], downs[:cfg.top_n]

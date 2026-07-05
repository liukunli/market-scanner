"""Unit tests for the pre-market gap scanner."""
import pytest

from scanners.premarket import Quote, GapResult, compute_gap, scan
from scanners.config import PremarketConfig


def test_compute_gap_basic():
    assert compute_gap(100.0, 105.0) == pytest.approx(5.0)
    assert compute_gap(100.0, 97.0) == pytest.approx(-3.0)


def test_compute_gap_guards():
    assert compute_gap(0, 105.0) is None
    assert compute_gap(-1, 105.0) is None
    assert compute_gap(100.0, 0) is None


def test_scan_ranks_both_directions():
    quotes = [
        Quote("AAA", 100, 110),   # +10%
        Quote("BBB", 100, 103),   # +3%
        Quote("CCC", 100, 94),    # -6%
        Quote("DDD", 100, 98),    # -2%
        Quote("EEE", 0, 50),      # invalid -> dropped
    ]
    ups, downs = scan(quotes)
    assert [r.symbol for r in ups] == ["AAA", "BBB"]
    assert [r.symbol for r in downs] == ["CCC", "DDD"]
    assert isinstance(ups[0], GapResult)


def test_scan_min_gap_filter():
    quotes = [Quote("AAA", 100, 101), Quote("BBB", 100, 110)]
    cfg = PremarketConfig(min_abs_gap_pct=5.0)
    ups, downs = scan(quotes, cfg)
    assert [r.symbol for r in ups] == ["BBB"]


def test_scan_volume_filter():
    quotes = [Quote("AAA", 100, 110, premarket_volume=10),
              Quote("BBB", 100, 108, premarket_volume=5000)]
    cfg = PremarketConfig(min_premarket_volume=1000)
    ups, _ = scan(quotes, cfg)
    assert [r.symbol for r in ups] == ["BBB"]


def test_scan_top_n():
    quotes = [Quote(f"S{i}", 100, 100 + i) for i in range(1, 30)]
    cfg = PremarketConfig(top_n=3)
    ups, _ = scan(quotes, cfg)
    assert len(ups) == 3
    assert ups[0].symbol == "S29"  # largest gap first

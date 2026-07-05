"""Tests for the option-target picker (pure logic; no network)."""
from scanners.options import pick_contract, _premium, describe


CHAIN = [
    {"strike": 615, "bid": 3.0, "ask": 3.4, "lastPrice": 3.1,
     "contractSymbol": "QQQ...C615", "expiration": 1783094400},
    {"strike": 620, "bid": 1.2, "ask": 1.4, "lastPrice": 1.3,
     "contractSymbol": "QQQ...C620", "expiration": 1783094400},
    {"strike": 625, "bid": 0.4, "ask": 0.6, "lastPrice": 0.5,
     "contractSymbol": "QQQ...C625", "expiration": 1783094400},
]


def test_pick_nearest_strike():
    assert pick_contract(CHAIN, 621)["strike"] == 620
    assert pick_contract(CHAIN, 624)["strike"] == 625


def test_pick_tie_prefers_lower_strike():
    # target 617.5 is equidistant from 615 and 620 -> lower (615) wins
    assert pick_contract(CHAIN, 617.5)["strike"] == 615


def test_pick_empty():
    assert pick_contract([], 620) is None
    assert pick_contract([{"strike": None}], 620) is None


def test_premium_mid_then_last():
    assert _premium({"bid": 1.0, "ask": 2.0, "lastPrice": 9}) == 1.5
    assert _premium({"bid": 0, "ask": 0, "lastPrice": 1.3}) == 1.3


def test_describe_formats_contract():
    opt = {"symbol": "QQQ", "type": "call", "strike": 620, "expiry": "2026-07-10",
           "premium": 1.30, "contract": "x", "approximate": False}
    s = describe(opt)
    assert "QQQ" in s and "2026-07-10" in s and "C620" in s and "1.30" in s


def test_describe_approximate_put():
    opt = {"symbol": "SPY", "type": "put", "strike": 500, "expiry": None,
           "premium": None, "contract": None, "approximate": True}
    s = describe(opt)
    assert "P500" in s and "approx" in s

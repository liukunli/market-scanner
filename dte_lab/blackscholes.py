"""European option pricing (Black-Scholes-Merton), stdlib only.

No dividend yield term - fine for the short-dated index ETFs this package
targets (SPY/QQQ/IWM), where a 0-1 day dividend drag is negligible.
"""
from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()


def _d1_d2(spot: float, strike: float, t_years: float, rate: float, sigma: float) -> tuple[float, float]:
    if t_years <= 0 or sigma <= 0:
        raise ValueError("t_years and sigma must be positive")
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return d1, d2


def call_price(spot: float, strike: float, t_years: float, rate: float, sigma: float) -> float:
    d1, d2 = _d1_d2(spot, strike, t_years, rate, sigma)
    return spot * _N.cdf(d1) - strike * math.exp(-rate * t_years) * _N.cdf(d2)


def put_price(spot: float, strike: float, t_years: float, rate: float, sigma: float) -> float:
    d1, d2 = _d1_d2(spot, strike, t_years, rate, sigma)
    return strike * math.exp(-rate * t_years) * _N.cdf(-d2) - spot * _N.cdf(-d1)


def call_delta(spot: float, strike: float, t_years: float, rate: float, sigma: float) -> float:
    d1, _ = _d1_d2(spot, strike, t_years, rate, sigma)
    return _N.cdf(d1)


def put_delta(spot: float, strike: float, t_years: float, rate: float, sigma: float) -> float:
    d1, _ = _d1_d2(spot, strike, t_years, rate, sigma)
    return _N.cdf(d1) - 1.0


def strike_for_delta(spot: float, t_years: float, rate: float, sigma: float,
                     target_delta: float, option_type: str) -> float:
    """Closed-form strike whose BS delta equals target_delta (a positive
    magnitude in (0, 1) for both calls and puts - e.g. 0.16 for a "16-delta"
    short strike). Inverts delta = N(d1) [call] or N(d1) - 1 [put] via the
    inverse normal CDF, then solves the standard d1 formula for K.
    """
    if not 0 < target_delta < 1:
        raise ValueError("target_delta must be in (0, 1)")
    if option_type == "call":
        d1 = _N.inv_cdf(target_delta)
    elif option_type == "put":
        d1 = _N.inv_cdf(1.0 - target_delta)
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")
    sqrt_t = math.sqrt(t_years)
    return spot * math.exp(-(d1 * sigma * sqrt_t - (rate + 0.5 * sigma * sigma) * t_years))


def intrinsic_value(spot: float, strike: float, option_type: str) -> float:
    if option_type == "call":
        return max(spot - strike, 0.0)
    if option_type == "put":
        return max(strike - spot, 0.0)
    raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")

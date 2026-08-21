"""Strategy framework: a Strategy turns (spot, iv, time-to-expiry) into a
defined-risk options structure. Iron condor is the first implementation;
new strategies plug in by implementing `Strategy.build`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from . import blackscholes as bs


@dataclass(frozen=True)
class Leg:
    option_type: str   # "call" | "put"
    strike: float
    side: str           # "short" | "long"

    def price(self, spot: float, t_years: float, rate: float, sigma: float) -> float:
        fn = bs.call_price if self.option_type == "call" else bs.put_price
        return fn(spot, self.strike, t_years, rate, sigma)

    def settlement_pnl_per_share(self, spot_settle: float) -> float:
        """PnL per share at expiration, excluding the premium paid/received
        (the engine nets that in separately as the trade's credit)."""
        intrinsic = bs.intrinsic_value(spot_settle, self.strike, self.option_type)
        return -intrinsic if self.side == "short" else intrinsic


@dataclass(frozen=True)
class TradeSetup:
    legs: tuple[Leg, ...]
    credit_per_share: float   # net premium received, > 0 for a credit structure
    max_loss_per_share: float  # worst-case loss per share at expiration

    def settlement_pnl_per_share(self, spot_settle: float) -> float:
        return self.credit_per_share + sum(leg.settlement_pnl_per_share(spot_settle) for leg in self.legs)


class Strategy(ABC):
    """A strategy builds a TradeSetup from that day's market state. Returning
    None means "skip this day" (e.g. credit too thin to be worth the risk)."""

    @abstractmethod
    def build(self, spot: float, iv: float, t_years: float, rate: float) -> TradeSetup | None:
        ...


@dataclass(frozen=True)
class IronCondorConfig:
    short_delta: float = 0.16        # magnitude - sell ~16-delta strikes both sides
    wing_width: float = 5.0          # points between short and long strike, each side
    strike_increment: float = 1.0    # round strikes to this increment
    min_credit_frac_of_width: float = 0.10  # skip the day if credit < this * wing_width


class IronCondorStrategy(Strategy):
    """Short strangle at `short_delta`, each side hedged by a long strike
    `wing_width` further out (the classic defined-risk iron condor)."""

    def __init__(self, config: IronCondorConfig = IronCondorConfig()):
        self.config = config

    def _round_strike(self, strike: float) -> float:
        inc = self.config.strike_increment
        return round(strike / inc) * inc

    def build(self, spot: float, iv: float, t_years: float, rate: float) -> TradeSetup | None:
        cfg = self.config
        call_short_k = self._round_strike(
            bs.strike_for_delta(spot, t_years, rate, iv, cfg.short_delta, "call"))
        put_short_k = self._round_strike(
            bs.strike_for_delta(spot, t_years, rate, iv, cfg.short_delta, "put"))
        call_long_k = call_short_k + cfg.wing_width
        put_long_k = put_short_k - cfg.wing_width
        if put_long_k <= 0:
            return None

        legs = (
            Leg("call", call_short_k, "short"),
            Leg("call", call_long_k, "long"),
            Leg("put", put_short_k, "short"),
            Leg("put", put_long_k, "long"),
        )
        credit = sum(
            (leg.price(spot, t_years, rate, iv) * (1 if leg.side == "short" else -1))
            for leg in legs
        )
        max_loss = cfg.wing_width - credit
        if credit <= 0 or max_loss <= 0:
            return None  # mispriced / degenerate under this vol assumption - skip
        if credit < cfg.min_credit_frac_of_width * cfg.wing_width:
            return None  # not enough premium to justify the risk
        return TradeSetup(legs=legs, credit_per_share=credit, max_loss_per_share=max_loss)

"""Map a signal's take-profit level to a tradable option contract.

Idea: rather than exit the underlying at the target, express the profit target
as an option struck at that price — for a long (scan-up) buy a CALL at the
target, for a short (scan-down) buy a PUT at the target. The scanner reports the
nearest-strike front-expiry contract and its premium.

`pick_contract` is pure and unit-tested; `option_for_signal` adds the network
fetch and degrades to an approximate contract (no live premium) if the chain
can't be retrieved.
"""
from __future__ import annotations

from typing import Optional, Sequence

from . import yahoo
from .timeutil import utc_date


def pick_contract(contracts: Sequence[dict], target: float) -> Optional[dict]:
    """Return the contract whose strike is nearest `target` (ties -> lower strike)."""
    valid = [c for c in contracts if c.get("strike") is not None]
    if not valid:
        return None
    return min(valid, key=lambda c: (abs(c["strike"] - target), c["strike"]))


def _premium(c: dict) -> Optional[float]:
    """Best available price: mid of bid/ask, else lastPrice."""
    bid, ask = c.get("bid"), c.get("ask")
    if bid and ask:
        return round((bid + ask) / 2, 2)
    return c.get("lastPrice")


def option_for_signal(symbol: str, target: float, side: str) -> Optional[dict]:
    """Recommend the option that represents this signal's take-profit target.

    side 'up' -> CALL at target, 'down' -> PUT at target. Returns a dict with
    type/strike/expiry/premium (premium None if the live chain is unavailable).
    """
    opt_type = "call" if side == "up" else "put"
    chain = yahoo.option_chain(symbol)
    if not chain or not chain.get("options"):
        # graceful fallback: approximate contract, no live premium/exact strike
        return {"symbol": symbol, "type": opt_type, "strike": round(target),
                "expiry": None, "premium": None, "contract": None,
                "approximate": True}

    front = chain["options"][0]
    contracts = front.get("calls" if opt_type == "call" else "puts", [])
    c = pick_contract(contracts, target)
    if not c:
        return {"symbol": symbol, "type": opt_type, "strike": round(target),
                "expiry": None, "premium": None, "contract": None,
                "approximate": True}
    exp = c.get("expiration")
    return {"symbol": symbol, "type": opt_type, "strike": c["strike"],
            "expiry": utc_date(exp) if exp else None, "premium": _premium(c),
            "contract": c.get("contractSymbol"), "approximate": False}


def describe(opt: Optional[dict]) -> str:
    """One-line human/Slack description of the recommended option."""
    if not opt:
        return ""
    t = "C" if opt["type"] == "call" else "P"
    exp = opt.get("expiry") or "front"
    prem = f" @ ~${opt['premium']:.2f}" if opt.get("premium") else ""
    approx = " (approx)" if opt.get("approximate") else ""
    return f"{opt['symbol']} {exp} {t}{opt['strike']:g}{prem}{approx}"

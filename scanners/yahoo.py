"""Yahoo Finance data client (daily / hourly / pre-post-market bars).

Network layer only — kept separate from the pure signal logic so it can be
monkeypatched out in tests.
"""
from __future__ import annotations

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .hourly import Bar

_UA = {"User-Agent": "Mozilla/5.0"}
_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}"


def _get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _chart(symbol: str, params: str) -> Optional[dict]:
    try:
        d = _get_json(_CHART.format(sym=symbol.replace(".", "-"), q=params))
        res = d["chart"]["result"]
        return res[0] if res else None
    except Exception:
        return None


def hourly_bars(symbol: str, lookback: str = "1mo") -> list[Bar]:
    """Completed 1-hour bars (drops null and zero-volume close-snapshot bars)."""
    res = _chart(symbol, f"interval=1h&range={lookback}")
    if not res:
        return []
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    bars = []
    for t, o, h, l, c, v in zip(ts, q["open"], q["high"], q["low"], q["close"], q["volume"]):
        if None in (o, h, l, c) or not v:
            continue
        bars.append(Bar(ts=t, open=o, high=h, low=l, close=c, volume=v))
    return bars


def premarket_quote(symbol: str) -> Optional[tuple[float, float, float]]:
    """Return (prev_close, premarket_price, premarket_volume) or None.

    Uses the latest pre/post bar as the pre-market price; falls back to the
    chart meta regularMarketPrice when no pre-market print exists yet.
    """
    res = _chart(symbol, "interval=1m&range=1d&includePrePost=true")
    if not res:
        return None
    meta = res.get("meta", {})
    prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
    if not prev_close:
        return None
    price = meta.get("regularMarketPrice")
    pm_vol = 0.0
    # prefer the most recent non-null pre/post print
    ts = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    closes, vols = q.get("close") or [], q.get("volume") or []
    for i in range(len(closes) - 1, -1, -1):
        if closes[i] is not None:
            price = closes[i]
            pm_vol = vols[i] or 0.0
            break
    if price is None:
        return None
    return float(prev_close), float(price), float(pm_vol)


def fetch_all(symbols, fn: Callable[[str], object], max_workers: int = 25) -> dict:
    """Run `fn` over symbols concurrently → {symbol: result}."""
    out = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fn, s): s for s in symbols}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
    return out

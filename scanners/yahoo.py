"""Yahoo Finance data client (daily / hourly / pre-post-market bars).

Network layer only — kept separate from the pure signal logic so it can be
monkeypatched out in tests.
"""
from __future__ import annotations

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .hourly import Bar
from .timeutil import local_date

_UA = {"User-Agent": "Mozilla/5.0"}
_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}"


def _get_json(url: str, timeout: int = 15, retries: int = 2) -> dict:
    """GET with small exponential backoff so a transient failure/429 doesn't
    silently drop a symbol on a scheduled run."""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001 - retry any transient error
            last = e
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))
    raise last


def _chart(symbol: str, params: str) -> Optional[dict]:
    try:
        d = _get_json(_CHART.format(sym=symbol.replace(".", "-"), q=params))
        res = d["chart"]["result"]
        return res[0] if res else None
    except Exception:
        return None


def latest_session_date(probe: str = "SPY") -> Optional[str]:
    """Local (display-zone) date of the most recent price print for `probe`,
    including pre/post-market. Used to detect holidays: if this != today,
    there is no live session and scanners should not post."""
    res = _chart(probe, "interval=1m&range=1d&includePrePost=true")
    if not res:
        return None
    ts = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    closes = q.get("close") or []
    for i in range(len(closes) - 1, -1, -1):
        if closes[i] is not None:
            return local_date(ts[i])
    rmt = res.get("meta", {}).get("regularMarketTime")
    return local_date(rmt) if rmt else None


def bars(symbol: str, interval: str = "1h", lookback: str = "1mo") -> list[Bar]:
    """Completed intraday bars at `interval` (e.g. '1h', '30m').

    Drops null bars and zero-volume close-snapshot bars. The signal engine is
    timeframe-agnostic, so the same scan runs on any interval.
    """
    res = _chart(symbol, f"interval={interval}&range={lookback}")
    if not res:
        return []
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    out = []
    for t, o, h, l, c, v in zip(ts, q["open"], q["high"], q["low"], q["close"], q["volume"]):
        if None in (o, h, l, c) or not v:
            continue
        out.append(Bar(ts=t, open=o, high=h, low=l, close=c, volume=v))
    return out


def hourly_bars(symbol: str, lookback: str = "1mo") -> list[Bar]:
    """Completed 1-hour bars."""
    return bars(symbol, "1h", lookback)


def half_hour_bars(symbol: str, lookback: str = "1mo") -> list[Bar]:
    """Completed 30-minute bars."""
    return bars(symbol, "30m", lookback)


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


_session = None  # (opener, crumb) cached for option-chain calls


def _crumb_session():
    global _session
    if _session is not None:
        return _session
    import http.cookiejar
    import urllib.parse  # noqa: F401 (used by callers)
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", _UA["User-Agent"])]
    for url in ("https://fc.yahoo.com", "https://finance.yahoo.com"):
        try:
            op.open(url, timeout=10).read()
        except Exception:
            pass
    crumb = op.open("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10).read().decode()
    _session = (op, crumb)
    return _session


def option_chain(symbol: str, expiry: Optional[int] = None) -> Optional[dict]:
    """Front (or given-expiry) option chain for `symbol`, or None on failure.

    Needs a crumb+cookie session; returns None if that can't be established
    (callers degrade gracefully to an approximate contract)."""
    import urllib.parse
    for attempt in range(2):
        try:
            op, crumb = _crumb_session()
            url = (f"https://query2.finance.yahoo.com/v7/finance/options/{symbol}"
                   f"?crumb={urllib.parse.quote(crumb)}")
            if expiry:
                url += f"&date={expiry}"
            d = json.loads(op.open(url, timeout=15).read())
            res = d["optionChain"]["result"]
            return res[0] if res else None
        except Exception:
            global _session
            _session = None            # force a fresh crumb next attempt
            time.sleep(0.5)
    return None


def fetch_all(symbols, fn: Callable[[str], object], max_workers: int = 25) -> dict:
    """Run `fn` over symbols concurrently → {symbol: result}."""
    out = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fn, s): s for s in symbols}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
    return out

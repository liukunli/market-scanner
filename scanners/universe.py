"""Constituent-list providers with a once-per-day disk cache.

    qqq_constituents()   Nasdaq-100  (~100)
    sp500_constituents() S&P 500     (~503, from Wikipedia)
    us_5b_universe()     all US stocks with market cap >= $5B (Nasdaq screener)

Parsing is isolated in pure `_parse_*` functions so tests can run against saved
fixtures without any network access.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
       "Accept": "application/json, text/plain, */*", "Referer": "https://www.nasdaq.com/"}

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, name)


def _read_cache(name: str, ttl_seconds: int, now: float) -> list | None:
    p = _cache_path(name)
    if os.path.isfile(p) and (now - os.path.getmtime(p)) < ttl_seconds:
        with open(p) as fh:
            return json.load(fh)
    return None


def _write_cache(name: str, data: list) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(name), "w") as fh:
        json.dump(data, fh)


def _fetch(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout) as r:
        return r.read().decode()


# --- pure parsers (tested against fixtures) -------------------------------------

def _parse_wikipedia_sp500(html: str) -> list[str]:
    m = re.search(r'id="constituents".*?</table>', html, re.S)
    if not m:
        return []
    syms = re.findall(r'<td><a[^>]*>([A-Z\.]+)</a>', m.group(0))
    seen, out = set(), []
    for s in syms:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _parse_nasdaq_screener(payload: dict, min_cap: float = 5e9) -> list[str]:
    rows = payload.get("data", {}).get("rows", [])
    seen = {}
    for r in rows:
        try:
            cap = float(r["marketCap"])
        except (KeyError, TypeError, ValueError):
            continue
        if cap < min_cap:
            continue
        sym = (r.get("symbol") or "").strip().upper()
        if not sym or any(ch in sym for ch in ("^", "/", " ")):
            continue
        if sym not in seen or cap > seen[sym]:
            seen[sym] = cap
    return [s for s, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


# --- public providers -----------------------------------------------------------

def us_5b_universe(now: float, ttl_seconds: int = 86400) -> list[str]:
    cached = _read_cache("us_5b.json", ttl_seconds, now)
    if cached is not None:
        return cached
    url = ("https://api.nasdaq.com/api/screener/stocks"
           "?tableonly=true&limit=0&offset=0&download=true")
    syms = _parse_nasdaq_screener(json.loads(_fetch(url)))
    _write_cache("us_5b.json", syms)
    return syms


def sp500_constituents(now: float, ttl_seconds: int = 86400) -> list[str]:
    cached = _read_cache("sp500.json", ttl_seconds, now)
    if cached is not None:
        return cached
    html = _fetch("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    syms = _parse_wikipedia_sp500(html)
    _write_cache("sp500.json", syms)
    return syms


def qqq_constituents(now: float, ttl_seconds: int = 86400) -> list[str]:
    cached = _read_cache("qqq.json", ttl_seconds, now)
    if cached is not None:
        return cached
    html = _fetch("https://en.wikipedia.org/wiki/Nasdaq-100")
    # Nasdaq-100 page lists tickers in a column of the constituents table
    syms = re.findall(r'<td><a[^>]*>([A-Z]{1,5})</a>\s*</td>', html)
    seen, out = set(), []
    for s in syms:
        if s not in seen:
            seen.add(s)
            out.append(s)
    _write_cache("qqq.json", out)
    return out

"""Eastern-time helpers with correct DST handling.

Uses the IANA zone America/New_York when available (stdlib zoneinfo), so EDT/EST
transitions are handled automatically. Falls back to a fixed -4 offset only if
the tz database is unavailable in the runtime.
"""
from __future__ import annotations

import datetime

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                       # pragma: no cover - only if tzdata missing
    ET = datetime.timezone(datetime.timedelta(hours=-4))


def to_et(ts: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(ts, ET)


def et_date(ts: int) -> str:
    return to_et(ts).strftime("%Y-%m-%d")


def et_stamp(ts: int) -> str:
    return to_et(ts).strftime("%Y-%m-%d %H:%M ET")


def today_et(now: float) -> str:
    return datetime.datetime.fromtimestamp(now, ET).strftime("%Y-%m-%d")


def utc_date(ts: int) -> str:
    """UTC calendar date. Option expiration timestamps are midnight UTC, so ET
    conversion would shift them a day earlier — use this for expiries."""
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")

"""Local-time helpers for displayed timestamps, with correct DST handling.

The display zone is config.DISPLAY_TZ (default America/Los_Angeles). Using the
IANA zone means PST/PDT transitions are handled automatically and the %Z label
prints the right abbreviation. Falls back to a fixed -8 (PST) only if the tz
database is unavailable.

Note: US equity sessions (incl. pre/post) fall within a single Pacific calendar
day, so date-based logic (bar-day filtering, session freshness) stays correct
under this zone as long as the same zone is used throughout.
"""
from __future__ import annotations

import datetime

from .config import DISPLAY_TZ

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo(DISPLAY_TZ)
except Exception:                       # pragma: no cover - only if tzdata missing
    LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=-8))


def to_local(ts: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(ts, LOCAL_TZ)


def local_date(ts: int) -> str:
    return to_local(ts).strftime("%Y-%m-%d")


def local_stamp(ts: int) -> str:
    # %Z -> PST or PDT automatically
    return to_local(ts).strftime("%Y-%m-%d %H:%M %Z")


def today_local(now: float) -> str:
    return datetime.datetime.fromtimestamp(now, LOCAL_TZ).strftime("%Y-%m-%d")


def utc_date(ts: int) -> str:
    """UTC calendar date. Option expiration timestamps are midnight UTC, so a
    local-zone conversion would shift them a day earlier — use this for expiries."""
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")

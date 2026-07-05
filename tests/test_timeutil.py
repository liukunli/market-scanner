"""Tests for local-time conversion (fixed instants, DST-independent).

Default display zone is America/Los_Angeles. 1783022401 = 2026-07-02 16:00 EDT
= 2026-07-02 13:00 PDT.
"""
from scanners.timeutil import local_date, local_stamp, to_local, LOCAL_TZ


def test_local_date_is_pacific():
    assert local_date(1783022401) == "2026-07-02"


def test_local_stamp_pacific_time_and_label():
    s = local_stamp(1783022401)
    assert "2026-07-02 13:00" in s          # 16:00 ET -> 13:00 PT
    assert s.endswith("PDT") or s.endswith("PST")


def test_to_local_returns_aware_datetime():
    dt = to_local(1783022401)
    assert dt.tzinfo is not None
    assert dt.hour == 13                      # Pacific


def test_zone_is_los_angeles():
    assert str(LOCAL_TZ) in ("America/Los_Angeles", "UTC-08:00")

"""Tests for Eastern-time conversion (fixed instants, DST-independent)."""
from scanners.timeutil import et_date, et_stamp, to_et


def test_et_date_summer():
    # 1783022401 = 2026-07-02 16:00 ET (EDT)
    assert et_date(1783022401) == "2026-07-02"


def test_et_stamp_has_label():
    assert et_stamp(1783022401).endswith("ET")
    assert "2026-07-02 16:00" in et_stamp(1783022401)


def test_to_et_returns_aware_datetime():
    dt = to_et(1783022401)
    assert dt.tzinfo is not None
    assert dt.year == 2026 and dt.month == 7

"""Time-scale conventions (docs/CONVENTIONS.md §2.2) and offline IERS behaviour."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from astropy.utils import iers

from astramesh.dynamics.earth_frames import gcrs_to_itrs
from astramesh.dynamics.timescales import (
    EarthOrientationRangeError,
    earth_orientation_data_version,
    require_eop_coverage,
    scenario_time,
)

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)


def test_astropy_configured_offline() -> None:
    assert iers.conf.auto_download is False
    assert iers.conf.iers_degraded_accuracy == "error"


def test_tt_minus_utc_at_reference_epoch() -> None:
    # TAI - UTC = 37 s since 2017-01-01; TT - TAI = 32.184 s exactly.
    t = scenario_time(EPOCH, 0)
    dt_s = (t.tt.jd1 - t.utc.jd1 + t.tt.jd2 - t.utc.jd2) * 86400.0
    assert dt_s == pytest.approx(69.184, abs=1e-6)


def test_ut1_minus_utc_is_bounded() -> None:
    t = scenario_time(EPOCH, 0)
    dut1_s = (t.ut1.jd1 - t.utc.jd1 + t.ut1.jd2 - t.utc.jd2) * 86400.0
    assert abs(dut1_s) < 0.9  # IERS keeps |UT1 - UTC| < 0.9 s


def test_elapsed_time_is_si_seconds_across_a_leap_second() -> None:
    # A leap second was inserted at 2016-12-31T23:59:60Z.
    epoch = datetime(2016, 12, 31, 23, 59, 59, tzinfo=UTC)
    assert scenario_time(epoch, 1 * 10**9).utc.isot == "2016-12-31T23:59:60.000"
    assert scenario_time(epoch, 2 * 10**9).utc.isot == "2017-01-01T00:00:00.000"


def test_sub_nanosecond_precision_over_24h() -> None:
    # Astropy's two-double Time keeps ~10 ps precision; 1 ns steps must be resolved.
    t = scenario_time(EPOCH, 86_400 * 10**9 + 1)
    t0 = scenario_time(EPOCH, 86_400 * 10**9)
    assert (t - t0).to_value("s") == pytest.approx(1e-9, abs=2e-11)


def test_array_times() -> None:
    t = scenario_time(EPOCH, np.array([0, 10**9, 2 * 10**9], dtype=np.int64))
    assert t.shape == (3,)


def test_float_times_rejected() -> None:
    with pytest.raises(TypeError, match="integer nanoseconds"):
        scenario_time(EPOCH, 1.5)


def test_non_utc_epoch_rejected() -> None:
    with pytest.raises(ValueError, match="UTC"):
        scenario_time(datetime(2025, 6, 1), 0)


def test_time_outside_bundled_iers_table_raises() -> None:
    # The bundled IERS-A table (with predictions) ends 2027-10-29 for this lock.
    # Astropy alone would silently reuse the last value; the guard must raise.
    require_eop_coverage(scenario_time(EPOCH, 0))
    before = scenario_time(datetime(1962, 1, 1, tzinfo=UTC), 0)
    after = scenario_time(datetime(2027, 11, 15, tzinfo=UTC), 0)
    for t in (before, after):
        with pytest.raises(EarthOrientationRangeError, match="outside the bundled IERS table"):
            require_eop_coverage(t)


def test_earth_fixed_transform_refuses_uncovered_time() -> None:
    with pytest.raises(EarthOrientationRangeError):
        gcrs_to_itrs(datetime(2027, 11, 15, tzinfo=UTC), 0, [7e6, 0, 0], [0, 7.5e3, 0])


def test_data_version_string() -> None:
    v = earth_orientation_data_version()
    assert v.startswith("astropy-iers-data==")
    assert "pyerfa==" in v

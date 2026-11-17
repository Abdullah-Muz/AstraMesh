"""IERS-A predictions stay usable however old the bundled table is (DL-137).

Astropy's ``IERS_Auto`` refuses predicted Earth-orientation values once the wall
clock is more than ``iers.conf.auto_max_age`` days past the table's first
predicted row (``IERS_Auto._check_interpolate_indices``). With downloads off,
that made results depend on the date a run is made. The same setting also picks
the leap-second table, so DL-137 loads the leap-second table first, under
Astropy's default rule (bundled table, warning once expired, DL-021), and only
then lifts the age limit. No network is used: the wall clock that
``_check_interpolate_indices`` reads (``Time.now()``) is moved instead.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import astropy.utils.iers.iers as iers_module
import erfa
import numpy as np
import pytest
from astropy.time import Time
from astropy.utils import iers

from astramesh.dynamics.earth_frames import gcrs_to_itrs
from astramesh.dynamics.timescales import scenario_time

MJD0 = datetime(1858, 11, 17, tzinfo=UTC)
R, V = [7e6, 0, 0], [0, 7.5e3, 0]


def _predictive_mjd() -> float:
    """MJD of the bundled table's first predicted row (2026-10-23 for this lock)."""
    return float(iers.earth_orientation_table.get().meta["predictive_mjd"])


def _freeze_wall_clock(monkeypatch: pytest.MonkeyPatch, now_mjd: float) -> None:
    """Make ``Time.now()`` return ``now_mjd`` until the test ends (monkeypatch undoes it).

    ``astropy.utils.iers.iers`` imported ``Time`` from ``astropy.time``, so patching
    the class attribute reaches ``IERS_Auto._check_interpolate_indices`` even for the
    already-opened (cached) table: it calls ``Time.now()`` on every interpolation.
    """
    assert iers_module.Time is Time  # the name the IERS module calls
    fake = Time(now_mjd, format="mjd", scale="utc")
    monkeypatch.setattr(Time, "now", staticmethod(lambda: fake))


def test_prediction_age_limit_is_lifted_after_the_leap_seconds_load() -> None:
    assert iers.conf.auto_max_age is None
    # The bundled leap-second table (not ERFA's built-in list, which expired in
    # 2017) was loaded under the default rule before the limit was lifted.
    bundled = iers.LeapSeconds.open(iers.IERS_LEAP_SECOND_FILE)
    assert erfa.leap_seconds.expires == bundled.expires.datetime


def test_predicted_epoch_transforms_long_after_the_table_was_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = _predictive_mjd()
    epoch = MJD0 + timedelta(days=int(p) + 120)  # 2027-02-20 for this lock
    t = scenario_time(epoch, 0)
    _, status = iers.earth_orientation_table.get().ut1_utc(t, return_status=True)
    assert status == iers.FROM_IERS_A_PREDICTION  # the predicted range, inside the table

    _freeze_wall_clock(monkeypatch, p + 60)  # the wall clock 60 days after the table
    r, v = gcrs_to_itrs(epoch, 0, R, V)  # calls require_eop_coverage first
    assert np.all(np.isfinite(r))
    assert np.all(np.isfinite(v))

    # The time bomb this guards against: with Astropy's default limit of 30 days the
    # same call is refused by IERS_Auto._check_interpolate_indices (INTERPOLATE_ERROR).
    # set_temp restores the configured value when the block ends.
    with (
        iers.conf.set_temp("auto_max_age", 30.0),
        pytest.raises(ValueError, match="using predictive values that are more"),
    ):
        gcrs_to_itrs(epoch, 0, R, V)
    assert iers.conf.auto_max_age is None

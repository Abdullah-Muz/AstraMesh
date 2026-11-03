"""Time-scale conversions (UTC, TAI, TT, UT1) via Astropy, configured offline.

Conventions (``docs/CONVENTIONS.md`` §2.2):

* The scenario epoch is a UTC instant; simulation time is an integer number of
  **elapsed SI nanoseconds** since that epoch. Adding elapsed SI seconds to a
  UTC instant is done by Astropy through TAI, so a leap second inside the
  interval is accounted for (UTC calendar labels skip or repeat, SI time does not).
* Earth-orientation data (UT1-UTC, polar motion) and the leap-second table
  come **only** from the locked ``astropy-iers-data`` / ``pyerfa`` packages.
  Automatic downloads are disabled so that every run on every machine uses the
  same data. Astropy itself silently reuses the last tabulated value beyond
  the table, so :func:`require_eop_coverage` checks coverage explicitly and
  raises instead (PA-10); Earth-fixed transforms call it. The IERS data
  version is the ``astropy-iers-data`` package version, recorded in each run
  manifest.

Importing this module sets these Astropy options process-wide.
"""

from __future__ import annotations

from datetime import datetime
from importlib.metadata import version

import numpy as np
from astropy.time import Time, TimeDelta
from astropy.utils import iers
from numpy.typing import ArrayLike

from astramesh.core.clock import NS_PER_S, require_utc


class EarthOrientationRangeError(ValueError):
    """Raised when a time lies outside the bundled Earth-orientation (IERS) table."""


def configure_astropy_offline() -> None:
    """Disable IERS/leap-second downloads (coverage is enforced by require_eop_coverage)."""
    iers.conf.auto_download = False
    iers.conf.iers_degraded_accuracy = "error"


configure_astropy_offline()


def earth_orientation_data_version() -> str:
    """Identifier of the IERS Earth-orientation and leap-second data in use."""
    return f"astropy-iers-data=={version('astropy-iers-data')}; pyerfa=={version('pyerfa')}"


def scenario_time(epoch_utc: datetime, t_ns: int | ArrayLike) -> Time:
    """Astropy ``Time`` (UTC scale) for ``epoch_utc`` + ``t_ns`` elapsed SI nanoseconds.

    ``t_ns`` may be a scalar or an integer array. The elapsed time is split into
    whole and fractional seconds so no precision is lost for long scenarios.
    """
    epoch = require_utc(epoch_utc, name="epoch_utc")
    t = np.asarray(t_ns)
    if not np.issubdtype(t.dtype, np.integer):
        raise TypeError(f"t_ns must be integer nanoseconds, got dtype {t.dtype}")
    whole_s = (t // NS_PER_S).astype(np.float64)
    frac_s = (t % NS_PER_S).astype(np.float64) / NS_PER_S
    t0 = Time(epoch.replace(tzinfo=None), scale="utc")
    return t0 + TimeDelta(whole_s, frac_s, format="sec")


def require_eop_coverage(t: Time) -> None:
    """Raise unless every time in ``t`` is covered by the bundled IERS table.

    Covered includes IERS-A *predictions* (status 2), which are expected for
    future-dated scenarios; times before or after the table (status < 0) raise.
    """
    table = iers.earth_orientation_table.get()
    _, status = table.ut1_utc(t, return_status=True)
    status_arr = np.atleast_1d(np.asarray(status))
    if np.any(status_arr < 0):
        bad = np.atleast_1d(t)[status_arr < 0]
        mjd = np.asarray(table["MJD"].value)
        raise EarthOrientationRangeError(
            f"{bad.size} time(s) outside the bundled IERS table "
            f"(MJD {mjd[0]:.0f}-{mjd[-1]:.0f}), first {bad[0].utc.isot}; "
            f"data: {earth_orientation_data_version()}"
        )

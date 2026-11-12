"""Centred tilted geomagnetic dipole and invariant latitude (DL-090, DL-091).

The dipole comes from the IGRF-14 first-order Gauss coefficients (IAGA Working Group
V-MOD, ``igrf14coeffs.txt``): DGRF 2020.0 and IGRF 2025.0, linearly interpolated
between them as IGRF prescribes, and extrapolated with the 2025-30 secular variation
up to 2030.0. The north geomagnetic pole is the direction -(g11, h11, g10) / B0 in the
Earth-fixed frame.

Invariant latitude follows from the dipole L shell, L = r / cos^2(lambda_m) with r in
reference radii (6371.2 km, the IGRF reference radius) and lambda_m the dipole
latitude: cos^2(Lambda) = 1 / L (R08 section 2). It is a model: R08 computes L from
the full IGRF, and the storm-time field is not dipolar (R09 section 6.2.3).
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

R_REF_M = 6_371_200.0  # IGRF reference radius [m]
#: (g10, g11, h11) [nT] at the IGRF-14 epochs used here
IGRF14_DIPOLE_NT = {
    2020.0: (-29403.41, -1451.37, 4653.35),  # DGRF 2020.0
    2025.0: (-29350.0, -1410.3, 4545.5),  # IGRF 2025.0
}
IGRF14_SV_2025_NTPYR = (12.6, 10.0, -21.5)  # secular variation 2025-30 [nT/yr]


def decimal_year(t: dt.datetime) -> float:
    """Calendar year plus the elapsed fraction of it (UTC)."""
    start = dt.datetime(t.year, 1, 1, tzinfo=dt.UTC)
    end = dt.datetime(t.year + 1, 1, 1, tzinfo=dt.UTC)
    return t.year + (t.astimezone(dt.UTC) - start) / (end - start)


def dipole_coefficients(year: float) -> tuple[float, float, float]:
    """(g10, g11, h11) [nT] at a decimal year in [2020, 2030]."""
    if not 2020.0 <= year <= 2030.0:
        raise ValueError(f"IGRF-14 dipole defined here for 2020-2030 only, got {year}")
    a, b = IGRF14_DIPOLE_NT[2020.0], IGRF14_DIPOLE_NT[2025.0]
    if year <= 2025.0:
        w = (year - 2020.0) / 5.0
        return (a[0] + w * (b[0] - a[0]), a[1] + w * (b[1] - a[1]), a[2] + w * (b[2] - a[2]))
    dy = year - 2025.0
    sv = IGRF14_SV_2025_NTPYR
    return (b[0] + dy * sv[0], b[1] + dy * sv[1], b[2] + dy * sv[2])


def dipole_axis(year: float) -> FloatArray:
    """Unit vector toward the north geomagnetic pole in the Earth-fixed frame."""
    g10, g11, h11 = dipole_coefficients(year)
    m = -np.array([g11, h11, g10], dtype=np.float64)
    out: FloatArray = m / np.linalg.norm(m)
    return out


def pole_lat_lon_deg(year: float) -> tuple[float, float]:
    """Geocentric latitude and east longitude of the north geomagnetic pole [deg]."""
    m = dipole_axis(year)
    return float(np.degrees(np.arcsin(m[2]))), float(np.degrees(np.arctan2(m[1], m[0])))


def dipole_latitude_deg(r_itrs_m: FloatArray, axis: FloatArray) -> FloatArray:
    """Dipole (geomagnetic) latitude of Earth-fixed positions ``(..., 3)`` [deg]."""
    r = np.linalg.norm(r_itrs_m, axis=-1)
    s = np.clip((r_itrs_m @ axis) / r, -1.0, 1.0)
    return np.degrees(np.arcsin(s))


def invariant_latitude_deg(r_itrs_m: FloatArray, axis: FloatArray) -> FloatArray:
    """Unsigned invariant latitude of Earth-fixed positions ``(..., 3)`` [deg]:
    cos^2(Lambda) = cos^2(lambda_m) / r, r in IGRF reference radii (r >= 1 assumed)."""
    r = np.linalg.norm(r_itrs_m, axis=-1) / R_REF_M
    lam = np.radians(dipole_latitude_deg(r_itrs_m, axis))
    c2 = np.clip(np.cos(lam) ** 2 / r, 0.0, 1.0)
    return np.degrees(np.arccos(np.sqrt(c2)))

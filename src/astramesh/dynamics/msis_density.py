"""Storm-time atmospheric density from NRLMSIS 2.0 (D2, spec §4.1; DL-084).

Optional: needs the ``atmosphere`` dependency group (``pymsis``). NRLMSIS 2.0 is
licensed by NRL for academic, non-commercial use only (``MSIS2_LICENSE`` in the
pymsis repository); AstraMesh does not modify or redistribute it.

Drivers come from the pinned OMNI2 hourly files (DS-10; words 50 = ap, 51 = F10.7):

* ``f107``: daily F10.7 of the previous UT day;
* ``f107a``: 81-day centred average of daily F10.7 (truth input only: it looks 40 days
  ahead, so it must never be shown to an agent);
* ``ap``: the MSIS array (daily Ap; 3-hour ap now and 3, 6, 9 h before; means over
  12-33 h and 36-57 h before).

Earth-fixed positions use GCRS-to-ITRS matrices precomputed on the run's step grid;
between grid points the Earth's rotation about the ITRS z-axis is added. Latitude
and height are geodetic on WGS 84.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from astramesh.dynamics.constants import OMEGA_EARTH_RADPS, R_EARTH_EQ_M, WGS84_E2

FloatArray = NDArray[np.float64]
MSIS_VERSION = 2.0
H_PER_DAY = 24


class DriverRangeError(ValueError):
    """A time outside the driver data (including the averaging margins)."""


@dataclass(frozen=True)
class MsisDrivers:
    """Hourly ap and daily F10.7 from OMNI2, starting at ``start`` (00 UT of a day)."""

    start: datetime
    ap_hourly: FloatArray  # 3-hour ap, repeated for each hour [nT]
    f107_daily: FloatArray  # daily F10.7 [sfu]
    _cache: dict[int, tuple[float, float, tuple[float, ...]]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    @classmethod
    def from_omni2(cls, paths: Sequence[Path]) -> MsisDrivers:
        rows: list[tuple[int, int, int, float, float]] = []
        for p in paths:
            for line in p.read_text().splitlines():
                w = line.split()
                if len(w) != 55:
                    raise ValueError(f"{p.name}: expected 55 OMNI2 words, got {len(w)}")
                rows.append((int(w[0]), int(w[1]), int(w[2]), float(w[49]), float(w[50])))
        rows.sort()
        t0 = datetime(rows[0][0], 1, 1, tzinfo=UTC) + timedelta(days=rows[0][1] - 1)
        hours = [
            (datetime(y, 1, 1, tzinfo=UTC) + timedelta(days=d - 1, hours=h) - t0)
            // timedelta(hours=1)
            for y, d, h, _, _ in rows
        ]
        if hours != list(range(len(rows))) or rows[0][2] != 0 or len(rows) % H_PER_DAY:
            raise ValueError("OMNI2 rows must be contiguous whole days from 00 UT")
        ap = np.array([r[3] for r in rows])
        f107 = np.array([r[4] for r in rows])
        if np.any(ap >= 999) or np.any(f107 >= 999.9):
            raise ValueError("OMNI2 fill values in ap or F10.7")
        return cls(t0, ap, f107.reshape(-1, H_PER_DAY)[:, 0].copy())

    def _hour(self, h: int) -> tuple[float, float, tuple[float, ...]]:
        day = h // H_PER_DAY
        three = self.ap_hourly[h - h % 3 :: -3]  # 3-hour values, newest first
        ap = (
            float(np.mean(self.ap_hourly[day * H_PER_DAY : (day + 1) * H_PER_DAY])),
            float(three[0]), float(three[1]), float(three[2]), float(three[3]),
            float(np.mean(three[4:12])), float(np.mean(three[12:20])),
        )  # fmt: skip
        f107a = float(np.mean(self.f107_daily[day - 40 : day + 41]))
        return float(self.f107_daily[day - 1]), f107a, ap

    def inputs(self, times: Sequence[datetime]) -> tuple[FloatArray, FloatArray, FloatArray]:
        """(f107, f107a, ap[n, 7]) for UTC ``times``; each hour is computed once and cached."""
        f107, f107a, ap = [], [], []
        n_days = self.f107_daily.size
        cache = self._cache
        for t in times:
            h_float = (t - self.start) / timedelta(hours=1)
            h, day = math.floor(h_float), math.floor(h_float / H_PER_DAY)
            if day - 40 < 0 or day + 40 >= n_days or h - h % 3 - 57 < 0:
                raise DriverRangeError(f"{t.isoformat()} is outside the MSIS driver data")
            if h not in cache:
                cache[h] = self._hour(h)
            a, b, c = cache[h]
            f107.append(a)
            f107a.append(b)
            ap.append(c)
        return np.array(f107), np.array(f107a), np.array(ap)


def itrs_to_geodetic(r: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Geodetic latitude [deg], longitude [deg] and height [m] on WGS 84, r shape (n, 3)."""
    x, y, z = r[:, 0], r[:, 1], r[:, 2]
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1.0 - WGS84_E2))
    for _ in range(5):
        n = R_EARTH_EQ_M / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1.0 - WGS84_E2 * n / (n + h)))
    n = R_EARTH_EQ_M / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
    h = p / np.cos(lat) - n
    return np.degrees(lat), np.degrees(np.arctan2(y, x)), h


@dataclass(frozen=True)
class MsisDensity:
    """Density along a run: ``density(r_gcrs, t_s)`` [kg m^-3].

    ``matrices`` are the GCRS-to-ITRS rotations at ``k * step_s`` from ``epoch``
    (shape (n, 3, 3)); ``scale`` multiplies the density (sensitivity runs, DL-084).
    """

    epoch: datetime
    step_s: float
    matrices: FloatArray
    drivers: MsisDrivers
    scale: float = 1.0

    def density(self, r_gcrs: FloatArray, t_s: float) -> FloatArray:
        import pymsis  # optional dependency group "atmosphere"

        k = min(int(t_s // self.step_s), self.matrices.shape[0] - 1)
        a = OMEGA_EARTH_RADPS * (t_s - k * self.step_s)
        c, s = math.cos(a), math.sin(a)
        m = self.matrices[k]
        r = r_gcrs[:, 0:1] * m[:, 0] + r_gcrs[:, 1:2] * m[:, 1] + r_gcrs[:, 2:3] * m[:, 2]
        r_itrs = np.stack((c * r[:, 0] + s * r[:, 1], -s * r[:, 0] + c * r[:, 1], r[:, 2]), axis=1)
        lat, lon, h = itrs_to_geodetic(r_itrs)
        when = self.epoch + timedelta(seconds=t_s)
        f107, f107a, ap = self.drivers.inputs([when])
        n = r_gcrs.shape[0]
        out = pymsis.calculate(
            np.full(n, np.datetime64(when.replace(tzinfo=None), "ms")), lon, lat, h / 1e3,
            f107s=np.repeat(f107, n), f107as=np.repeat(f107a, n), aps=np.repeat(ap, n, axis=0),
            version=MSIS_VERSION,
        )  # fmt: skip
        rho: FloatArray = self.scale * np.asarray(out, dtype=np.float64)[:, 0]
        return rho

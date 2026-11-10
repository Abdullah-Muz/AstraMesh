"""Nominal atmospheric drag (D1, spec §4.1; DL-080).

    a_drag = -1/2 rho(h) B |v_rel| v_rel,   B = C_D A / m,   v_rel = v - omega x r

Density ``rho`` comes from the U.S. Standard Atmosphere, 1976 (NOAA/NASA/USAF;
NASA NTRS 19770009539), Table I "Geometric Altitude, Metric Units", document
p. 72: values at 480-700 km, transcribed from the scanned table. Between nodes the
density is interpolated log-linearly, i.e. exponentially within each interval.
The table is a mid-solar-activity atmosphere (exospheric temperature about
1 000 K) with no solar-cycle, day-night or storm variation; that is D2.

Altitude is ``|r|`` minus the WGS 84 ellipsoid radius at the geocentric latitude,
to first order in the flattening (error of order 0.1 km). The atmosphere
co-rotates with the Earth about the given pole.

Drag uses ``exp``/``log``; runs with drag are checked with tolerances, not with
bit-exact digests across machines. With drag off, nothing here is evaluated.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from astramesh.dynamics.constants import OMEGA_EARTH_RADPS, R_EARTH_EQ_M, WGS84_FLATTENING
from astramesh.dynamics.state import NonPhysicalStateError, dot3, norm3

#: (geometric altitude [km], density [kg m^-3]) from USSA 1976 Table I, p. 72.
USSA76_TABLE: tuple[tuple[float, float], ...] = (
    (480, 7.208e-13), (482, 6.976e-13), (484, 6.753e-13), (486, 6.537e-13),
    (488, 6.328e-13), (490, 6.127e-13), (492, 5.932e-13), (494, 5.743e-13),
    (496, 5.561e-13), (498, 5.385e-13), (500, 5.215e-13), (505, 4.814e-13),
    (510, 4.446e-13), (515, 4.107e-13), (520, 3.796e-13), (525, 3.509e-13),
    (530, 3.246e-13), (535, 3.003e-13), (540, 2.780e-13), (545, 2.574e-13),
    (550, 2.384e-13), (555, 2.210e-13), (560, 2.049e-13), (565, 1.900e-13),
    (570, 1.763e-13), (575, 1.637e-13), (580, 1.520e-13), (585, 1.413e-13),
    (590, 1.313e-13), (595, 1.221e-13), (600, 1.137e-13), (605, 1.058e-13),
    (610, 9.859e-14), (615, 9.190e-14), (620, 8.571e-14), (625, 7.998e-14),
    (630, 7.468e-14), (635, 6.977e-14), (640, 6.523e-14), (645, 6.102e-14),
    (650, 5.712e-14), (655, 5.350e-14), (660, 5.015e-14), (665, 4.704e-14),
    (670, 4.416e-14), (675, 4.148e-14), (680, 3.900e-14), (685, 3.669e-14),
    (690, 3.455e-14), (695, 3.255e-14), (700, 3.070e-14),
)  # fmt: skip

_H_M = np.array([1000.0 * h for h, _ in USSA76_TABLE])
_LOG_RHO = np.log(np.array([rho for _, rho in USSA76_TABLE]))
H_MIN_M = float(_H_M[0])
H_MAX_M = float(_H_M[-1])

DRAG_MODEL_SUFFIX = "drag-ussa76"
MSIS_MODEL_SUFFIX = "drag-msis2"

#: Time-dependent density: (positions in GCRS (n, 3) [m], seconds since epoch) -> rho.
DensityFunction = Callable[[NDArray[np.float64], float], NDArray[np.float64]]


class DensityRangeError(ValueError):
    """An altitude outside the density table (480-700 km); no extrapolation."""


def density(h_m: NDArray[np.float64]) -> NDArray[np.float64]:
    """USSA 1976 density [kg m^-3] at geometric altitudes ``h_m`` [m]."""
    h = np.asarray(h_m, dtype=np.float64)
    if np.any(h < H_MIN_M) or np.any(h > H_MAX_M) or not np.all(np.isfinite(h)):
        raise DensityRangeError(
            f"altitude outside the density table {H_MIN_M / 1e3:.0f}-{H_MAX_M / 1e3:.0f} km: "
            f"{np.min(h) / 1e3:.1f}-{np.max(h) / 1e3:.1f} km"
        )
    out: NDArray[np.float64] = np.exp(np.interp(h, _H_M, _LOG_RHO))
    return out


def altitude(r: NDArray[np.float64], pole: tuple[float, float, float]) -> NDArray[np.float64]:
    """Height [m] above the WGS 84 ellipsoid, first order in the flattening."""
    rn = norm3(r)
    s = dot3(r, np.array(pole)) / rn
    out: NDArray[np.float64] = rn - R_EARTH_EQ_M * (1.0 - WGS84_FLATTENING * s * s)
    return out


@dataclass(frozen=True, slots=True)
class DragModel:
    """Drag parameters.

    Attributes:
        ballistic_m2pkg: B = C_D A / m [m^2/kg], one value for all spacecraft or one
            per spacecraft, in the order of the propagated states.
        corotating: atmosphere co-rotates with the Earth (``False`` only for tests).
        omega_radps: Earth rotation rate [rad/s].
        density_fn: optional time-dependent density (D2, e.g. NRLMSIS 2.0,
            :mod:`astramesh.dynamics.msis_density`); ``None`` uses USSA 1976.
    """

    ballistic_m2pkg: tuple[float, ...]
    corotating: bool = True
    omega_radps: float = OMEGA_EARTH_RADPS
    density_fn: DensityFunction | None = None

    @property
    def suffix(self) -> str:
        return DRAG_MODEL_SUFFIX if self.density_fn is None else MSIS_MODEL_SUFFIX

    def __post_init__(self) -> None:
        b = tuple(float(x) for x in self.ballistic_m2pkg)
        if not b or not all(math.isfinite(x) and x >= 0.0 for x in b):
            raise NonPhysicalStateError(f"ballistic coefficients must be >= 0, got {b!r}")
        if not (math.isfinite(self.omega_radps) and self.omega_radps >= 0.0):
            raise NonPhysicalStateError(f"omega must be >= 0, got {self.omega_radps!r}")
        object.__setattr__(self, "ballistic_m2pkg", b)

    def coefficients(self, n: int) -> NDArray[np.float64]:
        if len(self.ballistic_m2pkg) == 1:
            return np.full(n, self.ballistic_m2pkg[0])
        if len(self.ballistic_m2pkg) != n:
            raise ValueError(f"{len(self.ballistic_m2pkg)} ballistic coefficients for {n} states")
        return np.array(self.ballistic_m2pkg)


def drag_acceleration(
    y: NDArray[np.float64], drag: DragModel, pole: tuple[float, float, float], t_s: float = 0.0
) -> NDArray[np.float64]:
    """Drag acceleration [m/s^2] for stacked states ``y`` of shape (n, 6) at ``t_s``."""
    r, v = y[:, :3], y[:, 3:]
    if drag.corotating:
        w = drag.omega_radps * np.array(pole)
        v_rel = v - np.cross(np.broadcast_to(w, r.shape), r)
    else:
        v_rel = v
    rho = density(altitude(r, pole)) if drag.density_fn is None else drag.density_fn(r, t_s)
    speed = norm3(v_rel)
    k = -0.5 * rho * drag.coefficients(y.shape[0]) * speed
    out: NDArray[np.float64] = k[:, np.newaxis] * v_rel
    return out

"""Region access geometry: WGS 84 sites, elevation, and access windows.

A spacecraft has *access* to a region at a simulation tick when its elevation
above the region centre's local horizon is at least ``min_elevation_deg``.
The horizon is the WGS 84 ellipsoid tangent plane (geodetic normal), the site
is on the ellipsoid (height 0), and spacecraft positions are ITRS. No
refraction, terrain, or payload field of view is modelled.

Windows are runs of consecutive **simulation ticks** at which access holds, so
every reported window can be checked point by point: each tick inside meets
the constraint, and the ticks just outside do not (or are outside the
scenario). Edge times are therefore accurate to one time step (no
interpolation).

Determinism: thresholds are compared on sin(elevation), which needs only
IEEE-exact operations. ``math.asin`` (libm) converts the single peak value of
each window. NumPy transcendental functions are not used (their SIMD versions
depend on the CPU, see DL-031).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from astramesh.dynamics.constants import R_EARTH_EQ_M, WGS84_E2
from astramesh.dynamics.state import dot3, norm3

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class Site:
    """A point on the WGS 84 ellipsoid with its local vertical (geodetic normal)."""

    latitude_deg: float
    longitude_deg: float
    itrs_m: tuple[float, float, float]
    up: tuple[float, float, float]

    @classmethod
    def from_geodetic(cls, latitude_deg: float, longitude_deg: float) -> Site:
        if not (math.isfinite(latitude_deg) and -90.0 <= latitude_deg <= 90.0):
            raise ValueError(f"latitude_deg must be in [-90, 90], got {latitude_deg!r}")
        if not (math.isfinite(longitude_deg) and -180.0 <= longitude_deg <= 180.0):
            raise ValueError(f"longitude_deg must be in [-180, 180], got {longitude_deg!r}")
        lat, lon = math.radians(latitude_deg), math.radians(longitude_deg)
        slat, clat, slon, clon = math.sin(lat), math.cos(lat), math.sin(lon), math.cos(lon)
        n = R_EARTH_EQ_M / math.sqrt(1.0 - WGS84_E2 * slat * slat)
        itrs = (n * clat * clon, n * clat * slon, n * (1.0 - WGS84_E2) * slat)
        up = (clat * clon, clat * slon, slat)
        return cls(latitude_deg, longitude_deg, itrs, up)


def elevation_sine(r_itrs_m: FloatArray, site: Site) -> FloatArray:
    """sin(elevation) of positions ``r_itrs_m`` (..., 3) seen from ``site``."""
    rho = r_itrs_m - np.array(site.itrs_m)
    out: FloatArray = dot3(rho, np.array(site.up)) / norm3(rho)
    return out


@dataclass(frozen=True, slots=True)
class Window:
    """Inclusive tick range ``[first, last]`` with access, and its peak."""

    first: int
    last: int
    peak: int
    peak_elevation_deg: float
    truncated_start: bool  # access already held at the first tick of the scenario
    truncated_end: bool  # access still held at the last tick

    @property
    def n_ticks(self) -> int:
        return self.last - self.first + 1


def access_windows(sin_el: FloatArray, min_elevation_deg: float) -> list[Window]:
    """Windows of consecutive ticks where ``sin_el >= sin(min_elevation_deg)``."""
    if sin_el.ndim != 1:
        raise ValueError(f"sin_el must be 1-D (one value per tick), got shape {sin_el.shape}")
    if not (math.isfinite(min_elevation_deg) and 0.0 <= min_elevation_deg < 90.0):
        raise ValueError(f"min_elevation_deg must be in [0, 90), got {min_elevation_deg!r}")
    visible = sin_el >= math.sin(math.radians(min_elevation_deg))
    edges = np.flatnonzero(np.diff(visible.astype(np.int8)))
    starts = [0] if visible[0] else []
    ends: list[int] = []
    for e in edges.tolist():
        if visible[e]:
            ends.append(e)
        else:
            starts.append(e + 1)
    if visible[-1]:
        ends.append(len(visible) - 1)
    out = []
    n = len(visible)
    for a, b in zip(starts, ends, strict=True):
        peak = a + int(np.argmax(sin_el[a : b + 1]))
        out.append(
            Window(
                first=a,
                last=b,
                peak=peak,
                peak_elevation_deg=math.degrees(math.asin(min(1.0, float(sin_el[peak])))),
                truncated_start=a == 0,
                truncated_end=b == n - 1,
            )
        )
    return out

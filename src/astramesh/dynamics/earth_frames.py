"""Inertial (GCRS) <-> Earth-fixed (ITRS) transforms via Astropy.

Both frames are as implemented by Astropy (IAU 2006/2000A, CIO-based, with
IERS polar motion and UT1 from the locked ``astropy-iers-data`` package; see
:mod:`astramesh.dynamics.timescales`). Velocities are transformed too: the
ITRS velocity is relative to the rotating Earth.

These transforms use ERFA's transcendental functions, so their results are
not guaranteed bit-identical across platforms (unlike the GCRS propagator).
Propagation stays in GCRS; ITRS is used for geometry (ground tracks,
observation access) only.
"""

from __future__ import annotations

from datetime import datetime

import astropy.units as u
import numpy as np
from astropy.coordinates import (
    GCRS,
    ITRS,
    BaseCoordinateFrame,
    CartesianDifferential,
    CartesianRepresentation,
)
from numpy.typing import ArrayLike, NDArray

from astramesh.dynamics.state import CartesianState, Frame, NonPhysicalStateError
from astramesh.dynamics.timescales import require_eop_coverage, scenario_time

FloatArray = NDArray[np.float64]


def _as_vectors(value: ArrayLike, name: str) -> FloatArray:
    arr = np.array(value, dtype=np.float64, copy=True)
    if arr.ndim not in (1, 2) or arr.shape[-1] != 3:
        raise NonPhysicalStateError(f"{name} must have shape (3,) or (n, 3), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise NonPhysicalStateError(f"{name} must be finite")
    return arr


def _transform(
    epoch_utc: datetime,
    t_ns: int | ArrayLike,
    r_m: ArrayLike,
    v_mps: ArrayLike,
    *,
    to_itrs: bool,
) -> tuple[FloatArray, FloatArray]:
    r = _as_vectors(r_m, "r_m")
    v = _as_vectors(v_mps, "v_mps")
    if r.shape != v.shape:
        raise NonPhysicalStateError(f"r_m {r.shape} and v_mps {v.shape} shapes differ")
    t_arr = np.asarray(t_ns)
    if r.ndim == 2 and t_arr.ndim == 1 and t_arr.shape[0] != r.shape[0]:
        raise ValueError(f"t_ns has {t_arr.shape[0]} entries but there are {r.shape[0]} states")
    obstime = scenario_time(epoch_utc, t_arr)
    require_eop_coverage(obstime)
    rep = CartesianRepresentation(r.T * u.m, differentials=CartesianDifferential(v.T * (u.m / u.s)))
    src: BaseCoordinateFrame
    dst: BaseCoordinateFrame
    if to_itrs:
        src, dst = GCRS(rep, obstime=obstime), ITRS(obstime=obstime)
    else:
        src, dst = ITRS(rep, obstime=obstime), GCRS(obstime=obstime)
    out = src.transform_to(dst)
    r_out = np.asarray(out.cartesian.xyz.to_value(u.m), dtype=np.float64).T
    v_out = np.asarray(out.velocity.d_xyz.to_value(u.m / u.s), dtype=np.float64).T
    return r_out, v_out


def gcrs_to_itrs(
    epoch_utc: datetime, t_ns: int | ArrayLike, r_m: ArrayLike, v_mps: ArrayLike
) -> tuple[FloatArray, FloatArray]:
    """GCRS position [m] / velocity [m/s] (shape (3,) or (n, 3)) to ITRS."""
    return _transform(epoch_utc, t_ns, r_m, v_mps, to_itrs=True)


def itrs_to_gcrs(
    epoch_utc: datetime, t_ns: int | ArrayLike, r_m: ArrayLike, v_mps: ArrayLike
) -> tuple[FloatArray, FloatArray]:
    """ITRS position [m] / velocity [m/s] (shape (3,) or (n, 3)) to GCRS."""
    return _transform(epoch_utc, t_ns, r_m, v_mps, to_itrs=False)


def state_to_itrs(state: CartesianState) -> CartesianState:
    state.require_frame(Frame.GCRS)
    r, v = gcrs_to_itrs(state.epoch_utc, state.t_ns, state.r_m, state.v_mps)
    return CartesianState(Frame.ITRS, state.epoch_utc, state.t_ns, r, v)


def state_to_gcrs(state: CartesianState) -> CartesianState:
    state.require_frame(Frame.ITRS)
    r, v = itrs_to_gcrs(state.epoch_utc, state.t_ns, state.r_m, state.v_mps)
    return CartesianState(Frame.GCRS, state.epoch_utc, state.t_ns, r, v)


def earth_pole_gcrs(epoch_utc: datetime, t_ns: int = 0) -> tuple[float, float, float]:
    """Unit vector of the ITRS z-axis (Earth's figure axis, for J2) in GCRS.

    The ITRS z-axis differs from the Celestial Intermediate Pole only by polar
    motion (< ~0.5 arcsec). The result comes from ERFA, so its last bits may
    differ between platforms; record it with the run (or pass a literal vector
    in regression tests) to keep propagation bit-for-bit reproducible.
    """
    r, _ = itrs_to_gcrs(epoch_utc, t_ns, [0.0, 0.0, 1.0], [0.0, 0.0, 0.0])
    n = float(np.sqrt(r @ r))
    return (float(r[0] / n), float(r[1] / n), float(r[2] / n))

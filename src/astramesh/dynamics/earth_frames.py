"""Inertial (GCRS) <-> Earth-fixed (ITRS) transforms via Astropy.

Both frames are as implemented by Astropy (IAU 2006/2000A, CIO-based, with
IERS polar motion and UT1 from the locked ``astropy-iers-data`` package; see
:mod:`astramesh.dynamics.timescales`). Velocities are transformed too: the
ITRS velocity is relative to the rotating Earth.

These transforms use ERFA's transcendental functions, and Astropy applies the
matrices with NumPy ``matmul`` (BLAS), so their last bits can depend on the
platform and even the CPU model (unlike the GCRS propagator). Do not feed their
output into anything that is digest-pinned without rounding or a study;
:func:`earth_pole_gcrs` avoids BLAS for this reason (DL-031).
Propagation stays in GCRS; ITRS is used for geometry (ground tracks,
observation access) only.
"""

from __future__ import annotations

import math
from datetime import datetime

import astropy.units as u
import erfa
import numpy as np
from astropy.coordinates import (
    GCRS,
    ITRS,
    BaseCoordinateFrame,
    CartesianDifferential,
    CartesianRepresentation,
)
from astropy.coordinates.builtin_frames.utils import get_jd12, get_polar_motion
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


def gcrs_to_itrs_matrices(epoch_utc: datetime, t_ns: ArrayLike) -> FloatArray:
    """GCRS-to-ITRS rotation matrices, shape (n, 3, 3), for integer times ``t_ns``.

    Built exactly as Astropy builds them (``c2i06a``, then ``era00`` and
    ``pom00`` with IERS polar motion and ``sp00``) but combined by ERFA's
    ``c2tcio`` in C, so no NumPy ``@`` (BLAS, whose last bit depends on the CPU)
    is involved (DL-031). Apply them with :func:`rotate`. Results can still
    differ between C math libraries (DL-029).
    """
    t = np.atleast_1d(np.asarray(t_ns))
    if t.ndim != 1:
        raise ValueError(f"t_ns must be a scalar or a 1-D array, got shape {t.shape}")
    obstime = scenario_time(epoch_utc, t)
    require_eop_coverage(obstime)
    tt1, tt2 = get_jd12(obstime, "tt")
    ut1, ut2 = get_jd12(obstime, "ut1")
    xp, yp = get_polar_motion(obstime)
    rc2i = erfa.c2i06a(tt1, tt2)
    pom = erfa.pom00(xp, yp, erfa.sp00(tt1, tt2))
    out = np.asarray(erfa.c2tcio(rc2i, erfa.era00(ut1, ut2), pom), dtype=np.float64)
    return out.reshape(t.shape[0], 3, 3)


def rotate(m: FloatArray, v: FloatArray, *, transpose: bool = False) -> FloatArray:
    """Apply rotation matrices ``m`` (n, 3, 3) to vectors ``v`` (n, ..., 3) elementwise.

    ``v`` may have extra axes between the time axis and the vector axis (e.g.
    one per spacecraft). ``transpose=True`` applies ``m.T`` (ITRS to GCRS).
    Fixed evaluation order, no BLAS.
    """
    mm = np.swapaxes(m, -1, -2) if transpose else m
    mm = mm.reshape(mm.shape[0], *([1] * (v.ndim - 2)), 3, 3)
    out: FloatArray = (
        mm[..., :, 0] * v[..., 0:1] + mm[..., :, 1] * v[..., 1:2] + mm[..., :, 2] * v[..., 2:3]
    )
    return out


def earth_pole_gcrs(epoch_utc: datetime, t_ns: int = 0) -> tuple[float, float, float]:
    """Unit vector of the ITRS z-axis (Earth's figure axis, for J2) in GCRS.

    The ITRS z-axis differs from the Celestial Intermediate Pole only by polar
    motion (< ~0.5 arcsec). It is the third row of the GCRS-to-ITRS matrix from
    :func:`gcrs_to_itrs_matrices`, so no BLAS is involved (DL-031). It is
    recorded with every run.
    """
    row = gcrs_to_itrs_matrices(epoch_utc, t_ns)[0, 2]
    x, y, z = (float(c) for c in row)
    n = math.sqrt(x * x + y * y + z * z)
    return (x / n, y / n, z / n)

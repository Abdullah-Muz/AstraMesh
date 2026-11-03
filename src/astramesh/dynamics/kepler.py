"""Analytic two-body propagation with universal variables (Lagrange f and g).

This is the independent analytic reference for physics acceptance test PA-01
(``docs/NUMERICAL_MISSION_DESIGN.md``). It shares no code with the numerical
integrator in :mod:`astramesh.dynamics.twobody`: it solves the universal
Kepler equation for the universal anomaly ``chi`` by Newton's method and maps
the initial state with the f, g, fdot, gdot coefficients. It uses no orbital
elements, so it is also independent of :mod:`astramesh.dynamics.elements`.

Formulation: H. D. Curtis, *Orbital Mechanics for Engineering Students*,
universal-variable algorithm (Stumpff functions C(z), S(z)). Only bound
(elliptic, ``alpha > 0``) orbits are supported; others raise.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike

from astramesh.dynamics.constants import GM_EARTH_M3PS2
from astramesh.dynamics.state import NonPhysicalStateError, Vector3, as_vector3

_MAX_ITER = 100
_SERIES_Z = 1e-3  # below this |z|, use the Stumpff series (avoids cancellation)


def stumpff_c(z: float) -> float:
    """Stumpff function C(z) for z >= 0."""
    if z < _SERIES_Z:
        return 0.5 - z / 24.0 + z * z / 720.0 - z * z * z / 40320.0
    sz = math.sqrt(z)
    return (1.0 - math.cos(sz)) / z


def stumpff_s(z: float) -> float:
    """Stumpff function S(z) for z >= 0."""
    if z < _SERIES_Z:
        return 1.0 / 6.0 - z / 120.0 + z * z / 5040.0 - z * z * z / 362880.0
    sz = math.sqrt(z)
    return (sz - math.sin(sz)) / (sz * sz * sz)


def kepler_propagate(
    r0_m: ArrayLike, v0_mps: ArrayLike, dt_s: float, mu: float = GM_EARTH_M3PS2
) -> tuple[Vector3, Vector3]:
    """Propagate a bound two-body state by ``dt_s`` seconds (may be negative)."""
    r0 = as_vector3(r0_m, name="r0_m")
    v0 = as_vector3(v0_mps, name="v0_mps")
    if not math.isfinite(dt_s):
        raise NonPhysicalStateError(f"dt_s must be finite, got {dt_s!r}")
    r0n = math.sqrt(float(r0 @ r0))
    if r0n == 0.0:
        raise NonPhysicalStateError("r0_m must be non-zero")
    vr0 = float(r0 @ v0) / r0n
    v0sq = float(v0 @ v0)
    alpha = 2.0 / r0n - v0sq / mu  # reciprocal semi-major axis
    if alpha <= 0.0:
        raise NonPhysicalStateError(
            f"state is not on a bound orbit (1/a = {alpha:.3e} 1/m); "
            "only elliptic orbits are supported"
        )
    if dt_s == 0.0:
        return r0.copy(), v0.copy()

    sqrt_mu = math.sqrt(mu)
    chi = sqrt_mu * alpha * dt_s  # Curtis initial guess
    for _ in range(_MAX_ITER):
        z = alpha * chi * chi
        c, s = stumpff_c(z), stumpff_s(z)
        f_chi = (
            r0n * vr0 / sqrt_mu * chi * chi * c
            + (1.0 - alpha * r0n) * chi**3 * s
            + r0n * chi
            - sqrt_mu * dt_s
        )
        df_chi = (
            r0n * vr0 / sqrt_mu * chi * (1.0 - z * s) + (1.0 - alpha * r0n) * chi * chi * c + r0n
        )
        step = f_chi / df_chi
        chi -= step
        if abs(step) <= 8.0 * math.ulp(max(abs(chi), 1.0)):
            break
    else:
        raise ArithmeticError(
            f"universal Kepler equation did not converge (dt_s={dt_s}, alpha={alpha})"
        )

    z = alpha * chi * chi
    c, s = stumpff_c(z), stumpff_s(z)
    f = 1.0 - chi * chi / r0n * c
    g = dt_s - chi**3 / sqrt_mu * s
    r = f * r0 + g * v0
    rn = math.sqrt(float(r @ r))
    fdot = sqrt_mu / (rn * r0n) * (alpha * chi**3 * s - chi)
    gdot = 1.0 - chi * chi / rn * c
    v = fdot * r0 + gdot * v0
    return np.asarray(r, dtype=np.float64), np.asarray(v, dtype=np.float64)

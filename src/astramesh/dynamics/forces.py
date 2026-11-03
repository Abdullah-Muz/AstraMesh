"""Gravity force models: point mass (D0) and point mass + J2 (D1).

The J2 term is the degree-2 zonal harmonic about the Earth's figure axis. The
axis is given explicitly as a unit vector ``pole`` in GCRS, so the potential is
evaluated in the inertial frame without rotating every state to Earth-fixed
coordinates (J2 is axisymmetric, so Earth rotation does not enter). Use
:func:`astramesh.dynamics.earth_frames.earth_pole_gcrs` for the pole at the
scenario epoch; holding it fixed over a scenario neglects precession/nutation
of the pole during the run (< 1e-6 rad per day; ``NUMERICAL_MISSION_DESIGN.md`` §B.5).

Potential (positive convention, acceleration = grad V)::

    V(r) = mu/r * (1 - J2 (R/r)^2 P2(s)),  s = (r . p)/r,  P2(s) = (3 s^2 - 1)/2

    a = -mu r/r^3 - (3/2) J2 mu R^2 / r^5 * [(1 - 5 s^2) r + 2 (r . p) p]

All arithmetic is elementwise (no transcendental functions), so propagation
with a given pole vector is bit-for-bit reproducible (PA-09).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from astramesh.dynamics.constants import GM_EARTH_M3PS2, J2_EARTH, R_EARTH_EQ_M
from astramesh.dynamics.state import NonPhysicalStateError, dot3, norm3

D0_MODEL_ID = "D0-two-body-rk4"
D1_J2_MODEL_ID = "D1-j2-rk4"


@dataclass(frozen=True, slots=True)
class ForceModel:
    """Gravity model parameters (SI).

    Attributes:
        mu: Gravitational parameter [m^3 s^-2].
        j2: Unnormalized J2; ``0.0`` gives the point-mass (two-body) model.
        r_ref_m: Reference radius of the J2 coefficient [m].
        pole: Unit vector of the J2 symmetry axis in GCRS.
    """

    mu: float = GM_EARTH_M3PS2
    j2: float = 0.0
    r_ref_m: float = R_EARTH_EQ_M
    pole: tuple[float, float, float] = (0.0, 0.0, 1.0)

    def __post_init__(self) -> None:
        for name in ("mu", "j2", "r_ref_m"):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise NonPhysicalStateError(f"{name} must be finite, got {value!r}")
        if self.mu <= 0 or self.r_ref_m <= 0 or self.j2 < 0:
            raise NonPhysicalStateError(
                f"need mu > 0, r_ref_m > 0, j2 >= 0; got {self.mu}, {self.r_ref_m}, {self.j2}"
            )
        pole = tuple(float(x) for x in self.pole)
        if len(pole) != 3 or not all(math.isfinite(x) for x in pole):
            raise NonPhysicalStateError(f"pole must be a finite 3-vector, got {self.pole!r}")
        if abs(math.sqrt(sum(x * x for x in pole)) - 1.0) > 1e-12:
            raise NonPhysicalStateError(f"pole must be a unit vector, got {self.pole!r}")
        object.__setattr__(self, "pole", pole)

    @classmethod
    def two_body(cls, mu: float = GM_EARTH_M3PS2) -> ForceModel:
        return cls(mu=mu)

    @classmethod
    def with_j2(cls, pole: tuple[float, float, float], *, j2: float = J2_EARTH) -> ForceModel:
        return cls(j2=j2, pole=pole)

    @property
    def model_id(self) -> str:
        return D0_MODEL_ID if self.j2 == 0.0 else D1_J2_MODEL_ID


def acceleration(r: NDArray[np.float64], fm: ForceModel) -> NDArray[np.float64]:
    """Gravitational acceleration [m/s^2] for positions of shape (..., 3)."""
    rn = norm3(r)
    r3 = rn * rn * rn
    a = (-fm.mu / r3)[..., np.newaxis] * r
    if fm.j2 == 0.0:
        return a
    p = np.array(fm.pole)
    rp = dot3(r, p)
    s2 = (rp * rp) / (rn * rn)
    k = (-1.5 * fm.j2 * fm.mu * fm.r_ref_m * fm.r_ref_m) / (r3 * rn * rn)
    out: NDArray[np.float64] = (
        a + (k * (1.0 - 5.0 * s2))[..., np.newaxis] * r + (2.0 * k * rp)[..., np.newaxis] * p
    )
    return out


def potential(r: NDArray[np.float64], fm: ForceModel) -> NDArray[np.float64]:
    """Gravitational potential V [J/kg] (positive convention: a = grad V)."""
    rn = norm3(r)
    v = fm.mu / rn
    if fm.j2 == 0.0:
        return v
    s = dot3(r, np.array(fm.pole)) / rn
    p2 = 0.5 * (3.0 * s * s - 1.0)
    q = fm.r_ref_m / rn
    out: NDArray[np.float64] = v * (1.0 - fm.j2 * q * q * p2)
    return out


def specific_energy(y: NDArray[np.float64], fm: ForceModel) -> NDArray[np.float64]:
    """Conserved specific energy ``v^2/2 - V(r)`` for states of shape (..., 6)."""
    return 0.5 * dot3(y[..., 3:], y[..., 3:]) - potential(y[..., :3], fm)

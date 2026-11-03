"""Classical (Keplerian) orbital elements for bound orbits.

Used to set initial conditions from *consistent orbital elements* (spec §3.2)
and, through Kepler's equation, as one of two independent analytic two-body
references. Angles are radians; use :meth:`KeplerElements.from_degrees` at I/O
boundaries only (``docs/CONVENTIONS.md`` §1).

For a circular orbit (``e == 0``) the argument of periapsis is undefined; the
conversion still works and ``argp_rad + nu_rad`` is the argument of latitude.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from astramesh.dynamics.constants import GM_EARTH_M3PS2, R_EARTH_EQ_M
from astramesh.dynamics.state import (
    NonPhysicalStateError,
    Vector3,
    as_vector3,
    cross3,
    dot3,
    norm3,
)

_KEPLER_MAX_ITER = 50


@dataclass(frozen=True, slots=True)
class KeplerElements:
    """Osculating classical elements of a bound (elliptic or circular) orbit.

    Attributes:
        a_m: Semi-major axis [m], > 0.
        e: Eccentricity, 0 <= e < 1.
        i_rad: Inclination [rad], in [0, pi].
        raan_rad: Right ascension of the ascending node [rad].
        argp_rad: Argument of periapsis [rad].
        nu_rad: True anomaly [rad].
    """

    a_m: float
    e: float
    i_rad: float
    raan_rad: float
    argp_rad: float
    nu_rad: float

    def __post_init__(self) -> None:
        for name in ("a_m", "e", "i_rad", "raan_rad", "argp_rad", "nu_rad"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise TypeError(f"{name} must be a real number, got {type(value).__name__}")
            if not math.isfinite(value):
                raise NonPhysicalStateError(f"{name} must be finite, got {value!r}")
            object.__setattr__(self, name, float(value))
        if self.a_m <= 0:
            raise NonPhysicalStateError(f"a_m must be positive for a bound orbit, got {self.a_m}")
        if not 0.0 <= self.e < 1.0:
            raise NonPhysicalStateError(f"e must satisfy 0 <= e < 1 (bound orbit), got {self.e}")
        if not 0.0 <= self.i_rad <= math.pi:
            raise NonPhysicalStateError(f"i_rad must be in [0, pi], got {self.i_rad}")
        if self.periapsis_radius_m <= R_EARTH_EQ_M:
            raise NonPhysicalStateError(
                f"periapsis radius {self.periapsis_radius_m:.1f} m is not above the Earth's "
                f"equatorial radius ({R_EARTH_EQ_M} m)"
            )

    @classmethod
    def from_degrees(
        cls,
        *,
        a_m: float,
        e: float,
        i_deg: float,
        raan_deg: float,
        argp_deg: float,
        nu_deg: float,
    ) -> KeplerElements:
        return cls(
            a_m=a_m,
            e=e,
            i_rad=math.radians(i_deg),
            raan_rad=math.radians(raan_deg),
            argp_rad=math.radians(argp_deg),
            nu_rad=math.radians(nu_deg),
        )

    @property
    def periapsis_radius_m(self) -> float:
        return self.a_m * (1.0 - self.e)

    def period_s(self, mu: float = GM_EARTH_M3PS2) -> float:
        return 2.0 * math.pi * math.sqrt(self.a_m**3 / mu)

    def mean_motion_radps(self, mu: float = GM_EARTH_M3PS2) -> float:
        return math.sqrt(mu / self.a_m**3)

    def to_rv(self, mu: float = GM_EARTH_M3PS2) -> tuple[Vector3, Vector3]:
        """Position [m] and velocity [m/s] in the inertial frame the elements refer to."""
        a, e = self.a_m, self.e
        p = a * (1.0 - e * e)
        cnu, snu = math.cos(self.nu_rad), math.sin(self.nu_rad)
        r = p / (1.0 + e * cnu)
        sqrt_mu_p = math.sqrt(mu / p)
        r_pqw = np.array([r * cnu, r * snu, 0.0])
        v_pqw = np.array([-sqrt_mu_p * snu, sqrt_mu_p * (e + cnu), 0.0])
        rot = _pqw_to_inertial(self.raan_rad, self.i_rad, self.argp_rad)
        return rot @ r_pqw, rot @ v_pqw

    def advanced(self, dt_s: float, mu: float = GM_EARTH_M3PS2) -> KeplerElements:
        """Elements after ``dt_s`` s of unperturbed two-body motion (via Kepler's equation)."""
        m0 = true_to_mean_anomaly(self.nu_rad, self.e)
        m1 = m0 + self.mean_motion_radps(mu) * dt_s
        return KeplerElements(
            a_m=self.a_m,
            e=self.e,
            i_rad=self.i_rad,
            raan_rad=self.raan_rad,
            argp_rad=self.argp_rad,
            nu_rad=mean_to_true_anomaly(m1, self.e),
        )


def _pqw_to_inertial(raan: float, inc: float, argp: float) -> np.ndarray:
    """Rotation matrix R3(-raan) R1(-inc) R3(-argp) from perifocal to inertial axes."""
    cO, sO = math.cos(raan), math.sin(raan)
    ci, si = math.cos(inc), math.sin(inc)
    cw, sw = math.cos(argp), math.sin(argp)
    return np.array(
        [
            [cO * cw - sO * sw * ci, -cO * sw - sO * cw * ci, sO * si],
            [sO * cw + cO * sw * ci, -sO * sw + cO * cw * ci, -cO * si],
            [sw * si, cw * si, ci],
        ]
    )


def true_to_mean_anomaly(nu_rad: float, e: float) -> float:
    """Mean anomaly [rad] for true anomaly ``nu_rad`` on an elliptic orbit (0 <= e < 1)."""
    ecc_anom = 2.0 * math.atan2(
        math.sqrt(1.0 - e) * math.sin(nu_rad / 2.0), math.sqrt(1.0 + e) * math.cos(nu_rad / 2.0)
    )
    return ecc_anom - e * math.sin(ecc_anom)


def mean_to_true_anomaly(m_rad: float, e: float) -> float:
    """Solve Kepler's equation ``M = E - e sin E`` (Newton) and return the true anomaly [rad].

    The result is in (-pi, pi]. Raises :class:`ArithmeticError` if Newton's
    method fails to converge (it should not for 0 <= e < 1).
    """
    if not 0.0 <= e < 1.0:
        raise NonPhysicalStateError(f"e must satisfy 0 <= e < 1, got {e}")
    m = math.remainder(m_rad, 2.0 * math.pi)  # in [-pi, pi]
    ecc_anom = m if e < 0.8 else math.copysign(math.pi, m)
    for _ in range(_KEPLER_MAX_ITER):
        f = ecc_anom - e * math.sin(ecc_anom) - m
        step = f / (1.0 - e * math.cos(ecc_anom))
        ecc_anom -= step
        if abs(step) <= 4.0 * math.ulp(max(abs(ecc_anom), 1.0)):
            break
    else:  # pragma: no cover - not reachable for 0 <= e < 1
        raise ArithmeticError(f"Kepler's equation did not converge (M={m_rad}, e={e})")
    return 2.0 * math.atan2(
        math.sqrt(1.0 + e) * math.sin(ecc_anom / 2.0), math.sqrt(1.0 - e) * math.cos(ecc_anom / 2.0)
    )


def rv_to_elements(r_m: ArrayLike, v_mps: ArrayLike, mu: float = GM_EARTH_M3PS2) -> KeplerElements:
    """Osculating classical elements from an inertial position/velocity.

    Angles are computed with ``atan2`` from the node and eccentricity vectors.
    No near-circular or near-equatorial cut-off is applied: a cut-off that
    zeroes ``argp`` while keeping a small non-zero ``e`` would misplace the
    position by ~``a e`` (found by Hypothesis). For near-circular orbits the
    split between ``argp_rad`` and ``nu_rad`` is ill-conditioned and only their
    sum (argument of latitude) is meaningful; the state is still reproduced to
    round-off. Only the exactly singular cases use conventions: ``e == 0`` gives
    ``argp_rad = 0``; ``sin i == 0`` takes the node along the x-axis.

    Unbound or non-physical states raise :class:`NonPhysicalStateError` (via
    :class:`KeplerElements` validation).
    """
    r = as_vector3(r_m, name="r_m")
    v = as_vector3(v_mps, name="v_mps")
    rn = float(norm3(r))
    if rn == 0.0:
        raise NonPhysicalStateError("r_m must be non-zero")
    h = cross3(r, v)
    hn = float(norm3(h))
    if hn <= 1e-12 * rn * float(norm3(v)):
        raise NonPhysicalStateError("rectilinear motion has no orbital elements")
    h_hat = h / hn
    energy = 0.5 * float(dot3(v, v)) - mu / rn
    if energy >= 0.0:
        raise NonPhysicalStateError(f"state is not on a bound orbit (energy {energy:.3e} J/kg)")
    a = -mu / (2.0 * energy)
    e_vec = cross3(v, h) / mu - r / rn
    e = float(norm3(e_vec))
    sin_i = math.hypot(float(h_hat[0]), float(h_hat[1]))
    inc = math.atan2(sin_i, float(h_hat[2]))
    if sin_i == 0.0:
        node = np.array([1.0, 0.0, 0.0])
    else:
        node = np.array([-float(h_hat[1]), float(h_hat[0]), 0.0]) / sin_i
    raan = math.atan2(float(node[1]), float(node[0]))
    u = math.atan2(float(dot3(cross3(node, r), h_hat)), float(dot3(node, r)))
    if e == 0.0:
        argp = 0.0
    else:
        argp = math.atan2(float(dot3(cross3(node, e_vec), h_hat)), float(dot3(node, e_vec)))
    two_pi = 2.0 * math.pi
    return KeplerElements(
        a_m=a,
        e=e,
        i_rad=inc,
        raan_rad=raan % two_pi,
        argp_rad=argp % two_pi,
        nu_rad=(u - argp) % two_pi,
    )

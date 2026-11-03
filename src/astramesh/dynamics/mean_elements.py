"""Numerically defined mean elements and mean-element initialization (DL-026).

Definition used here (no analytic satellite theory involved): the **mean**
value of an osculating element is its time average over one *draconitic*
period, i.e. while the argument of latitude ``u`` (measured in the Earth's
equatorial frame, :func:`~astramesh.dynamics.forces.equatorial_basis`)
advances by exactly 2 pi, using the truth propagator. J2 short-period terms
are periodic in ``u``, so this average removes them (to O(J2^2)) and does not
depend on where in the orbit the average starts.

Initialization (DL-026 (b), option 2): starting from a guess, the initial
osculating semi-major axis (and, for the reference orbit, inclination) is
corrected by fixed-point iteration until the measured mean values equal the
targets. The correction map is close to the identity, so it converges in a
few iterations; failure to converge raises instead of returning a bad orbit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from astramesh.dynamics.elements import KeplerElements, rv_to_elements
from astramesh.dynamics.forces import ForceModel, equatorial_basis
from astramesh.dynamics.state import CartesianState, Frame, NonPhysicalStateError, matvec3
from astramesh.dynamics.twobody import propagate

DEFAULT_STEP_NS = 10 * 10**9
_MAX_ITER = 30


@dataclass(frozen=True, slots=True)
class MeanElements:
    """Time averages over one draconitic period (equatorial frame)."""

    a_m: float
    e: float
    ex: float  # e cos(argp): eccentricity-vector component along the node
    ey: float  # e sin(argp)
    i_rad: float
    draconitic_period_s: float


def equatorial_state(el: KeplerElements, forces: ForceModel) -> tuple[np.ndarray, np.ndarray]:
    """GCRS position/velocity for elements referred to the equator of ``forces.pole``."""
    r, v = el.to_rv(forces.mu)
    rot = equatorial_basis(forces.pole)
    return matvec3(rot.T, r), matvec3(rot.T, v)


def measure_mean_elements(
    r_m: np.ndarray,
    v_mps: np.ndarray,
    forces: ForceModel,
    *,
    epoch_utc: datetime,
    step_ns: int = DEFAULT_STEP_NS,
) -> MeanElements:
    """Average osculating a, e, i over one draconitic period starting at the given state."""
    rot = equatorial_basis(forces.pole)
    el0 = rv_to_elements(matvec3(rot, r_m), matvec3(rot, v_mps), forces.mu)
    n_steps = int(1.2 * el0.period_s(forces.mu) * 1e9 / step_ns) + 2
    start = CartesianState(Frame.GCRS, epoch_utc, 0, r_m, v_mps)
    traj = propagate([start], step_ns=step_ns, n_steps=n_steps, forces=forces)
    y = traj.y[:, 0, :]
    t = traj.t_ns.astype(np.float64) / 1e9
    osc = [rv_to_elements(matvec3(rot, row[:3]), matvec3(rot, row[3:]), forces.mu) for row in y]
    u = np.unwrap([(o.argp_rad + o.nu_rad) % (2 * math.pi) for o in osc])
    target = u[0] + 2 * math.pi
    k = int(np.searchsorted(u, target))  # u is strictly increasing for a prograde-in-u orbit
    if k == 0 or k >= len(u):
        raise ArithmeticError("argument of latitude did not complete one revolution")
    frac = (target - u[k - 1]) / (u[k] - u[k - 1])
    t_end = t[k - 1] + frac * (t[k] - t[k - 1])

    def average(values: np.ndarray) -> float:
        end_value = values[k - 1] + frac * (values[k] - values[k - 1])
        full = np.trapezoid(values[:k], t[:k])
        tail = 0.5 * (values[k - 1] + end_value) * (t_end - t[k - 1])
        return float((full + tail) / t_end)

    return MeanElements(
        a_m=average(np.array([o.a_m for o in osc])),
        e=average(np.array([o.e for o in osc])),
        ex=average(np.array([o.e * math.cos(o.argp_rad) for o in osc])),
        ey=average(np.array([o.e * math.sin(o.argp_rad) for o in osc])),
        i_rad=average(np.array([o.i_rad for o in osc])),
        draconitic_period_s=float(t_end),
    )


@dataclass(frozen=True, slots=True)
class InitializedOrbit:
    """Initial osculating elements (equatorial frame) and GCRS state, with diagnostics."""

    osculating: KeplerElements
    r_m: np.ndarray
    v_mps: np.ndarray
    mean: MeanElements
    iterations: int


def initialize_from_mean(
    *,
    mean_a_m: float,
    mean_i_rad: float | None,
    raan_rad: float,
    u_rad: float,
    forces: ForceModel,
    epoch_utc: datetime,
    osc_i_rad: float | None = None,
    match_eccentricity: bool = True,
    tol_a_m: float = 1e-4,
    tol_i_rad: float = 1e-10,
    tol_e: float = 1e-9,
    step_ns: int = DEFAULT_STEP_NS,
) -> InitializedOrbit:
    """Find an initial osculating orbit whose mean elements hit the targets.

    Targets: mean ``a`` = ``mean_a_m``; mean ``i`` = ``mean_i_rad`` (or, if that
    is ``None``, the osculating inclination ``osc_i_rad`` is held fixed); and,
    if ``match_eccentricity``, mean eccentricity vector = 0 (a mean-circular
    orbit, the reference "e = 0" read as a mean element, DL-026 (a)). The
    initial node is ``raan_rad`` and argument of latitude ``u_rad``
    (equatorial frame).
    """
    if (mean_i_rad is None) == (osc_i_rad is None):
        raise ValueError("give exactly one of mean_i_rad (to iterate i) or osc_i_rad (fixed)")
    a0 = mean_a_m
    i0 = float(mean_i_rad if mean_i_rad is not None else osc_i_rad)  # type: ignore[arg-type]
    ex0 = ey0 = 0.0
    da = di = de = math.inf
    for it in range(1, _MAX_ITER + 1):
        e0 = math.hypot(ex0, ey0)
        argp0 = math.atan2(ey0, ex0) if e0 > 0.0 else 0.0
        el = KeplerElements(
            a_m=a0,
            e=e0,
            i_rad=i0,
            raan_rad=raan_rad,
            argp_rad=argp0 % (2 * math.pi),
            nu_rad=(u_rad - argp0) % (2 * math.pi),
        )
        r, v = equatorial_state(el, forces)
        mean = measure_mean_elements(r, v, forces, epoch_utc=epoch_utc, step_ns=step_ns)
        da = mean_a_m - mean.a_m
        di = 0.0 if mean_i_rad is None else mean_i_rad - mean.i_rad
        de = math.hypot(mean.ex, mean.ey) if match_eccentricity else 0.0
        if abs(da) <= tol_a_m and abs(di) <= tol_i_rad and de <= tol_e:
            return InitializedOrbit(el, r, v, mean, it)
        a0 += da
        i0 += di
        if match_eccentricity:
            ex0 -= mean.ex
            ey0 -= mean.ey
    raise NonPhysicalStateError(
        f"mean-element initialization did not converge in {_MAX_ITER} iterations "
        f"(residual a {da:.3e} m, i {di:.3e} rad, e {de:.3e})"
    )


def mean_matched_formation(
    *,
    mean_a_m: float,
    mean_i_rad: float,
    raan_rad: float,
    u0_rad: float,
    n_spacecraft: int,
    spacing_m: float,
    forces: ForceModel,
    epoch_utc: datetime,
    step_ns: int = DEFAULT_STEP_NS,
) -> tuple[InitializedOrbit, ...]:
    """Along-track formation whose members all have the same mean semi-major axis.

    The leader (index 0) is initialized from the mean targets at argument of
    latitude ``u0_rad``. Spacecraft k starts at ``u0 - k * spacing_m / mean_a``
    with the leader's osculating inclination and node, and only its osculating
    ``a`` is iterated until its mean ``a`` equals the leader's (DL-026 (b)).
    """
    if isinstance(n_spacecraft, bool) or not isinstance(n_spacecraft, int) or n_spacecraft < 1:
        raise ValueError(f"n_spacecraft must be a positive int, got {n_spacecraft!r}")
    if not (math.isfinite(spacing_m) and spacing_m > 0):
        raise ValueError(f"spacing_m must be positive and finite, got {spacing_m!r}")
    du = spacing_m / mean_a_m
    if (n_spacecraft - 1) * du >= math.pi:
        raise ValueError("formation spans more than half an orbit")
    leader = initialize_from_mean(
        mean_a_m=mean_a_m,
        mean_i_rad=mean_i_rad,
        raan_rad=raan_rad,
        u_rad=u0_rad,
        forces=forces,
        epoch_utc=epoch_utc,
        step_ns=step_ns,
    )
    members = [leader]
    for k in range(1, n_spacecraft):
        members.append(
            initialize_from_mean(
                mean_a_m=leader.mean.a_m,
                mean_i_rad=None,
                osc_i_rad=leader.osculating.i_rad,
                raan_rad=raan_rad,
                u_rad=u0_rad - k * du,
                forces=forces,
                epoch_utc=epoch_utc,
                step_ns=step_ns,
            )
        )
    return tuple(members)

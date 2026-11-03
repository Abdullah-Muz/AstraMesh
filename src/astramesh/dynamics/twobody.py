"""Numerical two-body propagation of several spacecraft (dynamics level D0).

Integrator: classical fixed-step 4th-order Runge-Kutta (RK4) on the scenario
clock grid (integer-nanosecond time points, ``docs/CONVENTIONS.md`` §2.1).
Each spacecraft is an independent point mass in the Earth's central field;
there are no perturbations, thrust, or interactions.

Determinism (PA-09): all arithmetic is elementwise NumPy (no BLAS, no
reductions with platform-dependent ordering, no transcendental functions), so
the same inputs give bit-identical outputs.

Visible failure (PA-10): non-finite states, or a spacecraft at or below the
Earth's equatorial radius, raise :class:`NonPhysicalStateError` immediately
instead of continuing with fabricated dynamics.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from numpy.typing import NDArray

from astramesh.core.clock import NS_PER_S
from astramesh.dynamics.constants import GM_EARTH_M3PS2, R_EARTH_EQ_M
from astramesh.dynamics.state import (
    CartesianState,
    Frame,
    NonPhysicalStateError,
    cross3,
    dot3,
    norm3,
)

DYNAMICS_MODEL_ID = "D0-two-body-rk4"


def two_body_acceleration(r: NDArray[np.float64], mu: float) -> NDArray[np.float64]:
    """Central-field acceleration ``-mu r / |r|^3`` for positions of shape (..., 3)."""
    rn = norm3(r)
    return (-mu / (rn * rn * rn))[..., np.newaxis] * r


def _derivative(y: NDArray[np.float64], mu: float) -> NDArray[np.float64]:
    return np.concatenate((y[:, 3:], two_body_acceleration(y[:, :3], mu)), axis=1)


def rk4_step(y: NDArray[np.float64], h_s: float, mu: float) -> NDArray[np.float64]:
    """One classical RK4 step for stacked states ``y`` of shape (n, 6)."""
    k1 = _derivative(y, mu)
    k2 = _derivative(y + (0.5 * h_s) * k1, mu)
    k3 = _derivative(y + (0.5 * h_s) * k2, mu)
    k4 = _derivative(y + h_s * k3, mu)
    return y + (h_s / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def _check_physical(y: NDArray[np.float64], t_ns: int) -> None:
    if not np.all(np.isfinite(y)):
        bad = np.flatnonzero(~np.all(np.isfinite(y), axis=1)).tolist()
        raise NonPhysicalStateError(f"non-finite state for spacecraft {bad} at t_ns={t_ns}")
    rn = norm3(y[:, :3])
    if np.any(rn <= R_EARTH_EQ_M):
        bad = np.flatnonzero(rn <= R_EARTH_EQ_M).tolist()
        raise NonPhysicalStateError(
            f"spacecraft {bad} at or below the Earth's equatorial radius at t_ns={t_ns} "
            f"(|r| = {rn[bad].tolist()} m); two-body propagation would be non-physical"
        )


@dataclass(frozen=True, slots=True, eq=False)
class Trajectory:
    """Propagated states on the clock grid.

    Attributes:
        frame: Frame of all states (GCRS).
        epoch_utc: Scenario epoch.
        t_ns: Time points, shape (n_times,), int64.
        y: States ``[x, y, z, vx, vy, vz]`` in m and m/s, shape (n_times, n_spacecraft, 6).
        mu: Gravitational parameter used [m^3 s^-2].
        model_id: Dynamics model identifier (recorded in run manifests).
    """

    frame: Frame
    epoch_utc: datetime
    t_ns: NDArray[np.int64]
    y: NDArray[np.float64]
    mu: float
    model_id: str = DYNAMICS_MODEL_ID

    @property
    def n_spacecraft(self) -> int:
        return int(self.y.shape[1])

    def state(self, tick: int, spacecraft: int) -> CartesianState:
        row = self.y[tick, spacecraft]
        return CartesianState(self.frame, self.epoch_utc, int(self.t_ns[tick]), row[:3], row[3:])


def propagate_two_body(
    initial: Sequence[CartesianState],
    *,
    step_ns: int,
    n_steps: int,
    mu: float = GM_EARTH_M3PS2,
) -> Trajectory:
    """Propagate GCRS states of several spacecraft with fixed-step RK4.

    All initial states must be in GCRS at the same scenario time. The returned
    trajectory has ``n_steps + 1`` time points starting at that time.
    """
    if not initial:
        raise ValueError("at least one initial state is required")
    first = initial[0]
    for s in initial:
        s.require_frame(Frame.GCRS)
        s.require_same_time(first)
    for name, value in (("step_ns", step_ns), ("n_steps", n_steps)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    if step_ns <= 0:
        raise ValueError(f"step_ns must be positive, got {step_ns}")
    if n_steps < 0:
        raise ValueError(f"n_steps must be non-negative, got {n_steps}")
    if not (np.isfinite(mu) and mu > 0):
        raise NonPhysicalStateError(f"mu must be positive and finite, got {mu!r}")

    y0 = np.stack([np.concatenate((s.r_m, s.v_mps)) for s in initial])
    _check_physical(y0, first.t_ns)
    t_ns = first.t_ns + step_ns * np.arange(n_steps + 1, dtype=np.int64)
    out = np.empty((n_steps + 1, len(initial), 6), dtype=np.float64)
    out[0] = y0
    h_s = step_ns / NS_PER_S
    y = y0
    for k in range(1, n_steps + 1):
        y = rk4_step(y, h_s, mu)
        _check_physical(y, int(t_ns[k]))
        out[k] = y
    out.setflags(write=False)
    t_ns.setflags(write=False)
    return Trajectory(Frame.GCRS, first.epoch_utc, t_ns, out, float(mu))


def specific_energy(y: NDArray[np.float64], mu: float) -> NDArray[np.float64]:
    """Specific orbital energy ``v^2/2 - mu/r`` [J/kg] for states of shape (..., 6)."""
    return 0.5 * dot3(y[..., 3:], y[..., 3:]) - mu / norm3(y[..., :3])


def specific_angular_momentum(y: NDArray[np.float64]) -> NDArray[np.float64]:
    """Specific angular-momentum vector ``r x v`` [m^2/s] for states of shape (..., 6)."""
    return cross3(y[..., :3], y[..., 3:])

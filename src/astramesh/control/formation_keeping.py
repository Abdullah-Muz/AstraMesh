"""Along-track formation keeping against differential drag (DL-087, option A).

Leader-referenced slots: spacecraft 0 has no control; spacecraft k keeps its slot,
``(k - i)`` nominal spacings behind its *reference* i, the frontmost spacecraft it can
hear (normally spacecraft 0). If spacecraft 0 falls silent, spacecraft 1 hears no
one ahead and becomes the uncontrolled leader. DL-087 specified a chain (each
spacecraft follows the one directly ahead); the chain amplified errors down the
train, because every follower treated its predecessor's corrections as a
disturbance (string instability; DL-088).

Spacing and drift
    The spacing ``s`` is the along-track component of ``r[i] - r[k]`` (positive
    while the follower is behind). A tangential velocity change ``dv`` changes the
    semi-major axis by ``2 dv / n`` and the mean along-track drift of the spacing by
    ``ds/dt = 3 dv`` (circular orbit; the ``(4/n) dv sin(n t)`` short-period part is
    at most 1.5 m per 10 s burn step and is ignored).

Estimation
    Once per nominal orbit each follower measures ``s`` from both GNSS positions
    (truth plus Gaussian error, ``navigation_sigma_m`` per axis, modelled) and runs a
    three-state Kalman filter (spacing, drift rate, drift acceleration; white-jerk
    process noise), with its own burns as known inputs. Sampling once per orbit
    removes most orbit-periodic terms; the osculating semi-major axis is not used
    because its J2 short-period difference between neighbours (+-54 m at 525 km and
    20 km spacing) would imply a drift of several km per day.

Control
    With error ``e = s - spacing`` outside the deadband, the target drift rate is
    ``-e / time_constant`` (limited to ``max_drift_rate_mps``); the follower commands
    a whole number of 10 s steps of full thrust, prograde (drifts back) or retrograde
    (closes up), toward the target drift at mid-interval. Commanded steps are flown
    only while every check passes; steps not flown by the next decision are dropped.

Checks (modelled; spec §14.1)
    sunlight only; no burn after the delta-v budget; none while the spacecraft is
    unavailable, has an active critical fault or reduced generation; none while it
    cannot hear its reference (either radio down, or a partition between them). When
    the reference changes, the filter restarts and that decision commands nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from astramesh.dynamics.state import dot3, norm3
from astramesh.dynamics.sun import in_shadow
from astramesh.faults.schedule import FaultSchedule
from astramesh.resources.ledgers import PropulsionBudget

#: Floor on the spacing-measurement standard deviation from orbit-periodic terms that
#: sampling once per (nominal) orbit does not remove [m]; orbit-sampled spacings of a
#: gravity-only J2 run scatter by 0.55 - 0.64 m peak to peak over 2 days (DL-088).
SAMPLING_FLOOR_M = 1.0
#: Initial standard deviations of the drift rate [m/s] and drift acceleration [m/s^2]:
#: the formation starts mean-matched (zero drift) with unknown differential drag.
INITIAL_RATE_SIGMA_MPS = 1e-3
INITIAL_ACCEL_SIGMA_MPS2 = 1e-6


@dataclass(frozen=True, slots=True)
class KeepingParameters:
    spacing_m: float
    deadband_m: float
    time_constant_s: float
    max_drift_rate_mps: float
    navigation_sigma_m: float
    jerk_psd_m2ps5: float
    control_interval_steps: int
    thrust_n: float
    mass_kg: float
    specific_impulse_s: float
    budget_mps: float

    def __post_init__(self) -> None:
        if self.control_interval_steps < 1:
            raise ValueError("control_interval_steps must be >= 1")


@dataclass(frozen=True, slots=True)
class Command:
    """One control decision with at least one commanded step."""

    spacecraft: str
    reference: str
    t_ns: int
    steps: int  # signed: + prograde (drift back), - retrograde (close up)
    error_m: float
    rate_mps: float
    accel_mps2: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "spacecraft": self.spacecraft, "reference": self.reference, "t_ns": self.t_ns,
            "steps": self.steps,
            "error_m": self.error_m, "rate_mps": self.rate_mps, "accel_mps2": self.accel_mps2,
        }  # fmt: skip


@dataclass(frozen=True, slots=True, eq=False)
class KeepingResult:
    """What the controller did, for the ledgers and the run summary."""

    ids: tuple[str, ...]
    step_s: float
    thrust_on: NDArray[np.bool_]  # (n_t, n_sc): thrust during step k -> k+1
    delta_v_mps: tuple[float, ...]
    propellant_kg: tuple[float, ...]
    commands: tuple[Command, ...]
    held: tuple[int, ...]  # decisions without a fresh measurement, per spacecraft

    def summary(self, thruster_power_w: float) -> dict[str, Any]:
        steps = self.thrust_on.sum(axis=0)
        return {
            "model": "DL-087/088 along-track keeping, leader-referenced slots (option A)",
            "per_spacecraft": {
                sc: {
                    "delta_v_mps": self.delta_v_mps[j],
                    "propellant_kg": self.propellant_kg[j],
                    "thrust_s": float(steps[j]) * self.step_s,
                    "thruster_energy_wh": float(steps[j]) * self.step_s * thruster_power_w / 3600,
                    "commands": sum(1 for c in self.commands if c.spacecraft == sc),
                    "held_decisions": self.held[j],
                }
                for j, sc in enumerate(self.ids)
            },
        }


class _SpacingFilter:
    """Kalman filter on (spacing, drift rate, drift acceleration), sampled per decision."""

    __slots__ = ("p", "q", "r", "u", "x")

    def __init__(self, s0: float, r_var: float, q: float) -> None:
        self.x = np.array([s0, 0.0, 0.0])
        self.p = np.diag([r_var, INITIAL_RATE_SIGMA_MPS**2, INITIAL_ACCEL_SIGMA_MPS2**2])
        self.r, self.q = r_var, q
        self.u = np.zeros(3)  # effect of own burns since the last decision, at the next one

    def add_burn(self, d_rate: float, lead_s: float) -> None:
        self.u[0] += d_rate * lead_s
        self.u[1] += d_rate

    def predict(self, dt: float) -> None:
        f = np.array([[1.0, dt, 0.5 * dt * dt], [0.0, 1.0, dt], [0.0, 0.0, 1.0]])
        d2, d3, d4, d5 = dt * dt, dt**3, dt**4, dt**5
        q = self.q * np.array([[d5 / 20, d4 / 8, d3 / 6], [d4 / 8, d3 / 3, d2 / 2],
                               [d3 / 6, d2 / 2, dt]])  # fmt: skip
        self.x = f @ self.x + self.u
        self.p = f @ self.p @ f.T + q
        self.u = np.zeros(3)

    def update(self, z: float) -> None:
        s = self.p[0, 0] + self.r
        k = self.p[:, 0] / s
        self.x = self.x + k * (z - self.x[0])
        self.p = self.p - np.outer(k, self.p[0, :])


class FormationKeeper:
    """:class:`~astramesh.dynamics.twobody.ThrustController` for DL-087."""

    def __init__(
        self,
        params: KeepingParameters,
        ids: list[str],
        step_ns: int,
        sun_dir: NDArray[np.float64],
        faults: FaultSchedule | None,
        rng: np.random.Generator,
    ) -> None:
        self.p = params
        self.ids = list(ids)
        n = len(ids)
        if n < 2:
            raise ValueError("formation keeping needs at least two spacecraft")
        self.h_s = step_ns / 1e9
        self.sun = sun_dir
        self.faults = faults if faults else None
        self.rng = rng
        self.budgets = [
            PropulsionBudget(params.mass_kg, params.thrust_n, params.specific_impulse_s,
                             params.budget_mps)
            for _ in ids
        ]  # fmt: skip
        self.filters: list[_SpacingFilter | None] = [None] * n
        self.ref: list[int | None] = [None] * n  # reference of each filter
        self.pending = [0] * n
        self.held = [0] * n
        self.commands: list[Command] = []
        self.thrust_on = np.zeros((sun_dir.shape[0], n), dtype=np.bool_)
        self._next_k = 0
        self._r_var = 2.0 * params.navigation_sigma_m**2 + SAMPLING_FLOOR_M**2

    # ------------------------------------------------------------------ checks ----
    def _hears(self, j: int, i: int, t_ns: int) -> bool:
        f = self.faults
        if f is None:
            return True
        a, b = self.ids[j], self.ids[i]
        return f.radio_up(a, t_ns) and f.radio_up(b, t_ns) and not f.link_cut(a, b, t_ns)

    def _reference(self, j: int, t_ns: int) -> int | None:
        return next((i for i in range(j) if self._hears(j, i, t_ns)), None)

    def _may_burn(self, j: int, k: int, t_ns: int, y: NDArray[np.float64]) -> bool:
        f = self.faults
        if f is not None:
            sc = self.ids[j]
            if f.unavailable(sc, t_ns) or f.critical_flags(sc, t_ns):
                return False
            if f.generation_factor(sc, t_ns) < 1.0:
                return False
        ref = self.ref[j]
        if ref is None or not self._hears(j, ref, t_ns):
            return False
        return not bool(in_shadow(y[j : j + 1, :3], self.sun[k : k + 1])[0])

    # -------------------------------------------------------------- decisions ----
    def _measure(self, j: int, i: int, y: NDArray[np.float64]) -> float:
        r_lead, r_me = y[i, :3], y[j, :3]
        sigma = self.p.navigation_sigma_m
        if sigma > 0.0:
            noise = self.rng.normal(0.0, sigma, size=(2, 3))
            r_lead, r_me = r_lead + noise[0], r_me + noise[1]
        v = y[j, 3:]
        return float(dot3(r_lead - r_me, v / norm3(v)))

    def _decide(self, k: int, t_ns: int, y: NDArray[np.float64]) -> None:
        p = self.p
        dt = p.control_interval_steps * self.h_s
        for j in range(1, len(self.ids)):
            filt = self.filters[j]
            if filt is not None:
                filt.predict(dt)
            self.pending[j] = 0
            ref = self._reference(j, t_ns)
            if ref is None:
                self.held[j] += 1
                continue
            z = self._measure(j, ref, y)
            if filt is None or ref != self.ref[j]:
                self.filters[j] = _SpacingFilter(z, self._r_var, p.jerk_psd_m2ps5)
                self.ref[j] = ref
                continue
            filt.update(z)
            s, rate, accel = (float(v) for v in filt.x)
            err = s - (j - ref) * p.spacing_m
            if abs(err) <= p.deadband_m:
                continue
            target = -max(-p.max_drift_rate_mps, min(p.max_drift_rate_mps, err / p.time_constant_s))
            need = target - (rate + 0.5 * dt * accel)
            b = self.budgets[j]
            per_step = 3.0 * b.thrust_n / b.current_mass_kg * self.h_s
            steps = int(need / per_step)  # toward zero: no step smaller than one full step
            if steps:
                self.pending[j] = steps
                self.commands.append(
                    Command(self.ids[j], self.ids[ref], t_ns, steps, err, rate, accel)
                )

    # ------------------------------------------------------------------- step ----
    def thrust(self, k: int, t_ns: int, y: NDArray[np.float64]) -> NDArray[np.float64] | None:
        if k == self._next_k:
            self._decide(k, t_ns, y)
            self._next_k = k + self.p.control_interval_steps
        out: NDArray[np.float64] | None = None
        for j in range(1, len(self.ids)):
            steps = self.pending[j]
            if steps == 0 or not self._may_burn(j, k, t_ns, y):
                continue
            b = self.budgets[j]
            accel = b.thrust_n / b.current_mass_kg
            dv = accel * self.h_s
            if dv > b.remaining_mps:
                self.pending[j] = 0
                continue
            sign = 1 if steps > 0 else -1
            if out is None:
                out = np.zeros(len(self.ids))
            out[j] = sign * accel
            b.used_mps += dv
            self.pending[j] -= sign
            self.thrust_on[k, j] = True
            filt = self.filters[j]
            if filt is not None:
                filt.add_burn(3.0 * sign * dv, (self._next_k - k - 0.5) * self.h_s)
        return out

    def result(self) -> KeepingResult:
        return KeepingResult(
            ids=tuple(self.ids),
            step_s=self.h_s,
            thrust_on=self.thrust_on,
            delta_v_mps=tuple(b.used_mps for b in self.budgets),
            propellant_kg=tuple(b.propellant_kg(b.used_mps) for b in self.budgets),
            commands=tuple(self.commands),
            held=tuple(self.held),
        )


def control_interval_steps(mean_altitude_km: float, mu: float, r_eq_m: float, step_s: float) -> int:
    """Whole steps closest to one nominal (two-body) orbital period at the mean altitude."""
    a = r_eq_m + mean_altitude_km * 1e3
    return max(1, round(2.0 * math.pi * math.sqrt(a**3 / mu) / step_s))

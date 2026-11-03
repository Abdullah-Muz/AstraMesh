"""Resource ledgers: battery energy, data storage, and the delta-v/propellant budget.

Energy (per spacecraft, per simulation step)
    Step k covers [t_k, t_{k+1}). Loads and generation use the state at tick k
    (left endpoint): generation if sunlit at tick k; payload load if the payload
    is on at tick k. Net power P = generation - bus - payload - thruster.
    Charging stores ``charge_efficiency`` x P x dt; discharging removes P x dt
    (all inefficiency is put on the charge side). Accounting is in joules
    (CONVENTIONS §1); inputs and results are in watt-hours. The stored energy is clamped
    to [0, capacity]. Energy that cannot be stored (battery full) is counted as
    *curtailed*; energy that cannot be supplied (battery empty) is counted as
    *deficit*, together with the number of steps it occurs in. A deficit means
    the requested load profile is infeasible: it is reported, never hidden.

Storage
    Data accumulates at the payload rate while the payload is on. There is no
    downlink in Phase 1, so the fill only grows; overflow is reported the same
    way as an energy deficit.

Delta-v
    Tsiolkovsky: propellant m0 (1 - exp(-dv / (Isp g0))). Burns are refused if
    they exceed the remaining budget. Thrust time uses the current mass.

All arithmetic is plain Python floats in a fixed order (deterministic).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

#: Standard gravity [m s^-2] (CGPM 1901, exact), for specific impulse.
G0_MPS2 = 9.80665
S_PER_H = 3600.0


@dataclass(frozen=True, slots=True)
class EnergyResult:
    stored_wh: NDArray[np.float64]  # (n_t,) state of charge at each tick
    min_wh: float
    min_tick: int
    max_drawdown_wh: float  # largest drop below a preceding level (worst eclipse discharge)
    final_wh: float
    curtailed_wh: float
    deficit_wh: float
    deficit_steps: int
    generated_wh: float
    consumed_wh: float


def simulate_energy(
    *,
    sunlit: NDArray[np.bool_],
    payload_on: NDArray[np.bool_],
    step_s: float,
    capacity_wh: float,
    initial_fraction: float,
    charge_efficiency: float,
    generation_w: float,
    bus_w: float,
    payload_w: float,
    thruster_on: NDArray[np.bool_] | None = None,
    thruster_w: float = 0.0,
) -> EnergyResult:
    """Battery energy over the tick grid for one spacecraft (see module docstring)."""
    n = len(sunlit)
    if payload_on.shape != (n,) or (thruster_on is not None and thruster_on.shape != (n,)):
        raise ValueError("sunlit, payload_on and thruster_on must have the same length")
    if not (0.0 < initial_fraction <= 1.0 and 0.0 < charge_efficiency <= 1.0):
        raise ValueError("initial_fraction and charge_efficiency must be in (0, 1]")
    if capacity_wh <= 0.0 or step_s <= 0.0:
        raise ValueError("capacity_wh and step_s must be positive")
    cap_j = capacity_wh * S_PER_H
    e = cap_j * initial_fraction
    out = np.empty(n)
    out[0] = e
    curtailed = deficit = generated = consumed = 0.0
    deficit_steps = 0
    sun = sunlit.tolist()
    pay = payload_on.tolist()
    thr = thruster_on.tolist() if thruster_on is not None else [False] * n
    for k in range(n - 1):
        gen = generation_w if sun[k] else 0.0
        load = bus_w + (payload_w if pay[k] else 0.0) + (thruster_w if thr[k] else 0.0)
        generated += gen * step_s
        consumed += load * step_s
        net_j = (gen - load) * step_s
        if net_j >= 0.0:
            e += charge_efficiency * net_j
            if e > cap_j:
                curtailed += (e - cap_j) / charge_efficiency
                e = cap_j
        else:
            e += net_j
            if e < 0.0:
                deficit += -e
                deficit_steps += 1
                e = 0.0
        out[k + 1] = e
    out /= S_PER_H  # J -> Wh
    k_min = int(np.argmin(out))
    drawdown = float(np.max(np.maximum.accumulate(out) - out))
    return EnergyResult(
        stored_wh=out,
        min_wh=float(out[k_min]),
        min_tick=k_min,
        max_drawdown_wh=drawdown,
        final_wh=float(out[-1]),
        curtailed_wh=curtailed / S_PER_H,
        deficit_wh=deficit / S_PER_H,
        deficit_steps=deficit_steps,
        generated_wh=generated / S_PER_H,
        consumed_wh=consumed / S_PER_H,
    )


def data_volume_mb(on_steps: int, step_s: float, rate_kbps: float) -> float:
    """Data recorded in ``on_steps`` steps at ``rate_kbps`` [MB = 1e6 bytes]."""
    return on_steps * step_s * rate_kbps * 1e3 / 8.0 / 1e6


def energy_wh(on_steps: int, step_s: float, power_w: float) -> float:
    return on_steps * step_s * power_w / S_PER_H


@dataclass(slots=True)
class PropulsionBudget:
    """Delta-v and propellant bookkeeping for one spacecraft (constant Isp)."""

    mass_kg: float
    thrust_n: float
    specific_impulse_s: float
    budget_mps: float
    used_mps: float = field(default=0.0)

    def __post_init__(self) -> None:
        for name in ("mass_kg", "thrust_n", "specific_impulse_s"):
            v = getattr(self, name)
            if not (math.isfinite(v) and v > 0.0):
                raise ValueError(f"{name} must be positive and finite, got {v!r}")
        if not (math.isfinite(self.budget_mps) and self.budget_mps >= 0.0):
            raise ValueError(f"budget_mps must be >= 0, got {self.budget_mps!r}")

    @property
    def exhaust_velocity_mps(self) -> float:
        return self.specific_impulse_s * G0_MPS2

    @property
    def remaining_mps(self) -> float:
        return self.budget_mps - self.used_mps

    def propellant_kg(self, dv_mps: float, mass_kg: float | None = None) -> float:
        m0 = self.mass_kg if mass_kg is None else mass_kg
        return m0 * -math.expm1(-dv_mps / self.exhaust_velocity_mps)

    @property
    def current_mass_kg(self) -> float:
        return self.mass_kg - self.propellant_kg(self.used_mps)

    def burn_time_s(self, dv_mps: float) -> float:
        """Thrust time for ``dv_mps`` at full thrust from the current mass (exact, constant Isp)."""
        return (
            self.propellant_kg(dv_mps, self.current_mass_kg)
            * self.exhaust_velocity_mps
            / (self.thrust_n)
        )

    def burn(self, dv_mps: float) -> float:
        """Spend ``dv_mps``; return the propellant used [kg]. Raises if over budget."""
        if not (math.isfinite(dv_mps) and dv_mps >= 0.0):
            raise ValueError(f"dv_mps must be >= 0 and finite, got {dv_mps!r}")
        if dv_mps > self.remaining_mps:
            raise ValueError(
                f"burn of {dv_mps} m/s exceeds the remaining budget {self.remaining_mps} m/s"
            )
        used = self.propellant_kg(dv_mps, self.current_mass_kg)
        self.used_mps += dv_mps
        return used

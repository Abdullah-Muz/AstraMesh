"""Sensor packets: the only way simulator truth reaches an agent (spec §5.2 ``observe``).

Packets are immutable and contain plain tuples/floats, never arrays or
objects shared with the simulator. Each packet is a *measurement* with stated
noise, not truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavigationFix:
    """Own-orbit GNSS-like fix: GCRS position/velocity with isotropic 1-sigma noise."""

    t_ns: int
    r_m: tuple[float, float, float]
    v_mps: tuple[float, float, float]
    sigma_r_m: float
    sigma_v_mps: float

    def __post_init__(self) -> None:
        if isinstance(self.t_ns, bool) or not isinstance(self.t_ns, int) or self.t_ns < 0:
            raise ValueError("t_ns must be a non-negative int")
        for name in ("r_m", "v_mps"):
            v = getattr(self, name)
            if len(v) != 3 or not all(isinstance(x, float) and math.isfinite(x) for x in v):
                raise ValueError(f"{name} must be three finite floats")
        if not (self.sigma_r_m >= 0.0 and self.sigma_v_mps >= 0.0):
            raise ValueError("sigmas must be >= 0")


@dataclass(frozen=True, slots=True)
class Housekeeping:
    """Own resource telemetry at ``t_ns``: battery and storage (exact values in Phase 2)."""

    t_ns: int
    battery_wh: float
    battery_capacity_wh: float
    storage_used_mb: float
    storage_capacity_mb: float

    def __post_init__(self) -> None:
        vals = (self.battery_wh, self.battery_capacity_wh, self.storage_used_mb,
                self.storage_capacity_mb)  # fmt: skip
        if not all(math.isfinite(v) and v >= 0.0 for v in vals):
            raise ValueError("housekeeping values must be finite and >= 0")


@dataclass(frozen=True, slots=True)
class PlannedObservation:
    task_id: str
    start_ns: int  # first step starts here
    stop_ns: int  # exclusive: payload off from here


@dataclass(frozen=True, slots=True)
class PlanUplink:
    """A plan made outside the agent (B0 ground plan, B1 reference): this agent's part only."""

    t_ns: int
    algorithm: str
    version: int
    observations: tuple[PlannedObservation, ...]

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("plan version must be >= 1")
        for o in self.observations:
            if not (0 <= o.start_ns < o.stop_ns):
                raise ValueError(f"invalid observation interval for {o.task_id}")

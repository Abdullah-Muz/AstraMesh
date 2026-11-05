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
    critical_flags: tuple[str, ...] = ()  # own critical-subsystem flags (DL-054)

    def __post_init__(self) -> None:
        vals = (self.battery_wh, self.battery_capacity_wh, self.storage_used_mb,
                self.storage_capacity_mb)  # fmt: skip
        if not all(math.isfinite(v) and v >= 0.0 for v in vals):
            raise ValueError("housekeeping values must be finite and >= 0")


@dataclass(frozen=True, slots=True)
class PayloadCheck:
    """Own onboard anomaly detector output: calibrated P(payload anomalous) (DL-066)."""

    t_ns: int
    prob: float

    def __post_init__(self) -> None:
        if isinstance(self.t_ns, bool) or not isinstance(self.t_ns, int) or self.t_ns < 0:
            raise ValueError("t_ns must be a non-negative int")
        if not (isinstance(self.prob, float) and 0.0 <= self.prob <= 1.0):
            raise ValueError("prob must be a float in [0, 1]")


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
    public_tasks: tuple[PublicTask, ...] = ()  # B4 only: whole plan + catalogue (DL-052)

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("plan version must be >= 1")
        for o in self.observations:
            if not (0 <= o.start_ns < o.stop_ns):
                raise ValueError(f"invalid observation interval for {o.task_id}")


@dataclass(frozen=True, slots=True)
class OwnTask:
    """A task this agent can observe, with its own predicted slot and data volume."""

    task_id: str
    priority: int
    start_ns: int
    stop_ns: int
    data_mb: float


@dataclass(frozen=True, slots=True)
class CatalogUplink:
    """Predicted task catalogue for decentralized allocation (B2/B3), this agent's view.

    ``task_order`` lists every task ID (shared order, used for tie-breaking and
    message vectors); ``own`` holds only the tasks this agent can observe.
    """

    t_ns: int
    algorithm: str
    task_order: tuple[str, ...]
    own: tuple[OwnTask, ...]
    storage_capacity_mb: float

    def __post_init__(self) -> None:
        known = set(self.task_order)
        if len(known) != len(self.task_order):
            raise ValueError("task_order has duplicates")
        for t in self.own:
            if t.task_id not in known or not (0 <= t.start_ns < t.stop_ns):
                raise ValueError(f"invalid own task {t.task_id!r}")


@dataclass(frozen=True, slots=True)
class GroundNotice:
    """Explicit ground confirmation that spacecraft have failed (DL-052): the only
    evidence that can make an agent believe CONFIRMED_FAILED."""

    t_ns: int
    confirmed_failed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublicSlot:
    spacecraft: str
    start_ns: int
    stop_ns: int


@dataclass(frozen=True, slots=True)
class PublicTask:
    """B4: a task with every spacecraft's predicted slot and the planned owner."""

    task_id: str
    priority: int
    owner: str | None
    slots: tuple[PublicSlot, ...]
    data_mb: float


@dataclass(frozen=True, slots=True)
class RiskForecast:
    """Own predicted risks, each a ratio to its subsystem's modelled tolerance (1.0 = at
    the limit): radiation/electronics, navigation/communications, orbital disturbance.
    ``None`` = missing or invalid, which is never zero risk (DL-054, DL-056)."""

    t_ns: int
    radiation: float | None
    navcomms: float | None
    orbital: float | None

    def __post_init__(self) -> None:
        for r in (self.radiation, self.navcomms, self.orbital):
            if r is not None and not (math.isfinite(r) and r >= 0.0):
                raise ValueError("risk ratios must be finite and >= 0, or None")

    def as_mapping(self) -> dict[str, float | None]:
        return {"radiation": self.radiation, "navcomms": self.navcomms, "orbital": self.orbital}

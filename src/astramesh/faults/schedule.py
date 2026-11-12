"""Deterministic fault schedule: the simulator's ground truth (spec §5.4, DL-050).

Fault types and their *truth* effects while active (``start_ns <= t < end_ns``):

``unavailable``
    The spacecraft is completely unavailable: its agent is not stepped, sends
    nothing, receives nothing, gets no sensor packets, and its payload is off.
    It remains a physical object on its orbit (the trajectory is unchanged).
``comms_outage``
    The spacecraft's radio is off: it neither sends nor receives crosslink
    messages. Its agent still runs and executes its plan.
``partition``
    Crosslinks between the listed groups are cut (e.g. 2 + 2). Links inside a
    group are unaffected. Spacecraft not listed form an implicit extra group.
``payload_degraded``
    The payload produces no valid science: observations still use energy and
    storage, but are scored ``invalid_payload``. The agent is not told.
``power_degraded``
    Solar generation is multiplied by ``severity_fraction`` (0 = no power).
    The agent sees the consequence only in its own housekeeping (battery).
``critical_fault``
    A critical local subsystem fault (thermal/attitude abstraction): the
    spacecraft's *own* housekeeping carries a critical flag while it is active,
    which drives its supervisor to SAFE (DL-054).
``forecast_outage``
    No environment input (risk forecast and indices) reaches the spacecraft: a
    missed uplink, with no ground-station model (DL-090). Peer messages are
    unaffected.
``forecast_delay``
    Environment inputs reach the spacecraft ``delay_ns`` later than nominal.

Agents learn of faults only through effects (missing messages, housekeeping),
never from this module (enforced by the agent import rule).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

FAULT_TYPES = (
    "unavailable",
    "comms_outage",
    "partition",
    "payload_degraded",
    "power_degraded",
    "critical_fault",
    "forecast_outage",
    "forecast_delay",
)


@dataclass(frozen=True, slots=True)
class Fault:
    fault_id: str
    fault_type: str
    spacecraft: tuple[str, ...]  # affected spacecraft (all members, for partitions)
    groups: tuple[tuple[str, ...], ...]  # partition groups; empty otherwise
    start_ns: int
    end_ns: int | None  # None = permanent
    severity_fraction: float  # power: remaining generation fraction; else 1.0
    cause: str
    observability: str
    recoverable: bool
    consequences: str
    ground_confirmation_ns: int | None = None  # ground notice to all agents (DL-052)
    delay_ns: int = 0  # forecast_delay only (DL-090)

    def active(self, t_ns: int) -> bool:
        return self.start_ns <= t_ns and (self.end_ns is None or t_ns < self.end_ns)

    def record(self) -> dict[str, Any]:
        return {
            "fault_id": self.fault_id,
            "type": self.fault_type,
            "spacecraft": list(self.spacecraft),
            "groups": [list(g) for g in self.groups],
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
            "severity_fraction": self.severity_fraction,
            "cause": self.cause,
            "observability": self.observability,
            "recoverable": self.recoverable,
            "consequences": self.consequences,
            "ground_confirmation_ns": self.ground_confirmation_ns,
            **({"delay_ns": self.delay_ns} if self.fault_type == "forecast_delay" else {}),
        }


class FaultSchedule:
    """Query interface used by the simulator at every tick and message event."""

    def __init__(self, faults: Iterable[Fault], spacecraft: list[str]) -> None:
        self.faults = tuple(sorted(faults, key=lambda f: (f.start_ns, f.fault_id)))
        self.spacecraft = list(spacecraft)
        known = set(spacecraft)
        for f in self.faults:
            if (f.fault_type == "forecast_delay") != (f.delay_ns > 0):
                raise ValueError(f"{f.fault_id}: delay_ns > 0 for, and only for, forecast_delay")
            if f.fault_type not in FAULT_TYPES:
                raise ValueError(f"{f.fault_id}: unknown fault type {f.fault_type!r}")
            unknown = set(f.spacecraft) - known
            if unknown:
                raise ValueError(f"{f.fault_id}: unknown spacecraft {sorted(unknown)}")

    def __bool__(self) -> bool:
        return bool(self.faults)

    def _active(self, kind: str, t_ns: int) -> list[Fault]:
        return [f for f in self.faults if f.fault_type == kind and f.active(t_ns)]

    def unavailable(self, sc: str, t_ns: int) -> bool:
        return any(sc in f.spacecraft for f in self._active("unavailable", t_ns))

    def radio_up(self, sc: str, t_ns: int) -> bool:
        if self.unavailable(sc, t_ns):
            return False
        return not any(sc in f.spacecraft for f in self._active("comms_outage", t_ns))

    def link_cut(self, a: str, b: str, t_ns: int) -> bool:
        """True if an active partition separates a and b."""
        for f in self._active("partition", t_ns):
            ga = next((i for i, g in enumerate(f.groups) if a in g), -1)
            gb = next((i for i, g in enumerate(f.groups) if b in g), -1)
            if ga != gb:
                return True
        return False

    def ground_notices(self, t_ns: int) -> tuple[str, ...]:
        """Spacecraft whose failure the ground confirms exactly at ``t_ns``."""
        return tuple(sorted({sc for f in self.faults if f.ground_confirmation_ns == t_ns
                             for sc in f.spacecraft}))  # fmt: skip

    def critical_flags(self, sc: str, t_ns: int) -> tuple[str, ...]:
        return tuple(f.fault_id for f in self._active("critical_fault", t_ns) if sc in f.spacecraft)

    def payload_valid(self, sc: str, t_ns: int) -> bool:
        return not any(sc in f.spacecraft for f in self._active("payload_degraded", t_ns))

    def generation_factor(self, sc: str, t_ns: int) -> float:
        factor = 1.0
        for f in self._active("power_degraded", t_ns):
            if sc in f.spacecraft:
                factor = min(factor, f.severity_fraction)
        return factor

    def forecast_delivered(self, sc: str, t_ns: int) -> bool:
        """False while a forecast_outage covers ``sc`` (or it is unavailable)."""
        if self.unavailable(sc, t_ns):
            return False
        return not any(sc in f.spacecraft for f in self._active("forecast_outage", t_ns))

    def forecast_delay_ns(self, sc: str, t_ns: int) -> int:
        """Extra delivery latency of environment inputs for ``sc`` at ``t_ns``."""
        return max((f.delay_ns for f in self._active("forecast_delay", t_ns)
                    if sc in f.spacecraft), default=0)  # fmt: skip

    def transitions(self, end_ns: int) -> list[tuple[int, str, Fault]]:
        """(time, 'fault_started' | 'fault_ended', fault) within [0, end_ns], time-ordered."""
        out: list[tuple[int, str, Fault]] = []
        for f in self.faults:
            if f.start_ns <= end_ns:
                out.append((f.start_ns, "fault_started", f))
            if f.end_ns is not None and f.end_ns <= end_ns:
                out.append((f.end_ns, "fault_ended", f))
        return sorted(out, key=lambda x: (x[0], x[1] != "fault_ended", x[2].fault_id))

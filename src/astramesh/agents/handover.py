"""Handover policy slot (DL-079, DL-094): when a spacecraft announces a forecast
protection window and releases its own tasks inside it.

The agent calls its policy once per step with local observations only (own risk input,
own mode and plan, windows heard from peers). The policy never touches the supervisor:
it can release or decline tasks, not change a mode (spec §6.1, Gate P3).

* ``None`` (no policy) is the reactive baseline: tasks move only when protection starts.
* :class:`ForecastWindowRule` is the DL-078 candidate: while the own radiation ratio is
  at or above ``threshold_ratio``, or the spacecraft is PROTECTIVE or RECOVERY, it
  announces the window [now, now + lead] and releases its tasks starting inside it.
* RL policies (increment 4b) implement the same ``decide`` method.

Standard library only (agent isolation rule).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from astramesh.agents.packets import PlannedObservation

PROTECTED_MODES = frozenset({"PROTECTIVE", "RECOVERY"})


@dataclass(frozen=True, slots=True)
class HandoverObservation:
    now_ns: int
    radiation_ratio: float | None  # own option A input; None = invalid or expired
    mode: str
    planned: tuple[PlannedObservation, ...]
    peer_windows: Mapping[str, int]  # announced window ends heard from peers [ns]


@dataclass(frozen=True, slots=True)
class HandoverAction:
    window_end_ns: int | None = None  # announce [now, end) and release tasks starting in it


class HandoverPolicy(Protocol):
    def decide(self, obs: HandoverObservation) -> HandoverAction: ...


@dataclass(frozen=True, slots=True)
class ForecastWindowRule:
    threshold_ratio: float
    lead_ns: int

    def __post_init__(self) -> None:
        if not self.threshold_ratio > 0.0:
            raise ValueError("threshold_ratio must be > 0")
        if self.lead_ns <= 0:
            raise ValueError("lead_ns must be > 0")

    def decide(self, obs: HandoverObservation) -> HandoverAction:
        r = obs.radiation_ratio
        if obs.mode in PROTECTED_MODES or (r is not None and r >= self.threshold_ratio):
            return HandoverAction(obs.now_ns + self.lead_ns)
        return HandoverAction()

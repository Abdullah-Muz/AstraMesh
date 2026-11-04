"""Plan data types shared by every allocation method."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Assignment:
    """Spacecraft ``spacecraft`` observes ``task_id`` during ticks [start_tick, stop_tick)."""

    task_id: str
    spacecraft: str
    start_tick: int
    stop_tick: int


@dataclass(frozen=True, slots=True)
class Plan:
    algorithm: str
    version: int
    assignments: tuple[Assignment, ...]
    unassigned: tuple[str, ...]  # task IDs no spacecraft could take
    privileged_information: bool  # True for references that use truth (B1)
    excluded: tuple[str, ...] = ()  # (task@spacecraft) options a planner ruled out, e.g. energy

    def for_spacecraft(self, spacecraft: str) -> tuple[Assignment, ...]:
        return tuple(a for a in self.assignments if a.spacecraft == spacecraft)

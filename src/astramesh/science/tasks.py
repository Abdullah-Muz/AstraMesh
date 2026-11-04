"""Task catalogue and observation slots (spec §3.4, DL-041).

A *task* is one science opportunity (one formation pass over one region) with
the access window of every eligible spacecraft. The catalogue is a
**prediction** made before the run (from the initial states and the planned
attitude-free geometry), the way a ground segment would uplink it; in the
nominal scenario nothing manoeuvres, so it coincides with truth geometry.

Observation slot
    An observation is ``n`` consecutive simulation steps [t_k, t_{k+1}) with
    the payload on. A step uses the state at its left tick, so a slot of
    ticks ``start .. start+n-1`` is inside a window when all of those ticks
    are access ticks. The slot is centred on the window's peak-elevation tick
    and shifted to fit inside the window. Windows shorter than ``n`` ticks, or
    that would need a step after the final tick, cannot hold an observation.

Utility (DL-041): U = sum over completed tasks of w_j * q_j with q_j = 1;
a task is completed by the first valid observation, later ones are duplicates.
"""

from __future__ import annotations

from dataclasses import dataclass

from astramesh.science.opportunities import Opportunity


@dataclass(frozen=True, slots=True)
class TaskWindow:
    spacecraft: str
    first_tick: int
    last_tick: int
    peak_tick: int


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    region_id: str
    priority: int
    windows: tuple[TaskWindow, ...]

    def window_of(self, spacecraft: str) -> TaskWindow | None:
        for w in self.windows:
            if w.spacecraft == spacecraft:
                return w
        return None


def catalog_from_opportunities(opportunities: list[Opportunity]) -> tuple[Task, ...]:
    return tuple(
        Task(
            task_id=o.task_id,
            region_id=o.region.region_id,
            priority=o.region.priority,
            windows=tuple(
                TaskWindow(e.spacecraft, e.window.first, e.window.last, e.window.peak)
                for e in o.eligible
            ),
        )
        for o in opportunities
    )


def observation_slot(window: TaskWindow, n_steps: int, n_ticks: int) -> tuple[int, int] | None:
    """Ticks ``(start, stop)`` (stop exclusive) of an n-step observation, or None.

    ``n_ticks`` is the number of ticks in the scenario (the last tick has no step).
    """
    if n_steps <= 0:
        raise ValueError("n_steps must be positive")
    last_usable = min(window.last_tick, n_ticks - 2)
    if last_usable - window.first_tick + 1 < n_steps:
        return None
    start = window.peak_tick - n_steps // 2
    start = max(window.first_tick, min(start, last_usable - n_steps + 1))
    return start, start + n_steps


def slots_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]

"""B0: static, no-replanning scheduler (spec §9.1).

Made once, before the run, from the predicted task catalogue only, and never
revised. Greedy in a fixed order:

1. Tasks by decreasing priority, then earliest window start, then task ID.
2. For each task, candidate spacecraft in order of fewest assignments so far,
   then spacecraft ID (spreads work across the formation deterministically).
3. A candidate is accepted if its own window holds an observation slot
   (``science.tasks.observation_slot``), the slot does not overlap that
   spacecraft's earlier slots (one task at a time), and the predicted data
   still fits in storage.

Energy is not predicted by B0: the executing agent refuses to start an
observation when its believed battery is below the reserve (DL-043), so an
energy-infeasible plan shows up as skipped observations, not hidden.
"""

from __future__ import annotations

from astramesh.planning.plans import Assignment, Plan
from astramesh.science.tasks import Task, observation_slot, slots_overlap

ALGORITHM = "B0-static-greedy"


def plan_static(
    catalog: tuple[Task, ...],
    spacecraft: list[str],
    *,
    n_steps: int,
    n_ticks: int,
    storage_capacity_mb: float,
    data_mb_per_step: float,
) -> Plan:
    order = sorted(
        catalog,
        key=lambda t: (-t.priority, min(w.first_tick for w in t.windows), t.task_id),
    )
    slots: dict[str, list[tuple[int, int]]] = {s: [] for s in spacecraft}
    storage = dict.fromkeys(spacecraft, 0.0)
    assigned: list[Assignment] = []
    unassigned: list[str] = []
    need_mb = n_steps * data_mb_per_step
    for task in order:
        for sc in sorted(spacecraft, key=lambda s: (len(slots[s]), s)):
            window = task.window_of(sc)
            if window is None:
                continue
            slot = observation_slot(window, n_steps, n_ticks)
            if slot is None or any(slots_overlap(slot, o) for o in slots[sc]):
                continue
            if storage[sc] + need_mb > storage_capacity_mb:
                continue
            slots[sc].append(slot)
            storage[sc] += need_mb
            assigned.append(Assignment(task.task_id, sc, slot[0], slot[1]))
            break
        else:
            unassigned.append(task.task_id)
    assigned.sort(key=lambda a: (a.start_tick, a.spacecraft, a.task_id))
    return Plan(ALGORITHM, 1, tuple(assigned), tuple(sorted(unassigned)), False)

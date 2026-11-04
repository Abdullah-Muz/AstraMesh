"""B1: centralized, information-rich reference allocation (spec §9.1, DL-042).

**Privileged information (disclosed):** B1 uses truth illumination (sunlit at
every tick) and every spacecraft's resource parameters to check energy. It is a
comparative reference bound, not a deployable decentralized method.

Formulation (binary integer program, solved with SciPy ``milp``/HiGHS):

* one variable x_v per feasible (task, spacecraft) pair, where the spacecraft's
  own window holds the centred observation slot (DL-043; same slots as B0, so
  B1 differs only in *which* spacecraft does *which* task);
* maximise sum_v w_task(v) x_v (w = priority; q = 1, DL-041);
* each task at most once; on each spacecraft, overlapping slots exclusive;
  total data per spacecraft within storage.

Energy (lazy constraints): after a solve, every spacecraft's battery is
simulated under the plan with truth illumination (``resources.ledgers.Battery``,
same rules as execution). The first observation per spacecraft that would start
below the battery reserve or could not be supplied is forbidden (x_v = 0) and
the problem is solved again, until the plan is energy-feasible.

Unique answer (cross-CPU determinism): after the optimal value V* is known,
variables are visited in a fixed order (slot start, task ID, spacecraft ID)
and fixed to 1 if that still admits an assignment of value V*, else to 0. The
result is the lexicographically first optimal plan, whichever optimal vertex
the solver happened to find.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import Bounds, LinearConstraint, milp

from astramesh.planning.plans import Assignment, Plan
from astramesh.resources.ledgers import Battery
from astramesh.science.tasks import Task, observation_slot, slots_overlap

ALGORITHM = "B1-centralized-milp"


@dataclass(frozen=True, slots=True)
class EnergyModel:
    sunlit: NDArray[np.bool_]  # (n_ticks, n_sc) truth illumination (privileged)
    step_s: float
    capacity_wh: float
    initial_fraction: float
    charge_efficiency: float
    generation_w: float
    bus_w: float
    payload_w: float
    reserve_fraction: float


@dataclass(frozen=True, slots=True)
class _Var:
    task: Task
    spacecraft: str
    slot: tuple[int, int]


class B1Error(RuntimeError):
    """Raised if the solver fails (reported, never silently replaced by a heuristic)."""


def _solve(
    c: NDArray[np.float64],
    a: NDArray[np.float64],
    ub: NDArray[np.float64],
    lo: NDArray[np.float64],
    hi: NDArray[np.float64],
) -> NDArray[np.float64] | None:
    n = len(c)
    res = milp(
        c=-c,
        constraints=[LinearConstraint(a, -np.inf, ub)] if len(ub) else [],
        integrality=np.ones(n),
        bounds=Bounds(lo, hi),
    )
    if res.status == 2:  # infeasible
        return None
    if res.status != 0 or res.x is None:
        raise B1Error(f"milp failed: status {res.status}: {res.message}")
    out: NDArray[np.float64] = np.round(np.asarray(res.x, dtype=np.float64))
    return out


def _energy_violation(plan: list[_Var], ids: list[str], energy: EnergyModel,
                      n_ticks: int) -> list[_Var]:  # fmt: skip
    """First energy-infeasible observation per spacecraft under ``plan`` (truth illumination)."""
    bad: list[_Var] = []
    for j, sc in enumerate(ids):
        mine = sorted((v for v in plan if v.spacecraft == sc), key=lambda v: v.slot)
        on = np.zeros(n_ticks, dtype=bool)
        start_of = {}
        for v in mine:
            on[v.slot[0] : v.slot[1]] = True
            start_of[v.slot[0]] = v
        bat = Battery(energy.capacity_wh, energy.initial_fraction, energy.charge_efficiency)
        current: _Var | None = None
        for k in range(n_ticks - 1):
            if k in start_of:
                current = start_of[k]
                if bat.stored_wh < energy.reserve_fraction * energy.capacity_wh:
                    bad.append(current)
                    break
            gen = energy.generation_w if bool(energy.sunlit[k, j]) else 0.0
            load = energy.bus_w + (energy.payload_w if on[k] else 0.0)
            if not bat.step(gen, load, energy.step_s) and on[k] and current is not None:
                bad.append(current)
                break
    return bad


def plan_centralized(
    catalog: tuple[Task, ...],
    spacecraft: list[str],
    *,
    n_steps: int,
    n_ticks: int,
    storage_capacity_mb: float,
    data_mb_per_step: float,
    energy: EnergyModel,
    max_rounds: int = 200,
) -> Plan:
    variables: list[_Var] = []
    for task in catalog:
        for sc in spacecraft:
            w = task.window_of(sc)
            slot = observation_slot(w, n_steps, n_ticks) if w is not None else None
            if slot is not None:
                variables.append(_Var(task, sc, slot))
    variables.sort(key=lambda v: (v.slot[0], v.task.task_id, v.spacecraft))
    n = len(variables)
    if n == 0:
        return Plan(ALGORITHM, 1, (), tuple(sorted(t.task_id for t in catalog)), True, ())
    c = np.array([float(v.task.priority) for v in variables])

    rows: list[NDArray[np.float64]] = []
    ub: list[float] = []
    for task in catalog:  # each task at most once
        row = np.array([1.0 if v.task is task else 0.0 for v in variables])
        if row.sum() > 1:
            rows.append(row)
            ub.append(1.0)
    for i in range(n):  # one task at a time per spacecraft
        for k in range(i + 1, n):
            vi, vk = variables[i], variables[k]
            if vi.spacecraft == vk.spacecraft and slots_overlap(vi.slot, vk.slot):
                row = np.zeros(n)
                row[i] = row[k] = 1.0
                rows.append(row)
                ub.append(1.0)
    need = n_steps * data_mb_per_step
    for sc in spacecraft:  # storage
        rows.append(np.array([need if v.spacecraft == sc else 0.0 for v in variables]))
        ub.append(storage_capacity_mb)
    a = np.vstack(rows)
    ubv = np.array(ub)
    lo, hi = np.zeros(n), np.ones(n)

    excluded: list[str] = []
    for _ in range(max_rounds):
        lo = np.zeros(n)
        x = _solve(c, a, ubv, lo, hi)
        if x is None:  # pragma: no cover - x = 0 is always feasible
            raise B1Error("relaxed problem infeasible")
        # Lexicographic tie-break: fix variables in order, keeping the optimal value.
        best = float(c @ x)
        a_obj = np.vstack([a, -c])
        ub_obj = np.append(ubv, -(best - 0.5))
        fixed_hi = hi.copy()
        for i in range(n):
            if fixed_hi[i] == 0.0:
                continue
            lo[i] = 1.0
            if _solve(c, a_obj, ub_obj, lo, fixed_hi) is None:
                lo[i] = fixed_hi[i] = 0.0
        chosen = [v for v, xi in zip(variables, lo, strict=True) if xi > 0.5]
        bad = _energy_violation(chosen, spacecraft, energy, n_ticks)
        if not bad:
            break
        for v in bad:  # lazy energy constraints
            hi[variables.index(v)] = 0.0
            excluded.append(f"{v.task.task_id}@{v.spacecraft}")
    else:
        raise B1Error(f"energy feasibility not reached in {max_rounds} rounds")

    assigned = sorted(
        (Assignment(v.task.task_id, v.spacecraft, v.slot[0], v.slot[1]) for v in chosen),
        key=lambda a_: (a_.start_tick, a_.spacecraft, a_.task_id),
    )
    done = {a_.task_id for a_ in assigned}
    unassigned = tuple(sorted(t.task_id for t in catalog if t.task_id not in done))
    return Plan(ALGORITHM, 1, tuple(assigned), unassigned, True, tuple(excluded))

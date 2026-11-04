"""Phase 2 S00: nominal science operations with isolated agents (increment 2a: B0).

Truth (simulator) side:

* formation dynamics, illumination and the task catalogue (as in ``mission_geometry``);
* one battery and one data store per spacecraft, stepped every tick from the
  payload state the agent commands (``resources.ledgers.Battery``);
* observation segments: maximal runs of steps a spacecraft spends on one task,
  closed when the command changes; a segment is *aborted* if the battery could
  not supply the load or storage overflowed during it.

Agent side (via :class:`~astramesh.scenarios.kernel.AgentKernel`): navigation
fixes, own housekeeping every tick, the plan uplink at t = 0 (its own part
only), status messages over the crosslink network, and ``payload_command``.

Scoring (DL-041): a segment is a *valid observation* of its task if it was not
aborted, lasted at least ``min_observation_s``, and every step lies inside the
observing spacecraft's own access window. The first valid observation
completes the task (utility += priority, q = 1); later valid ones are
duplicates. Evaluation uses truth; agents never see it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from astramesh.agents.agent import AgentSettings, SpacecraftAgent
from astramesh.agents.packets import Housekeeping, PlannedObservation, PlanUplink
from astramesh.core.clock import seconds_to_ns
from astramesh.core.config import NominalOperationsScenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.planning.centralized_b1 import EnergyModel, plan_centralized
from astramesh.planning.plans import Plan
from astramesh.planning.static_b0 import plan_static
from astramesh.resources.ledgers import Battery, data_volume_mb
from astramesh.scenarios.agent_network import make_kernel
from astramesh.scenarios.formation_dynamics import (
    FormationRun,
    record_scenario_end,
    run_formation_dynamics,
    spacecraft_ids,
)
from astramesh.scenarios.mission_geometry import geometry_products
from astramesh.science.tasks import Task, catalog_from_opportunities

PLAN_FILE = "plan.json"
OBSERVATIONS_FILE = "observations.json"


@dataclass(slots=True)
class Segment:
    spacecraft: str
    task_id: str
    start_tick: int
    stop_tick: int = -1  # exclusive
    aborted: str | None = None  # "power" | "storage"
    valid: bool = False
    outcome: str = "open"

    def to_dict(self, step_ns: int) -> dict[str, Any]:
        return {
            "spacecraft": self.spacecraft,
            "task": self.task_id,
            "start_t_ns": self.start_tick * step_ns,
            "stop_t_ns": self.stop_tick * step_ns,
            "steps": self.stop_tick - self.start_tick,
            "aborted": self.aborted,
            "outcome": self.outcome,
        }


@dataclass(frozen=True, slots=True)
class OperationsRun:
    formation: FormationRun
    plan: Plan
    catalog: tuple[Task, ...]
    segments: list[Segment]
    trace: list[dict[str, Any]]
    summary: dict[str, Any]
    agents: dict[str, SpacecraftAgent] = field(default_factory=dict)


def _plan(
    config: NominalOperationsScenario,
    catalog: tuple[Task, ...],
    ids: list[str],
    sunlit: NDArray[np.bool_],
    n_steps: int,
    n_ticks: int,
    mb_per_step: float,
) -> Plan:
    sc = config.spacecraft
    common = {
        "n_steps": n_steps,
        "n_ticks": n_ticks,
        "storage_capacity_mb": sc.storage_capacity_mb,
        "data_mb_per_step": mb_per_step,
    }
    if config.operations.algorithm == "static_b0":
        return plan_static(catalog, ids, **common)  # type: ignore[arg-type]
    if config.operations.algorithm == "centralized_b1":
        energy = EnergyModel(
            sunlit=sunlit,
            step_s=config.time.time_step_s,
            capacity_wh=sc.battery_capacity_wh,
            initial_fraction=sc.battery_initial_fraction,
            charge_efficiency=sc.charge_efficiency_fraction,
            generation_w=sc.solar_generation_w,
            bus_w=sc.bus_power_w,
            payload_w=sc.payload_power_w,
            reserve_fraction=config.operations.battery_reserve_fraction,
        )
        return plan_centralized(catalog, ids, energy=energy, **common)  # type: ignore[arg-type]
    raise ValueError(f"unknown algorithm {config.operations.algorithm!r}")  # pragma: no cover


def plan_to_dict(plan: Plan, step_ns: int) -> dict[str, Any]:
    return {
        "algorithm": plan.algorithm,
        "version": plan.version,
        "privileged_information": plan.privileged_information,
        "assignments": [
            {
                "task": a.task_id,
                "spacecraft": a.spacecraft,
                "start_t_ns": a.start_tick * step_ns,
                "stop_t_ns": a.stop_tick * step_ns,
            }
            for a in plan.assignments
        ],
        "unassigned": list(plan.unassigned),
        "excluded": list(plan.excluded),
    }


def run_nominal_operations(
    config: NominalOperationsScenario, streams: RandomStreams, log: EventLog
) -> OperationsRun:
    formation = run_formation_dynamics(config, log, end_event=False)
    geo = geometry_products(config, formation)
    traj = formation.trajectory
    spec = config.time.clock_spec()
    step_ns, step_s = spec.step_ns, config.time.time_step_s
    n_ticks = len(traj.t_ns)
    ids = spacecraft_ids(traj.n_spacecraft)
    sc = config.spacecraft
    n_steps = seconds_to_ns(config.operations.min_observation_s) // step_ns
    mb_per_step = data_volume_mb(1, step_s, sc.payload_data_rate_kbps)
    catalog = catalog_from_opportunities(geo.opportunities)
    by_id = {t.task_id: t for t in catalog}

    plan = _plan(config, catalog, ids, geo.sunlit, n_steps, n_ticks, mb_per_step)
    log.record(tick=0, time_ns=0, source="planner", kind="plan_made",
               data={"algorithm": plan.algorithm, "version": plan.version,
                     "privileged_information": plan.privileged_information,
                     "n_tasks": len(catalog), "n_assigned": len(plan.assignments),
                     "unassigned": list(plan.unassigned),
                     "excluded": list(plan.excluded)})  # fmt: skip

    settings = AgentSettings(
        status_interval_ns=seconds_to_ns(config.agents.status_interval_s),
        status_lifetime_ns=seconds_to_ns(config.agents.status_lifetime_s),
        battery_reserve_fraction=config.operations.battery_reserve_fraction,
    )
    agents = {a: SpacecraftAgent(a, tuple(p for p in ids if p != a), settings) for a in ids}
    for a in ids:
        agents[a].observe(PlanUplink(
            t_ns=0, algorithm=plan.algorithm, version=plan.version,
            observations=tuple(PlannedObservation(x.task_id, x.start_tick * step_ns,
                                                  x.stop_tick * step_ns)
                               for x in plan.for_spacecraft(a)),
        ))  # fmt: skip

    batteries = {a: Battery(sc.battery_capacity_wh, sc.battery_initial_fraction,
                            sc.charge_efficiency_fraction) for a in ids}  # fmt: skip
    storage = dict.fromkeys(ids, 0.0)
    min_wh = {a: batteries[a].stored_wh for a in ids}
    active: dict[str, Segment] = {}
    segments: list[Segment] = []
    kernel = make_kernel(config, formation, agents, streams, log)

    def close(a: str, k: int) -> None:
        seg = active.pop(a)
        seg.stop_tick = k
        segments.append(seg)
        kernel.record(k * step_ns, "sim", "observation_stopped",
                      {"spacecraft": a, "task": seg.task_id, "steps": k - seg.start_tick,
                       "aborted": seg.aborted})  # fmt: skip

    def hook(k: int, t: int) -> None:
        for j, a in enumerate(ids):
            bat = batteries[a]
            agents[a].observe(Housekeeping(t, bat.stored_wh, sc.battery_capacity_wh,
                                           storage[a], sc.storage_capacity_mb))  # fmt: skip
            if k == n_ticks - 1:
                continue  # no step after the final tick
            cmd = agents[a].payload_command(t, step_ns, mb_per_step)
            if a in active and active[a].task_id != cmd:
                close(a, k)
            if cmd is not None and a not in active:
                if cmd not in by_id:
                    raise RuntimeError(f"{a} commanded unknown task {cmd!r}")
                active[a] = Segment(a, cmd, k)
                kernel.record(t, "sim", "observation_started", {"spacecraft": a, "task": cmd})
            gen = sc.solar_generation_w if bool(geo.sunlit[k, j]) else 0.0
            load = sc.bus_power_w + (sc.payload_power_w if cmd is not None else 0.0)
            supplied = bat.step(gen, load, step_s)
            min_wh[a] = min(min_wh[a], bat.stored_wh)
            if cmd is not None:
                seg = active[a]
                storage[a] += mb_per_step
                if storage[a] > sc.storage_capacity_mb:
                    storage[a] = sc.storage_capacity_mb
                    seg.aborted = seg.aborted or "storage"
                if not supplied:
                    seg.aborted = seg.aborted or "power"

    kernel.run(tick_hook=hook)
    for a in sorted(active):
        close(a, n_ticks - 1)
    record_scenario_end(config, log)

    completed: dict[str, Segment] = {}
    for seg in sorted(segments, key=lambda s: (s.stop_tick, s.spacecraft)):
        w = by_id[seg.task_id].window_of(seg.spacecraft)
        inside = (
            w is not None and w.first_tick <= seg.start_tick and seg.stop_tick - 1 <= w.last_tick
        )
        seg.valid = seg.aborted is None and inside and seg.stop_tick - seg.start_tick >= n_steps
        if not seg.valid:
            seg.outcome = "invalid" if seg.aborted is None else f"aborted_{seg.aborted}"
        elif seg.task_id in completed:
            seg.outcome = "duplicate"
        else:
            seg.outcome = "completed"
            completed[seg.task_id] = seg
    segments.sort(key=lambda s: (s.start_tick, s.spacecraft))

    utility = sum(by_id[t].priority for t in completed)
    summary = dict(formation.summary)
    summary.update({
        "operations": {
            "algorithm": plan.algorithm,
            "privileged_information": plan.privileged_information,
            "utility": utility,
            "utility_all_tasks": sum(t.priority for t in catalog),
            "n_tasks": len(catalog),
            "n_completed": len(completed),
            "n_duplicates": sum(1 for s in segments if s.outcome == "duplicate"),
            "n_aborted": sum(1 for s in segments if s.aborted is not None),
            "n_invalid": sum(1 for s in segments if s.outcome == "invalid"),
            "n_assigned": len(plan.assignments),
            "unassigned": list(plan.unassigned),
            "declined": {a: agents[a].execution_view()["declined"] for a in ids},
            "min_battery_wh": min_wh,
            "final_battery_wh": {a: batteries[a].stored_wh for a in ids},
            "deficit_steps": {a: batteries[a].deficit_steps for a in ids},
            "storage_used_mb": storage,
            "note": "q_j = 1 (DL-041); utility counts each task once",
        },
        "network": kernel.network_summary(),
        **kernel.agents_summary(),
    })  # fmt: skip
    return OperationsRun(formation, plan, catalog, segments, kernel.trace, summary, agents)

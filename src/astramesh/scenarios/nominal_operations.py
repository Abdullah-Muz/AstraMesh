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

import itertools
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from astramesh.agents.agent import AgentSettings, SpacecraftAgent
from astramesh.agents.handover import ForecastWindowRule
from astramesh.agents.health import (
    AVAILABLE_BELIEFS,
    CONFIRMED,
    UNAVAILABLE_BELIEFS,
    PayloadSettings,
)
from astramesh.agents.packets import (
    CatalogUplink,
    GroundNotice,
    Housekeeping,
    OwnTask,
    PayloadCheck,
    PlannedObservation,
    PlanUplink,
    PublicSlot,
    PublicTask,
    RiskForecast,
)
from astramesh.agents.supervisor import (
    MODES,
    NOMINAL,
    PROTECTIVE,
    RECOVERY,
    SCIENCE_MODES,
    SupervisorSettings,
)
from astramesh.anomaly.adapter import ScoreSensor
from astramesh.core.clock import seconds_to_ns
from astramesh.core.config import NominalOperationsScenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.dynamics.geomagnetic import decimal_year, dipole_axis, invariant_latitude_deg
from astramesh.faults.schedule import Fault, FaultSchedule
from astramesh.forecast.access import CutoffModel, forward_window_max
from astramesh.forecast.replay import StormSeries
from astramesh.planning.centralized_b1 import EnergyModel, plan_centralized
from astramesh.planning.plans import Assignment, Plan
from astramesh.planning.static_b0 import plan_static
from astramesh.resources.ledgers import Battery, data_volume_mb
from astramesh.scenarios.agent_network import health_settings, make_kernel
from astramesh.scenarios.formation_dynamics import (
    FormationRun,
    record_scenario_end,
    run_formation_dynamics,
    spacecraft_ids,
)
from astramesh.scenarios.mission_geometry import geometry_products
from astramesh.science.tasks import Task, catalog_from_opportunities, observation_slot

DECENTRALIZED = {"auction_b2": "B2-auction", "cbba_b3": "B3-cbba",
                 "cbba_b3_timeout": "B3-cbba+timeout"}  # fmt: skip
B4_NAME = "B4-rule-redistribution"
PLAN_FILE = "plan.json"
OBSERVATIONS_FILE = "observations.json"


@dataclass(slots=True)
class Segment:
    spacecraft: str
    task_id: str
    start_tick: int
    stop_tick: int = -1  # exclusive
    aborted: str | None = None  # "power" | "storage"
    payload_invalid: bool = False  # a payload_degraded fault was active during a step
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
    if config.operations.algorithm in ("static_b0", "rule_b4"):
        plan = plan_static(catalog, ids, **common)  # type: ignore[arg-type]
        if config.operations.algorithm == "rule_b4":  # B4 starts from the B0 ground plan
            return Plan(B4_NAME, plan.version, plan.assignments, plan.unassigned, False)
        return plan
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


def fault_schedule(config: NominalOperationsScenario, ids: list[str]) -> FaultSchedule:
    def ns(s: float) -> int:
        return seconds_to_ns(s)

    return FaultSchedule(
        [
            Fault(
                fault_id=f.fault_id,
                fault_type=f.type,
                spacecraft=tuple(f.spacecraft) or tuple(m for g in f.groups for m in g),
                groups=tuple(tuple(g) for g in f.groups),
                start_ns=ns(f.start_s),
                end_ns=None if f.end_s is None else ns(f.end_s),
                severity_fraction=f.severity_fraction,
                cause=f.cause,
                observability=f.observability,
                recoverable=f.recoverable,
                consequences=f.consequences,
                ground_confirmation_ns=(
                    None if f.ground_confirmation_s is None else ns(f.ground_confirmation_s)
                ),
                delay_ns=0 if f.delay_s is None else ns(f.delay_s),
            )
            for f in config.faults
        ],
        ids,
    )


def _handover_policy(config: NominalOperationsScenario) -> ForecastWindowRule | None:
    ho = config.agents.handover
    if ho is None:
        return None
    return ForecastWindowRule(ho.window_threshold_ratio, seconds_to_ns(ho.lead_s))


def _forecast_max_age_ns(config: NominalOperationsScenario) -> int | None:
    rp = config.environment.replay if config.environment is not None else None
    age = rp.forecast_max_age_s if rp is not None else None
    return None if age is None else seconds_to_ns(age)


def supervisor_settings(config: NominalOperationsScenario) -> SupervisorSettings:
    sv = config.supervisor
    return SupervisorSettings(
        safe_battery_fraction=sv.safe_battery_fraction,
        safe_exit_battery_fraction=sv.safe_exit_battery_fraction,
        safe_exit_dwell_ns=seconds_to_ns(sv.safe_exit_dwell_s),
        protect_ratio=sv.protect_exposure_ratio,
        release_ratio=sv.release_exposure_ratio,
        release_dwell_ns=seconds_to_ns(sv.release_dwell_s),
        watch_ratio=sv.watch_enter_ratio,
        watch_release_ratio=sv.watch_release_ratio,
        watch_release_dwell_ns=seconds_to_ns(sv.watch_release_dwell_s),
        invalid_to_watch_ns=seconds_to_ns(sv.invalid_to_watch_s),
        recovery_min_dwell_ns=seconds_to_ns(sv.recovery_min_dwell_s),
    )


def risk_ratio(config: NominalOperationsScenario, sc: str, dim: str, t_ns: int) -> float | None:
    """Truth-side forecast service: scheduled ratio for ``sc``, dimension ``dim``, at ``t_ns``."""
    env = config.environment
    assert env is not None
    t_s = t_ns / 1e9
    for fc in env.forecasts:  # first matching interval wins (config order)
        if (fc.dimension == dim and (not fc.spacecraft or sc in fc.spacecraft)
                and fc.start_s <= t_s < fc.end_s):  # fmt: skip
            return fc.exposure_ratio
    return env.background_exposure_ratio


def _ratio(x: float | None, tol: float) -> float | None:
    return None if x is None else max(x, 0.0) / tol


def replay_risks(config: NominalOperationsScenario, series: StormSeries,
                 t_unix_ns: int, index: int = 0,
                 ) -> tuple[float | None, float | None, float | None]:  # fmt: skip
    """(radiation, navcomms, orbital) ratios at ``t`` from the S11 storm replay (DL-069):
    the chosen forecast over spacecraft ``index``'s radiation tolerance (DL-090), AE and
    -SYM-H over theirs. GOES is a GEO upper-bound proxy; position-based access, when
    configured, is applied by the caller."""
    rp = config.environment.replay if config.environment is not None else None
    assert rp is not None
    sym, ae = series.indices(t_unix_ns)
    return (_ratio(series.forecast(rp.forecast, t_unix_ns), rp.tolerance_pfu(index)),
            _ratio(ae, rp.navcomms_tolerance_nt),
            _ratio(None if sym is None else -sym, rp.orbital_tolerance_nt))  # fmt: skip


def run_nominal_operations(
    config: NominalOperationsScenario, streams: RandomStreams, log: EventLog
) -> OperationsRun:
    ids = spacecraft_ids(config.formation.n_spacecraft)
    faults = fault_schedule(config, ids)  # truth; also gates formation-keeping burns (DL-087)
    formation = run_formation_dynamics(config, log, end_event=False, faults=faults)
    geo = geometry_products(config, formation)
    traj = formation.trajectory
    spec = config.time.clock_spec()
    step_ns, step_s = spec.step_ns, config.time.time_step_s
    n_ticks = len(traj.t_ns)
    thrust_on = formation.keeping.thrust_on if formation.keeping is not None else None
    sc = config.spacecraft
    n_steps = seconds_to_ns(config.operations.min_observation_s) // step_ns
    mb_per_step = data_volume_mb(1, step_s, sc.payload_data_rate_kbps)
    catalog = catalog_from_opportunities(geo.opportunities)
    by_id = {t.task_id: t for t in catalog}

    algo = config.operations.algorithm
    decentralized = algo in DECENTRALIZED
    plan = (
        Plan(DECENTRALIZED[algo], 0, (), (), False)
        if decentralized
        else _plan(config, catalog, ids, geo.sunlit, n_steps, n_ticks, mb_per_step)
    )
    if not decentralized:
        log.record(tick=0, time_ns=0, source="planner", kind="plan_made",
               data={"algorithm": plan.algorithm, "version": plan.version,
                     "privileged_information": plan.privileged_information,
                     "n_tasks": len(catalog), "n_assigned": len(plan.assignments),
                     "unassigned": list(plan.unassigned),
                     "excluded": list(plan.excluded)})  # fmt: skip
    else:
        log.record(tick=0, time_ns=0, source="planner", kind="catalog_uplinked",
                   data={"algorithm": plan.algorithm, "n_tasks": len(catalog),
                         "note": "allocation decided by the agents"})  # fmt: skip

    pc = config.agents.health.payload_check if config.agents.health is not None else None
    sensor = None
    if pc is not None:
        sensor = ScoreSensor.load(
            pc.sensor_file, pc.sensor_sha256, pc.sensor_split, pc.nominal_contamination_fraction
        )
    payload_settings = (
        PayloadSettings(
            interval_ns=seconds_to_ns(pc.interval_s),
            mtbf_ns=seconds_to_ns(pc.mtbf_s),
            repair_ns=seconds_to_ns(pc.repair_s),
            train_prior=sensor.train_prior,
            degraded_p=pc.degraded_probability,
            clear_p=pc.clear_probability,
            clip=pc.clip_probability,
        )
        if pc is not None and sensor is not None
        else None
    )
    check_ns = payload_settings.interval_ns if payload_settings is not None else 0
    sensor_rng = streams.substream("sensors", "payload_check")  # unused unless H-C
    settings = AgentSettings(
        status_interval_ns=seconds_to_ns(config.agents.status_interval_s),
        status_lifetime_ns=seconds_to_ns(config.agents.status_lifetime_s),
        battery_reserve_fraction=config.operations.battery_reserve_fraction,
        health=health_settings(config),
        supervisor=supervisor_settings(config),
        watch_status_interval_ns=seconds_to_ns(config.supervisor.watch_status_interval_s),
        recovery_nav_max_age_ns=seconds_to_ns(config.supervisor.recovery_nav_max_age_s),
        recovery_peer_heard_ns=seconds_to_ns(config.supervisor.recovery_peer_heard_s),
        payload_check=payload_settings,
        forecast_max_age_ns=_forecast_max_age_ns(config),
        handover=_handover_policy(config),
        share_window=config.agents.handover is None or config.agents.handover.share_window,
    )
    agents = {a: SpacecraftAgent(a, tuple(p for p in ids if p != a), settings) for a in ids}
    for a in ids:
        if decentralized:
            own = []
            for t in catalog:
                w = t.window_of(a)
                slot = observation_slot(w, n_steps, n_ticks) if w is not None else None
                if slot is not None:
                    own.append(OwnTask(t.task_id, t.priority, slot[0] * step_ns,
                                       slot[1] * step_ns, n_steps * mb_per_step))  # fmt: skip
            agents[a].observe(CatalogUplink(0, plan.algorithm, tuple(t.task_id for t in catalog),
                                            tuple(own), sc.storage_capacity_mb))  # fmt: skip
            continue
        public: tuple[PublicTask, ...] = ()
        if algo == "rule_b4":
            owner = {x.task_id: x.spacecraft for x in plan.assignments}
            public = tuple(
                PublicTask(t.task_id, t.priority, owner.get(t.task_id), tuple(
                    PublicSlot(w.spacecraft, sl[0] * step_ns, sl[1] * step_ns)
                    for w in t.windows
                    if (sl := observation_slot(w, n_steps, n_ticks)) is not None
                ), n_steps * mb_per_step)
                for t in catalog
            )  # fmt: skip
        agents[a].observe(PlanUplink(
            t_ns=0, algorithm=plan.algorithm, version=plan.version,
            observations=tuple(PlannedObservation(x.task_id, x.start_tick * step_ns,
                                                  x.stop_tick * step_ns)
                               for x in plan.for_spacecraft(a)),
            public_tasks=public,
        ))  # fmt: skip

    batteries = {a: Battery(sc.battery_capacity_wh, sc.battery_initial_fraction,
                            sc.charge_efficiency_fraction) for a in ids}  # fmt: skip
    storage = dict.fromkeys(ids, 0.0)
    min_wh = {a: batteries[a].stored_wh for a in ids}
    protection_violations = dict.fromkeys(ids, 0)
    rp = config.environment.replay if config.environment is not None else None
    series = StormSeries.load(rp.series_file, rp.series_sha256) if rp is not None else None
    epoch_unix_ns = int(config.time.epoch_utc.timestamp()) * 10**9
    storm = {k: dict.fromkeys(ids, 0.0) for k in
             ("hazard_s", "exposed_s", "protected_in_hazard_s", "protected_outside_hazard_s",
              "no_truth_s")}  # fmt: skip
    acc = rp.access if rp is not None else None
    cutoff = track_max = in_access = None
    if acc is not None and series is not None:  # DL-090 option A, values DL-091
        cutoff = CutoffModel(acc.quiet_cutoff_deg, acc.storm_slope_deg_per_nt, acc.max_shift_deg)
        lam = invariant_latitude_deg(geo.r_itrs, dipole_axis(decimal_year(config.time.epoch_utc)))
        track_max = forward_window_max(lam, seconds_to_ns(acc.horizon_s) // step_ns + 1)
        truth_cut = np.array([cutoff.cutoff_deg(series.sym_h_truth(epoch_unix_ns + int(t)))
                              for t in traj.t_ns])  # fmt: skip
        in_access = lam >= truth_cut[:, None]
        storm["in_access_s"] = {a: float(in_access[:, j].sum()) * step_s
                                for j, a in enumerate(ids)}  # fmt: skip
    active: dict[str, Segment] = {}
    segments: list[Segment] = []
    transitions = faults.transitions(spec.duration_ns)
    kernel = make_kernel(config, formation, agents, streams, log, faults)

    def close(a: str, k: int) -> None:
        seg = active.pop(a)
        seg.stop_tick = k
        segments.append(seg)
        kernel.record(k * step_ns, "sim", "observation_stopped",
                      {"spacecraft": a, "task": seg.task_id, "steps": k - seg.start_tick,
                       "aborted": seg.aborted})  # fmt: skip

    def hook(k: int, t: int) -> None:
        for when, kind, f in transitions:  # truth events, never seen by agents
            if when == t:
                kernel.record(t, "faults", kind, f.record())
        confirmed_now = faults.ground_notices(t) if faults else ()
        if confirmed_now:  # explicit evidence (DL-052): ground notice to every available agent
            kernel.record(t, "ground", "failure_confirmed", {"spacecraft": list(confirmed_now)})
            for a in ids:
                if not faults.unavailable(a, t):
                    agents[a].observe(GroundNotice(t, confirmed_now))
        for j, a in enumerate(ids):
            bat = batteries[a]
            down = bool(faults) and faults.unavailable(a, t)
            if not down:
                flags = faults.critical_flags(a, t) if faults else ()
                hk = Housekeeping(t, bat.stored_wh, sc.battery_capacity_wh, storage[a],
                                  sc.storage_capacity_mb, flags)  # fmt: skip
                agents[a].observe(hk)
                delivered = not faults or faults.forecast_delivered(a, t)  # DL-090
                if series is not None and delivered:
                    tu = epoch_unix_ns + t - (faults.forecast_delay_ns(a, t) if faults else 0)
                    rad, nav, orb = replay_risks(config, series, tu, j)
                    if (
                        cutoff is not None
                        and track_max is not None
                        and rad is not None
                        and track_max[k, j] < cutoff.cutoff_deg(series.indices(tu)[0])
                    ):
                        rad = 0.0  # own track stays below the cutoff over the horizon
                    issued = series.issued_ns(tu)
                    agents[a].observe(
                        RiskForecast(
                            t, rad, nav, orb, None if issued is None else issued - epoch_unix_ns
                        )
                    )
                elif series is None and config.environment is not None:  # scheduled forecasts
                    dims = ("radiation", "navcomms", "orbital")
                    r_rad, r_nav, r_orb = (risk_ratio(config, a, d, t) for d in dims)
                    agents[a].observe(RiskForecast(t, r_rad, r_nav, r_orb))
                if sensor is not None and t > 0 and t % check_ns == 0:  # H-C onboard detector
                    bad = bool(faults) and not faults.payload_valid(a, t)
                    agents[a].observe(PayloadCheck(t, sensor.draw(sensor_rng, bad)))
            if k == n_ticks - 1:
                continue  # no step after the final tick
            cmd = None if down else agents[a].payload_command(t, step_ns, mb_per_step)
            if cmd is not None and agents[a].mode not in SCIENCE_MODES:  # truth check (Gate P3)
                protection_violations[a] += 1
            if series is not None and rp is not None and not down:  # S11 truth (DL-069)
                flux = series.truth(epoch_unix_ns + t)
                if flux is None:
                    storm["no_truth_s"][a] += step_s
                else:
                    if in_access is not None and not in_access[k, j]:
                        flux = 0.0  # below the cutoff: no access (DL-090)
                    hazard = flux >= rp.tolerance_pfu(j)
                    protected = agents[a].mode in (PROTECTIVE, RECOVERY)
                    if hazard:
                        storm["hazard_s"][a] += step_s
                        storm["exposed_s"][a] += step_s if cmd is not None else 0.0
                        storm["protected_in_hazard_s"][a] += step_s if protected else 0.0
                    elif protected:
                        storm["protected_outside_hazard_s"][a] += step_s
            if a in active and active[a].task_id != cmd:
                close(a, k)
            if cmd is not None and a not in active:
                if cmd not in by_id:
                    raise RuntimeError(f"{a} commanded unknown task {cmd!r}")
                active[a] = Segment(a, cmd, k)
                kernel.record(t, "sim", "observation_started", {"spacecraft": a, "task": cmd})
            gen = sc.solar_generation_w if bool(geo.sunlit[k, j]) else 0.0
            if faults:
                gen *= faults.generation_factor(a, t)
            load = sc.bus_power_w + (sc.payload_power_w if cmd is not None else 0.0)
            if thrust_on is not None and thrust_on[k, j]:  # DL-087 burn during this step
                load += sc.thruster_power_w
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
                if faults and not faults.payload_valid(a, t):
                    seg.payload_invalid = True

    kernel.run(tick_hook=hook)
    for a in sorted(active):
        close(a, n_ticks - 1)
    record_scenario_end(config, log)

    if decentralized:  # the plan on record is what each agent finally believed
        final = [
            Assignment(o.task_id, a, o.start_ns // step_ns, o.stop_ns // step_ns)
            for a in ids
            for o in agents[a].planned_observations()
        ]
        claimed = {x.task_id for x in final}
        plan = Plan(
            plan.algorithm,
            max(agents[a].plan_version for a in ids),
            tuple(sorted(final, key=lambda x: (x.start_tick, x.spacecraft, x.task_id))),
            tuple(t.task_id for t in catalog if t.task_id not in claimed),
            False,
        )

    completed: dict[str, Segment] = {}
    for seg in sorted(segments, key=lambda s: (s.stop_tick, s.spacecraft)):
        w = by_id[seg.task_id].window_of(seg.spacecraft)
        inside = (
            w is not None and w.first_tick <= seg.start_tick and seg.stop_tick - 1 <= w.last_tick
        )
        seg.valid = seg.aborted is None and inside and seg.stop_tick - seg.start_tick >= n_steps
        if seg.valid and seg.payload_invalid:
            seg.valid = False
            seg.outcome = "invalid_payload"
        elif not seg.valid:
            seg.outcome = "invalid" if seg.aborted is None else f"aborted_{seg.aborted}"
        elif seg.task_id in completed:
            seg.outcome = "duplicate"
        else:
            seg.outcome = "completed"
            completed[seg.task_id] = seg
    segments.sort(key=lambda s: (s.start_tick, s.spacecraft))

    utility = sum(by_id[t].priority for t in completed)
    health = _health_metrics(agents, ids, faults, spec.duration_ns, step_ns)
    if config.agents.health is not None:  # DL-066 runs only, so pinned summaries are unchanged
        health["model"] = config.agents.health.model
        health["payload_check"] = pc is not None
        health["payload"] = _payload_metrics(agents, ids, faults, spec.duration_ns, step_ns)
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
            **({"n_invalid_payload": sum(1 for s in segments if s.outcome == "invalid_payload"),
                "faults": [f.record() for f in faults.faults]} if faults else {}),
            "n_assigned": len(plan.assignments),
            "unassigned": list(plan.unassigned),
            "decentralized": decentralized,
            "conflicting_final_claims": sorted(
                t for t in {x.task_id for x in plan.assignments}
                if sum(1 for x in plan.assignments if x.task_id == t) > 1
            ),
            "last_plan_change_s": {
                a: (v / 1e9 if (v := agents[a].execution_view()["last_plan_change_ns"]) is not None
                    else None)
                for a in ids
            },
            "declined": {a: agents[a].execution_view()["declined"] for a in ids},
            "min_battery_wh": min_wh,
            "final_battery_wh": {a: batteries[a].stored_wh for a in ids},
            "deficit_steps": {a: batteries[a].deficit_steps for a in ids},
            "storage_used_mb": storage,
            "note": "q_j = 1 (DL-041); utility counts each task once",
        },
        "health": health,
        "protection": _protection_summary(agents, ids, spec.duration_ns, protection_violations),
        **({"storm": {"forecast": rp.forecast,
                      "radiation_tolerance_pfu": rp.radiation_tolerance_pfu, **storm,
                      **({"access": acc.model_dump(mode="json")} if acc is not None else {})}}
           if rp is not None else {}),
        "network": kernel.network_summary(),
        **kernel.agents_summary(),
    })  # fmt: skip
    return OperationsRun(formation, plan, catalog, segments, kernel.trace, summary, agents)


def _health_metrics(
    agents: dict[str, SpacecraftAgent],
    ids: list[str],
    faults: FaultSchedule,
    end_ns: int,
    step: int,
) -> dict[str, Any]:
    """Beliefs vs truth (evaluation only; agents never see truth).

    * ``confirmed_while_available``: CONFIRMED_FAILED believed about a peer that was
      actually available at that time (must be 0: Gate P3).
    * ``false_unavailable_s``: time a peer was believed LOST/CONFIRMED while available.
    * ``missed_unavailable_s``: time a peer was actually unavailable but believed available.
    * ``detection_latency_s``: per observer and unavailable peer, from the fault start to
      the first LOST/CONFIRMED belief (None if never detected).
    """

    def truth_available(peer: str, t: int) -> bool:
        return not (faults and faults.unavailable(peer, t))

    out: dict[str, Any] = {"confirmed_while_available": 0, "false_unavailable_s": 0.0,
                           "missed_unavailable_s": 0.0, "belief_changes": 0,
                           "detection_latency_s": {}, "final_beliefs": {}}  # fmt: skip
    starts: dict[str, int] = {}
    for f in faults.faults if faults else ():
        if f.fault_type == "unavailable":
            for sc in f.spacecraft:
                starts[sc] = min(starts.get(sc, f.start_ns), f.start_ns)
    for obs in ids:
        if faults and faults.unavailable(obs, end_ns):
            continue  # a dead observer's beliefs are frozen; not evaluated after it died
        hist = agents[obs].belief_history()
        out["belief_changes"] += len(hist)
        out["final_beliefs"][obs] = agents[obs].health_beliefs()
        for peer in agents[obs].peers:
            changes = [(t, new) for t, p, _, new in hist if p == peer]
            if any(new == CONFIRMED and truth_available(peer, t) for t, new in changes):
                out["confirmed_while_available"] += 1
            bounds = [0, *[t for t, _ in changes], end_ns]
            beliefs = ["UNKNOWN", *[b for _, b in changes]]
            for (a, b), belief in zip(itertools.pairwise(bounds), beliefs, strict=False):
                for t in range(a - a % step, b, step):  # sample on the 10 s grid
                    if t < a:
                        continue
                    avail = truth_available(peer, t)
                    if belief in UNAVAILABLE_BELIEFS and avail:
                        out["false_unavailable_s"] += step / 1e9
                    if belief in AVAILABLE_BELIEFS and not avail:
                        out["missed_unavailable_s"] += step / 1e9
            if peer in starts:
                hit = next((t for t, b in changes if b in UNAVAILABLE_BELIEFS
                            and t >= starts[peer]), None)  # fmt: skip
                out["detection_latency_s"][f"{obs}->{peer}"] = (
                    None if hit is None else (hit - starts[peer]) / 1e9
                )
    return out


def _payload_metrics(
    agents: dict[str, SpacecraftAgent],
    ids: list[str],
    faults: FaultSchedule,
    end_ns: int,
    step: int,
) -> dict[str, Any]:
    """Own-payload beliefs (H-C) vs truth, sampled on the step grid while the spacecraft
    is available: ``false_degraded_s`` (believed degraded, payload fine),
    ``missed_degraded_s`` (degraded, believed fine), ``detection_latency_s`` per
    ``payload_degraded`` fault (fault start to first DEGRADED belief; 0 if already
    believed degraded at the start; None if never)."""
    out: dict[str, Any] = {"false_degraded_s": 0.0, "missed_degraded_s": 0.0,
                           "belief_changes": 0, "detection_latency_s": {}}  # fmt: skip
    for a in ids:
        hist = agents[a].payload_belief_history()
        out["belief_changes"] += len(hist)
        for t in range(0, end_ns, step):
            if faults and faults.unavailable(a, t):
                continue
            believed = next((d for tt, d, _ in reversed(hist) if tt <= t), False)
            bad = bool(faults) and not faults.payload_valid(a, t)
            if believed and not bad:
                out["false_degraded_s"] += step / 1e9
            elif bad and not believed:
                out["missed_degraded_s"] += step / 1e9
    for f in faults.faults if faults else ():
        if f.fault_type != "payload_degraded":
            continue
        for a in f.spacecraft:
            hist = agents[a].payload_belief_history()
            if next((d for tt, d, _ in reversed(hist) if tt <= f.start_ns), False):
                hit: int | None = f.start_ns  # already believed degraded (false alarm)
            else:
                hit = next((tt for tt, d, _ in hist if d and tt >= f.start_ns), None)
            out["detection_latency_s"][f"{f.fault_id}:{a}"] = (
                None if hit is None else (hit - f.start_ns) / 1e9
            )
    return out


def _protection_summary(agents: dict[str, SpacecraftAgent], ids: list[str], end_ns: int,
                        violations: dict[str, int]) -> dict[str, Any]:  # fmt: skip
    """Time per mode and transitions per spacecraft; payload-on steps in PROTECTIVE,
    RECOVERY or SAFE (must be 0: the planner cannot defeat protection, Gate P3)."""
    time_s: dict[str, dict[str, float]] = {}
    transitions: dict[str, list[dict[str, Any]]] = {}
    for a in ids:
        hist = agents[a].mode_history()
        bounds = [0, *[t for t, _, _, _ in hist], end_ns]
        modes = [NOMINAL, *[new for _, _, new, _ in hist]]
        acc = dict.fromkeys(MODES, 0.0)
        for (t0, t1), m in zip(itertools.pairwise(bounds), modes, strict=False):
            acc[m] += (t1 - t0) / 1e9
        time_s[a] = acc
        transitions[a] = [{"t_s": t / 1e9, "from": o, "to": n, "reason": w} for t, o, n, w in hist]
    return {"time_in_mode_s": time_s, "transitions": transitions,
            "payload_steps_in_protected_modes": violations}  # fmt: skip

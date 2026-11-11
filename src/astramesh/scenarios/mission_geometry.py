"""Phase 1 mission-geometry scenario: formation + illumination + science opportunities.

Steps:

1. Formation dynamics exactly as in ``formation_dynamics`` (mean-element
   initialization, RK4, J2 about the epoch pole).
2. GCRS-to-ITRS matrices for every tick (ERFA, no BLAS) and the Sun direction
   (ERFA ``epv00``); cylindrical-shadow illumination per spacecraft and tick.
3. Region access windows on the tick grid and their merger into
   opportunities (``astramesh.science``).
4. Resource accounting (``astramesh.resources``): payload energy and data
   cost of every eligible window; battery energy over the day for two load
   profiles, *bus only* and *payload on in every eligible window* (the most
   observing can draw, not a schedule); storage fill; the delta-v/propellant
   budget. The profiles are bookkeeping, not agent decisions (Phase 2).

Everything is evaluated at every simulation tick, not only at the trajectory
sampling interval. The outputs are truth geometry, not agent knowledge. Nothing
here is a research result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from astramesh.control.formation_keeping import KeepingResult
from astramesh.core.config import MissionGeometryScenario, MissionScenarioBase
from astramesh.core.events import EventLog
from astramesh.dynamics.earth_frames import gcrs_to_itrs_matrices, rotate
from astramesh.dynamics.forces import equatorial_basis
from astramesh.dynamics.state import cross3, dot3, matvec3, norm3
from astramesh.dynamics.sun import in_shadow, sun_direction_gcrs
from astramesh.resources.ledgers import (
    PropulsionBudget,
    data_volume_mb,
    energy_wh,
    simulate_energy,
)
from astramesh.scenarios.formation_dynamics import (
    FormationRun,
    record_scenario_end,
    run_formation_dynamics,
    spacecraft_ids,
)
from astramesh.science.access import Site
from astramesh.science.opportunities import Opportunity, Region, find_opportunities

ALGORITHM_NAME = "none (truth geometry only)"
OPPORTUNITIES_FILE = "opportunities.json"


@dataclass(frozen=True, slots=True)
class MissionGeometryRun:
    formation: FormationRun
    sunlit: NDArray[np.bool_]  # (n_t, n_sc)
    opportunities: list[Opportunity]
    records: list[dict[str, Any]]
    summary: dict[str, Any]


def _transitions(sunlit: NDArray[np.bool_]) -> list[tuple[int, int, str]]:
    """(tick, spacecraft index, 'eclipse_entry' | 'eclipse_exit') at changes of state."""
    out = []
    change = np.flatnonzero(np.any(sunlit[1:] != sunlit[:-1], axis=1))
    for k in change.tolist():
        for j in np.flatnonzero(sunlit[k + 1] != sunlit[k]).tolist():
            out.append((k + 1, int(j), "eclipse_exit" if sunlit[k + 1, j] else "eclipse_entry"))
    return sorted(set(out))


def _orbit_orientation(
    r: NDArray[np.float64], v: NDArray[np.float64], sun: NDArray[np.float64], pole: Any
) -> dict[str, float]:
    """Beta angle and local time of the ascending node (equator of the epoch pole)."""
    h = cross3(r, v)
    h = h / norm3(h)
    rot = equatorial_basis(pole)
    he, se = matvec3(rot, h), matvec3(rot, sun)
    raan = math.atan2(float(he[0]), -float(he[1]))  # node = pole x h
    sun_ra = math.atan2(float(se[1]), float(se[0]))
    ltan_h = (12.0 + math.degrees(raan - sun_ra) / 15.0) % 24.0
    beta = math.degrees(math.asin(max(-1.0, min(1.0, float(dot3(h, sun))))))
    return {"beta_angle_deg": beta, "ltan_h": ltan_h}


@dataclass(frozen=True, slots=True)
class GeometryProducts:
    sun: NDArray[np.float64]  # (n_t, 3) unit vectors
    sunlit: NDArray[np.bool_]  # (n_t, n_sc)
    regions: list[Region]
    opportunities: list[Opportunity]


def geometry_products(config: MissionScenarioBase, formation: FormationRun) -> GeometryProducts:
    """Illumination and science opportunities on the tick grid (no events logged)."""
    traj = formation.trajectory
    epoch = config.time.epoch_utc
    ids = spacecraft_ids(traj.n_spacecraft)
    r_gcrs = np.ascontiguousarray(traj.y[:, :, :3])
    sun = sun_direction_gcrs(epoch, traj.t_ns)
    sunlit = ~in_shadow(r_gcrs, sun)
    r_itrs = rotate(gcrs_to_itrs_matrices(epoch, traj.t_ns), r_gcrs)
    regions = [
        Region(r.region_id, r.priority, Site.from_geodetic(r.latitude_deg, r.longitude_deg))
        for r in config.science.regions
    ]
    opportunities = find_opportunities(
        regions, ids, r_itrs, sunlit, config.science.min_elevation_deg
    )
    return GeometryProducts(sun, sunlit, regions, opportunities)


def run_mission_geometry(config: MissionGeometryScenario, log: EventLog) -> MissionGeometryRun:
    formation = run_formation_dynamics(config, log, end_event=False)
    traj = formation.trajectory
    step_ns = config.time.clock_spec().step_ns
    ids = spacecraft_ids(traj.n_spacecraft)
    geo = geometry_products(config, formation)
    sun, sunlit, regions, opportunities = geo.sun, geo.sunlit, geo.regions, geo.opportunities
    records = [o.to_record(traj.t_ns, step_ns) for o in opportunities]
    resources = _account_resources(config, ids, sunlit, opportunities, records, formation.keeping)

    # Events in time order: eclipse transitions, then opportunity open/close.
    pending: list[tuple[int, int, str, str, dict[str, Any]]] = []
    for tick, j, kind in _transitions(sunlit):
        pending.append((tick, 0, ids[j], kind, {}))
    for o, rec in zip(opportunities, records, strict=True):
        eligible = [e["spacecraft"] for e in rec["eligible_spacecraft"]]
        pending.append(
            (o.first, 1, "science", "opportunity_open",
             {"id": o.task_id, "region": o.region.region_id, "eligible": eligible})
        )  # fmt: skip
        pending.append((o.last, 2, "science", "opportunity_close", {"id": o.task_id}))
    for tick, _, source, kind, data in sorted(pending, key=lambda p: (p[0], p[1], p[2], p[3])):
        log.record(tick=tick, time_ns=int(traj.t_ns[tick]), source=source, kind=kind, data=data)
    record_scenario_end(config, log)

    n_t = len(traj.t_ns)
    entries = [sum(1 for _, j, k in _transitions(sunlit) if j == jj and k == "eclipse_entry")
               for jj in range(len(ids))]  # fmt: skip
    per_region = {r.region_id: 0 for r in regions}
    for o in opportunities:
        per_region[o.region.region_id] += 1
    summary = dict(formation.summary)
    summary.update(
        {
            "orbit_orientation_at_epoch": _orbit_orientation(
                traj.y[0, 0, :3], traj.y[0, 0, 3:], sun[0], traj.forces.pole
            ),
            "illumination": {
                "model": "cylindrical shadow, spherical Earth R_eq; Sun from ERFA epv00",
                "eclipse_fraction": {
                    sc: float(np.count_nonzero(~sunlit[:, j]) / n_t) for j, sc in enumerate(ids)
                },
                "eclipse_entries": dict(zip(ids, entries, strict=True)),
            },
            "science": {
                "min_elevation_deg": config.science.min_elevation_deg,
                "n_regions": len(regions),
                "n_opportunities": len(opportunities),
                "opportunities_per_region": per_region,
                "n_with_all_spacecraft_eligible": sum(
                    1 for o in opportunities if len(o.eligible) == len(ids)
                ),
                "total_duration_s": sum(r["duration_s"] for r in records),
                "note": "geometry-only scheduling abstraction (spec §3.1); not TEC retrieval",
            },
            "resources": resources,
        }
    )
    return MissionGeometryRun(formation, sunlit, opportunities, records, summary)


def _on_steps(first: int, last: int, n_t: int) -> int:
    """Steps [t_k, t_k+1) covered by ticks first..last (no step after the final tick)."""
    return min(last, n_t - 2) - first + 1


def _account_resources(
    config: MissionScenarioBase,
    ids: list[str],
    sunlit: NDArray[np.bool_],
    opportunities: list[Opportunity],
    records: list[dict[str, Any]],
    keeping: KeepingResult | None = None,
) -> dict[str, Any]:
    """Fill task costs in ``records`` (in place) and return the resource summary."""
    sc = config.spacecraft
    step_s = config.time.time_step_s
    n_t = sunlit.shape[0]
    payload_on = np.zeros_like(sunlit)
    for o, rec in zip(opportunities, records, strict=True):
        costs = []
        for e, entry in zip(o.eligible, rec["eligible_spacecraft"], strict=True):
            steps = _on_steps(e.window.first, e.window.last, n_t)
            entry["payload_energy_wh"] = energy_wh(steps, step_s, sc.payload_power_w)
            entry["storage_mb"] = data_volume_mb(steps, step_s, sc.payload_data_rate_kbps)
            costs.append((entry["payload_energy_wh"], entry["storage_mb"]))
            payload_on[e.window.first : e.window.last + 1, ids.index(e.spacecraft)] = True
        # Task-level cost: one spacecraft observing its (longest) eligible window.
        rec["payload_energy_wh"] = max(c[0] for c in costs)
        rec["storage_mb"] = max(c[1] for c in costs)
    payload_on[-1, :] = False  # no step after the final tick

    def energy(profile_payload: NDArray[np.bool_], j: int) -> dict[str, Any]:
        r = simulate_energy(
            sunlit=sunlit[:, j],
            payload_on=profile_payload[:, j],
            step_s=step_s,
            capacity_wh=sc.battery_capacity_wh,
            initial_fraction=sc.battery_initial_fraction,
            charge_efficiency=sc.charge_efficiency_fraction,
            generation_w=sc.solar_generation_w,
            bus_w=sc.bus_power_w,
            payload_w=sc.payload_power_w,
            thruster_on=None if keeping is None else keeping.thrust_on[:, j],  # DL-087 burns
            thruster_w=0.0 if keeping is None else sc.thruster_power_w,
        )
        return {
            "min_wh": r.min_wh,
            "min_fraction": r.min_wh / sc.battery_capacity_wh,
            "min_t_ns": r.min_tick * config.time.clock_spec().step_ns,
            "max_drawdown_wh": r.max_drawdown_wh,
            "max_drawdown_fraction": r.max_drawdown_wh / sc.battery_capacity_wh,
            "final_wh": r.final_wh,
            "generated_wh": r.generated_wh,
            "consumed_wh": r.consumed_wh,
            "curtailed_wh": r.curtailed_wh,
            "deficit_wh": r.deficit_wh,
            "deficit_steps": r.deficit_steps,
        }

    bus_only = np.zeros_like(sunlit)
    prop = PropulsionBudget(
        mass_kg=sc.mass_kg,
        thrust_n=sc.thrust_mn * 1e-3,
        specific_impulse_s=sc.specific_impulse_s,
        budget_mps=sc.delta_v_budget_mps,
    )
    full_burn_s = prop.burn_time_s(sc.delta_v_budget_mps)
    data = {
        sc_id: data_volume_mb(int(np.count_nonzero(payload_on[:, j])), step_s,
                              sc.payload_data_rate_kbps)
        for j, sc_id in enumerate(ids)
    }  # fmt: skip
    return {
        "model": "left-endpoint steps; charge efficiency on charging; clamp [0, capacity]",
        "energy_bus_only": {sc_id: energy(bus_only, j) for j, sc_id in enumerate(ids)},
        "energy_payload_all_eligible": {
            sc_id: energy(payload_on, j) for j, sc_id in enumerate(ids)
        },
        "payload_on_s": {
            sc_id: float(np.count_nonzero(payload_on[:, j]) * step_s) for j, sc_id in enumerate(ids)
        },
        "storage_payload_all_eligible": {
            sc_id: {"used_mb": mb, "fraction": mb / sc.storage_capacity_mb}
            for sc_id, mb in data.items()
        },
        "propulsion": {
            "delta_v_budget_mps": sc.delta_v_budget_mps,
            "delta_v_used_mps": 0.0
            if keeping is None
            else dict(zip(ids, keeping.delta_v_mps, strict=True)),
            "propellant_for_budget_kg": prop.propellant_kg(sc.delta_v_budget_mps),
            "thrust_time_for_budget_h": full_burn_s / 3600.0,
            "thruster_energy_for_budget_wh": sc.thruster_power_w * full_burn_s / 3600.0,
            "initial_acceleration_mps2": prop.thrust_n / sc.mass_kg,
        },
    }

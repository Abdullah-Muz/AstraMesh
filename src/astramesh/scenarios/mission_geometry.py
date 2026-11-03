"""Phase 1 mission-geometry scenario: formation + illumination + science opportunities.

Steps:

1. Formation dynamics exactly as in ``formation_dynamics`` (mean-element
   initialization, RK4, J2 about the epoch pole).
2. GCRS-to-ITRS matrices for every tick (ERFA, no BLAS) and the Sun direction
   (ERFA ``epv00``); cylindrical-shadow illumination per spacecraft and tick.
3. Region access windows on the tick grid and their merger into
   opportunities (``astramesh.science``).

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

from astramesh.core.config import MissionGeometryScenario
from astramesh.core.events import EventLog
from astramesh.dynamics.earth_frames import gcrs_to_itrs_matrices, rotate
from astramesh.dynamics.forces import equatorial_basis
from astramesh.dynamics.state import cross3, dot3, matvec3, norm3
from astramesh.dynamics.sun import in_shadow, sun_direction_gcrs
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


def run_mission_geometry(config: MissionGeometryScenario, log: EventLog) -> MissionGeometryRun:
    formation = run_formation_dynamics(config, log, end_event=False)
    traj = formation.trajectory
    epoch = config.time.epoch_utc
    step_ns = config.time.clock_spec().step_ns
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
    records = [o.to_record(traj.t_ns, step_ns) for o in opportunities]

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
        }
    )
    return MissionGeometryRun(formation, sunlit, opportunities, records, summary)

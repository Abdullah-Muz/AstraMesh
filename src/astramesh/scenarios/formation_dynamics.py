"""Phase 1 formation-dynamics scenario: truth orbits of the along-track formation.

Steps:

1. Earth's pole at the scenario epoch (GCRS ITRS-z, Astropy) defines the
   equatorial frame for the elements and the J2 axis (DL-025).
2. Initial states from the configured **mean** elements (DL-026/027):
   ``j2`` uses :func:`~astramesh.dynamics.mean_elements.mean_matched_formation`;
   ``two_body`` has no short-period terms, so mean = osculating and the
   two-body :func:`~astramesh.dynamics.formation.along_track_formation` is used
   (rotated into the same equatorial frame).
3. Fixed-step RK4 propagation on the scenario clock grid.

Outputs are truth states only. No agent, science, or resource model is
involved, and nothing here is a research result (it is a validated dynamics
baseline).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from astramesh.core.clock import NS_PER_S, seconds_to_ns
from astramesh.core.config import FormationScenarioBase
from astramesh.core.events import EventLog
from astramesh.dynamics.constants import GM_EARTH_M3PS2, J2_EARTH, R_EARTH_EQ_M
from astramesh.dynamics.earth_frames import earth_pole_gcrs
from astramesh.dynamics.elements import KeplerElements
from astramesh.dynamics.forces import ForceModel
from astramesh.dynamics.formation import along_track_formation
from astramesh.dynamics.mean_elements import equatorial_state, mean_matched_formation
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.twobody import Trajectory, propagate

ALGORITHM_NAME = "none (truth dynamics only)"
TRAJECTORY_FILE = "trajectory.csv"
TRAJECTORY_HEADER = "t_ns,spacecraft,x_m,y_m,z_m,vx_mps,vy_mps,vz_mps"


def spacecraft_ids(n: int) -> list[str]:
    return [f"sc{k:02d}" for k in range(n)]


@dataclass(frozen=True, slots=True)
class FormationRun:
    trajectory: Trajectory
    sample_stride: int
    summary: dict[str, Any]


def _initial_states(
    config: FormationScenarioBase, forces: ForceModel, log: EventLog
) -> list[CartesianState]:
    ref = config.reference_orbit
    mean_a = R_EARTH_EQ_M + ref.mean_altitude_km * 1e3
    inc = math.radians(ref.mean_inclination_deg)
    raan = math.radians(ref.raan_deg)
    u0 = math.radians(ref.start_argument_of_latitude_deg)
    n = config.formation.n_spacecraft
    spacing_m = config.formation.along_track_spacing_km * 1e3
    epoch = config.time.epoch_utc
    ids = spacecraft_ids(n)
    states: list[CartesianState] = []
    if config.dynamics.model == "j2":
        members = mean_matched_formation(
            mean_a_m=mean_a,
            mean_i_rad=inc,
            raan_rad=raan,
            u0_rad=u0,
            n_spacecraft=n,
            spacing_m=spacing_m,
            forces=forces,
            epoch_utc=epoch,
        )
        for sc, m in zip(ids, members, strict=True):
            log.record(
                tick=0,
                time_ns=0,
                source=sc,
                kind="initial_orbit",
                data={
                    "method": "mean_element_iteration",
                    "iterations": m.iterations,
                    "osculating_a_m": m.osculating.a_m,
                    "osculating_e": m.osculating.e,
                    "osculating_i_deg": math.degrees(m.osculating.i_rad),
                    "mean_a_m": m.mean.a_m,
                    "mean_i_deg": math.degrees(m.mean.i_rad),
                    "mean_e_vector": math.hypot(m.mean.ex, m.mean.ey),
                },
            )
            states.append(CartesianState(Frame.GCRS, epoch, 0, m.r_m, m.v_mps))
    else:
        reference = KeplerElements(
            a_m=mean_a, e=0.0, i_rad=inc, raan_rad=raan, argp_rad=0.0, nu_rad=u0
        )
        for sc, el in zip(
            ids, along_track_formation(reference, n_spacecraft=n, spacing_m=spacing_m), strict=True
        ):
            r, v = equatorial_state(el, forces)
            log.record(
                tick=0,
                time_ns=0,
                source=sc,
                kind="initial_orbit",
                data={
                    "method": "two_body_elements",
                    "a_m": el.a_m,
                    "argument_of_latitude_deg": math.degrees(el.argp_rad + el.nu_rad),
                },
            )
            states.append(CartesianState(Frame.GCRS, epoch, 0, r, v))
    return states


def _summary(config: FormationScenarioBase, traj: Trajectory, forces: ForceModel) -> dict[str, Any]:
    y = traj.y
    radius_minus_req_km = (np.linalg.norm(y[:, :, :3], axis=2) - R_EARTH_EQ_M) / 1e3
    out: dict[str, Any] = {
        "dynamics_model": forces.model_id,
        "gm_m3ps2": forces.mu,
        "j2": forces.j2,
        "r_ref_m": forces.r_ref_m,
        "pole_gcrs": list(forces.pole),
        "n_spacecraft": config.formation.n_spacecraft,
        "n_steps": len(traj.t_ns) - 1,
        "radius_minus_req_km_min": float(radius_minus_req_km.min()),
        "radius_minus_req_km_max": float(radius_minus_req_km.max()),
        "note": "truth-dynamics bookkeeping; not research metrics",
    }
    if config.formation.n_spacecraft > 1:
        sep_km = np.linalg.norm(y[:, 1:, :3] - y[:, :-1, :3], axis=2) / 1e3
        out["adjacent_separation_km"] = {
            "min": float(sep_km.min()),
            "max": float(sep_km.max()),
            "initial": sep_km[0].tolist(),
            "final": sep_km[-1].tolist(),
        }
    return out


def run_formation_dynamics(
    config: FormationScenarioBase, log: EventLog, *, end_event: bool = True
) -> FormationRun:
    """Initialize and propagate the formation.

    With ``end_event=False`` the caller records ``scenario_end`` itself (after
    its own events, which must not precede earlier ticks).
    """
    epoch = config.time.epoch_utc
    spec = config.time.clock_spec()
    pole = earth_pole_gcrs(epoch)
    forces = (
        ForceModel.with_j2(pole, j2=J2_EARTH)
        if config.dynamics.model == "j2"
        else ForceModel(mu=GM_EARTH_M3PS2, j2=0.0, pole=pole)
    )
    log.record(
        tick=0,
        time_ns=0,
        source="sim",
        kind="scenario_start",
        data={
            "scenario_id": config.scenario_id,
            "spacecraft": spacecraft_ids(config.formation.n_spacecraft),
            "n_steps": spec.n_steps,
            "dynamics_model": forces.model_id,
            "pole_gcrs": list(pole),
        },
    )
    initial = _initial_states(config, forces, log)
    traj = propagate(initial, step_ns=spec.step_ns, n_steps=spec.n_steps, forces=forces)
    stride = seconds_to_ns(config.output.trajectory_sample_interval_s) // spec.step_ns
    summary = _summary(config, traj, forces)
    if end_event:
        record_scenario_end(config, log)
    return FormationRun(traj, int(stride), summary)


def record_scenario_end(config: FormationScenarioBase, log: EventLog) -> None:
    spec = config.time.clock_spec()
    log.record(
        tick=spec.n_steps,
        time_ns=spec.duration_ns,
        source="sim",
        kind="scenario_end",
        data={"duration_s": spec.duration_ns / NS_PER_S},
    )


def write_trajectory_csv(run: FormationRun, path: Any) -> None:
    """Sampled GCRS states, one row per (time, spacecraft); floats as shortest repr."""
    traj = run.trajectory
    ids = spacecraft_ids(traj.n_spacecraft)
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write(TRAJECTORY_HEADER + "\n")
        for k in range(0, len(traj.t_ns), run.sample_stride):
            t = int(traj.t_ns[k])
            for j, sc in enumerate(ids):
                row = ",".join(repr(float(x)) for x in traj.y[k, j])
                fh.write(f"{t},{sc},{row}\n")

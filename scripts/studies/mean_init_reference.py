"""Study for mean-element initialization (DL-026): reference orbit and formation.

Run:  uv run python scripts/studies/mean_init_reference.py [--out m.json]

Recorded in docs/NUMERICAL_MISSION_DESIGN.md §B.6; tolerances in
tests/physics_validation/test_mean_elements.py derive from it (DL-019).

  S1  Reference orbit from mean targets (a = R + 525 km, i = 97.5 deg, mean
      e-vector = 0): iterations, residuals, and an independent consistency
      check of the mean definition: the one-period mean re-measured from states
      later on the same trajectory (1, 6, 12, 23 h) must not change. (A plain
      24 h average is NOT used: 24 h is not a whole number of draconitic periods,
      and the leftover fraction biases the mean of the +/-9 km a-oscillation by
      tens of metres.)
  S2  Nodal precession of the mean-initialized reference orbit vs analytic
      (mean elements) and vs the sun-synchronous rate.
  S3  Mean-matched 4-spacecraft formation (20 km) for start angles 0-90 deg:
      secular drift (orbit-averaged separation trend over 3 days), periodic
      in-orbit separation swing, mean separation, 24 h max separation change.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from astramesh.dynamics.constants import GM_EARTH_M3PS2, J2_EARTH, R_EARTH_EQ_M
from astramesh.dynamics.earth_frames import earth_pole_gcrs
from astramesh.dynamics.elements import rv_to_elements
from astramesh.dynamics.forces import ForceModel, equatorial_basis
from astramesh.dynamics.mean_elements import (
    initialize_from_mean,
    mean_matched_formation,
    measure_mean_elements,
)
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.twobody import propagate

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
NS = 10**9
DAY_S = 86_400
MEAN_A = R_EARTH_EQ_M + 525e3
MEAN_I = math.radians(97.5)
SSO_RATE = 2 * math.pi / (365.2421897 * DAY_S)


def study_reference(fm: ForceModel) -> dict[str, Any]:
    t0 = time.perf_counter()
    orb = initialize_from_mean(
        mean_a_m=MEAN_A, mean_i_rad=MEAN_I, raan_rad=0.0, u_rad=0.0, forces=fm, epoch_utc=EPOCH
    )
    elapsed = time.perf_counter() - t0
    s = CartesianState(Frame.GCRS, EPOCH, 0, orb.r_m, orb.v_mps)
    traj = propagate([s], step_ns=10 * NS, n_steps=8640, forces=fm)
    rot = equatorial_basis(fm.pole)
    osc = [rv_to_elements(rot @ row[:3], rot @ row[3:]) for row in traj.y[:, 0, :]]
    t = traj.t_ns.astype(np.float64) / NS
    later = []
    for hours in (1, 6, 12, 23):
        row = traj.y[hours * 360, 0, :]
        m = measure_mean_elements(row[:3], row[3:], fm, epoch_utc=EPOCH)
        later.append((m.a_m - MEAN_A, m.i_rad - MEAN_I, math.hypot(m.ex, m.ey)))
    rate = float(np.polyfit(t, np.unwrap([o.raan_rad for o in osc]), 1)[0])
    n = math.sqrt(GM_EARTH_M3PS2 / MEAN_A**3)
    analytic = -1.5 * n * J2_EARTH * (R_EARTH_EQ_M / MEAN_A) ** 2 * math.cos(MEAN_I)
    alt = np.linalg.norm(traj.y[:, 0, :3], axis=1) - R_EARTH_EQ_M
    return {
        "iterations": orb.iterations,
        "init_time_s": elapsed,
        "osculating_init": {
            "a_minus_mean_a_m": orb.osculating.a_m - MEAN_A,
            "i_minus_mean_i_deg": math.degrees(orb.osculating.i_rad - MEAN_I),
            "e": orb.osculating.e,
        },
        "one_period_mean_residuals": {
            "a_m": orb.mean.a_m - MEAN_A,
            "i_rad": orb.mean.i_rad - MEAN_I,
            "e_vector": math.hypot(orb.mean.ex, orb.mean.ey),
            "avg_osculating_e_magnitude": orb.mean.e,
        },
        "remeasured_later_on_trajectory_max_abs": {
            "a_m": max(abs(x[0]) for x in later),
            "i_rad": max(abs(x[1]) for x in later),
            "e_vector": max(x[2] for x in later),
        },
        "geodetic_note": "altitude here is |r| - R_eq (not geodetic)",
        "radius_minus_req_range_km": [float(alt.min() / 1e3), float(alt.max() / 1e3)],
        "precession": {
            "measured_deg_per_day": math.degrees(rate) * DAY_S,
            "analytic_mean_deg_per_day": math.degrees(analytic) * DAY_S,
            "rel_diff_vs_analytic": (rate - analytic) / analytic,
            "sso_deg_per_day": math.degrees(SSO_RATE) * DAY_S,
            "rel_diff_vs_sso": (rate - SSO_RATE) / SSO_RATE,
        },
    }


def study_formation(fm: ForceModel) -> dict[str, Any]:
    out: dict[str, Any] = {}
    k_orbit = round(2 * math.pi / math.sqrt(GM_EARTH_M3PS2 / MEAN_A**3) / 10)
    for u0 in (0.0, 22.5, 45.0, 67.5, 90.0):
        t0 = time.perf_counter()
        members = mean_matched_formation(
            mean_a_m=MEAN_A,
            mean_i_rad=MEAN_I,
            raan_rad=0.0,
            u0_rad=math.radians(u0),
            n_spacecraft=4,
            spacing_m=20_000.0,
            forces=fm,
            epoch_utc=EPOCH,
        )
        init_s = time.perf_counter() - t0
        states = [CartesianState(Frame.GCRS, EPOCH, 0, m.r_m, m.v_mps) for m in members]
        y = propagate(states, step_ns=10 * NS, n_steps=3 * 8640, forces=fm).y
        sep = np.linalg.norm(y[:, 1:, :3] - y[:, :-1, :3], axis=2)
        avg = np.array(
            [sep[i : i + k_orbit].mean(axis=0) for i in range(0, len(sep) - k_orbit, k_orbit)]
        )
        trend = [float(np.polyfit(np.arange(len(avg)), avg[:, j], 1)[0]) for j in range(3)]
        out[f"u0_{u0:g}deg"] = {
            "iterations": [m.iterations for m in members],
            "init_time_s": init_s,
            "max_abs_mean_a_diff_vs_leader_m": max(
                abs(m.mean.a_m - members[0].mean.a_m) for m in members
            ),
            "secular_trend_m_per_orbit_max_abs": max(abs(x) for x in trend),
            "in_orbit_sep_swing_m_max": float(np.ptp(sep[:k_orbit], axis=0).max()),
            "mean_sep_first_orbit_m": avg[0].tolist(),
            "max_abs_sep_change_24h_m": float(np.max(np.abs(sep[:8641] - sep[0]))),
            "max_abs_sep_change_72h_m": float(np.max(np.abs(sep - sep[0]))),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    fm = ForceModel.with_j2(earth_pole_gcrs(EPOCH))
    result = {"reference_orbit": study_reference(fm), "formation": study_formation(fm)}
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

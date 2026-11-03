"""Reference-error studies for PA-06 (formation initialization) and PA-07 (CW).

Run:  uv run python scripts/studies/formation_cw_reference_errors.py [--out f.json]

Results are recorded in docs/NUMERICAL_MISSION_DESIGN.md §B.4; tolerances in
tests/physics_validation/test_formation.py and test_cw.py derive from them by
the approved rule (DL-019).

  S1  Elements round trips: state -> elements -> state (position/velocity,
      in units of eps*|r|, eps*|v|) and elements -> state -> elements.
  S2  Formation geometry at t0: adjacent chord vs 2a sin(du/2); follower RIC
      coordinates vs (-a(1-cos du), -a sin du, 0).
  S3  24 h RK4 (10 s) propagation of the 4-spacecraft formation: variation of
      adjacent separations and of follower RIC coordinates.
  S4  CW vs RK4 truth over one orbit: (a) error scaling with separation for
      random relative states; (b) the 20 km in-train case vs the analytic
      curvature-error prediction.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.elements import KeplerElements, rv_to_elements
from astramesh.dynamics.formation import along_track_formation
from astramesh.dynamics.frames import eci_to_ric, ric_to_eci
from astramesh.dynamics.relative import cw_propagate
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.twobody import Trajectory, propagate_two_body

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
NS = 10**9
STEP_NS = 10 * NS
EPS = float(np.finfo(np.float64).eps)
SPACING_M = 20_000.0
REFERENCE = KeplerElements.from_degrees(
    a_m=R_EARTH_EQ_M + 525e3, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=0.0
)
CW_HORIZON_S = 5700  # ~1 orbit (5708 s), a whole number of 10 s steps


def _wrap(x: float) -> float:
    return abs(math.remainder(x, 2 * math.pi))


def _random_elements(rng: np.random.Generator) -> KeplerElements:
    return KeplerElements(
        a_m=float(rng.uniform(R_EARTH_EQ_M + 200e3, R_EARTH_EQ_M + 2000e3)),
        e=float(rng.choice([0.0, rng.uniform(0.0, 0.02)])),
        i_rad=float(rng.choice([rng.uniform(0.01, 0.05), rng.uniform(0.01, math.pi - 0.01)])),
        raan_rad=float(rng.uniform(0, 2 * math.pi)),
        argp_rad=float(rng.uniform(0, 2 * math.pi)),
        nu_rad=float(rng.uniform(0, 2 * math.pi)),
    )


def study_elements(rng: np.random.Generator, n: int = 20_000) -> dict[str, float]:
    w: dict[str, float] = dict.fromkeys(
        ["pos_eps_r", "vel_eps_v", "a_rel", "e_abs", "i_rad", "raan_x_sin_i", "u_x_sin_i"], 0.0
    )
    for _ in range(n):
        el = _random_elements(rng)
        r, v = el.to_rv()
        back = rv_to_elements(r, v)
        r2, v2 = back.to_rv()
        w["pos_eps_r"] = max(w["pos_eps_r"], np.linalg.norm(r2 - r) / (EPS * np.linalg.norm(r)))
        w["vel_eps_v"] = max(w["vel_eps_v"], np.linalg.norm(v2 - v) / (EPS * np.linalg.norm(v)))
        w["a_rel"] = max(w["a_rel"], abs(back.a_m - el.a_m) / el.a_m)
        w["e_abs"] = max(w["e_abs"], abs(back.e - el.e))
        w["i_rad"] = max(w["i_rad"], abs(back.i_rad - el.i_rad))
        # Node direction has absolute error ~eps, so angles measured from the
        # node scale as eps / sin(i); record them multiplied by sin(i).
        sin_i = math.sin(el.i_rad)
        w["raan_x_sin_i"] = max(w["raan_x_sin_i"], _wrap(back.raan_rad - el.raan_rad) * sin_i)
        w["u_x_sin_i"] = max(
            w["u_x_sin_i"],
            _wrap(back.argp_rad + back.nu_rad - el.argp_rad - el.nu_rad) * sin_i,
        )
    return {"samples": n, **{k: float(x) for k, x in w.items()}}


def _formation_trajectory(n_steps: int) -> Trajectory:
    els = along_track_formation(REFERENCE, n_spacecraft=4, spacing_m=SPACING_M)
    states = [CartesianState(Frame.GCRS, EPOCH, 0, *el.to_rv()) for el in els]
    return propagate_two_body(states, step_ns=STEP_NS, n_steps=n_steps)


def _ric_series(traj: Trajectory, chief: int, deputy: int) -> np.ndarray:
    out = np.empty((len(traj.t_ns), 6))
    for k in range(len(traj.t_ns)):
        rel = eci_to_ric(traj.state(k, chief), traj.state(k, deputy))
        out[k, :3], out[k, 3:] = rel.r_m, rel.v_mps
    return out


def study_formation() -> dict[str, Any]:
    a = REFERENCE.a_m
    du = SPACING_M / a
    traj = _formation_trajectory(86_400 // 10)
    y = traj.y
    sep = np.linalg.norm(y[:, 1:, :3] - y[:, :-1, :3], axis=2)  # (n_times, 3 pairs)
    chord = 2 * a * math.sin(du / 2)
    expected_ric = np.array([-a * (1 - math.cos(du)), -a * math.sin(du), 0.0])
    ric = _ric_series(traj, 0, 1)  # 24 h series for the first pair
    t0_ric_err = max(
        float(np.linalg.norm(_ric_series(traj, k, k + 1)[0, :3] - expected_ric)) for k in range(3)
    )
    t0_ric_vel = max(float(np.linalg.norm(_ric_series(traj, k, k + 1)[0, 3:])) for k in range(3))
    return {
        "a_m": a,
        "du_rad": du,
        "expected_chord_m": chord,
        "expected_ric_m": expected_ric.tolist(),
        "t0_max_chord_err_m": float(np.max(np.abs(sep[0] - chord))),
        "t0_ric_err_m_all_pairs": t0_ric_err,
        "t0_ric_vel_m_s_all_pairs": t0_ric_vel,
        "24h_max_sep_change_m": float(np.max(np.abs(sep - sep[0]))),
        "24h_max_ric_pos_change_m": float(np.max(np.linalg.norm(ric[:, :3] - ric[0, :3], axis=1))),
        "24h_max_ric_vel_m_s": float(np.max(np.linalg.norm(ric[:, 3:], axis=1))),
    }


def _cw_error(chief: CartesianState, rel0: np.ndarray, n_rad: float) -> float:
    dep = ric_to_eci(chief, CartesianState(Frame.RIC, EPOCH, 0, rel0[:3], rel0[3:]))
    traj = propagate_two_body([chief, dep], step_ns=STEP_NS, n_steps=CW_HORIZON_S // 10)
    truth = _ric_series(traj, 0, 1)
    cw = cw_propagate(rel0, n_rad, traj.t_ns.astype(np.float64) / NS)
    return float(np.max(np.linalg.norm(cw[:, :3] - truth[:, :3], axis=1)))


def study_cw(rng: np.random.Generator, n_dirs: int = 20) -> dict[str, Any]:
    chief = CartesianState(Frame.GCRS, EPOCH, 0, *REFERENCE.to_rv())
    n_rad = REFERENCE.mean_motion_radps()
    rhos = [125.0, 250.0, 500.0, 1000.0, 2000.0, 20_000.0]
    dirs = []
    for _ in range(n_dirs):
        p = rng.normal(size=3)
        v = rng.normal(size=3)
        dirs.append((p / np.linalg.norm(p), v / np.linalg.norm(v)))
    errs = np.array(
        [
            [_cw_error(chief, np.concatenate((rho * p, rho * n_rad * v)), n_rad) for rho in rhos]
            for p, v in dirs
        ]
    )
    orders = [
        [math.log2(e2 / e1) for e1, e2 in itertools.pairwise(row[:5])] for row in errs
    ]  # successive doublings 125->...->2000
    # 20 km in-train: analytic CW-vs-truth difference is
    # dx = 3(1-c) x0, dy = 6(s - nt) x0 with x0 = -a(1-cos du).
    a = REFERENCE.a_m
    du = SPACING_M / a
    x0 = -a * (1 - math.cos(du))
    rel0 = np.array([x0, -a * math.sin(du), 0.0, 0.0, 0.0, 0.0])
    dep = ric_to_eci(chief, CartesianState(Frame.RIC, EPOCH, 0, rel0[:3], rel0[3:]))
    traj = propagate_two_body([chief, dep], step_ns=STEP_NS, n_steps=CW_HORIZON_S // 10)
    truth = _ric_series(traj, 0, 1)
    t = traj.t_ns.astype(np.float64) / NS
    cw = cw_propagate(rel0, n_rad, t)
    nt = n_rad * t
    predicted = np.stack(
        (3 * (1 - np.cos(nt)) * x0, 6 * (np.sin(nt) - nt) * x0, np.zeros_like(t)), axis=1
    )
    actual = cw[:, :3] - truth[:, :3]
    return {
        "horizon_s": CW_HORIZON_S,
        "rhos_m": rhos,
        "max_err_by_rho_m": errs.max(axis=0).tolist(),
        "min_err_by_rho_m": errs.min(axis=0).tolist(),
        "max_err_over_rho2_per_m": float(np.max(errs[:, :5] / np.array(rhos[:5]) ** 2)),
        "observed_orders_min": float(np.min(orders)),
        "observed_orders_max": float(np.max(orders)),
        "in_train_20km": {
            "x0_m": x0,
            "max_cw_error_m": float(np.max(np.linalg.norm(actual, axis=1))),
            "final_cw_error_m": float(np.linalg.norm(actual[-1])),
            "max_residual_vs_analytic_m": float(np.max(np.linalg.norm(actual - predicted, axis=1))),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    rng = np.random.default_rng(31415)
    result = {
        "elements_round_trip": study_elements(rng),
        "formation": study_formation(),
        "cw": study_cw(rng),
    }
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

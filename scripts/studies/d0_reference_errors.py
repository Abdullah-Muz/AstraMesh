"""Reference-error studies for the D0 physics acceptance tests (PA-01 … PA-04).

Run:  uv run python scripts/studies/d0_reference_errors.py [--out study.json]

Results are recorded in docs/NUMERICAL_MISSION_DESIGN.md §B.2, and the
tolerances in tests/physics_validation/tolerances.py are derived from them
(spec §4.4: tolerances come from independent reference-error studies).

Studies:
  S1  Analytic-reference agreement: universal-variable Kepler (one jump from t0)
      vs Kepler's-equation element advance vs chained 10 s universal-variable
      jumps. Their mutual disagreement bounds the reference's own error.
  S2  RK4 error vs step size against the analytic reference (24 h), and the
      observed order of convergence.
  S3  Invariant drift (energy, angular momentum) for RK4 at each step size.
  S4  RIC round-trip round-off for randomized chief/deputy states.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from astramesh.dynamics.constants import GM_EARTH_M3PS2, R_EARTH_EQ_M
from astramesh.dynamics.elements import KeplerElements
from astramesh.dynamics.frames import eci_to_ric, ric_to_eci
from astramesh.dynamics.kepler import kepler_propagate
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.twobody import (
    propagate_two_body,
    specific_angular_momentum,
    specific_energy,
)

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
HORIZON_S = 86_400
STEPS_NS = (80 * 10**9, 40 * 10**9, 20 * 10**9, 10 * 10**9, 5 * 10**9, 2_500_000_000, 1_250_000_000)
NS = 1_000_000_000

# Must match CASES in tests/physics_validation/test_two_body.py
CASES: dict[str, KeplerElements] = {
    "ref_525km_circular": KeplerElements.from_degrees(
        a_m=R_EARTH_EQ_M + 525e3, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=0.0
    ),
    "eccentric_e0.1": KeplerElements.from_degrees(
        a_m=8_000e3, e=0.1, i_deg=51.6, raan_deg=40.0, argp_deg=30.0, nu_deg=10.0
    ),
}


def _state(el: KeplerElements) -> CartesianState:
    r, v = el.to_rv()
    return CartesianState(Frame.GCRS, EPOCH, 0, r, v)


def _reference(el: KeplerElements, times_s: np.ndarray) -> np.ndarray:
    r0, v0 = el.to_rv()
    out = np.empty((len(times_s), 6))
    for k, t in enumerate(times_s):
        r, v = kepler_propagate(r0, v0, float(t))
        out[k, :3], out[k, 3:] = r, v
    return out


def study_reference(el: KeplerElements) -> dict[str, float]:
    times = np.arange(0, HORIZON_S + 1, 600, dtype=np.float64)
    uv = _reference(el, times)
    elem = np.empty_like(uv)
    for k, t in enumerate(times):
        r, v = el.advanced(float(t)).to_rv()
        elem[k, :3], elem[k, 3:] = r, v
    # chained 10 s jumps
    r, v = el.to_rv()
    chained = np.empty_like(uv)
    chained[0, :3], chained[0, 3:] = r, v
    idx = 1
    for step in range(1, HORIZON_S // 10 + 1):
        r, v = kepler_propagate(r, v, 10.0)
        if step * 10 == times[idx]:
            chained[idx, :3], chained[idx, 3:] = r, v
            idx += 1
            if idx == len(times):
                break
    d_elem = uv - elem
    d_chain = uv - chained
    return {
        "max_pos_diff_uv_vs_elements_m": float(np.max(np.linalg.norm(d_elem[:, :3], axis=1))),
        "max_vel_diff_uv_vs_elements_mps": float(np.max(np.linalg.norm(d_elem[:, 3:], axis=1))),
        "max_pos_diff_uv_vs_chained10s_m": float(np.max(np.linalg.norm(d_chain[:, :3], axis=1))),
        "max_vel_diff_uv_vs_chained10s_mps": float(np.max(np.linalg.norm(d_chain[:, 3:], axis=1))),
    }


def study_integrator(el: KeplerElements) -> dict[str, Any]:
    rows = []
    s0 = _state(el)
    for step_ns in STEPS_NS:
        n = HORIZON_S * NS // step_ns
        traj = propagate_two_body([s0], step_ns=step_ns, n_steps=n)
        y = traj.y[:, 0, :]
        ref = _reference(el, traj.t_ns.astype(np.float64) / NS)
        dpos = np.linalg.norm(y[:, :3] - ref[:, :3], axis=1)
        dvel = np.linalg.norm(y[:, 3:] - ref[:, 3:], axis=1)
        e = specific_energy(y, GM_EARTH_M3PS2)
        h = specific_angular_momentum(y)
        rows.append(
            {
                "step_s": step_ns / NS,
                "max_pos_err_m": float(dpos.max()),
                "final_pos_err_m": float(dpos[-1]),
                "max_vel_err_mps": float(dvel.max()),
                "max_rel_energy_drift": float(np.max(np.abs((e - e[0]) / e[0]))),
                "max_rel_angmom_drift": float(
                    np.max(np.linalg.norm(h - h[0], axis=1) / np.linalg.norm(h[0]))
                ),
            }
        )
    for a, b in itertools.pairwise(rows):
        b["observed_order_pos_vs_prev"] = math.log2(a["final_pos_err_m"] / b["final_pos_err_m"])
        b["observed_order_energy_vs_prev"] = math.log2(
            a["max_rel_energy_drift"] / b["max_rel_energy_drift"]
        )
    return {"rows": rows}


def study_ric_roundoff(n: int = 20_000, seed: int = 12345) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    eps = float(np.finfo(np.float64).eps)
    worst_r, worst_v, worst_rel_r, worst_rel_v = 0.0, 0.0, 0.0, 0.0
    for _ in range(n):
        el = KeplerElements(
            a_m=float(rng.uniform(R_EARTH_EQ_M + 200e3, R_EARTH_EQ_M + 2000e3)),
            e=float(rng.uniform(0.0, 0.02)),  # periapsis stays > 6378 km + ~60 km
            i_rad=float(rng.uniform(0.0, math.pi)),
            raan_rad=float(rng.uniform(0.0, 2 * math.pi)),
            argp_rad=float(rng.uniform(0.0, 2 * math.pi)),
            nu_rad=float(rng.uniform(0.0, 2 * math.pi)),
        )
        rc, vc = el.to_rv()
        chief = CartesianState(Frame.GCRS, EPOCH, 0, rc, vc)
        dep = CartesianState(
            Frame.GCRS,
            EPOCH,
            0,
            rc + rng.uniform(-100e3, 100e3, 3),
            vc + rng.uniform(-100.0, 100.0, 3),
        )
        back = ric_to_eci(chief, eci_to_ric(chief, dep))
        er = float(np.linalg.norm(back.r_m - dep.r_m))
        ev = float(np.linalg.norm(back.v_mps - dep.v_mps))
        worst_r, worst_v = max(worst_r, er), max(worst_v, ev)
        worst_rel_r = max(worst_rel_r, er / (eps * float(np.linalg.norm(rc))))
        worst_rel_v = max(worst_rel_v, ev / (eps * float(np.linalg.norm(vc))))
    return {
        "samples": n,
        "max_pos_roundtrip_err_m": worst_r,
        "max_vel_roundtrip_err_mps": worst_v,
        "max_pos_err_in_eps_times_chief_r": worst_rel_r,
        "max_vel_err_in_eps_times_chief_v": worst_rel_v,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    result: dict[str, Any] = {
        "platform": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "machine": platform.machine(),
            "system": platform.platform(),
        },
        "horizon_s": HORIZON_S,
        "cases": {},
        "ric_roundoff": study_ric_roundoff(),
    }
    for name, el in CASES.items():
        result["cases"][name] = {
            "period_s": el.period_s(),
            "reference": study_reference(el),
            "integrator": study_integrator(el),
        }
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

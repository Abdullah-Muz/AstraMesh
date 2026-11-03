"""Reference studies for D1 (point mass + J2): PA-08 and open questions 1-2.

Run:  uv run python scripts/studies/j2_reference_errors.py [--out j2.json]

Results are recorded in docs/NUMERICAL_MISSION_DESIGN.md §B.5 and Part A;
tolerances in tests/physics_validation/test_j2.py derive from them (DL-019).

  S1  J2 acceleration vs central finite difference of the J2 potential
      (independent check of the acceleration formula and its sign).
  S2  Invariants with J2 (fixed pole): energy v^2/2 - V and the angular
      momentum component along the pole; RK4 step convergence against a
      1.25 s solution.
  S3  Nodal precession: secular RAAN rate (about the pole) fitted over 24 h vs
      the first-order analytic J2 rate; sun-synchronous target comparison;
      inclination needed for sun-synchrony at 525 km.
  S4  The 20 km formation under J2 with equal *osculating* elements: mean
      semi-major axes and along-track separation drift over 24 h.
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

from astramesh.dynamics.constants import GM_EARTH_M3PS2, J2_EARTH, R_EARTH_EQ_M
from astramesh.dynamics.earth_frames import earth_pole_gcrs
from astramesh.dynamics.elements import KeplerElements, rv_to_elements
from astramesh.dynamics.forces import ForceModel, acceleration, potential, specific_energy
from astramesh.dynamics.formation import along_track_formation
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.twobody import Trajectory, propagate

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
NS = 10**9
DAY_S = 86_400
SSO_RATE_RADPS = 2 * math.pi / (365.2421897 * DAY_S)  # mean Sun motion (tropical year)
REFERENCE = KeplerElements.from_degrees(
    a_m=R_EARTH_EQ_M + 525e3, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=0.0
)
ECCENTRIC = KeplerElements.from_degrees(
    a_m=8_000e3, e=0.1, i_deg=51.6, raan_deg=40.0, argp_deg=30.0, nu_deg=10.0
)


def pole_frame(pole: tuple[float, float, float]) -> np.ndarray:
    """Rotation whose rows are (x', y', pole): x' is GCRS x projected on the equator."""
    p = np.array(pole)
    x = np.array([1.0, 0.0, 0.0]) - p[0] * p
    x /= np.linalg.norm(x)
    return np.stack((x, np.cross(p, x), p))


def _propagate(
    els: list[KeplerElements], fm: ForceModel, step_s: float, horizon_s: int
) -> Trajectory:
    step_ns = round(step_s * NS)
    states = [CartesianState(Frame.GCRS, EPOCH, 0, *el.to_rv()) for el in els]
    return propagate(states, step_ns=step_ns, n_steps=horizon_s * NS // step_ns, forces=fm)


def j2_potential_only(r: np.ndarray, pole: np.ndarray) -> float:
    """J2 part of V, written independently: -mu/r * J2 (R/r)^2 * P2(sin phi)."""
    rn = float(np.linalg.norm(r))
    s = float(r @ pole) / rn
    return -GM_EARTH_M3PS2 / rn * J2_EARTH * (R_EARTH_EQ_M / rn) ** 2 * 0.5 * (3 * s * s - 1)


def study_gradient(fm: ForceModel, rng: np.random.Generator, n: int = 5000) -> dict[str, float]:
    point = ForceModel.two_body()
    pole = np.array(fm.pole)
    worst = 0.0
    h = 10.0  # m: truncation ~ (h/r)^2 ~ 2e-12; round-off ~ eps*V_J2/h
    for _ in range(n):
        d = rng.normal(size=3)
        r = d / np.linalg.norm(d) * rng.uniform(R_EARTH_EQ_M + 200e3, R_EARTH_EQ_M + 2000e3)
        a_j2 = acceleration(r[None], fm)[0] - acceleration(r[None], point)[0]
        grad = np.empty(3)
        for k in range(3):
            e = np.zeros(3)
            e[k] = h
            grad[k] = (j2_potential_only(r + e, pole) - j2_potential_only(r - e, pole)) / (2 * h)
        worst = max(worst, float(np.linalg.norm(grad - a_j2) / np.linalg.norm(a_j2)))
    # Consistency of forces.potential with the independent expression.
    r = np.array([4e6, 3e6, 4.5e6])
    pot_diff = abs(
        (potential(r[None], fm)[0] - potential(r[None], point)[0]) - j2_potential_only(r, pole)
    ) / abs(j2_potential_only(r, pole))
    return {
        "samples": n,
        "fd_step_m": h,
        "max_rel_err_j2_accel_vs_fd_gradient": worst,
        "rel_diff_potential_vs_independent_expr": float(pot_diff),
    }


def study_invariants(fm: ForceModel) -> dict[str, Any]:
    out: dict[str, Any] = {}
    p = np.array(fm.pole)
    for name, el in (("ref_525km_circular", REFERENCE), ("eccentric_e0.1", ECCENTRIC)):
        fine = _propagate([el], fm, 1.25, DAY_S).y[:, 0, :]
        rows = []
        for step in (20.0, 10.0, 5.0):
            y = _propagate([el], fm, step, DAY_S).y[:, 0, :]
            stride = round(step / 1.25)
            err = np.linalg.norm(y[:, :3] - fine[::stride, :3], axis=1)
            e = specific_energy(y, fm)
            hz = np.cross(y[:, :3], y[:, 3:]) @ p
            rows.append(
                {
                    "step_s": step,
                    "max_pos_err_vs_1.25s_m": float(err.max()),
                    "final_pos_err_vs_1.25s_m": float(err[-1]),
                    "max_rel_energy_drift": float(np.max(np.abs((e - e[0]) / e[0]))),
                    "max_rel_hpole_drift": float(np.max(np.abs((hz - hz[0]) / hz[0]))),
                }
            )
        for a, b in itertools.pairwise(rows):
            b["observed_order"] = math.log2(
                a["final_pos_err_vs_1.25s_m"] / b["final_pos_err_vs_1.25s_m"]
            )
        # Richardson form used by the test (no 1.25 s run): successive differences.
        ys = {st: _propagate([el], fm, st, DAY_S).y[:, 0, :3] for st in (20.0, 10.0, 5.0)}
        d1 = np.linalg.norm(ys[20.0] - ys[10.0][::2], axis=1)
        d2 = np.linalg.norm(ys[10.0] - ys[5.0][::2], axis=1)
        out[name + "_richardson"] = {
            "max_diff_10s_vs_5s_m": float(d2.max()),
            "observed_order_from_differences": math.log2(float(d1[-1]) / float(d2[-1])),
        }
        out[name] = rows
    return out


def secular_raan_rate(traj: Trajectory, sc: int, rot: np.ndarray) -> tuple[float, float, float]:
    """Least-squares RAAN rate about the pole, plus mean a and mean i."""
    y = traj.y[:, sc, :]
    t = traj.t_ns.astype(np.float64) / NS
    raan, a, inc = [], [], []
    for k in range(0, len(t)):
        el = rv_to_elements(rot @ y[k, :3], rot @ y[k, 3:])
        raan.append(el.raan_rad)
        a.append(el.a_m)
        inc.append(el.i_rad)
    raan_u = np.unwrap(np.array(raan))
    slope = float(np.polyfit(t, raan_u, 1)[0])
    return slope, float(np.mean(a)), float(np.mean(inc))


def analytic_raan_rate(a: float, e: float, i: float) -> float:
    n = math.sqrt(GM_EARTH_M3PS2 / a**3)
    p = a * (1 - e * e)
    return -1.5 * n * J2_EARTH * (R_EARTH_EQ_M / p) ** 2 * math.cos(i)


def study_precession(fm: ForceModel) -> dict[str, Any]:
    rot = pole_frame(fm.pole)
    res: dict[str, Any] = {}
    for name, el in (("ref_525km_circular", REFERENCE), ("eccentric_e0.1", ECCENTRIC)):
        traj = _propagate([el], fm, 10.0, DAY_S)
        rate, a_mean, i_mean = secular_raan_rate(traj, 0, rot)
        an_mean = analytic_raan_rate(a_mean, el.e, i_mean)
        an_osc0 = analytic_raan_rate(el.a_m, el.e, el.i_rad)
        res[name] = {
            "measured_raan_rate_deg_per_day": math.degrees(rate) * DAY_S,
            "analytic_rate_mean_elements_deg_per_day": math.degrees(an_mean) * DAY_S,
            "analytic_rate_initial_osculating_deg_per_day": math.degrees(an_osc0) * DAY_S,
            "rel_diff_vs_analytic_mean": (rate - an_mean) / an_mean,
            "rel_diff_vs_analytic_osc0": (rate - an_osc0) / an_osc0,
            "mean_a_minus_osc_a0_m": a_mean - el.a_m,
            "mean_i_minus_osc_i0_deg": math.degrees(i_mean - el.i_rad),
        }
    ref = res["ref_525km_circular"]
    sso_deg_day = math.degrees(SSO_RATE_RADPS) * DAY_S
    ref["sso_target_deg_per_day"] = sso_deg_day
    ref["measured_minus_sso_deg_per_day"] = ref["measured_raan_rate_deg_per_day"] - sso_deg_day
    # Inclination for sun-synchrony at the measured mean semi-major axis (first order).
    traj = _propagate([REFERENCE], fm, 10.0, DAY_S)
    _, a_mean, _ = secular_raan_rate(traj, 0, rot)
    n = math.sqrt(GM_EARTH_M3PS2 / a_mean**3)
    cos_i = -SSO_RATE_RADPS / (1.5 * n * J2_EARTH * (R_EARTH_EQ_M / a_mean) ** 2)
    ref["sso_inclination_deg_at_mean_a"] = math.degrees(math.acos(cos_i))
    # If 525 km is read as the *mean* altitude instead:
    a525 = R_EARTH_EQ_M + 525e3
    n525 = math.sqrt(GM_EARTH_M3PS2 / a525**3)
    cos_i525 = -SSO_RATE_RADPS / (1.5 * n525 * J2_EARTH * (R_EARTH_EQ_M / a525) ** 2)
    ref["sso_inclination_deg_if_525km_is_mean_altitude"] = math.degrees(math.acos(cos_i525))
    ref["rate_deg_per_day_if_525km_97.5deg_are_mean"] = (
        math.degrees(analytic_raan_rate(a525, 0.0, math.radians(97.5))) * DAY_S
    )
    return res


def study_formation(fm: ForceModel) -> dict[str, Any]:
    rot = pole_frame(fm.pole)
    els = list(along_track_formation(REFERENCE, n_spacecraft=4, spacing_m=20_000.0))
    traj = _propagate(els, fm, 10.0, DAY_S)
    y = traj.y
    sep = np.linalg.norm(y[:, 1:, :3] - y[:, :-1, :3], axis=2)
    mean_a = [secular_raan_rate(traj, k, rot)[1] for k in range(4)]
    two_body = _propagate(els, ForceModel.two_body(), 10.0, DAY_S).y
    sep2 = np.linalg.norm(two_body[:, 1:, :3] - two_body[:, :-1, :3], axis=2)
    return {
        "initial_sep_m": sep[0].tolist(),
        "sep_after_24h_m": sep[-1].tolist(),
        "max_abs_sep_change_24h_m": float(np.max(np.abs(sep - sep[0]))),
        "sep_change_per_orbit_trend_m": [
            float(np.polyfit(traj.t_ns / NS, sep[:, k], 1)[0] * REFERENCE.period_s())
            for k in range(3)
        ],
        "mean_a_m": mean_a,
        "mean_a_minus_leader_m": [m - mean_a[0] for m in mean_a],
        "two_body_max_abs_sep_change_24h_m": float(np.max(np.abs(sep2 - sep2[0]))),
        "by_start_argument_of_latitude": _formation_by_start_u(fm),
    }


def _formation_by_start_u(fm: ForceModel) -> dict[str, Any]:
    """Equal osculating elements; the drift depends on where the formation starts."""
    out: dict[str, Any] = {}
    for u0 in (0.0, 22.5, 45.0, 67.5, 90.0):
        ref = KeplerElements.from_degrees(
            a_m=REFERENCE.a_m, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=u0
        )
        els = list(along_track_formation(ref, n_spacecraft=4, spacing_m=20_000.0))
        y = _propagate(els, fm, 10.0, DAY_S).y
        sep = np.linalg.norm(y[:, 1:, :3] - y[:, :-1, :3], axis=2)
        out[f"u0_{u0:g}deg"] = {
            "max_abs_sep_change_24h_m": float(np.max(np.abs(sep - sep[0]))),
            "sep_after_24h_m": sep[-1].tolist(),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    pole = earth_pole_gcrs(EPOCH)
    fm = ForceModel.with_j2(pole)
    rng = np.random.default_rng(2718)
    result = {
        "j2": J2_EARTH,
        "pole_gcrs": list(pole),
        "gradient": study_gradient(fm, rng),
        "invariants_and_convergence": study_invariants(fm),
        "precession": study_precession(fm),
        "formation_under_j2": study_formation(fm),
    }
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

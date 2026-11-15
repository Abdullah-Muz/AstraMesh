"""Basilisk cross-check of the truth dynamics (DL-116 design, DL-117 code).

Three steps, the middle one in the separate ``tools/basilisk`` environment:

    uv run --locked python scripts/experiments/basilisk_comparison.py cases --out <dir>
    uv run --locked --project tools/basilisk python tools/basilisk/propagate.py <dir>
    uv run --locked python scripts/experiments/basilisk_comparison.py compare --out <dir>

``cases`` writes ``cases.json`` (constants, initial states, density table, step) and
AstraMesh's trajectories (``astramesh.npz``). ``compare`` reads both sides and writes
``basilisk_comparison.csv`` (every measure with its tolerance), ``basilisk_daily.csv``
(differences at each whole day) and ``basilisk_comparison_meta.json``.

Common setup (DL-116): AstraMesh's constants; the initial GCRS states of sc00 and sc01 of
the 20 km formation (``formation_24h_j2.yaml``, mean-element initialization); 8 days;
fixed-step RK4 at 10 s in both. Cases:

* K1 two-body (also against the analytic Kepler reference, one jump from t0);
* K2 J2 with the pole on GCRS z;
* K3 J2 + drag on sc00, matched: USSA 1976 on the spherical altitude |r| - R (AstraMesh
  through ``density_fn``; Basilisk through a table of AstraMesh's density every 100 m,
  480 - 700 km), atmosphere co-rotating about z, B = 0.0092 m^2/kg (DL-080);
* K4 sc00 and sc01 under the K3 models, sc01 with B + 20 % (DL-083): their spacing;
* M1 (reported only): AstraMesh's production model (ellipsoidal altitude, pole at the
  epoch) for the K3 / K4 spacecraft, and Basilisk RKF78 at tight tolerance on K2 and K3.

Tolerances (DL-116, fixed before any run): T1 K1 and K2, max |dr| <= 1 m and max |dv| <=
1e-3 m/s; T2 K3, max |dr| <= 0.5 % of drag's own effect (max |r_K3 - r_K2|); T3 K4, max
|d spacing| <= 0.5 % of the spacing change (max |s(t) - s(0)|).
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import yaml

from astramesh.core.config import FormationScenarioBase, parse_scenario
from astramesh.core.events import EventLog
from astramesh.dynamics.constants import (
    C20_NORMALIZED_EGM2008,
    GM_EARTH_M3PS2,
    J2_EARTH,
    OMEGA_EARTH_RADPS,
    R_EARTH_EQ_M,
)
from astramesh.dynamics.drag import DragModel, density
from astramesh.dynamics.earth_frames import earth_pole_gcrs
from astramesh.dynamics.forces import ForceModel
from astramesh.dynamics.kepler import kepler_propagate
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.twobody import propagate
from astramesh.scenarios.formation_dynamics import run_formation_dynamics

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "configs" / "experiments" / "formation_24h_j2.yaml"
TOOLS_LOCK = ROOT / "tools" / "basilisk" / "uv.lock"
B = 0.0092  # DL-080 nominal [m^2/kg]
B_SC01 = 1.2 * B  # DL-083 credible spread
STEP_S = 10
DURATION_S = 8 * 86_400
TABLE_STEP_M = 100.0
TABLE_RANGE_M = (480e3, 700e3)
POLE_Z = (0.0, 0.0, 1.0)
RKF78 = {"rel_tol": 1e-12, "abs_tol": 1e-9}
T1_DR_M, T1_DV_MPS = 1.0, 1e-3
T2_FRACTION = T3_FRACTION = 0.005
CASES = (  # name, gravity, drag, integrator, spacecraft (indices into sc00, sc01)
    ("K1", "point_mass", False, "rk4", (0,)),
    ("K2", "j2", False, "rk4", (0,)),
    ("K3", "j2", True, "rk4", (0,)),
    ("K4", "j2", True, "rk4", (0, 1)),
    ("K2_rkf78", "j2", False, "rkf78", (0,)),
    ("K3_rkf78", "j2", True, "rkf78", (0,)),
)
BALLISTIC = (B, B_SC01)


def density_table() -> dict[str, list[float]]:
    """AstraMesh's USSA 1976 density (log-interpolated) sampled every 100 m."""
    lo, hi = TABLE_RANGE_M
    h = lo + TABLE_STEP_M * np.arange(round((hi - lo) / TABLE_STEP_M) + 1)
    return {"alt_m": h.tolist(), "rho_kgpm3": density(h).tolist()}


def spherical_density(r: npt.NDArray[np.float64], t_s: float) -> npt.NDArray[np.float64]:
    """USSA 1976 on the spherical altitude |r| - R (Basilisk's altitude), any time."""
    out: npt.NDArray[np.float64] = density(np.linalg.norm(r, axis=-1) - R_EARTH_EQ_M)
    return out


def production_config(duration_s: int = DURATION_S) -> FormationScenarioBase:
    raw: dict[str, Any] = copy.deepcopy(yaml.safe_load(BASE.read_text()))
    raw["time"]["duration_s"] = duration_s
    raw["output"]["trajectory_sample_interval_s"] = STEP_S
    raw["dynamics"]["drag"] = {"ballistic_m2pkg": [B, B_SC01, B, B]}
    cfg = parse_scenario(raw)
    assert isinstance(cfg, FormationScenarioBase)
    return cfg


def force_model(gravity: str, drag: bool, ballistic: tuple[float, ...]) -> ForceModel:
    """Matched AstraMesh model of a case (pole on GCRS z, spherical-altitude density)."""
    j2 = J2_EARTH if gravity == "j2" else 0.0
    d = DragModel(ballistic, density_fn=spherical_density) if drag else None
    return ForceModel(mu=GM_EARTH_M3PS2, j2=j2, pole=POLE_Z, drag=d)


def case_doc(y0: npt.NDArray[np.float64], duration_s: int = DURATION_S) -> dict[str, Any]:
    """The case file for both sides; ``y0`` holds the sc00 and sc01 GCRS states."""
    return {
        "decision": "DL-116",
        "constants": {"mu": GM_EARTH_M3PS2, "r_ref_m": R_EARTH_EQ_M,
                      "c20_normalized": C20_NORMALIZED_EGM2008, "j2": J2_EARTH,
                      "omega_radps": OMEGA_EARTH_RADPS},
        "step_s": STEP_S, "duration_s": duration_s, "n_steps": duration_s // STEP_S,
        "rkf78": RKF78,
        "density_table": density_table(),
        "cases": [{"name": n, "gravity": g, "drag": d, "integrator": i,
                   "spacecraft": [{"r_m": y0[k, :3].tolist(), "v_mps": y0[k, 3:].tolist(),
                                   "ballistic_m2pkg": BALLISTIC[k]} for k in idx]}
                  for n, g, d, i, idx in CASES],
    }  # fmt: skip


def astramesh_runs(doc: dict[str, Any], epoch: Any) -> dict[str, npt.NDArray[np.float64]]:
    """AstraMesh RK4 on every rk4 case, plus the K1 Kepler reference."""
    out: dict[str, npt.NDArray[np.float64]] = {}
    step_ns, n = doc["step_s"] * 10**9, doc["n_steps"]
    for case in doc["cases"]:
        if case["integrator"] != "rk4":
            continue
        scs = case["spacecraft"]
        states = [CartesianState(Frame.GCRS, epoch, 0, s["r_m"], s["v_mps"]) for s in scs]
        fm = force_model(case["gravity"], case["drag"],
                         tuple(s["ballistic_m2pkg"] for s in scs))  # fmt: skip
        out[case["name"]] = np.array(propagate(states, step_ns=step_ns, n_steps=n, forces=fm).y)
    s0 = doc["cases"][0]["spacecraft"][0]
    kep = np.empty((n + 1, 1, 6))
    for k in range(n + 1):
        r, v = kepler_propagate(s0["r_m"], s0["v_mps"], float(k * doc["step_s"]))
        kep[k, 0, :3], kep[k, 0, 3:] = r, v
    out["K1_kepler"] = kep
    return out


def max_diff(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> tuple[float, float]:
    """Largest position [m] and velocity [m/s] difference over steps and spacecraft."""
    d = a - b
    return (float(np.linalg.norm(d[..., :3], axis=-1).max()),
            float(np.linalg.norm(d[..., 3:], axis=-1).max()))  # fmt: skip


def spacing(y: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Distance between spacecraft 0 and 1 at every step [m]."""
    out: npt.NDArray[np.float64] = np.linalg.norm(y[:, 1, :3] - y[:, 0, :3], axis=-1)
    return out


def measures(am: dict[str, npt.NDArray[np.float64]],
             bsk: dict[str, npt.NDArray[np.float64]]) -> list[dict[str, Any]]:  # fmt: skip
    """Every DL-116 measure; ``tolerance`` and ``passed`` only on T1 - T3."""
    rows: list[dict[str, Any]] = []

    def add(case: str, quantity: str, value: float, tol: float | None = None,
            test: str = "") -> None:  # fmt: skip
        passed = None if tol is None else value <= tol
        rows.append({"case": case, "quantity": quantity, "value": value, "test": test,
                     "tolerance": tol, "passed": passed})  # fmt: skip

    for c in ("K1", "K2"):
        dr, dv = max_diff(am[c], bsk[c])
        add(c, "max |dr| AstraMesh - Basilisk [m]", dr, T1_DR_M, "T1")
        add(c, "max |dv| AstraMesh - Basilisk [m/s]", dv, T1_DV_MPS, "T1")
    for side, y in (("AstraMesh", am["K1"]), ("Basilisk", bsk["K1"])):
        dr, dv = max_diff(y, am["K1_kepler"])
        add("K1", f"max |dr| {side} - Kepler [m]", dr)
        add("K1", f"max |dv| {side} - Kepler [m/s]", dv)
    effect = max_diff(am["K3"], am["K2"])[0]
    dr3 = max_diff(am["K3"], bsk["K3"])[0]
    add("K3", "drag effect max |r_K3 - r_K2| (AstraMesh) [m]", effect)
    add("K3", "max |dr| AstraMesh - Basilisk [m]", dr3)
    add("K3", "max |dr| / drag effect", dr3 / effect, T2_FRACTION, "T2")
    add("K3", "max |dv| AstraMesh - Basilisk [m/s]", max_diff(am["K3"], bsk["K3"])[1])
    s_am, s_bsk = spacing(am["K4"]), spacing(bsk["K4"])
    change = float(np.abs(s_am - s_am[0]).max())
    ds = float(np.abs(s_am - s_bsk).max())
    add("K4", "spacing change max |s(t) - s(0)| (AstraMesh) [m]", change)
    add("K4", "max |d spacing| AstraMesh - Basilisk [m]", ds)
    add("K4", "max |d spacing| / spacing change", ds / change, T3_FRACTION, "T3")
    add("K4", "max |dr| AstraMesh - Basilisk, both spacecraft [m]",
        max_diff(am["K4"], bsk["K4"])[0])  # fmt: skip
    add("M1", "K3: max |dr| production AstraMesh - Basilisk [m]",
        max_diff(am["production"][:, :1], bsk["K3"])[0])  # fmt: skip
    add("M1", "K3: max |dr| production - matched AstraMesh [m]",
        max_diff(am["production"][:, :1], am["K3"])[0])  # fmt: skip
    add("M1", "K4: max |d spacing| production AstraMesh - Basilisk [m]",
        float(np.abs(spacing(am["production"][:, :2]) - s_bsk).max()))  # fmt: skip
    add("M1", "K4: spacing change, production AstraMesh [m]",
        float(np.abs(spacing(am["production"][:, :2]) - s_am[0]).max()))  # fmt: skip
    for c in ("K2", "K3"):
        add("M1", f"{c}: max |dr| Basilisk RK4 - RKF78 [m]", max_diff(bsk[c], bsk[f"{c}_rkf78"])[0])
        add("M1", f"{c}: max |dr| AstraMesh RK4 - Basilisk RKF78 [m]",
            max_diff(am[c], bsk[f"{c}_rkf78"])[0])  # fmt: skip
    return rows


def daily(am: dict[str, npt.NDArray[np.float64]], bsk: dict[str, npt.NDArray[np.float64]],
          steps_per_day: int) -> list[dict[str, Any]]:  # fmt: skip
    """Position (spacing for K4) differences at each whole day [m]."""
    out = []
    for k in range(0, len(am["K1"]), steps_per_day):
        row: dict[str, Any] = {"day": k // steps_per_day}
        for c in ("K1", "K2", "K3"):
            row[f"{c}_dr_m"] = float(np.linalg.norm(am[c][k, 0, :3] - bsk[c][k, 0, :3]))
        row["K3_drag_effect_m"] = float(np.linalg.norm(am["K3"][k, 0, :3] - am["K2"][k, 0, :3]))
        row["K4_spacing_m"] = float(spacing(am["K4"][k : k + 1])[0])
        row["K4_d_spacing_m"] = float(
            (spacing(am["K4"][k : k + 1]) - spacing(bsk["K4"][k : k + 1]))[0])  # fmt: skip
        row["production_K3_dr_m"] = float(
            np.linalg.norm(am["production"][k, 0, :3] - bsk["K3"][k, 0, :3]))  # fmt: skip
        out.append(row)
    return out


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def cmd_cases(out: Path) -> None:
    t0 = time.perf_counter()
    cfg = production_config()
    run = run_formation_dynamics(cfg, EventLog())
    y = np.array(run.trajectory.y)
    doc = case_doc(y[0, :2])
    raw = json.dumps(doc, indent=1) + "\n"
    (out / "cases.json").write_text(raw)
    am = astramesh_runs(doc, cfg.time.epoch_utc)
    am["production"] = y[:, :2]
    np.savez(out / "astramesh.npz", **am)
    info = {"production_config_hash": cfg.config_hash(), "epoch_utc": str(cfg.time.epoch_utc),
            "production_pole_gcrs": list(earth_pole_gcrs(cfg.time.epoch_utc)),
            "cases_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "wall_s": round(time.perf_counter() - t0, 1)}  # fmt: skip
    (out / "astramesh_meta.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info))


def cmd_compare(out: Path) -> None:
    from astramesh.evaluation.manifest import git_state

    doc = json.loads((out / "cases.json").read_text())
    am = dict(np.load(out / "astramesh.npz"))
    bsk = dict(np.load(out / "basilisk.npz"))
    am_meta = json.loads((out / "astramesh_meta.json").read_text())
    bsk_meta = json.loads((out / "basilisk_meta.json").read_text())
    if bsk_meta["cases_sha256"] != am_meta["cases_sha256"]:
        raise ValueError("Basilisk ran a different cases.json")
    rows = measures(am, bsk)
    _write(out / "basilisk_comparison.csv", rows)
    _write(out / "basilisk_daily.csv", daily(am, bsk, 86_400 // doc["step_s"]))
    git = git_state(ROOT)
    meta = {
        "experiment": "Basilisk cross-check of the truth dynamics (DL-116)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "tools_lockfile_sha256": hashlib.sha256(TOOLS_LOCK.read_bytes()).hexdigest(),
        "basilisk": bsk_meta, "astramesh": am_meta,
        "tolerances": {"T1_dr_m": T1_DR_M, "T1_dv_mps": T1_DV_MPS,
                       "T2_fraction": T2_FRACTION, "T3_fraction": T3_FRACTION},
        "passed": {f"{r['test']} {r['case']} {r['quantity']}": r["passed"]
                   for r in rows if r["test"]},
        "all_passed": all(r["passed"] for r in rows if r["test"]),
    }  # fmt: skip
    if meta["tools_lockfile_sha256"] != bsk_meta["tools_lockfile_sha256"]:
        raise ValueError("tools/basilisk/uv.lock changed since the Basilisk run")
    (out / "basilisk_comparison_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for r in rows:
        print(r)
    print(json.dumps({"all_passed": meta["all_passed"], "git_dirty": git["dirty"]}))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=("cases", "compare"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.step == "cases":
        cmd_cases(args.out)
    else:
        cmd_compare(args.out)


if __name__ == "__main__":
    main()

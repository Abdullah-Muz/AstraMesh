"""Closed-loop formation keeping over the S11 storm week (DL-087, DL-088).

Runs ``configs/experiments/mission_geometry_24h.yaml`` (the formation of the drift
studies plus the ``spacecraft`` propulsion values) over the DL-086 storm week
(8 May 2024 00:10 UT, 690 600 s) with NRLMSIS 2.0 density and the formation-keeping
controller on:

* equal B, and B x0.8 / x1.2 / x0.5 / x2 on sc01, at density scale 1.0;
* B x0.8 / x1.2 at density scales 0.8 and 1.25;
* B x1.2 at scale 1.0 with navigation error 0 m and 100 m (sensitivity).

Writes ``formation_keeping.csv`` (adjacent spacings at every 10 s step: initial,
final, min, max, and the largest slot error of the follower), ``formation_keeping_dv.csv``
(per spacecraft: delta-v, propellant, thrust time, thruster energy, commands, held
decisions) and ``formation_keeping_meta.json`` (commit, git_dirty, lockfile hash,
config hashes) to ``--out``. Needs the ``atmosphere`` group and DS-10 (DL-084).

    uv run python scripts/experiments/formation_keeping_study.py --out /tmp/fk
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
import yaml

from astramesh.core.config import MissionScenarioBase, parse_scenario
from astramesh.core.events import EventLog
from astramesh.evaluation.manifest import git_state
from astramesh.scenarios.formation_dynamics import run_formation_dynamics

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "configs" / "experiments" / "mission_geometry_24h.yaml"
B = 0.0092  # DL-080 nominal [m^2/kg]
S11_EPOCH = "2024-05-08T00:10:00Z"  # as drag_drift_study.py --msis (DL-086)
S11_DURATION_S = 8 * 86_400 - 600
SAMPLE_S = 600  # recorded-output interval only; spacings use every step
SPACING_KM = 20.0
BAND_KM, FLOOR_KM = 2.0, 1.0  # DL-087 pass criteria
MULT = {"equal_B": 1.0, "sc01_B_x0.8": 0.8, "sc01_B_x1.2": 1.2, "sc01_B_x0.5": 0.5,
        "sc01_B_x2": 2.0}  # fmt: skip
#: (variant, density scale, navigation sigma [m])
JOBS = (
    [(v, 1.0, 10.0) for v in MULT]
    + [(v, s, 10.0) for s in (0.8, 1.25) for v in ("sc01_B_x0.8", "sc01_B_x1.2")]
    + [("sc01_B_x1.2", 1.0, sigma) for sigma in (0.0, 100.0)]
)


def _config(variant: str, scale: float, sigma: float) -> MissionScenarioBase:
    raw: dict[str, Any] = copy.deepcopy(yaml.safe_load(BASE.read_text()))
    raw["time"].update(epoch_utc=S11_EPOCH, duration_s=S11_DURATION_S)
    raw["output"]["trajectory_sample_interval_s"] = SAMPLE_S
    b = [B, MULT[variant] * B, B, B]
    raw["dynamics"]["drag"] = {"ballistic_m2pkg": b, "density": "msis2",
                               "density_scale_ratio": scale}  # fmt: skip
    raw["control"] = {"formation_keeping": {"navigation_sigma_m": sigma}}
    cfg = parse_scenario(raw)
    assert isinstance(cfg, MissionScenarioBase)
    return cfg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    rows: list[dict[str, Any]] = []
    dv_rows: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for variant, scale, sigma in JOBS:
        name = f"{variant}/scale{scale:g}/nav{sigma:g}m"
        cfg = _config(variant, scale, sigma)
        hashes[name] = cfg.config_hash()
        run = run_formation_dynamics(cfg, EventLog())
        assert run.keeping is not None
        r = run.trajectory.y[:, :, :3]  # every 10 s step
        sep_km = np.linalg.norm(np.diff(r, axis=1), axis=2) / 1e3
        slot_err_km = np.linalg.norm(r[:, 1:] - r[:, :1], axis=2) / 1e3 - SPACING_KM * np.arange(
            1, r.shape[1]
        )  # distance behind sc00 minus the slot (all spacecraft hear sc00 here)
        for k in range(sep_km.shape[1]):
            rows.append({
                "variant": name, "pair": f"sc{k:02d}-sc{k + 1:02d}",
                "initial_km": round(float(sep_km[0, k]), 4),
                "final_km": round(float(sep_km[-1, k]), 4),
                "min_km": round(float(sep_km[:, k].min()), 4),
                "max_km": round(float(sep_km[:, k].max()), 4),
                "max_abs_slot_error_km": round(float(np.abs(slot_err_km[:, k]).max()), 4),
                "within_band": bool(np.abs(sep_km[:, k] - SPACING_KM).max() <= BAND_KM),
                "above_floor": bool(sep_km[:, k].min() >= FLOOR_KM),
            })  # fmt: skip
        per = run.summary["formation_keeping"]["per_spacecraft"]
        for sc, d in per.items():
            dv_rows.append({"variant": name, "spacecraft": sc,
                            **{k: round(v, 7) if isinstance(v, float) else v
                               for k, v in d.items()}})  # fmt: skip
        print(f"{name}: max |slot error| {rows[-3]['max_abs_slot_error_km']} km, "
              f"dv sc01 {per['sc01']['delta_v_mps']:.4f} m/s", flush=True)  # fmt: skip
    for stem, data in (("formation_keeping", rows), ("formation_keeping_dv", dv_rows)):
        with (args.out / f"{stem}.csv").open("w", newline="\n") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(data)
    git = git_state(ROOT)
    meta = {
        "experiment": "Closed-loop formation keeping over the S11 storm week (DL-087, DL-088)",
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "base_config": str(BASE.relative_to(ROOT)),
        "ballistic_nominal_m2pkg": B,
        "variants_b_multiplier_sc01": MULT,
        "jobs": [list(j) for j in JOBS],
        "density": "msis2 (NRLMSIS 2.0, DS-10 drivers)",
        "epoch_utc": S11_EPOCH,
        "duration_s": S11_DURATION_S,
        "pass_criteria_km": {"band": BAND_KM, "floor": FLOOR_KM, "spacing": SPACING_KM},
        "sample_interval_s": SAMPLE_S,
        "config_hashes": hashes,
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }
    (args.out / "formation_keeping_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"rows": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

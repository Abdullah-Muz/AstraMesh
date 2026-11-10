"""Along-track drift of the four-spacecraft formation under nominal drag (DL-080, DL-081).

Runs ``configs/experiments/formation_24h_j2.yaml`` with drag over 24 h and 8 days:
no drag (reference), equal B for all, and B x0.5 or x2 on sc01 only. Writes
``drag_drift.csv`` (adjacent spacings at every 10 s step: initial, final, min, max) and
``drag_drift_meta.json`` (commit, git_dirty, lockfile hash, config hashes) to ``--out``.

    uv run python scripts/experiments/drag_drift_study.py --out /tmp/drag_drift
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

from astramesh.core.config import FormationScenarioBase, parse_scenario
from astramesh.core.events import EventLog
from astramesh.evaluation.manifest import git_state
from astramesh.scenarios.formation_dynamics import run_formation_dynamics

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "configs" / "experiments" / "formation_24h_j2.yaml"
B = 0.0092  # DL-080 nominal [m^2/kg]
VARIANTS: dict[str, list[float] | None] = {
    "no_drag": None,
    "equal_B": [B],
    "sc01_B_x0.5": [B, 0.5 * B, B, B],
    "sc01_B_x2": [B, 2.0 * B, B, B],
}
DURATIONS_S = (86_400, 8 * 86_400)
SAMPLE_S = 600  # recorded-output interval only; spacings use every step


def _config(variant: list[float] | None, duration_s: int) -> FormationScenarioBase:
    raw: dict[str, Any] = copy.deepcopy(yaml.safe_load(BASE.read_text()))
    raw["time"]["duration_s"] = duration_s
    raw["output"]["trajectory_sample_interval_s"] = SAMPLE_S
    if variant is not None:
        raw["dynamics"]["drag"] = {"ballistic_m2pkg": variant}
    cfg = parse_scenario(raw)
    assert isinstance(cfg, FormationScenarioBase)
    return cfg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    rows, hashes = [], {}
    for duration_s in DURATIONS_S:
        for name, variant in VARIANTS.items():
            cfg = _config(variant, duration_s)
            hashes[f"{name}/{duration_s}"] = cfg.config_hash()
            run = run_formation_dynamics(cfg, EventLog())
            r = run.trajectory.y[:, :, :3]  # every 10 s step, so the minimum is not sampled
            sep_km = np.linalg.norm(np.diff(r, axis=1), axis=2) / 1e3  # adjacent pairs
            for k in range(sep_km.shape[1]):
                rows.append({
                    "variant": name, "duration_s": duration_s, "pair": f"sc{k:02d}-sc{k + 1:02d}",
                    "initial_km": round(float(sep_km[0, k]), 4),
                    "final_km": round(float(sep_km[-1, k]), 4),
                    "min_km": round(float(sep_km[:, k].min()), 4),
                    "t_min_s": round(int(sep_km[:, k].argmin()) * cfg.time.time_step_s),
                    "max_km": round(float(sep_km[:, k].max()), 4),
                })  # fmt: skip
    with (args.out / "drag_drift.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    git = git_state(ROOT)
    meta = {
        "experiment": "Formation drift under nominal drag (DL-080, DL-081)",
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "base_config": str(BASE.relative_to(ROOT)),
        "ballistic_nominal_m2pkg": B,
        "variants": VARIANTS,
        "durations_s": list(DURATIONS_S),
        "sample_interval_s": SAMPLE_S,
        "config_hashes": hashes,
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }
    (args.out / "drag_drift_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"rows": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

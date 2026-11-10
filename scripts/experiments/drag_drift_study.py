"""Along-track drift of the four-spacecraft formation under nominal drag (DL-080, DL-081).

Runs ``configs/experiments/formation_24h_j2.yaml`` with drag over 24 h and 8 days:
no drag (reference), equal B for all, and B x0.8, x1.2 (credible spread) or
x0.5, x2 (stress) on sc01 only. Writes
``drag_drift.csv`` (adjacent spacings at every 10 s step: initial, final, min, max) and
``drag_drift_meta.json`` (commit, git_dirty, lockfile hash, config hashes) to ``--out``.

    uv run python scripts/experiments/drag_drift_study.py --out /tmp/drag_drift

With ``--msis`` it instead runs the S11 week (8 May 2024 00:10 UT, 8 days) with NRLMSIS 2.0
density (DL-084; needs the ``atmosphere`` group and DS-10): equal B and B x0.8 / x1.2 on
sc01, at density scales 0.8, 1.0 and 1.25; files ``drag_drift_msis.csv`` and
``drag_drift_msis_meta.json``.
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
    "sc01_B_x0.8": [B, 0.8 * B, B, B],  # credible spread for one design (DL-082)
    "sc01_B_x1.2": [B, 1.2 * B, B, B],
    "sc01_B_x0.5": [B, 0.5 * B, B, B],  # stress cases
    "sc01_B_x2": [B, 2.0 * B, B, B],
}
DURATIONS_S = (86_400, 8 * 86_400)
SAMPLE_S = 600
S11_EPOCH = "2024-05-08T00:10:00Z"  # as storm_replay_comparison.py (DL-069)
S11_DURATION_S = 8 * 86_400 - 600
MSIS_VARIANTS = {k: VARIANTS[k] for k in ("equal_B", "sc01_B_x0.8", "sc01_B_x1.2")}
MSIS_SCALES = (0.8, 1.0, 1.25)  # recorded-output interval only; spacings use every step


def _config(
    variant: list[float] | None, duration_s: int, msis_scale: float | None = None
) -> FormationScenarioBase:
    raw: dict[str, Any] = copy.deepcopy(yaml.safe_load(BASE.read_text()))
    raw["time"]["duration_s"] = duration_s
    raw["output"]["trajectory_sample_interval_s"] = SAMPLE_S
    if variant is not None:
        raw["dynamics"]["drag"] = {"ballistic_m2pkg": variant}
    if msis_scale is not None:
        raw["time"]["epoch_utc"] = S11_EPOCH
        raw["dynamics"]["drag"].update(density="msis2", density_scale_ratio=msis_scale)
    cfg = parse_scenario(raw)
    assert isinstance(cfg, FormationScenarioBase)
    return cfg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--msis", action="store_true", help="S11 week with NRLMSIS 2.0 density")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    rows, hashes = [], {}
    if args.msis:
        jobs = [(f"{n}/scale{s:g}", v, S11_DURATION_S, s)
                for s in MSIS_SCALES for n, v in MSIS_VARIANTS.items()]  # fmt: skip
    else:
        jobs = [(n, v, d, None) for d in DURATIONS_S for n, v in VARIANTS.items()]
    for name, variant, duration_s, scale in jobs:
        cfg = _config(variant, duration_s, scale)
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
    stem = "drag_drift_msis" if args.msis else "drag_drift"
    with (args.out / f"{stem}.csv").open("w", newline="") as f:
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
        "variants": MSIS_VARIANTS if args.msis else VARIANTS,
        "durations_s": [S11_DURATION_S] if args.msis else list(DURATIONS_S),
        "density": "msis2 (NRLMSIS 2.0, DS-10 drivers)" if args.msis else "ussa76",
        "msis_scales": list(MSIS_SCALES) if args.msis else None,
        "epoch_utc": S11_EPOCH
        if args.msis
        else yaml.safe_load(BASE.read_text())["time"]["epoch_utc"],
        "sample_interval_s": SAMPLE_S,
        "config_hashes": hashes,
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }
    (args.out / f"{stem}_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"rows": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

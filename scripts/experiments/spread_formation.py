"""Spread formation on 23-24 Mar 2024: shared hazard against shared tasks (DL-105, DL-106).

The DL-100 setup of the 23 Mar 2024 storm (``multi_storm_comparison.config``), planner
B4, seeds 1-3, with the along-track spacing set to 20 / 500 / 2000 / 5000 km and the
crosslink range raised to 6000 km at every spacing (line of sight still applies; at
525 km altitude neighbours lose it beyond about 5400 km). Arms: QUIET, the baseline
protection and the DL-103 shorter protection (``protection_comparison.FROZEN``).
Retention is against QUIET at the same spacing, because spacing changes the task set.

Reports per run: tasks, tasks with windows on more than one spacecraft, tasks lost
against QUIET, hours with all four spacecraft out of the tasking modes at once, and the
``protection_tuning.storm_metrics`` fields. Writes ``spread_runs.csv``,
``spread_summary.csv`` and ``spread_meta.json`` to ``--out``.

    uv run python scripts/experiments/spread_formation.py --out /tmp/spread
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_storm_comparison import config as storm_config  # noqa: E402
from multi_storm_comparison import series  # noqa: E402
from protection_comparison import FROZEN  # noqa: E402
from protection_tuning import apply_protection, storm_metrics  # noqa: E402

STORM = "mar23_2024"
PLANNER = "rule_b4"
SPACINGS_KM = (20.0, 500.0, 2000.0, 5000.0)
LINK_RANGE_KM = 6000.0
ARMS = ("quiet", "baseline", "shorter")
SEEDS = (1, 2, 3)


def config(spacing_km: float, arm: str, seed: int) -> dict[str, Any]:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    raw = storm_config(STORM, PLANNER, "quiet" if arm == "quiet" else "baseline", seed)
    raw["scenario_id"] = f"SPREAD_{STORM}_{spacing_km:g}km_{arm}"
    raw["formation"]["along_track_spacing_km"] = float(spacing_km)
    raw["network"]["crosslink_range_km"] = LINK_RANGE_KM
    if arm == "shorter":
        assert FROZEN is not None
        raw = apply_protection(raw, FROZEN)
    return raw


def non_tasking_mask(transitions: list[dict[str, Any]], grid_s: np.ndarray) -> np.ndarray:
    """True where the spacecraft is outside the tasking modes (start NOMINAL)."""
    from astramesh.agents.supervisor import TASKING_MODES

    if not transitions:
        return np.zeros(len(grid_s), dtype=bool)
    t = np.array([x["t_s"] for x in transitions])
    bad = np.array([x["to"] not in TASKING_MODES for x in transitions])
    i = np.searchsorted(t, grid_s, side="right") - 1
    return np.where(i >= 0, bad[np.clip(i, 0, None)], False)


def all_out_h(run: Any, duration_s: float, step_s: float) -> float:
    """Hours with every spacecraft outside the tasking modes at once."""
    grid = np.arange(0.0, duration_s, step_s)
    tr = run.summary["protection"]["transitions"]
    masks = [non_tasking_mask(tr[a], grid) for a in sorted(tr)]
    return round(float(np.logical_and.reduce(masks).sum()) * step_s / 3600, 2)


def run_one(job: tuple[float, str, int]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    spacing, arm, seed = job
    cfg = parse_scenario(config(spacing, arm, seed))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    shared = sum(1 for t in run.catalog if len({w.spacecraft for w in t.windows}) > 1)
    done = sorted(g.task_id for g in run.segments if g.outcome == "completed")
    row: dict[str, Any] = {"spacing_km": spacing, "arm": arm, "seed": seed,
                           "n_shared_tasks": shared}  # fmt: skip
    if arm != "quiet":
        row.update(storm_metrics(run))
        row["all_four_out_h"] = all_out_h(run, cfg.time.duration_s, cfg.time.time_step_s)
    else:
        ops = run.summary["operations"]
        row.update(utility=ops["utility"], n_tasks=ops["n_tasks"], n_completed=ops["n_completed"])
    row.update(completed_ids=json.dumps(done), config_hash=cfg.config_hash(),
               wall_s=round(time.perf_counter() - t0, 1))  # fmt: skip
    return row


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by = {(r["spacing_km"], r["arm"], r["seed"]): r for r in rows}
    out = []
    for sp in SPACINGS_KM:
        for arm in ("baseline", "shorter"):
            ret, lost = [], []
            for s in SEEDS:
                q, r = by[(sp, "quiet", s)], by[(sp, arm, s)]
                ret.append(r["utility"] / q["utility"])
                done_q, done_r = json.loads(q["completed_ids"]), json.loads(r["completed_ids"])
                lost.append(len(set(done_q) - set(done_r)))
            r1 = by[(sp, arm, 1)]
            out.append({
                "spacing_km": sp, "arm": arm, "n_tasks": r1["n_tasks"],
                "n_shared_tasks": r1["n_shared_tasks"],
                "quiet_utility": float(np.mean([by[(sp, "quiet", s)]["utility"] for s in SEEDS])),
                "utility": float(np.mean([by[(sp, arm, s)]["utility"] for s in SEEDS])),
                "retention": round(float(np.mean(ret)), 6),
                "retention_seed_spread": round(float(np.ptp(ret)), 6),
                "lost_vs_quiet": float(np.mean(lost)),
                "all_four_out_h": float(
                    np.mean([by[(sp, arm, s)]["all_four_out_h"] for s in SEEDS])),
                "unprotected_hazard_s_seed1": r1["unprotected_hazard_s"],
            })  # fmt: skip
    return out


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with path.open("w", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    from astramesh.evaluation.manifest import git_state

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    todo = [(sp, arm, s) for sp in SPACINGS_KM for arm in ARMS for s in SEEDS]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = list(ex.map(run_one, todo))
    summary = summarize(rows)
    _write(args.out / "spread_runs.csv", rows)
    _write(args.out / "spread_summary.csv", summary)
    git = git_state(ROOT)
    meta = {
        "experiment": "Spread formation on 23-24 Mar 2024 (DL-106)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "storm": STORM, "planner": PLANNER, "spacings_km": list(SPACINGS_KM),
        "crosslink_range_km": LINK_RANGE_KM, "shorter": FROZEN, "seeds": list(SEEDS),
        "series_sha256": hashlib.sha256(series(STORM).read_bytes()).hexdigest(),
        "n_runs": len(rows),
        "config_hashes": {f"{r['spacing_km']:g}km/{r['arm']}/seed{r['seed']}": r["config_hash"]
                          for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "spread_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for r in summary:
        print(r, flush=True)
    print(json.dumps({"runs": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

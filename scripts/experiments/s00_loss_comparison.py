"""Phase 2 increment 4: S00 comparison of B0-B3 under crosslink message loss (DL-047).

Run:  uv run python scripts/experiments/s00_loss_comparison.py [--workers 8]
          [--seeds 10] [--hours 24] [--out docs/results]

Every method runs on the *same* configuration (``configs/experiments/nominal_ops_b0_24h.yaml``)
with only ``operations.algorithm``, ``network.loss_probability`` and ``random.seed``
changed. The task catalogue, slots, resources and network model are therefore
identical across methods for a given seed (the script checks the catalogue).
The random *realisation* of losses differs between methods, because each method
sends a different number of messages from the same ``comms`` stream; paired
comparison is by seed and configuration, not by identical loss events.

Outputs (in ``--out``):
* ``s00_loss_comparison.csv`` - one row per run (deterministic columns + wall time)
* ``s00_loss_comparison_summary.csv`` - per (method, loss): mean, sd, 95% t-interval
* ``s00_loss_comparison_meta.json`` - git commit, lockfile hash, base config hash, settings

Wall-clock time is the only non-deterministic column and is reported separately.
Not a research result: S00 has no faults; this characterises the baselines.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import yaml
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "configs" / "experiments" / "nominal_ops_b0_24h.yaml"
METHODS = ("static_b0", "centralized_b1", "auction_b2", "cbba_b3")
LOSSES = (0.01, 0.10, 0.30)
METRICS = ("utility", "n_completed", "n_duplicates", "n_conflicts", "n_aborted",
           "n_declined", "n_unassigned", "messages_sent", "bytes_sent", "settle_s")  # fmt: skip


def _config(algorithm: str, loss: float, seed: int, hours: float) -> dict[str, Any]:
    raw = yaml.safe_load(BASE.read_text(encoding="utf-8"))
    cfg: dict[str, Any] = copy.deepcopy(raw)
    cfg["scenario_id"] = f"S00_LOSS_{algorithm.upper()}"
    cfg["operations"]["algorithm"] = algorithm
    cfg["network"]["loss_probability"] = loss
    cfg["random"]["seed"] = seed
    cfg["time"]["duration_s"] = int(hours * 3600)
    return cfg


def run_one(job: tuple[str, float, int, float]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    algorithm, loss, seed, hours = job
    cfg = parse_scenario(_config(algorithm, loss, seed, hours))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    wall = time.perf_counter() - t0
    o, net = run.summary["operations"], run.summary["network"]
    settle = [v for v in o["last_plan_change_s"].values() if v is not None]
    catalog = [(t.task_id, t.priority, tuple((w.spacecraft, w.first_tick, w.last_tick)
                                             for w in t.windows)) for t in run.catalog]  # fmt: skip
    return {
        "method": algorithm,
        "loss": loss,
        "seed": seed,
        "utility": o["utility"],
        "utility_all_tasks": o["utility_all_tasks"],
        "n_tasks": o["n_tasks"],
        "n_completed": o["n_completed"],
        "n_duplicates": o["n_duplicates"],
        "n_conflicts": len(o["conflicting_final_claims"]),
        "n_aborted": o["n_aborted"],
        "n_declined": sum(len(d) for d in o["declined"].values()),
        "n_unassigned": len(o["unassigned"]),
        "messages_sent": net["sent"],
        "bytes_sent": net["bytes_sent"],
        "settle_s": max(settle) if settle else 0.0,
        "privileged_information": o["privileged_information"],
        "catalog_sha256": hashlib.sha256(json.dumps(catalog).encode()).hexdigest(),
        "config_hash": cfg.config_hash(),
        "wall_s": round(wall, 2),
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for method in METHODS:
        for loss in sorted({r["loss"] for r in rows}):
            sel = [r for r in rows if r["method"] == method and r["loss"] == loss]
            if not sel:
                continue
            rec: dict[str, Any] = {"method": method, "loss": loss, "n_runs": len(sel)}
            for m in METRICS:
                xs = [float(r[m]) for r in sel]
                n = len(xs)
                mean = sum(xs) / n
                sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
                half = float(stats.t.ppf(0.975, n - 1)) * sd / math.sqrt(n) if n > 1 else 0.0
                rec[f"{m}_mean"] = round(mean, 6)
                rec[f"{m}_sd"] = round(sd, 6)
                rec[f"{m}_ci95_lo"] = round(mean - half, 6)
                rec[f"{m}_ci95_hi"] = round(mean + half, 6)
            rec["runs_with_duplicates"] = sum(1 for r in sel if r["n_duplicates"] > 0)
            rec["runs_with_conflicts"] = sum(1 for r in sel if r["n_conflicts"] > 0)
            out.append(rec)
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="\n", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--losses", type=float, nargs="*", default=list(LOSSES))
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "results")
    args = ap.parse_args()
    jobs = [(m, loss, s, args.hours) for loss in args.losses for s in range(1, args.seeds + 1)
            for m in METHODS]  # fmt: skip
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs))
    rows.sort(key=lambda r: (r["loss"], r["seed"], METHODS.index(r["method"])))
    for loss in args.losses:  # identical tasks/resources across methods (Gate P2)
        for s in range(1, args.seeds + 1):
            cats = {r["catalog_sha256"] for r in rows if r["loss"] == loss and r["seed"] == s}
            if len(cats) != 1:
                raise RuntimeError(f"catalogue differs between methods (loss {loss}, seed {s})")
    args.out.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out / "s00_loss_comparison.csv", rows)
    _write_csv(args.out / "s00_loss_comparison_summary.csv", summarize(rows))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, check=False).stdout.strip()  # fmt: skip
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                                text=True, check=False).stdout.strip())  # fmt: skip
    meta = {
        "experiment": "S00 loss comparison (DL-047)",
        "git_commit": commit,
        "git_dirty": dirty,
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "base_config": str(BASE.relative_to(ROOT)),
        "base_config_sha256": hashlib.sha256(BASE.read_bytes()).hexdigest(),
        "methods": list(METHODS),
        "losses": args.losses,
        "seeds": list(range(1, args.seeds + 1)),
        "hours": args.hours,
        "n_runs": len(rows),
        "total_wall_s": round(time.perf_counter() - t0, 1),
        "note": "S00 has no faults; wall_s is the only non-deterministic column",
    }
    (args.out / "s00_loss_comparison_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

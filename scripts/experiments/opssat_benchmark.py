"""Phase 4 increment 2: anomaly-detection benchmark on OPS-SAT-AD (DL-064).

Run:  uv run python scripts/experiments/opssat_benchmark.py [--seeds 5] [--workers 4]
          [--out docs/results]

Nine detectors (``astramesh.anomaly.detectors.METHODS``) on two splits (``official``,
``time``), each seed, under two protocols (``paper``, ``calibrated``; see
``astramesh.anomaly.benchmark``). Independent of the simulation (spec §7.2): real
telemetry, no AstraMesh spacecraft.

Outputs (in ``--out``):

* ``opssat_benchmark.csv``: one row per split, method, seed and protocol;
* ``opssat_benchmark_summary.csv``: mean and sd over seeds per split, method, protocol;
  plus the reference row ``all_anomalous`` (flag every segment);
* ``opssat_reliability.csv``: calibrated reliability bins per split, method and seed;
* ``opssat_benchmark_meta.json``: commit, dirty flag, lockfile and data hashes, settings.

CPU times and wall time are the only columns that change between repeated runs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from astramesh.anomaly.benchmark import run, stratified_folds
from astramesh.anomaly.detectors import METHODS
from astramesh.anomaly.metrics import detection
from astramesh.datasets.opssat import FEATURES, load, time_folds
from astramesh.datasets.sources import load_sources

ROOT = Path(__file__).resolve().parents[2]
SPLITS = ("official", "time")
SUMMARY_METRICS = ("aucpr", "aucroc", "accuracy", "f1", "precision", "recall", "mcc",
                   "false_alert_rate", "missed", "brier", "ece", "fit_cpu_s",
                   "score_cpu_ms_per_segment", "model_bytes")  # fmt: skip
VARIABLE = ("fit_cpu_s", "score_cpu_ms_per_segment")  # timing: differs between runs


def folds_for(split: str, seed: int) -> Any:
    d = load()
    tr = d.split(split)
    if split == "official":
        return stratified_folds(d.y[tr], seed)
    return time_folds(d.channel[tr], d.start[tr])


def job(args: tuple[str, str, int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    split, name, seed = args
    d = load()
    tr = d.split(split)
    out = run(METHODS[name], d.X, d.y, tr, folds_for(split, seed), seed)
    rows = [{"split": split, **r} for r in out.rows]
    bins = [{"split": split, "method": name, "seed": seed, "bin": b, "count": n,
             "mean_prob": p, "anomaly_fraction": f} for b, n, p, f in out.bins]  # fmt: skip
    print(f"{split:8} {name:14} seed {seed}  F1 paper {rows[0]['f1']:.3f} "
          f"calibrated {rows[1]['f1']:.3f}", flush=True)  # fmt: skip
    return rows, bins


def split_counts(y: Any, train: Any) -> dict[str, int]:
    return {
        "n_train": int(train.sum()),
        "n_test": int((~train).sum()),
        "train_anomalies": int(y[train].sum()),
        "test_anomalies": int(y[~train].sum()),
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    keys = sorted({(r["split"], r["method"], r["kind"], r["protocol"]) for r in rows},
                  key=lambda k: (SPLITS.index(k[0]), k[3], list(METHODS).index(k[1])))  # fmt: skip
    for split, method, kind, protocol in keys:
        sel = [r for r in rows if (r["split"], r["method"], r["protocol"]) == (split, method,
               protocol)]  # fmt: skip
        s: dict[str, Any] = {"split": split, "method": method, "kind": kind,
                             "protocol": protocol, "n_seeds": len(sel)}  # fmt: skip
        for m in SUMMARY_METRICS:
            v = [x for r in sel if not math.isnan(x := float(r[m]))]  # paper rows: no ECE
            s[f"{m}_mean"] = statistics.fmean(v) if v else math.nan
            s[f"{m}_sd"] = statistics.stdev(v) if len(v) > 1 else (0.0 if v else math.nan)
        out.append(s)
    d = load()
    for split in SPLITS:  # reference: flag every test segment
        y = d.y[~d.split(split)]
        ref = detection(y, np.ones_like(y), np.zeros(len(y)))
        s = {"split": split, "method": "all_anomalous", "kind": "reference",
             "protocol": "reference", "n_seeds": 1}  # fmt: skip
        for m in SUMMARY_METRICS:
            s[f"{m}_mean"] = ref.get(m, float("nan"))
            s[f"{m}_sd"] = 0.0
        out.append(s)
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: f"{v:.6g}" if isinstance(v, float) else v for k, v in r.items()})


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out", type=Path, default=ROOT / "docs" / "results")
    p.add_argument("--summarize-only", action="store_true",
                   help="rebuild the summary from an existing opssat_benchmark.csv")  # fmt: skip
    args = p.parse_args()
    if args.summarize_only:
        with (args.out / "opssat_benchmark.csv").open(newline="", encoding="utf-8") as fh:
            saved = list(csv.DictReader(fh))
        _write_csv(args.out / "opssat_benchmark_summary.csv", summarize(saved))
        return 0

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()  # fmt: skip

    # Record the tree state before writing outputs: new result files would mark it dirty.
    commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    seeds = list(range(args.seeds))
    jobs = [(s, m, seed) for s in SPLITS for m in METHODS for seed in seeds]
    t0 = time.time()
    with ProcessPoolExecutor(args.workers) as ex:
        results = list(ex.map(job, jobs))
    rows = [r for rs, _ in results for r in rs]
    bins = [b for _, bs in results for b in bs]
    args.out.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out / "opssat_benchmark.csv", rows)
    _write_csv(args.out / "opssat_benchmark_summary.csv", summarize(rows))
    _write_csv(args.out / "opssat_reliability.csv", bins)

    d = load()
    meta = {
        "experiment": "Phase 4 OPS-SAT-AD anomaly-detection benchmark (DL-064)",
        "git_commit": commit,
        "git_dirty": dirty,
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "data": {f.name: f.sha256 for f in load_sources()["DS-02"].files},
        "features": list(FEATURES),
        "methods": {m.name: m.kind for m in METHODS.values()},
        "splits": {s: split_counts(d.y, d.split(s)) for s in SPLITS},
        "seeds": seeds,
        "variable_columns": list(VARIABLE),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "workers": args.workers,
        "total_wall_s": round(time.time() - t0, 1),
    }
    (args.out / "opssat_benchmark_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ("git_commit", "git_dirty", "total_wall_s")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

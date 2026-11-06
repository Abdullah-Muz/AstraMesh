"""Phase 4 increment 4: skill of the P-A / P-B / P-C proton forecasts (DL-069).

Run:  uv run python scripts/experiments/storm_forecast_benchmark.py [--out docs/results]

Real data only, independent of the simulation. Training data: GOES-18 SGPS and OMNI for
Jan 2023 - Apr 2024 (DS-08, DS-09). Two evaluations:

* ``cv``: forward-chaining folds inside the training period (test blocks 2023 Q3, 2023 Q4,
  2024 Q1, Apr 2024). Each fold trains only on rows whose whole target window ends before
  the block starts.
* ``storm``: trained once on all of DS-08/DS-09, tested once on the held-out storm week
  8-15 May 2024 (DS-06, DS-07).

Target: log10 of the largest >= 10 MeV flux in the next H after issue (H = 30 min, 1 h,
3 h); quantiles 0.5 and 0.9. Scores: pinball loss, coverage, and warnings at 50, 100 and
200 pfu (the 100 pfu tolerance x 0.5, 1, 2; DL-068): row-wise POD and false-alarm ratio,
and onsets warned with lead times. Outputs ``storm_forecast.csv`` and
``storm_forecast_meta.json``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np

from astramesh.datasets import goes, omni
from astramesh.forecast.features import (
    FEATURES,
    LATENCY_NS,
    Grid,
    build_grid,
    features,
    target,
)
from astramesh.forecast.models import (
    PB,
    PC,
    PC_SETTINGS,
    coverage,
    pa_predict,
    pinball,
    warnings,
)

ROOT = Path(__file__).resolve().parents[2]
HORIZONS_S = (1800, 3600, 10800)
QUANTILES = (0.5, 0.9)
THRESHOLDS_PFU = (50.0, 100.0, 200.0)
FOLD_STARTS = ("2023-07-01", "2023-10-01", "2024-01-01", "2024-04-01", "2024-05-01")


def _ns(day: str) -> int:
    return int(np.datetime64(day, "ns").astype(np.int64))


def predict_all(Xtr: Any, ytr: Any, Xte: Any, q: float) -> dict[str, Any]:
    return {"P-A": pa_predict(Xte), "P-B": PB(q).fit(Xtr, ytr).predict(Xte),
            "P-C": PC(q).fit(Xtr, ytr).predict(Xte)}  # fmt: skip


def score(split: str, fold: str, h: int, q: float, y: Any, preds: dict[str, Any],
          level: Any) -> list[dict[str, Any]]:  # fmt: skip
    rows = []
    for name, p in preds.items():
        r: dict[str, Any] = {"split": split, "fold": fold, "horizon_s": h, "quantile": q,
                             "model": name, "n": int(np.sum(np.isfinite(y) & np.isfinite(p))),
                             "pinball": round(pinball(y, p, q), 6),
                             "coverage": round(coverage(y, p), 6)}  # fmt: skip
        for thr in THRESHOLDS_PFU:
            w = warnings(y, p, level, math.log10(thr), horizon_steps=h // 300)
            tag = f"{int(thr)}pfu"
            r.update({f"pod_{tag}": round(w.pod, 6) if w.hits + w.misses else "",
                      f"far_{tag}": round(w.far, 6) if w.hits + w.false_alarms else "",
                      f"onsets_{tag}": w.onsets, f"warned_{tag}": w.onsets_warned})  # fmt: skip
            r[f"lead_median_s_{tag}"] = float(np.median(w.lead_s)) if w.lead_s else ""
        rows.append(r)
    return rows


def run(train: Grid, storm: Grid) -> list[dict[str, Any]]:
    Xtr, Xst = features(train), features(storm)
    rows: list[dict[str, Any]] = []
    for h in HORIZONS_S:
        ytr, yst = target(train, h), target(storm, h)
        issue_end = train.t_ns + LATENCY_NS + h * 10**9  # end of each row's target window
        for q in QUANTILES:
            for a, b in itertools.pairwise(FOLD_STARTS):
                fit = issue_end <= _ns(a)
                test = (train.t_ns >= _ns(a)) & (train.t_ns < _ns(b))
                preds = predict_all(Xtr[fit], ytr[fit], Xtr[test], q)
                rows += score("cv", a[:7], h, q, ytr[test], preds, train.log_flux[test])
            preds = predict_all(Xtr, ytr, Xst, q)
            rows += score("storm", "2024-05-08", h, q, yst, preds, storm.log_flux)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "results")
    args = ap.parse_args()

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()  # fmt: skip

    commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    t0 = time.time()
    train = build_grid(goes.load("DS-08"), omni.load("DS-09"))
    storm = build_grid(goes.load("DS-07"), omni.load("DS-06"))
    rows = run(train, storm)
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "storm_forecast.csv").open("w", newline="\n", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    meta = {
        "experiment": "Phase 4 proton forecast skill P-A/P-B/P-C (DL-069)",
        "git_commit": commit,
        "git_dirty": dirty,
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "train": "DS-08 + DS-09 (2023-01-01 .. 2024-04-30)",
        "test": "DS-07 + DS-06 (2024-05-08 .. 2024-05-15)",
        "features": list(FEATURES),
        "latency_s": LATENCY_NS // 10**9,
        "horizons_s": list(HORIZONS_S),
        "quantiles": list(QUANTILES),
        "thresholds_pfu": list(THRESHOLDS_PFU),
        "fold_starts": list(FOLD_STARTS),
        "pc_settings": PC_SETTINGS,
        "storm_rows": len(storm.t_ns),
        "train_rows": len(train.t_ns),
        "total_wall_s": round(time.time() - t0, 1),
    }
    (args.out / "storm_forecast_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ("git_commit", "git_dirty", "total_wall_s")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
and onsets warned with lead times. 95 % intervals (DL-072, ``forecast.uncertainty``): a
paired bootstrap over UTC days for the row scores and for the differences between
models, and Clopper-Pearson for the fraction of onsets warned. Outputs
``storm_forecast.csv`` (one row per evaluation and model), ``storm_forecast_pairs.csv``
(model differences) and ``storm_forecast_meta.json``.
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
from astramesh.datasets.sources import load_sources
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
from astramesh.forecast.uncertainty import N_BOOT, SEED, clopper_pearson, row_intervals

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


def _r(x: float) -> float | str:
    return round(x, 6) if math.isfinite(x) else ""


def score(split: str, fold: str, h: int, q: float, y: Any, preds: dict[str, Any],
          level: Any, t_ns: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:  # fmt: skip
    """One row per model (scores with 95 % intervals) and one per pair of models and score
    (paired difference, later model minus earlier, with its 95 % interval)."""
    logs = tuple(math.log10(thr) for thr in THRESHOLDS_PFU)
    ci, diffs = row_intervals(y, preds, q, t_ns, logs)
    key = {"split": split, "fold": fold, "horizon_s": h, "quantile": q}
    rows = []
    for name, p in preds.items():
        c = ci[name]
        r: dict[str, Any] = {**key, "model": name,
                             "n": int(np.sum(np.isfinite(y) & np.isfinite(p))),
                             "pinball": round(pinball(y, p, q), 6),
                             "pinball_lo": _r(c["pinball"].lo), "pinball_hi": _r(c["pinball"].hi),
                             "coverage": round(coverage(y, p), 6),
                             "coverage_lo": _r(c["coverage"].lo),
                             "coverage_hi": _r(c["coverage"].hi)}  # fmt: skip
        for thr, lg in zip(THRESHOLDS_PFU, logs, strict=True):
            w = warnings(y, p, level, lg, horizon_steps=h // 300)
            tag = f"{int(thr)}pfu"
            pod, far = c[f"pod@{lg}"], c[f"far@{lg}"]
            r.update({f"pod_{tag}": round(w.pod, 6) if w.hits + w.misses else "",
                      f"pod_{tag}_lo": _r(pod.lo), f"pod_{tag}_hi": _r(pod.hi),
                      f"pod_{tag}_boot_n": pod.n_defined,
                      f"far_{tag}": round(w.far, 6) if w.hits + w.false_alarms else "",
                      f"far_{tag}_lo": _r(far.lo), f"far_{tag}_hi": _r(far.hi),
                      f"far_{tag}_boot_n": far.n_defined,
                      f"onsets_{tag}": w.onsets, f"warned_{tag}": w.onsets_warned})  # fmt: skip
            lo, hi = clopper_pearson(w.onsets_warned, w.onsets)
            r[f"warned_frac_{tag}_lo"], r[f"warned_frac_{tag}_hi"] = _r(lo), _r(hi)
            r[f"lead_median_s_{tag}"] = float(np.median(w.lead_s)) if w.lead_s else ""
        rows.append(r)
    names = {f"pod@{lg}": f"pod_{int(t)}pfu" for t, lg in zip(THRESHOLDS_PFU, logs, strict=True)}
    names |= {f"far@{lg}": f"far_{int(t)}pfu" for t, lg in zip(THRESHOLDS_PFU, logs, strict=True)}
    pairs = []
    for (a, b), by_score in diffs.items():
        for k, (d, iv) in by_score.items():
            pairs.append({**key, "pair": f"{b} - {a}", "score": names.get(k, k),
                          "diff": _r(d), "lo": _r(iv.lo), "hi": _r(iv.hi),
                          "boot_n": iv.n_defined})  # fmt: skip
    return rows, pairs


def run(train: Grid, storm: Grid) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    Xtr, Xst = features(train), features(storm)
    rows: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    for h in HORIZONS_S:
        ytr, yst = target(train, h), target(storm, h)
        issue_end = train.t_ns + LATENCY_NS + h * 10**9  # end of each row's target window
        for q in QUANTILES:
            for a, b in itertools.pairwise(FOLD_STARTS):
                fit = issue_end <= _ns(a)
                test = (train.t_ns >= _ns(a)) & (train.t_ns < _ns(b))
                preds = predict_all(Xtr[fit], ytr[fit], Xtr[test], q)
                r, p = score("cv", a[:7], h, q, ytr[test], preds, train.log_flux[test],
                             train.t_ns[test])  # fmt: skip
                rows, pairs = rows + r, pairs + p
            preds = predict_all(Xtr, ytr, Xst, q)
            r, p = score("storm", "2024-05-08", h, q, yst, preds, storm.log_flux, storm.t_ns)
            rows, pairs = rows + r, pairs + p
    return rows, pairs


def data_versions() -> dict[str, dict[str, Any]]:
    """Per dataset: file count and the sha256 of its sorted ``name sha256`` lines, from the
    pinned registry (``configs/data/sources.yaml``) that the loaders verify against."""
    out = {}
    for ds in ("DS-06", "DS-07", "DS-08", "DS-09"):
        files = load_sources()[ds].files
        lines = "".join(f"{f.name} {f.sha256}\n" for f in sorted(files, key=lambda f: f.name))
        out[ds] = {
            "files": len(files),
            "sha256_of_pins": hashlib.sha256(lines.encode()).hexdigest(),
        }
    return out


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
    rows, pairs = run(train, storm)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, table in (("storm_forecast.csv", rows), ("storm_forecast_pairs.csv", pairs)):
        with (args.out / name).open("w", newline="\n", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(table)
    meta = {
        "experiment": "Phase 4 proton forecast skill P-A/P-B/P-C (DL-069), intervals (DL-072)",
        "git_commit": commit,
        "git_dirty": dirty,
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "train": "DS-08 + DS-09 (2023-01-01 .. 2024-04-30)",
        "test": "DS-07 + DS-06 (2024-05-08 .. 2024-05-15)",
        "data": data_versions(),
        "features": list(FEATURES),
        "latency_s": LATENCY_NS // 10**9,
        "horizons_s": list(HORIZONS_S),
        "quantiles": list(QUANTILES),
        "thresholds_pfu": list(THRESHOLDS_PFU),
        "fold_starts": list(FOLD_STARTS),
        "pc_settings": PC_SETTINGS,
        "intervals": {
            "level": 0.95,
            "row_scores": "paired percentile bootstrap over UTC days",
            "n_boot": N_BOOT,
            "seed": SEED,
            "onsets_warned": "Clopper-Pearson exact",
        },
        "storm_rows": len(storm.t_ns),
        "train_rows": len(train.t_ns),
        "total_wall_s": round(time.time() - t0, 1),
    }
    (args.out / "storm_forecast_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ("git_commit", "git_dirty", "total_wall_s")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

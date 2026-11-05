"""Build the H-C payload score sensor from the OPS-SAT benchmark (DL-066).

Run:  uv run python scripts/data/make_score_sensor.py

Fits histogram gradient boosting (seed 0, ``calibrated`` protocol, as in
``docs/results/OPSSAT_BENCHMARK.md``) on each split and stores the calibrated anomaly
probabilities of the *test* segments, grouped by label, with the training anomaly rate
the probabilities were calibrated to. The simulator draws from these distributions
(``configs/data/opssat_score_sensor.json``): it carries the real detector's error
rates, drift included, into the simulation without claiming that OPS-SAT telemetry
belongs to AstraMesh's spacecraft (spec §7.2). Derived from OPS-SAT-AD (CC BY 4.0 / MIT,
Ruszczak et al. 2025); prints the file's sha256 to pin in experiment configs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from astramesh.anomaly.benchmark import run, stratified_folds
from astramesh.anomaly.detectors import METHODS
from astramesh.datasets.opssat import load, time_folds
from astramesh.datasets.sources import load_sources

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "configs" / "data" / "opssat_score_sensor.json"
METHOD, SEED = "hist_gbdt", 0


def main() -> int:
    d = load()
    splits = {}
    for split in ("time", "official"):
        tr = d.split(split)
        folds = (stratified_folds(d.y[tr], SEED) if split == "official"
                 else time_folds(d.channel[tr], d.start[tr]))  # fmt: skip
        out = run(METHODS[METHOD], d.X, d.y, tr, folds, SEED)
        y = d.y[~tr]
        splits[split] = {
            "train_prior": round(float(d.y[tr].mean()), 6),
            "test_f1_calibrated": round(out.rows[1]["f1"], 6),
            "nominal": [round(float(p), 6) for p in out.test_prob[y == 0]],
            "anomalous": [round(float(p), 6) for p in out.test_prob[y == 1]],
        }
    doc = {
        "description": "Calibrated P(anomalous) of OPS-SAT-AD test segments, by true label",
        "source": "OPS-SAT-AD (DS-02), Ruszczak et al. 2025, CC BY 4.0 / MIT",
        "data_sha256": {f.name: f.sha256 for f in load_sources()["DS-02"].files},
        "method": METHOD,
        "seed": SEED,
        "protocol": "calibrated (isotonic, out-of-fold on training rows only)",
        "decision_log": "DL-066",
        "splits": splits,
    }
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(OUT.relative_to(ROOT), hashlib.sha256(OUT.read_bytes()).hexdigest())
    for s, v in splits.items():
        print(s, v["train_prior"], len(v["nominal"]), len(v["anomalous"]), v["test_f1_calibrated"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

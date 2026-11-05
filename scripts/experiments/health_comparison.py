"""Phase 4 increment 3: health models H-A / H-B / H-C under fixed planning (DL-066).

Run:  uv run python scripts/experiments/health_comparison.py [--workers 6] [--seeds 10]
          [--out docs/results]

Every run is a fault-comparison configuration (``fault_comparison.scenario_config``:
same base config, same per-seed fault draws) with ``agents.health`` set by the model.
Downstream planning is identical across models (spec §7.2): B3 + timeout and B4, with the
same response to a believed-degraded payload (DL-066).

Models: ``H-A`` timeout (90 s / 300 s), ``H-B`` Bayesian silence model, ``H-C`` H-B plus
the onboard payload detector (empirical score sensor from the OPS-SAT benchmark, time
split). Sensitivity variants: ``H-C/official`` (official-split sensor), ``H-C/shift05``
(5 % of healthy checks drawn from anomalous scores), ``H-B/mtbf3d`` and ``H-B/mtbf300d``
(prior mean time to unavailability 3 or 300 days instead of 30).

Outputs: ``health_comparison.csv`` (per run), ``health_comparison_summary.csv`` (per
scenario, planner and model: mean, sd, 95 % t-interval), ``health_comparison_meta.json``.
Wall time is the only non-deterministic column. Synthetic faults; real-data detector.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fault_comparison import draws, scenario_config

ROOT = Path(__file__).resolve().parents[2]
SENSOR = ROOT / "configs" / "data" / "opssat_score_sensor.json"
PLANNERS = ("cbba_b3_timeout", "rule_b4")
DAY = 86400.0


def models(sensor_sha: str) -> dict[str, dict[str, Any]]:
    check = {"sensor_sha256": sensor_sha}
    return {
        "H-A": {"model": "timeout"},
        "H-B": {"model": "bayes"},
        "H-C": {"model": "bayes", "payload_check": check},
        "H-C/official": {"model": "bayes", "payload_check": {**check, "sensor_split": "official"}},
        "H-C/shift05": {
            "model": "bayes",
            "payload_check": {**check, "nominal_contamination_fraction": 0.05},
        },
        "H-B/mtbf3d": {"model": "bayes", "bayes": {"mtbf_s": 3 * DAY}},
        "H-B/mtbf300d": {"model": "bayes", "bayes": {"mtbf_s": 300 * DAY}},
    }


# (model, scenarios): the main comparison, then sensitivity runs (each with its S00).
PLAN = (
    ("H-A", ("S00", "S01", "S03", "S04")),
    ("H-B", ("S00", "S01", "S03", "S04")),
    ("H-C", ("S00", "S01", "S03", "S04")),
    ("H-C/official", ("S00", "S03")),
    ("H-C/shift05", ("S00", "S03")),
    ("H-B/mtbf3d", ("S00", "S01", "S04")),
    ("H-B/mtbf300d", ("S00", "S01", "S04")),
)
METRICS = ("utility", "retention", "n_completed", "n_duplicates", "n_invalid_payload",
           "detection_latency_s", "false_unavailable_s", "missed_unavailable_s",
           "payload_detection_latency_s", "payload_false_degraded_s",
           "payload_missed_degraded_s", "messages_sent", "bytes_sent")  # fmt: skip


def run_one(job: tuple[str, str, str, int, float, dict[str, Any]]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    scenario, planner, model, seed, hours, health = job
    raw = scenario_config(scenario, planner, seed, hours)
    raw["agents"]["health"] = health
    cfg = parse_scenario(raw)
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    wall = time.perf_counter() - t0
    o, n, h = run.summary["operations"], run.summary["network"], run.summary["health"]
    p, pay = run.summary["protection"], h["payload"]
    lat = [v for v in h["detection_latency_s"].values() if v is not None]
    plat = [v for v in pay["detection_latency_s"].values() if v is not None]
    d = draws(seed)
    return {
        "scenario": scenario, "planner": planner, "model": model, "seed": seed,
        "affected": d["a"], "t0_s": d["t0_s"],
        "utility": o["utility"], "n_completed": o["n_completed"],
        "n_duplicates": o["n_duplicates"], "n_invalid_payload": o.get("n_invalid_payload", 0),
        "detection_latency_s": max(lat) if lat else "",
        "false_unavailable_s": h["false_unavailable_s"],
        "missed_unavailable_s": h["missed_unavailable_s"],
        "payload_detection_latency_s": max(plat) if plat else "",
        "payload_undetected": sum(v is None for v in pay["detection_latency_s"].values()),
        "payload_false_degraded_s": pay["false_degraded_s"],
        "payload_missed_degraded_s": pay["missed_degraded_s"],
        "confirmed_while_available": h["confirmed_while_available"],
        "protected_payload_steps": sum(p["payload_steps_in_protected_modes"].values()),
        "messages_sent": n["sent"], "bytes_sent": n["bytes_sent"],
        "config_hash": cfg.config_hash(), "wall_s": round(wall, 2),
    }  # fmt: skip


def add_retention(rows: list[dict[str, Any]]) -> None:
    ref = {(r["planner"], r["model"], r["seed"]): r["utility"] for r in rows
           if r["scenario"] == "S00"}  # fmt: skip
    for r in rows:
        u = ref.get((r["planner"], r["model"], r["seed"]))
        r["retention"] = round(r["utility"] / u, 6) if u else ""


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    order = [m for m, _ in PLAN]
    keys = sorted({(r["scenario"], r["planner"], r["model"]) for r in rows},
                  key=lambda k: (k[0], PLANNERS.index(k[1]), order.index(k[2])))  # fmt: skip
    for scenario, planner, model in keys:
        sel = [r for r in rows if (r["scenario"], r["planner"], r["model"]) ==
               (scenario, planner, model)]  # fmt: skip
        rec: dict[str, Any] = {"scenario": scenario, "planner": planner, "model": model,
                               "n_runs": len(sel)}  # fmt: skip
        for m in METRICS:
            xs = [float(r[m]) for r in sel if r.get(m, "") != ""]
            k = len(xs)
            if k == 0:
                rec.update({f"{m}_mean": "", f"{m}_sd": "", f"{m}_ci95_lo": "",
                            f"{m}_ci95_hi": "", f"{m}_n": 0})  # fmt: skip
                continue
            mean = sum(xs) / k
            sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (k - 1)) if k > 1 else 0.0
            half = float(stats.t.ppf(0.975, k - 1)) * sd / math.sqrt(k) if k > 1 else 0.0
            rec.update({f"{m}_mean": round(mean, 6), f"{m}_sd": round(sd, 6),
                        f"{m}_ci95_lo": round(mean - half, 6),
                        f"{m}_ci95_hi": round(mean + half, 6), f"{m}_n": k})  # fmt: skip
        rec["runs_with_duplicates"] = sum(1 for r in sel if r["n_duplicates"] > 0)
        rec["runs_payload_undetected"] = sum(1 for r in sel if r["payload_undetected"] > 0)
        out.append(rec)
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="\n", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "results")
    args = ap.parse_args()

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()  # fmt: skip

    commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    sensor_sha = hashlib.sha256(SENSOR.read_bytes()).hexdigest()
    health = models(sensor_sha)
    seeds = list(range(1, args.seeds + 1))
    jobs = [(s, p, m, seed, args.hours, health[m]) for m, scs in PLAN for s in scs
            for p in PLANNERS for seed in seeds]  # fmt: skip
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs))
    bad = [r for r in rows if r["protected_payload_steps"] or r["confirmed_while_available"]]
    if bad:
        raise RuntimeError(f"safety invariant violated in {len(bad)} runs")
    add_retention(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out / "health_comparison.csv", rows)
    _write_csv(args.out / "health_comparison_summary.csv", summarize(rows))
    meta = {
        "experiment": "Phase 4 health-model comparison H-A/H-B/H-C (DL-066)",
        "git_commit": commit,
        "git_dirty": dirty,
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "sensor_file": str(SENSOR.relative_to(ROOT)),
        "sensor_sha256": sensor_sha,
        "models": health,
        "plan": {m: list(s) for m, s in PLAN},
        "planners": list(PLANNERS),
        "seeds": seeds,
        "hours": args.hours,
        "draws": {s: draws(s) for s in seeds},
        "n_runs": len(rows),
        "workers": args.workers,
        "total_wall_s": round(time.time() - t0, 1),
    }
    (args.out / "health_comparison_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ("git_commit", "git_dirty", "n_runs", "total_wall_s")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

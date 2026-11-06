"""Phase 4 increment 4: S11 May 2024 storm replay, protection P-A / P-B / P-C (DL-069).

Run:  uv run python scripts/experiments/storm_replay_comparison.py [--workers 6] [--seeds 10]
          [--out docs/results]

Every run is the S00 base configuration moved to 8 May 2024 00:10 UT and run to 16 May
00:00 (8 days less 10 min), with ``environment.replay`` reading the pinned real-data series
(``configs/data/s11_storm_series.json``). The three protection inputs feed the **same**
supervisor (spec §7.3): P-A the latest measured flux, P-B and P-C 1 h forecasts of the
maximum (median; the 0.9 quantile as a sensitivity). The payload tolerance is 100 pfu
(50 and 200 as sensitivities). ``QUIET`` is the same week with no environment input:
the reference for retention.

Truth metrics (``summary.storm``, per spacecraft summed): hazard time (measured flux at
or above the tolerance), payload-on time during it (exposure: the missed defined
hazard), protected time inside and outside it (false protective time). Faults: none. The
seeds change only message loss. Outputs ``storm_replay.csv``,
``storm_replay_summary.csv`` and ``storm_replay_meta.json``.
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
SERIES = ROOT / "configs" / "data" / "s11_storm_series.json"
EPOCH = "2024-05-08T00:10:00Z"
DURATION_S = 8 * 86400 - 600
PLANNERS = ("cbba_b3_timeout", "rule_b4")
# (variant, forecast, tolerance_pfu); QUIET has no environment input.
VARIANTS = (
    ("QUIET", None, None),
    ("P-A", "P-A", 100.0),
    ("P-B", "P-B/q50", 100.0),
    ("P-C", "P-C/q50", 100.0),
    ("P-B/q90", "P-B/q90", 100.0),
    ("P-C/q90", "P-C/q90", 100.0),
    ("P-A/tol50", "P-A", 50.0),
    ("P-B/tol50", "P-B/q50", 50.0),
    ("P-C/tol50", "P-C/q50", 50.0),
    ("P-A/tol200", "P-A", 200.0),
    ("P-B/tol200", "P-B/q50", 200.0),
    ("P-C/tol200", "P-C/q50", 200.0),
)
STORM = ("hazard_s", "exposed_s", "protected_in_hazard_s", "protected_outside_hazard_s",
         "no_truth_s")  # fmt: skip
METRICS = ("utility", "retention", "n_completed", "n_duplicates", *STORM,
           "protective_entries", "time_protective_s", "time_storm_watch_s")  # fmt: skip


def scenario_config(variant: str, planner: str, seed: int, sha: str) -> dict[str, Any]:
    raw = yaml.safe_load(BASE.read_text(encoding="utf-8"))
    cfg: dict[str, Any] = copy.deepcopy(raw)
    _, forecast, tol = next(v for v in VARIANTS if v[0] == variant)
    cfg["scenario_id"] = f"S11_{variant.replace('/', '_').replace('-', '')}_{planner.upper()}"
    cfg["time"]["epoch_utc"] = EPOCH
    cfg["time"]["duration_s"] = DURATION_S
    cfg["operations"]["algorithm"] = planner
    cfg["random"]["seed"] = seed
    cfg["faults"] = []
    if forecast is not None:
        cfg["environment"] = {
            "background_exposure_ratio": 0.0,
            "replay": {"series_sha256": sha, "forecast": forecast,
                       "radiation_tolerance_pfu": tol},
        }  # fmt: skip
    return cfg


def run_one(job: tuple[str, str, int, str]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    variant, planner, seed, sha = job
    cfg = parse_scenario(scenario_config(variant, planner, seed, sha))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    wall = time.perf_counter() - t0
    o, p = run.summary["operations"], run.summary["protection"]
    st = run.summary.get("storm", {})
    modes = p["time_in_mode_s"]
    row: dict[str, Any] = {
        "variant": variant, "planner": planner, "seed": seed,
        "utility": o["utility"], "n_completed": o["n_completed"],
        "n_duplicates": o["n_duplicates"], "n_tasks": o["n_tasks"],
        "protective_entries": sum(
            1 for tr in p["transitions"].values() for x in tr if x["to"] == "PROTECTIVE"),
        "time_protective_s": sum(m.get("PROTECTIVE", 0.0) for m in modes.values()),
        "time_storm_watch_s": sum(m.get("STORM_WATCH", 0.0) for m in modes.values()),
        "protected_payload_steps": sum(p["payload_steps_in_protected_modes"].values()),
        "confirmed_while_available": run.summary["health"]["confirmed_while_available"],
    }  # fmt: skip
    for k in STORM:
        row[k] = sum(st[k].values()) if st else ""
    row.update({"config_hash": cfg.config_hash(), "wall_s": round(wall, 2)})
    return row


def add_retention(rows: list[dict[str, Any]]) -> None:
    ref = {(r["planner"], r["seed"]): r["utility"] for r in rows if r["variant"] == "QUIET"}
    for r in rows:
        u = ref.get((r["planner"], r["seed"]))
        r["retention"] = round(r["utility"] / u, 6) if u else ""


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    order = [v[0] for v in VARIANTS]
    keys = sorted({(r["planner"], r["variant"]) for r in rows},
                  key=lambda k: (PLANNERS.index(k[0]), order.index(k[1])))  # fmt: skip
    for planner, variant in keys:
        sel = [r for r in rows if (r["planner"], r["variant"]) == (planner, variant)]
        rec: dict[str, Any] = {"planner": planner, "variant": variant, "n_runs": len(sel)}
        for m in METRICS:
            xs = [float(r[m]) for r in sel if r.get(m, "") != ""]
            k = len(xs)
            if k == 0:
                rec.update({f"{m}_mean": "", f"{m}_ci95_lo": "", f"{m}_ci95_hi": ""})
                continue
            mean = sum(xs) / k
            sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (k - 1)) if k > 1 else 0.0
            half = float(stats.t.ppf(0.975, k - 1)) * sd / math.sqrt(k) if k > 1 else 0.0
            rec.update({f"{m}_mean": round(mean, 6), f"{m}_ci95_lo": round(mean - half, 6),
                        f"{m}_ci95_hi": round(mean + half, 6)})  # fmt: skip
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
    ap.add_argument("--variants", nargs="*", default=[v[0] for v in VARIANTS])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "results")
    args = ap.parse_args()

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()  # fmt: skip

    commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    sha = hashlib.sha256(SERIES.read_bytes()).hexdigest()
    seeds = list(range(1, args.seeds + 1))
    variants = ["QUIET", *[v for v in args.variants if v != "QUIET"]]
    jobs = [(v, p, s, sha) for v in variants for p in PLANNERS for s in seeds]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs))
    bad = [r for r in rows if r["protected_payload_steps"] or r["confirmed_while_available"]]
    if bad:
        raise RuntimeError(f"safety invariant violated in {len(bad)} runs")
    add_retention(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out / "storm_replay.csv", rows)
    _write_csv(args.out / "storm_replay_summary.csv", summarize(rows))
    meta = {
        "experiment": "Phase 4 S11 storm replay, protection P-A/P-B/P-C (DL-069)",
        "git_commit": commit,
        "git_dirty": dirty,
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "series_file": str(SERIES.relative_to(ROOT)),
        "series_sha256": sha,
        "epoch_utc": EPOCH,
        "duration_s": DURATION_S,
        "variants": [list(v) for v in VARIANTS if v[0] in variants],
        "planners": list(PLANNERS),
        "seeds": seeds,
        "n_runs": len(rows),
        "workers": args.workers,
        "total_wall_s": round(time.time() - t0, 1),
    }
    (args.out / "storm_replay_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ("git_commit", "git_dirty", "n_runs", "total_wall_s")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

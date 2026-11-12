"""Tune the forecast-handover candidate on the February 2024 storm (DL-094).

Out-of-sample fold forecasts (``configs/data/tuning_feb2024_series.json``, P-B median),
the S11 setup moved to 8 Feb 2024 00:10 UT (690 600 s), position-based access, the age
rule and tolerances 100 / 100 / 50 / 200 pfu, no outage; planner B4; seeds 1-3. Arms:
QUIET (no environment), the reactive baseline, and the candidate on the grid
theta in {0.5, 0.7, 0.9} x lead in {30, 60, 120} min.

Selection (fixed in DL-094 before any run): the largest mean retention gain over the
baseline under the duplicate-charging utility; ties go to the larger theta, then the
shorter lead. Writes ``handover_tuning.csv`` (one row per run),
``handover_tuning_summary.csv`` (per setting: mean gains) and ``handover_tuning_meta.json``
(commit, git_dirty, hashes, the chosen setting) to ``--out``.

    uv run python scripts/experiments/handover_tuning.py --out /tmp/hot
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from storm_replay_comparison import scenario_config  # noqa: E402

SERIES = ROOT / "configs" / "data" / "tuning_feb2024_series.json"
EPOCH = "2024-02-08T00:10:00Z"
TOLERANCES = [100.0, 100.0, 50.0, 200.0]
THETAS = (0.5, 0.7, 0.9)
LEADS_S = (1800.0, 3600.0, 7200.0)
SEEDS = (1, 2, 3)
PLANNER = "rule_b4"
ARMS = ["quiet", "baseline"] + [f"candidate:{th:g}:{ld:g}" for th in THETAS for ld in LEADS_S]


def config(arm: str, seed: int, sha: str) -> dict[str, Any]:
    raw = scenario_config("P-B", PLANNER, seed, sha)
    raw["scenario_id"] = "HO_TUNE_FEB2024"
    raw["time"]["epoch_utc"] = EPOCH
    if arm == "quiet":
        del raw["environment"]
        return raw
    raw["environment"]["replay"].update(
        series_file=str(SERIES.relative_to(ROOT)), access={}, forecast_max_age_s=3600.0,
        radiation_tolerance_pfu=TOLERANCES,
    )  # fmt: skip
    if arm.startswith("candidate"):
        _, th, ld = arm.split(":")
        raw["agents"]["handover"] = {"window_threshold_ratio": float(th), "lead_s": float(ld)}
    return raw


def utilities(run: Any) -> tuple[int, int]:
    """(utility, duplicate-charged utility: each duplicate costs its task's priority)."""
    pri = {t.task_id: t.priority for t in run.catalog}
    u = run.summary["operations"]["utility"]
    dup = sum(pri[s.task_id] for s in run.segments if s.outcome == "duplicate")
    return u, u - dup


def run_one(job: tuple[str, int, str]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    arm, seed, sha = job
    cfg = parse_scenario(config(arm, seed, sha))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    u, u_dup = utilities(run)
    st = run.summary.get("storm", {})
    unprot = {a: st["hazard_s"][a] - st["protected_in_hazard_s"][a] for a in st.get("hazard_s", {})}
    return {
        "arm": arm, "seed": seed, "utility": u, "utility_dup_charged": u_dup,
        "n_completed": run.summary["operations"]["n_completed"],
        "n_duplicates": run.summary["operations"]["n_duplicates"],
        "unprotected_hazard_s": json.dumps(unprot, sort_keys=True),
        "config_hash": cfg.config_hash(), "wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip


def summarize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    by = {(r["arm"], r["seed"]): r for r in rows}
    out = []
    for arm in ARMS[1:]:
        g, gd = [], []
        for s in SEEDS:
            q = by[("quiet", s)]["utility"]
            g.append((by[(arm, s)]["utility"] - by[("baseline", s)]["utility"]) / q)
            gd.append((by[(arm, s)]["utility_dup_charged"]
                       - by[("baseline", s)]["utility_dup_charged"]) / q)  # fmt: skip
            hazard_same = (
                by[(arm, s)]["unprotected_hazard_s"] == by[("baseline", s)]["unprotected_hazard_s"]
            )
            if not hazard_same:
                print(f"WARNING: {arm} seed {s}: unprotected hazard differs", flush=True)
        out.append({"arm": arm, "mean_retention_gain": round(sum(g) / len(g), 6),
                    "mean_retention_gain_dup_charged": round(sum(gd) / len(gd), 6)})  # fmt: skip

    def key(r: dict[str, Any]) -> tuple[float, float, float]:
        _, th, ld = r["arm"].split(":")
        return (r["mean_retention_gain_dup_charged"], float(th), -float(ld))

    best = max((r for r in out if r["arm"].startswith("candidate")), key=key)
    return out, best["arm"]


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    from astramesh.evaluation.manifest import git_state

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(SERIES.read_bytes()).hexdigest()
    t0 = time.perf_counter()
    jobs = [(a, s, sha) for a in ARMS for s in SEEDS]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = list(ex.map(run_one, jobs))
    summary, chosen = summarize(rows)
    _write(args.out / "handover_tuning.csv", rows)
    _write(args.out / "handover_tuning_summary.csv", summary)
    git = git_state(ROOT)
    _, th, ld = chosen.split(":")
    meta = {
        "experiment": "Forecast-handover tuning on 8-16 Feb 2024 (DL-094)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "series_sha256": sha, "epoch_utc": EPOCH, "planner": PLANNER, "seeds": list(SEEDS),
        "tolerances_pfu": TOLERANCES, "thetas": list(THETAS), "leads_s": list(LEADS_S),
        "selection": "max mean retention gain (duplicate-charged); ties: larger theta, "
                     "then shorter lead",
        "chosen": {"window_threshold_ratio": float(th), "lead_s": float(ld)},
        "config_hashes": {f"{r['arm']}/seed{r['seed']}": r["config_hash"] for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "handover_tuning_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for r in summary:
        print(r, flush=True)
    print(json.dumps({"chosen": meta["chosen"], "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

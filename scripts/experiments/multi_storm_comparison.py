"""Frozen forecast handover against the baseline on four more storms (DL-098, scope A).

The four out-of-sample evaluation storms (``configs/data/fold_<name>_series.json``:
18 Jul 2023, 29 Jul 2023, 29 Jan 2024, 23-24 Mar 2024; forecasts fitted before each
fold's start), each run for 690 600 s from 00:10 UT on its window's first day, with the
DL-093 per-spacecraft risk (position-based access, the 3600 s age rule, tolerances
100 / 100 / 50 / 200 pfu, no outage), forecast P-B median, planners B3 + timeout and
B4, seeds 1-3. Arms: baseline, candidate (the setting frozen in DL-096, taken from
``handover_comparison.FROZEN``) and QUIET (no environment). Nothing is tuned here.

Writes ``multi_storm_runs.csv`` (one row per run), ``multi_storm_summary.csv`` (per storm
and planner, and pooled over storms: retention differences, both utilities, hazard
identity) and ``multi_storm_meta.json`` to ``--out``.

    uv run python scripts/experiments/multi_storm_comparison.py --out /tmp/msc
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
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_comparison import FROZEN  # noqa: E402
from storm_replay_comparison import scenario_config  # noqa: E402

STORMS = {  # name -> run epoch (window start + 10 min, first record available at t = 0)
    "jul18_2023": "2023-07-16T00:10:00Z",
    "jul29_2023": "2023-07-27T00:10:00Z",
    "jan29_2024": "2024-01-27T00:10:00Z",
    "mar23_2024": "2024-03-21T00:10:00Z",
}
TOLERANCES = [100.0, 100.0, 50.0, 200.0]
PLANNERS = ("cbba_b3_timeout", "rule_b4")
ARMS = ("baseline", "candidate", "quiet")
SEEDS = (1, 2, 3)


def series(name: str) -> Path:
    return ROOT / "configs" / "data" / f"fold_{name}_series.json"


def config(storm: str, planner: str, arm: str, seed: int) -> dict[str, Any]:
    path = series(storm)
    raw = scenario_config("P-B", planner, seed, hashlib.sha256(path.read_bytes()).hexdigest())
    raw["scenario_id"] = f"HO_MULTI_{storm}_{arm}"
    raw["time"]["epoch_utc"] = STORMS[storm]
    if arm == "quiet":
        del raw["environment"]
        return raw
    raw["environment"]["replay"].update(
        series_file=str(path.relative_to(ROOT)), access={}, forecast_max_age_s=3600.0,
        radiation_tolerance_pfu=TOLERANCES,
    )  # fmt: skip
    if arm == "candidate":
        assert FROZEN is not None
        raw["agents"]["handover"] = dict(FROZEN)
    return raw


def run_one(job: tuple[str, str, str, int]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    storm, planner, arm, seed = job
    cfg = parse_scenario(config(storm, planner, arm, seed))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    log = EventLog()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), log)
    s, st = run.summary, run.summary.get("storm", {})
    pri = {t.task_id: t.priority for t in run.catalog}
    u = s["operations"]["utility"]
    dup = sum(pri[g.task_id] for g in run.segments if g.outcome == "duplicate")
    kinds = [e.kind for e in log]
    hz = st.get("hazard_s", {})
    unprot = {a: hz[a] - st["protected_in_hazard_s"][a] for a in hz}
    prot = {a: sum(m.get(k, 0.0) for k in ("PROTECTIVE", "RECOVERY"))
            for a, m in s["protection"]["time_in_mode_s"].items()}  # fmt: skip
    return {
        "storm": storm, "planner": planner, "arm": arm, "seed": seed,
        "utility": u, "utility_dup_charged": u - dup,
        "n_tasks": s["operations"]["n_tasks"], "n_completed": s["operations"]["n_completed"],
        "n_duplicates": s["operations"]["n_duplicates"],
        "tasks_taken_over": kinds.count("task_taken_over"),
        "window_releases": kinds.count("window_release"),
        "hazard_s": sum(hz.values()), "unprotected_hazard_s": sum(unprot.values()),
        "unprotected_by_sc": json.dumps(unprot, sort_keys=True),
        "exposure_s": sum(st["exposed_s"].values()) if st else 0.0,
        "protected_s": sum(prot.values()),
        "payload_steps_in_protected_modes": sum(
            s["protection"]["payload_steps_in_protected_modes"].values()),
        "config_hash": cfg.config_hash(), "wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip


def _interval(d: list[float]) -> dict[str, Any]:
    a = np.asarray(d, dtype=float)
    m = float(a.mean())
    if len(a) < 2 or np.all(a == a[0]):
        lo = hi = m
    else:
        half = float(stats.t.ppf(0.975, len(a) - 1) * a.std(ddof=1) / np.sqrt(len(a)))
        lo, hi = m - half, m + half
    p = 1.0 if np.all(a == 0) else float(stats.wilcoxon(a).pvalue)
    return {"n": len(a), "mean": round(m, 6), "ci_lo": round(lo, 6), "ci_hi": round(hi, 6),
            "wilcoxon_p": round(p, 6)}  # fmt: skip


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by = {(r["storm"], r["planner"], r["arm"], r["seed"]): r for r in rows}
    out = []
    for pl in PLANNERS:
        per_storm: dict[str, dict[str, float]] = {}
        for st in STORMS:
            row: dict[str, Any] = {"scope": st, "planner": pl}
            same = True
            for util in ("utility", "utility_dup_charged"):
                d = []
                for s in SEEDS:
                    c, b = by[(st, pl, "candidate", s)], by[(st, pl, "baseline", s)]
                    q = by[(st, pl, "quiet", s)]["utility"]
                    d.append((c[util] - b[util]) / q)
                    same &= (c["unprotected_by_sc"] == b["unprotected_by_sc"]
                             and c["exposure_s"] == b["exposure_s"])  # fmt: skip
                row[f"gain_{util}"] = round(float(np.mean(d)), 6)
                row[f"gain_{util}_seed_spread"] = round(float(np.ptp(d)), 6)
                per_storm.setdefault(util, {})[st] = float(np.mean(d))
            row["baseline_retention"] = round(float(np.mean(
                [by[(st, pl, "baseline", s)]["utility"] / by[(st, pl, "quiet", s)]["utility"]
                 for s in SEEDS])), 6)  # fmt: skip
            row["hazard_identical"] = same
            out.append(row)
        for util in ("utility", "utility_dup_charged"):
            out.append({"scope": f"pooled over storms ({util})", "planner": pl,
                        **_interval(list(per_storm[util].values()))})  # fmt: skip
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
    if FROZEN is None:
        raise SystemExit("FROZEN is not set (DL-096)")
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    todo = [(st, pl, arm, s) for pl in PLANNERS for st in STORMS for arm in ARMS for s in SEEDS]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = list(ex.map(run_one, todo))
    summary = summarize(rows)
    _write(args.out / "multi_storm_runs.csv", rows)
    _write(args.out / "multi_storm_summary.csv", summary)
    git = git_state(ROOT)
    meta = {
        "experiment": "Frozen forecast handover on four more storms (DL-098, scope A)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "frozen": FROZEN, "storms": STORMS,
        "series_sha256": {st: hashlib.sha256(series(st).read_bytes()).hexdigest()
                          for st in STORMS},
        "tolerances_pfu": TOLERANCES, "seeds": list(SEEDS), "n_runs": len(rows),
        "config_hashes": {f"{r['storm']}/{r['planner']}/{r['arm']}/seed{r['seed']}":
                          r["config_hash"] for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "multi_storm_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for r in summary:
        print(r, flush=True)
    print(json.dumps({"runs": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

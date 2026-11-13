"""Ablations of the baseline protection system on five storms (DL-106).

Storms: the four DL-099 evaluation storms in the DL-100 setup
(``multi_storm_comparison.config``) and May 2024 in the DL-097 S11-H main case
(``handover_comparison.config``: P-B, sc01 forecast outage). May 2024 was the held-out
test; this is a disclosed second use and nothing is tuned here.

Arms, one change each against the full baseline:

* ``no_lookahead`` (A1): ``environment.replay.access.horizon_s`` one time step instead of
  3600 s, so the radiation input is the current position;
* ``no_forecast`` (A2): P-A (latest measurement) instead of the P-B median;
* ``no_hysteresis`` (A3): ``release_exposure_ratio`` 0.99 (must stay below the protect
  ratio 1.0), ``release_dwell_s``, ``watch_release_dwell_s`` and ``recovery_min_dwell_s`` 0;
* ``no_reconciliation`` (A4): planner B0 (``static_b0``: the B4 ground plan without
  redistribution) with the baseline protection, compared with each planner's baseline.

A1 - A3 run under B3 + timeout and B4 with their own baseline and QUIET (identical to the
recorded DL-100 and DL-097 runs); B0 runs its baseline and QUIET. Seeds 1-3. The study is
descriptive (no hypothesis is accepted or rejected). B4 and B0 jobs run first, and each
finished run is appended to ``progress.jsonl`` so they can be inspected while B3 runs.

Writes ``ablation_runs.csv``, ``ablation_summary.csv`` and ``ablation_meta.json`` to ``--out``.

    uv run python scripts/experiments/ablation_study.py --out /tmp/abl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_comparison import config as may_config  # noqa: E402
from multi_storm_comparison import STORMS as EVAL_STORMS  # noqa: E402
from multi_storm_comparison import _interval, series  # noqa: E402
from multi_storm_comparison import config as storm_config  # noqa: E402
from protection_tuning import extra_unprotected_s, storm_metrics  # noqa: E402
from storm_replay_comparison import SERIES as MAY_SERIES  # noqa: E402

MAY = "may2024"
STORMS = (*EVAL_STORMS, MAY)
PLANNERS = ("cbba_b3_timeout", "rule_b4")
B0 = "static_b0"
ABLATIONS = ("no_lookahead", "no_forecast", "no_hysteresis")
ARMS = ("baseline", "quiet", *ABLATIONS)
SEEDS = (1, 2, 3)


def _base(storm: str, planner: str, arm: str, seed: int) -> dict[str, Any]:
    """The recorded baseline or QUIET run of ``storm`` (DL-100 or DL-097), byte for byte."""
    if storm == MAY:
        sha = hashlib.sha256(MAY_SERIES.read_bytes()).hexdigest()
        return may_config("S11-H", "P-B", planner, arm, seed, sha)
    return storm_config(storm, planner, arm, seed)


def config(storm: str, planner: str, arm: str, seed: int) -> dict[str, Any]:
    if arm in ("baseline", "quiet"):
        return _base(storm, planner, arm, seed)
    if arm not in ABLATIONS:
        raise ValueError(f"unknown arm {arm!r}")
    if planner == B0:
        raise ValueError("B0 runs only its baseline and QUIET (A4)")
    raw = _base(storm, planner, "baseline", seed)
    raw["scenario_id"] = f"ABL_{storm}_{arm}"
    replay = raw["environment"]["replay"]
    if replay["forecast"] != "P-B/q50" or "access" not in replay:
        raise ValueError("ablations expect the P-B median and position-based access")
    if arm == "no_lookahead":
        replay["access"] = {**replay["access"], "horizon_s": float(raw["time"]["time_step_s"])}
    elif arm == "no_forecast":
        replay["forecast"] = "P-A"
    else:  # no_hysteresis
        sup = raw.setdefault("supervisor", {})
        sup.update(release_exposure_ratio=0.99, release_dwell_s=0.0, watch_release_dwell_s=0.0,
                   recovery_min_dwell_s=0.0)  # fmt: skip
    return raw


def jobs() -> list[tuple[str, str, str, int]]:
    """B4 and B0 first (fast), then B3 + timeout with the no-hysteresis arm first."""
    fast = [(st, pl, arm, s) for pl in ("rule_b4",) for st in STORMS for arm in ARMS
            for s in SEEDS]  # fmt: skip
    fast += [(st, B0, arm, s) for st in STORMS for arm in ("baseline", "quiet") for s in SEEDS]
    b3_arms = ("no_hysteresis", "baseline", "quiet", "no_lookahead", "no_forecast")
    slow = [(st, "cbba_b3_timeout", arm, s) for arm in b3_arms for st in STORMS for s in SEEDS]
    return fast + slow


def run_one(job: tuple[str, str, str, int]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    storm, planner, arm, seed = job
    cfg = parse_scenario(config(storm, planner, arm, seed))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    return {
        "storm": storm, "planner": planner, "arm": arm, "seed": seed, **storm_metrics(run),
        "config_hash": cfg.config_hash(), "wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip


def _sum(js: str) -> float:
    return float(sum(json.loads(js).values()))


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per storm and pooled over storms (n = 5): retention change against each planner's
    baseline, worst extra unprotected hazard, protected time and protection entries."""
    by = {(r["storm"], r["planner"], r["arm"], r["seed"]): r for r in rows}
    out: list[dict[str, Any]] = []
    for pl in PLANNERS:
        for abl in (*ABLATIONS, "no_reconciliation"):
            changes: list[float] = []
            worst = -np.inf
            for st in STORMS:
                d, extra, dprot, dent, dunp = [], [], [], [], []
                for s in SEEDS:
                    base, q = by[(st, pl, "baseline", s)], by[(st, pl, "quiet", s)]
                    a = by[(st, B0, "baseline", s)] if abl == "no_reconciliation" else by[
                        (st, pl, abl, s)]  # fmt: skip
                    d.append((a["utility"] - base["utility"]) / q["utility"])
                    extra.append(extra_unprotected_s(a, base))
                    key = "unprotected_hazard_s"
                    dunp.append(_sum(a[key]) - _sum(base[key]))
                    dprot.append((_sum(a["protected_s"]) - _sum(base["protected_s"])) / 3600)
                    dent.append(_sum(a["protective_entries"]) - _sum(base["protective_entries"]))
                changes.append(float(np.mean(d)))
                worst = max(worst, max(extra))
                out.append({
                    "scope": st, "planner": pl, "ablation": abl,
                    "baseline_retention": round(float(np.mean(
                        [by[(st, pl, "baseline", s)]["utility"]
                         / by[(st, pl, "quiet", s)]["utility"] for s in SEEDS])), 6),
                    "retention_change": round(float(np.mean(d)), 6),
                    "retention_change_seed_spread": round(float(np.ptp(d)), 6),
                    "max_extra_unprotected_s": max(extra),
                    "unprotected_change_s_all_sc": float(np.mean(dunp)),
                    "protected_change_h_all_sc": round(float(np.mean(dprot)), 2),
                    "protective_entries_change_all_sc": float(np.mean(dent)),
                })  # fmt: skip
            out.append({"scope": "pooled over storms", "planner": pl, "ablation": abl,
                        **_interval(changes), "max_extra_unprotected_s": worst})  # fmt: skip
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
    todo = jobs()
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(args.workers) as ex, (args.out / "progress.jsonl").open("w") as pf:
        futs = [ex.submit(run_one, j) for j in todo]
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            pf.write(json.dumps({k: r[k] for k in ("storm", "planner", "arm", "seed", "utility",
                                                   "unprotected_hazard_s", "protective_entries",
                                                   "wall_s")}) + "\n")  # fmt: skip
            pf.flush()
    order = {j: i for i, j in enumerate(todo)}
    rows.sort(key=lambda r: order[(r["storm"], r["planner"], r["arm"], r["seed"])])
    summary = summarize(rows)
    _write(args.out / "ablation_runs.csv", rows)
    _write(args.out / "ablation_summary.csv", summary)
    git = git_state(ROOT)
    files = {st: series(st) for st in EVAL_STORMS} | {MAY: MAY_SERIES}
    meta = {
        "experiment": "Ablations of the baseline protection system on five storms (DL-106)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "storms": list(STORMS), "planners": [*PLANNERS, B0], "arms": list(ARMS),
        "seeds": list(SEEDS), "n_runs": len(rows),
        "series_sha256": {st: hashlib.sha256(f.read_bytes()).hexdigest()
                          for st, f in files.items()},
        "config_hashes": {f"{r['storm']}/{r['planner']}/{r['arm']}/seed{r['seed']}":
                          r["config_hash"] for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "ablation_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for r in summary:
        if r["scope"] == "pooled over storms":
            print(r, flush=True)
    print(json.dumps({"runs": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

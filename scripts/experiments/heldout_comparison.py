"""Phase 6 held-out storms: the Phase 5 arms on storms after May 2024 (DL-113).

Test storms and their series come from ``configs/data/heldout_selection.json``
(``scripts/data/make_heldout_series.py``); the reserved storms are never run. Setup as
DL-100 (per-spacecraft risk, tolerances 100 / 100 / 50 / 200 pfu, no outage, 20 km
formation, P-B median). Per storm and seed, under B3 + timeout and under B4: baseline,
QUIET, the forecast-handover candidate (DL-096), shorter protection (DL-103) and the
ablations no look-ahead, no forecast and no hysteresis (DL-106); under B0: baseline and
QUIET (no reconciliation). Seeds 1 - 3. Every setting is frozen; nothing is tuned.

Expectations E1 - E5 (DL-113) are evaluated by fixed rules in ``expectations``. Pooled
results use n = test storms and are reported for all test storms and separately by GOES
processing version. B4 and B0 jobs run first, then B3; each finished run is appended to
``progress.jsonl``. Writes ``heldout_runs.csv``, ``heldout_summary.csv`` and
``heldout_meta.json`` to ``--out``.

    uv run python scripts/experiments/heldout_comparison.py --out /tmp/heldout
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
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_comparison import FROZEN as HANDOVER  # noqa: E402
from multi_storm_comparison import TOLERANCES  # noqa: E402
from protection_comparison import FROZEN as SHORTER  # noqa: E402
from protection_tuning import apply_protection, extra_unprotected_s, storm_metrics  # noqa: E402
from storm_replay_comparison import scenario_config  # noqa: E402

SELECTION = ROOT / "configs" / "data" / "heldout_selection.json"
PLANNERS = ("cbba_b3_timeout", "rule_b4")
B0 = "static_b0"
ABLATIONS = ("no_lookahead", "no_forecast", "no_hysteresis")
ARMS = ("baseline", "quiet", "handover", "shorter", *ABLATIONS)
COMPARED = ("handover", "shorter", *ABLATIONS, "no_reconciliation")
SEEDS = (1, 2, 3)


def held_out_storms(path: Path = SELECTION) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in json.loads(path.read_text())["test_storms"]}


def raw_config(series: Path, epoch: str, planner: str, arm: str, seed: int) -> dict[str, Any]:
    """The DL-100 storm config (``multi_storm_comparison.config``) for any series."""
    raw = scenario_config("P-B", planner, seed, hashlib.sha256(series.read_bytes()).hexdigest())
    raw["time"]["epoch_utc"] = epoch
    if arm == "quiet":
        del raw["environment"]
        return raw
    raw["environment"]["replay"].update(
        series_file=str(series.relative_to(ROOT)), access={}, forecast_max_age_s=3600.0,
        radiation_tolerance_pfu=TOLERANCES,
    )  # fmt: skip
    return raw


def arm_config(raw: dict[str, Any], arm: str) -> dict[str, Any]:
    """Apply one arm to a baseline config (the Phase 5 definitions)."""
    if arm == "baseline":
        return raw
    if arm == "handover":
        assert HANDOVER is not None
        raw["agents"]["handover"] = dict(HANDOVER)
        return raw
    if arm == "shorter":
        assert SHORTER is not None
        return apply_protection(raw, SHORTER)
    replay = raw["environment"]["replay"]
    if replay["forecast"] != "P-B/q50" or "access" not in replay:
        raise ValueError("ablations expect the P-B median and position-based access")
    if arm == "no_lookahead":
        replay["access"] = {**replay["access"], "horizon_s": float(raw["time"]["time_step_s"])}
    elif arm == "no_forecast":
        replay["forecast"] = "P-A"
    elif arm == "no_hysteresis":
        sup = raw.setdefault("supervisor", {})
        sup.update(release_exposure_ratio=0.99, release_dwell_s=0.0, watch_release_dwell_s=0.0,
                   recovery_min_dwell_s=0.0)  # fmt: skip
    else:
        raise ValueError(f"unknown arm {arm!r}")
    return raw


def config(storm: str, planner: str, arm: str, seed: int) -> dict[str, Any]:
    if planner == B0 and arm not in ("baseline", "quiet"):
        raise ValueError("B0 runs only its baseline and QUIET (no reconciliation)")
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    s = held_out_storms()[storm]
    raw = raw_config(ROOT / s["series_file"], s["epoch_utc"], planner,
                     "quiet" if arm == "quiet" else "baseline", seed)  # fmt: skip
    raw["scenario_id"] = f"HELDOUT_{storm}_{arm}"
    return raw if arm == "quiet" else arm_config(raw, arm)


def jobs(storms: list[str]) -> list[tuple[str, str, str, int]]:
    """B4 and B0 first (fast), then B3 + timeout."""
    out = [(st, "rule_b4", arm, s) for st in storms for arm in ARMS for s in SEEDS]
    out += [(st, B0, arm, s) for st in storms for arm in ("baseline", "quiet") for s in SEEDS]
    out += [(st, "cbba_b3_timeout", arm, s) for arm in ARMS for st in storms for s in SEEDS]
    return out


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


def interval(d: list[float]) -> dict[str, Any]:
    """Mean, 95 % t-interval and Wilcoxon p over storms; no interval for n < 2."""
    a = np.asarray(d, dtype=float)
    m = float(a.mean()) if len(a) else float("nan")
    if len(a) < 2:
        return {"n": len(a), "mean": round(m, 6), "ci_lo": None, "ci_hi": None,
                "wilcoxon_p": None}  # fmt: skip
    if np.all(a == a[0]):
        lo = hi = m
    else:
        half = float(stats.t.ppf(0.975, len(a) - 1) * a.std(ddof=1) / np.sqrt(len(a)))
        lo, hi = m - half, m + half
    p = 1.0 if np.all(a == 0) else float(stats.wilcoxon(a).pvalue)
    return {"n": len(a), "mean": round(m, 6), "ci_lo": round(lo, 6), "ci_hi": round(hi, 6),
            "wilcoxon_p": round(p, 6)}  # fmt: skip


def _sum(js: str) -> float:
    return float(sum(json.loads(js).values()))


def _arm_row(by: dict[Any, Any], st: str, pl: str, cmp: str, s: int) -> dict[str, Any]:
    return by[(st, B0, "baseline", s)] if cmp == "no_reconciliation" else by[(st, pl, cmp, s)]


def summarize(rows: list[dict[str, Any]], processing: dict[str, str]) -> list[dict[str, Any]]:
    """Per storm and pooled over storms: retention change against each planner's
    baseline (÷ that planner's QUIET), extra unprotected hazard, protected time, entries."""
    by = {(r["storm"], r["planner"], r["arm"], r["seed"]): r for r in rows}
    storms = sorted(processing)
    out: list[dict[str, Any]] = []
    for pl in PLANNERS:
        for cmp in COMPARED:
            change: dict[str, float] = {}
            worst: dict[str, float] = {}
            for st in storms:
                d, extra, dunp, dprot, dent, ddup = [], [], [], [], [], []
                for s in SEEDS:
                    base, q = by[(st, pl, "baseline", s)], by[(st, pl, "quiet", s)]
                    a = _arm_row(by, st, pl, cmp, s)
                    d.append((a["utility"] - base["utility"]) / q["utility"])
                    ddup.append((a["utility_dup_charged"] - base["utility_dup_charged"])
                                / q["utility"])  # fmt: skip
                    extra.append(extra_unprotected_s(a, base))
                    unp = a["unprotected_hazard_s"], base["unprotected_hazard_s"]
                    dunp.append(_sum(unp[0]) - _sum(unp[1]))
                    dprot.append((_sum(a["protected_s"]) - _sum(base["protected_s"])) / 3600)
                    dent.append(_sum(a["protective_entries"]) - _sum(base["protective_entries"]))
                change[st], worst[st] = float(np.mean(d)), max(extra)
                out.append({
                    "scope": st, "processing": processing[st], "planner": pl, "compared": cmp,
                    "baseline_retention": round(float(np.mean(
                        [by[(st, pl, "baseline", s)]["utility"]
                         / by[(st, pl, "quiet", s)]["utility"] for s in SEEDS])), 6),
                    "retention_change": round(float(np.mean(d)), 6),
                    "retention_change_dup_charged": round(float(np.mean(ddup)), 6),
                    "retention_change_seed_spread": round(float(np.ptp(d)), 6),
                    "max_extra_unprotected_s": max(extra),
                    "unprotected_change_s_all_sc": float(np.mean(dunp)),
                    "protected_change_h_all_sc": round(float(np.mean(dprot)), 2),
                    "protective_entries_change_all_sc": float(np.mean(dent)),
                })  # fmt: skip
            for scope, members in (("pooled: all test storms", storms),
                                   *((f"pooled: {v}", [s for s in storms if processing[s] == v])
                                     for v in sorted(set(processing.values())))):  # fmt: skip
                if not members:
                    continue
                out.append({"scope": scope, "planner": pl, "compared": cmp,
                            **interval([change[s] for s in members]),
                            "max_extra_unprotected_s": max(worst[s] for s in members),
                            "storms_with_extra_unprotected":
                                sum(worst[s] > 0 for s in members)})  # fmt: skip
    return out


def seed_differences(rows: list[dict[str, Any]]) -> list[str]:
    """Groups whose seeds differ in utility or per-spacecraft unprotected hazard (E5)."""
    groups: dict[tuple[str, str, str], set[tuple[Any, ...]]] = {}
    for r in rows:
        key = (r["storm"], r["planner"], r["arm"])
        groups.setdefault(key, set()).add((r["utility"], r["unprotected_hazard_s"]))
    return sorted("/".join(k) for k, v in groups.items() if len(v) > 1)


def expectations(summary: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """E1 - E5 of DL-113, each by its fixed rule, over all test storms."""
    pooled = {(r["planner"], r["compared"]): r for r in summary
              if r["scope"] == "pooled: all test storms"}  # fmt: skip

    def above(pl: str, cmp: str) -> bool:
        lo = pooled[(pl, cmp)]["ci_lo"]
        return lo is not None and lo > 0

    def below(pl: str, cmp: str) -> bool:
        hi = pooled[(pl, cmp)]["ci_hi"]
        return hi is not None and hi < 0

    n = pooled[(PLANNERS[0], "handover")]["n"]
    e4 = {a: {pl: pooled[(pl, a)]["storms_with_extra_unprotected"] for pl in PLANNERS}
          for a in ABLATIONS}  # fmt: skip
    diffs = seed_differences(rows)
    return {
        "E1_handover_no_reliable_gain": {
            "held": not any(above(pl, "handover") for pl in PLANNERS),
            "rule": "not held if the pooled interval lies above 0 under either planner"},
        "E2_shorter_no_reliable_gain": {
            "held": not any(above(pl, "shorter")
                            and pooled[(pl, "shorter")]["max_extra_unprotected_s"] <= 600
                            for pl in PLANNERS),
            "rule": "not held if the pooled interval lies above 0 with worst extra "
                    "unprotected hazard <= 600 s"},
        "E3_reconciliation_costs_science": {
            "held": all(below(pl, "no_reconciliation") for pl in PLANNERS),
            "rule": "held only if the pooled interval lies below 0 under both planners"},
        "E4_ablations_add_hazard_on_most_storms": {
            "held": {a: all(v > n / 2 for v in e4[a].values()) for a in ABLATIONS},
            "storms_with_extra_unprotected": e4, "n_storms": n,
            "rule": "held for an ablation if it adds unprotected hazard on more than half "
                    "the test storms under each planner"},
        "E5_seeds_change_no_outcome": {
            "held": not diffs, "groups_that_differ": diffs,
            "rule": "not held if any group's seeds differ in utility or unprotected hazard"},
    }  # fmt: skip


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
    sel = held_out_storms()
    todo = jobs(sorted(sel))
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
    processing = {k: v["processing"] for k, v in sel.items()}
    summary = summarize(rows, processing)
    exp = expectations(summary, rows)
    _write(args.out / "heldout_runs.csv", rows)
    _write(args.out / "heldout_summary.csv", summary)
    git = git_state(ROOT)
    meta = {
        "experiment": "Held-out storms after May 2024: the Phase 5 arms (DL-113)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "selection_sha256": hashlib.sha256(SELECTION.read_bytes()).hexdigest(),
        "storms": sorted(sel), "processing": processing,
        "planners": [*PLANNERS, B0], "arms": list(ARMS), "seeds": list(SEEDS),
        "handover": HANDOVER, "shorter": SHORTER, "n_runs": len(rows),
        "series_sha256": {k: v["series_sha256"] for k, v in sel.items()},
        "expectations": exp,
        "config_hashes": {f"{r['storm']}/{r['planner']}/{r['arm']}/seed{r['seed']}":
                          r["config_hash"] for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "heldout_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for r in summary:
        if r["scope"].startswith("pooled"):
            print(r, flush=True)
    print(json.dumps(exp))
    print(json.dumps({"runs": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

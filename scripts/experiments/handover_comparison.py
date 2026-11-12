"""Forecast handover against the reactive baseline on May 2024 (DL-078, DL-094).

Runs once, after the candidate's setting is frozen from ``handover_tuning.py``
(``FROZEN`` below, set in the tuning-results commit). The S11 setup
(``storm_replay_comparison.scenario_config``: 8 May 2024 00:10 UT, 690 600 s) with:

* ``S11-H``: position-based access, the 3600 s age rule, tolerances 100 / 100 / 50 /
  200 pfu and a forecast outage on sc01 from 1 h before to 5 h after the first onset
  >= 100 pfu (the DL-093 main case);
* ``S11-H+partition``: plus {sc00, sc01} | {sc02, sc03} from 10 May 12:00 to 11 May
  12:00 UT;
* ``S11-H+fault``: plus a critical fault on sc00 for 2 h from the first onset;
* ``S00``: no environment, both arms (identity check).

The tight-schedule scenario of DL-094 is dropped (DL-096): densifying the regions did
not tighten the schedule.

Arms: ``baseline`` (no policy), ``candidate`` (frozen rule), ``candidate-noshare``
(no window in status; S11-H, P-B only), ``quiet`` (the scenario without environment,
for retention). Forecasts P-B (main), P-A and P-C (S11-H only). Planners B3 + timeout
and B4. Seeds: 1-10 for the main comparison and every B4 run; 1-5 for B3 elsewhere.

Writes ``handover_runs.csv`` (one row per run), ``handover_summary.csv`` (paired
retention differences with t-intervals and Wilcoxon tests, both utilities, hazard
identity), ``handover_value.csv`` (cost-loss value over C/L) and
``handover_meta.json`` to ``--out``.

    uv run python scripts/experiments/handover_comparison.py --out /tmp/hoc
"""

from __future__ import annotations

import argparse
import copy
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
from storm_replay_comparison import SERIES, scenario_config  # noqa: E402

#: Frozen candidate setting from the tuning run (DL-094, DL-096: handover_tuning_meta.json
#: from clean commit a7b2046; every setting tied, so the tie rule chose it).
FROZEN: dict[str, float] | None = {"window_threshold_ratio": 0.9, "lead_s": 1800.0}
FIRST_ONSET_S = 234_600  # 2024-05-10 17:20 UT
TOLERANCES = [100.0, 100.0, 50.0, 200.0]
OUTAGE = {"fault_id": "forecast_outage_sc01", "type": "forecast_outage", "spacecraft": ["sc01"],
          "start_s": FIRST_ONSET_S - 3600, "end_s": FIRST_ONSET_S + 5 * 3600,
          "cause": "missed forecast uplinks (DL-090)", "observability": "effects_only",
          "consequences": "sc01's inputs expire after 3600 s"}  # fmt: skip
PARTITION = {"fault_id": "partition_storm", "type": "partition", "spacecraft": [],
             "groups": [["sc00", "sc01"], ["sc02", "sc03"]], "start_s": 215_400,
             "end_s": 301_800, "cause": "crosslink partition during the storm (S09-style)",
             "observability": "effects_only", "consequences": "two isolated pairs"}  # fmt: skip
CRITICAL = {"fault_id": "critical_sc00", "type": "critical_fault", "spacecraft": ["sc00"],
            "start_s": FIRST_ONSET_S, "end_s": FIRST_ONSET_S + 7200,
            "cause": "synthetic thermal/attitude anomaly (S10-style)",
            "observability": "effects_only", "consequences": "sc00 in SAFE for 2 h"}  # fmt: skip
FORECAST = {"P-A": "P-A", "P-B": "P-B/q50", "P-C": "P-C/q50"}
PLANNERS = ("cbba_b3_timeout", "rule_b4")
ALPHAS = tuple(round(0.01 * k, 2) for k in range(1, 100))


def config(scenario: str, forecast: str, planner: str, arm: str, seed: int,
           sha: str) -> dict[str, Any]:  # fmt: skip
    raw = scenario_config("P-B", planner, seed, sha)
    raw["scenario_id"] = ("HO_" + scenario + "_" + arm).replace("+", "_").replace("-", "_")
    rp = raw["environment"]["replay"]
    rp.update(forecast=FORECAST[forecast], access={}, forecast_max_age_s=3600.0,
              radiation_tolerance_pfu=TOLERANCES)  # fmt: skip
    faults: list[dict[str, Any]] = [copy.deepcopy(OUTAGE)]
    if scenario == "S11-H+partition":
        faults.append(copy.deepcopy(PARTITION))
    elif scenario == "S11-H+fault":
        faults.append(copy.deepcopy(CRITICAL))
    if scenario == "S00" or arm == "quiet":
        del raw["environment"]
        faults = [f for f in faults if not f["type"].startswith("forecast_")]
        if scenario == "S00":
            faults = []
    raw["faults"] = faults
    if arm.startswith("candidate"):
        assert FROZEN is not None
        raw["agents"]["handover"] = {**FROZEN, "share_window": arm == "candidate"}
    return raw


def run_one(job: tuple[Any, ...]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    scenario, forecast, planner, arm, seed, sha = job
    cfg = parse_scenario(config(scenario, forecast, planner, arm, seed, sha))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    log = EventLog()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), log)
    s, st = run.summary, run.summary.get("storm", {})
    pri = {t.task_id: t.priority for t in run.catalog}
    u = s["operations"]["utility"]
    dup = sum(pri[g.task_id] for g in run.segments if g.outcome == "duplicate")
    kinds = [e.kind for e in log]
    hz = {a: st["hazard_s"][a] for a in st.get("hazard_s", {})}
    unprot = {a: hz[a] - st["protected_in_hazard_s"][a] for a in hz}
    return {
        "scenario": scenario, "forecast": forecast, "planner": planner, "arm": arm,
        "seed": seed, "utility": u, "utility_dup_charged": u - dup,
        "n_tasks": s["operations"]["n_tasks"], "n_completed": s["operations"]["n_completed"],
        "n_duplicates": s["operations"]["n_duplicates"],
        "n_invalid": s["operations"]["n_invalid"],
        "tasks_taken_over": kinds.count("task_taken_over"),
        "window_releases": kinds.count("window_release"),
        "messages_sent": s["network"]["sent"], "bytes_sent": s["network"]["bytes_sent"],
        "hazard_s": sum(hz.values()), "unprotected_hazard_s": sum(unprot.values()),
        "unprotected_by_sc": json.dumps(unprot, sort_keys=True),
        "exposure_s": sum(st["exposed_s"].values()) if st else 0.0,
        "false_protection_s": sum(st["protected_outside_hazard_s"].values()) if st else 0.0,
        "no_truth_s": sum(st["no_truth_s"].values()) if st else 0.0,
        "duration_s": cfg.time.duration_s * len(s["protection"]["time_in_mode_s"]),
        "config_hash": cfg.config_hash(), "wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip


def jobs(sha: str) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []

    def add(sc: str, fc: str, arms: tuple[str, ...], b3_seeds: int) -> None:
        for planner in PLANNERS:
            n = b3_seeds if planner == "cbba_b3_timeout" else 10
            for arm in arms:
                for seed in range(1, n + 1):
                    out.append((sc, fc, planner, arm, seed, sha))

    add("S11-H", "P-B", ("baseline", "candidate", "quiet"), 10)
    for fc in ("P-A", "P-C"):
        add("S11-H", fc, ("baseline", "candidate"), 5)
    for sc in ("S11-H+partition", "S11-H+fault"):
        add(sc, "P-B", ("baseline", "candidate", "quiet"), 5)
    add("S11-H", "P-B", ("candidate-noshare",), 5)
    for planner in PLANNERS:
        for arm in ("baseline", "candidate"):
            out.append(("S00", "P-B", planner, arm, 1, sha))
    return list(dict.fromkeys(out))


def _paired(d: list[float]) -> dict[str, Any]:
    a = np.asarray(d, dtype=float)
    n, m = len(a), float(a.mean())
    if n < 2 or np.all(a == a[0]):
        return {"n": n, "mean": round(m, 6), "ci_lo": round(m, 6), "ci_hi": round(m, 6),
                "wilcoxon_p": 1.0 if np.all(a == 0) else ""}  # fmt: skip
    half = float(stats.t.ppf(0.975, n - 1) * a.std(ddof=1) / np.sqrt(n))
    p = float(stats.wilcoxon(a).pvalue) if np.any(a != 0) else 1.0
    return {"n": n, "mean": round(m, 6), "ci_lo": round(m - half, 6),
            "ci_hi": round(m + half, 6), "wilcoxon_p": round(p, 6)}  # fmt: skip


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by = {(r["scenario"], r["forecast"], r["planner"], r["arm"], r["seed"]): r for r in rows}
    quiet = {(r["scenario"], r["planner"], r["seed"]): r["utility"]
             for r in rows if r["arm"] == "quiet"}  # fmt: skip
    out = []
    groups = sorted({(r["scenario"], r["forecast"], r["planner"], r["arm"]) for r in rows
                     if r["arm"].startswith("candidate") and r["scenario"] != "S00"})  # fmt: skip
    for sc, fc, pl, arm in groups:
        seeds = sorted(s for (a, b, c, d, s) in by if (a, b, c, d) == (sc, fc, pl, arm)
                       and (sc, fc, pl, "baseline", s) in by and (sc, pl, s) in quiet)  # fmt: skip
        if not seeds:
            continue
        cand = [by[(sc, fc, pl, arm, s)] for s in seeds]
        base = [by[(sc, fc, pl, "baseline", s)] for s in seeds]
        q = [quiet[(sc, pl, s)] for s in seeds]
        for util in ("utility", "utility_dup_charged"):
            d = [(c[util] - b[util]) / qq for c, b, qq in zip(cand, base, q, strict=True)]
            out.append({
                "scenario": sc, "forecast": fc, "planner": pl, "arm": arm, "utility_kind": util,
                **_paired(d),
                "hazard_identical": all(c["unprotected_by_sc"] == b["unprotected_by_sc"]
                                        and c["exposure_s"] == b["exposure_s"]
                                        for c, b in zip(cand, base, strict=True)),
                "mean_retention_baseline": round(float(np.mean(
                    [b[util] / qq for b, qq in zip(base, q, strict=True)])), 6),
            })  # fmt: skip
    return out


def value_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cost-loss value (R03) of the protection decisions: per unit time, protecting costs
    alpha (= C/L) and unprotected hazard costs 1; V = (E_clim - E) / (E_clim - E_perfect)."""
    acc: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for r in rows:
        if r["arm"] in ("quiet",) or r["scenario"] == "S00":
            continue
        acc.setdefault((r["scenario"], r["forecast"], r["planner"], r["arm"]), []).append(r)
    out = []
    for key, rs in sorted(acc.items()):
        tot = sum(r["duration_s"] - r["no_truth_s"] for r in rs)
        hz = sum(r["hazard_s"] for r in rs) / tot
        miss = sum(r["unprotected_hazard_s"] for r in rs) / tot
        prot = (sum(r["hazard_s"] - r["unprotected_hazard_s"] + r["false_protection_s"]
                    for r in rs) / tot)  # fmt: skip
        for a in ALPHAS:
            clim, perf, e = min(a, hz), a * hz, a * prot + miss
            v = (clim - e) / (clim - perf) if clim > perf else float("nan")
            out.append({"scenario": key[0], "forecast": key[1], "planner": key[2],
                        "arm": key[3], "cost_loss_ratio": a, "value": round(v, 6)})  # fmt: skip
    return out


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    from astramesh.evaluation.manifest import git_state

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    if FROZEN is None:
        raise SystemExit("FROZEN is not set: run handover_tuning.py and freeze first (DL-094)")
    args.out.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(SERIES.read_bytes()).hexdigest()
    t0 = time.perf_counter()
    todo = jobs(sha)
    todo.sort(key=lambda j: j[2] != "cbba_b3_timeout")  # long B3 runs first
    with ProcessPoolExecutor(args.workers) as ex:
        rows = list(ex.map(run_one, todo))
    summary = summarize(rows)
    _write(args.out / "handover_runs.csv", rows)
    _write(args.out / "handover_summary.csv", summary)
    _write(args.out / "handover_value.csv", value_rows(rows))
    git = git_state(ROOT)
    meta = {
        "experiment": "Forecast handover vs reactive baseline on May 2024 (DL-078, DL-094)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "series_sha256": sha, "frozen": FROZEN, "n_runs": len(rows),
        "config_hashes": {"/".join(str(r[k]) for k in ("scenario", "forecast", "planner",
                                                        "arm", "seed")): r["config_hash"]
                          for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "handover_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for r in summary:
        if r["scenario"] == "S11-H" and r["forecast"] == "P-B":
            print(r, flush=True)
    print(json.dumps({"runs": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

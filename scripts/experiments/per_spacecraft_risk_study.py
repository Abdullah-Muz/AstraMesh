"""Per-spacecraft risk on the S11 storm week (Phase 5 increment 3; DL-090, DL-091).

Runs the Phase 4 S11 setup (``storm_replay_comparison.scenario_config``: S00 base moved
to 8 May 2024 00:10 UT, 690 600 s) with forecast P-B median, planner B4 and seed 1, in
these cases:

* ``phase4``: no position model (the Phase 4 P-B run; reference for RK-04);
* ``position``: position-based access (DL-090 option A) and the 3600 s age rule;
* ``position+tolerances``: plus tolerances 100 / 100 / 50 / 200 pfu;
* ``position+outage``: plus a forecast outage on sc01 from 1 h before the first onset
  >= 100 pfu (10 May 17:20 UT) to 5 h after it;
* ``main``: position, tolerances and outage;
* cutoff sensitivity on ``main``: cap 8 deg, no cap, slope x0.5 and x1.5, and the
  Stormer cutoff (R09 eq. 6.17 at 525 km, as invariant latitude) with no storm shift.

Modes depend on the planner only through recovery peer contact, so the fast planner
is used. Writes ``per_spacecraft_risk.csv`` (per case and spacecraft: time in the
caps, hazard, unprotected hazard, exposure, false protection, time protected,
PROTECTIVE entries), ``per_spacecraft_risk_cases.csv`` (per case: utility, tasks,
time in which spacecraft are in different modes, time in which one is protected while
another can do science, and the handover-opportunity measure of DL-090) and
``per_spacecraft_risk_meta.json`` (commit, git_dirty, lockfile and config hashes).

    uv run python scripts/experiments/per_spacecraft_risk_study.py --out /tmp/psr
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from storm_replay_comparison import SERIES, scenario_config  # noqa: E402

FIRST_ONSET_S = 234_600  # first record >= 100 pfu starts 2024-05-10 17:20 UT
OUTAGE = {"fault_id": "forecast_outage_sc01", "type": "forecast_outage",
          "spacecraft": ["sc01"], "start_s": FIRST_ONSET_S - 3600,
          "end_s": FIRST_ONSET_S + 5 * 3600, "cause": "missed forecast uplinks (DL-090)",
          "observability": "effects_only",
          "consequences": "sc01's inputs expire after 3600 s"}  # fmt: skip
TOLERANCES = [100.0, 100.0, 50.0, 200.0]
R_525 = (6_378_137.0 + 525_000.0) / 6_371_200.0
P10_GV = math.sqrt(10.0 * (10.0 + 2 * 938.272)) / 1000.0
STORMER_LAT = math.acos((P10_GV * R_525**2 / 14.9) ** 0.25)  # dipole latitude, R09 eq. 6.17
STORMER_INV_DEG = round(math.degrees(math.acos(math.cos(STORMER_LAT) / math.sqrt(R_525))), 2)
SLOPE = 1.0 / 19.11
#: name -> (access overrides or None, tolerances, outage)
CASES: dict[str, tuple[dict[str, Any] | None, Any, bool]] = {
    "phase4": (None, 100.0, False),
    "position": ({}, 100.0, False),
    "position+tolerances": ({}, TOLERANCES, False),
    "position+outage": ({}, 100.0, True),
    "main": ({}, TOLERANCES, True),
    "main/cap8": ({"max_shift_deg": 8.0}, TOLERANCES, True),
    "main/nocap": ({"max_shift_deg": None}, TOLERANCES, True),
    "main/slope0.5": ({"storm_slope_deg_per_nt": 0.5 * SLOPE}, TOLERANCES, True),
    "main/slope1.5": ({"storm_slope_deg_per_nt": 1.5 * SLOPE}, TOLERANCES, True),
    "main/stormer_noshift": ({"quiet_cutoff_deg": STORMER_INV_DEG,
                              "storm_slope_deg_per_nt": 0.0}, TOLERANCES, True),
}  # fmt: skip
SCIENCE = ("NOMINAL", "STORM_WATCH")
PROTECTED = ("PROTECTIVE", "RECOVERY")


def config(case: str, sha: str) -> dict[str, Any]:
    access, tol, outage = CASES[case]
    raw = scenario_config("P-B", "rule_b4", 1, sha)
    raw["scenario_id"] = "S11_PSR_" + case.replace("+", "_").replace("/", "_").replace(".", "")
    rp = raw["environment"]["replay"]
    rp["radiation_tolerance_pfu"] = tol
    if access is not None:
        rp["access"] = dict(access)
        rp["forecast_max_age_s"] = 3600.0
    if outage:
        raw["faults"] = [OUTAGE]
    return raw


def _mode_grid(history: list[tuple[int, str, str, str]], t_ns: np.ndarray) -> np.ndarray:
    modes = np.full(len(t_ns), "NOMINAL", dtype=object)
    for t, _, new, _ in history:
        modes[t_ns >= t] = new
    return modes


def run_case(job: tuple[str, str]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    case, sha = job
    cfg = parse_scenario(config(case, sha))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    wall = time.perf_counter() - t0
    s, st = run.summary, run.summary["storm"]
    p = s["protection"]
    ids = sorted(p["time_in_mode_s"])
    t_ns = np.asarray(run.formation.trajectory.t_ns)
    step_s = cfg.time.time_step_s
    grid = {a: _mode_grid(run.agents[a].mode_history(), t_ns) for a in ids}
    stack = np.stack([grid[a] for a in ids], axis=1)
    differ = np.array([len(set(row)) > 1 for row in stack])
    science = np.isin(stack, SCIENCE)
    protected = np.isin(stack, PROTECTED)
    split = protected.any(axis=1) & science.any(axis=1)
    # Handover opportunity (DL-090): tasks with a window for a spacecraft that is not in
    # a science mode at its window start while another spacecraft with a window is.
    opp_tasks, opp_priority = 0, 0
    for task in run.catalog:
        starts = {w.spacecraft: w.first_tick for w in task.windows}
        blocked = {a for a, k in starts.items() if grid[a][k] not in SCIENCE}
        free = {a for a, k in starts.items() if grid[a][k] in SCIENCE}
        if blocked and free:
            opp_tasks += 1
            opp_priority += task.priority
    per = []
    for a in ids:
        hazard = st["hazard_s"][a]
        per.append({
            "case": case, "spacecraft": a,
            "tolerance_pfu": cfg.environment.replay.tolerance_pfu(ids.index(a))
            if cfg.environment and cfg.environment.replay else "",
            "in_access_h": round(st["in_access_s"][a] / 3600, 3) if "in_access_s" in st else "",
            "hazard_h": round(hazard / 3600, 3),
            "unprotected_hazard_h": round((hazard - st["protected_in_hazard_s"][a]) / 3600, 3),
            "exposure_s": st["exposed_s"][a],
            "false_protection_h": round(st["protected_outside_hazard_s"][a] / 3600, 3),
            "protected_h": round(sum(p["time_in_mode_s"][a][m] for m in PROTECTED) / 3600, 3),
            "protective_entries": sum(1 for x in p["transitions"][a] if x["to"] == "PROTECTIVE"),
        })  # fmt: skip
    row = {
        "case": case, "utility": s["operations"]["utility"],
        "n_completed": s["operations"]["n_completed"], "n_tasks": s["operations"]["n_tasks"],
        "n_duplicates": s["operations"]["n_duplicates"],
        "modes_differ_h": round(float(differ.sum()) * step_s / 3600, 3),
        "protected_while_peer_science_h": round(float(split.sum()) * step_s / 3600, 3),
        "handover_opportunity_tasks": opp_tasks,
        "handover_opportunity_priority": opp_priority,
        "config_hash": cfg.config_hash(), "wall_s": round(wall, 1),
    }  # fmt: skip
    return {"row": row, "per": per}


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    from astramesh.evaluation.manifest import git_state

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=len(CASES))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(SERIES.read_bytes()).hexdigest()
    t0 = time.perf_counter()
    with ProcessPoolExecutor(args.workers) as ex:
        results = list(ex.map(run_case, [(c, sha) for c in CASES]))
    rows = [r["row"] for r in results]
    per = [x for r in results for x in r["per"]]
    for r in rows:
        print(f"{r['case']}: utility {r['utility']}, modes differ {r['modes_differ_h']} h, "
              f"opportunity {r['handover_opportunity_tasks']} tasks", flush=True)  # fmt: skip
    _write(args.out / "per_spacecraft_risk.csv", per)
    _write(args.out / "per_spacecraft_risk_cases.csv", rows)
    git = git_state(ROOT)
    meta = {
        "experiment": "Per-spacecraft risk on the S11 storm week (DL-090, DL-091)",
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "series_sha256": sha,
        "forecast": "P-B/q50", "planner": "rule_b4", "seed": 1,
        "outage": OUTAGE, "tolerances_pfu": TOLERANCES,
        "stormer_invariant_cutoff_deg": STORMER_INV_DEG,
        "cases": {c: {"access": a, "tolerances_pfu": t, "outage": o}
                  for c, (a, t, o) in CASES.items()},
        "config_hashes": {r["case"]: r["config_hash"] for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "per_spacecraft_risk_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"cases": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

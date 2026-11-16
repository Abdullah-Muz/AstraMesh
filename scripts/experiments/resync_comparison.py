"""B4 ownership re-sync against B4 (DL-122 design, DL-123 code).

Every run pairs B4 as recorded with "B4 + re-sync" (``agents.ownership_sync`` with the
DL-122 values: 3 h claim horizon, grace 2 status intervals); nothing else differs.

* **Development storms** (seed 1): the five Phase 5 storms (QUIET, baseline, A1 - A3;
  shorter protection on the four DL-099 storms) and the six held-out storms (QUIET,
  baseline, shorter, A1 - A3) as in ``negative_results.py``, and the 2 000 / 5 000 km
  spread runs (QUIET, baseline).
* **Test storms** (seeds 1 - 3): the two reserved windows (``configs/data/
  reserved_selection.json``), with the held-out setup (``heldout_comparison``): QUIET,
  baseline, shorter, A1 - A3; plus a B3 + timeout QUIET and baseline (seed 1) as a
  reference.

Per run: utility, tasks completed, duplicates, bytes sent, the tasks whose four owner
views disagree at the end ("split"), tasks completed in the same storm's B4 QUIET but not
here while some spacecraft was in a tasking mode for a whole window ("lost while
available") and how many of those are split, and a digest of the protection record
(transitions, hazard, unprotected intervals). Expectations R1 - R6 (DL-122) are evaluated
by fixed rules, for the test and the development storms separately. B3 runs first, then
the rest. Writes ``resync_runs.csv``, ``resync_pairs.csv``, ``resync_meta.json`` and
``progress.jsonl`` to ``--out``.

    uv run python scripts/experiments/resync_comparison.py --out /tmp/resync
"""

from __future__ import annotations

import argparse
import copy
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
from ablation_study import ABLATIONS  # noqa: E402
from heldout_comparison import arm_config, raw_config  # noqa: E402
from negative_results import AVAILABLE, classify, mode_mask  # noqa: E402
from negative_results import config as dev_config  # noqa: E402
from negative_results import jobs as negative_jobs  # noqa: E402

RESERVED = ROOT / "configs" / "data" / "reserved_selection.json"
SYNC = {"horizon_s": 10800.0, "grace_status_intervals": 2}  # DL-122, fixed
VARIANTS = ("b4", "b4_resync")
TEST_ARMS = ("quiet", "baseline", "shorter", *ABLATIONS)
TEST_SEEDS = (1, 2, 3)
B3 = "cbba_b3_timeout"
BYTES_LIMIT = 1.2  # R6
Job = tuple[str, str, str, str, int]  # (group, storm, arm, variant, seed)


def reserved_storms(path: Path = RESERVED) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in json.loads(path.read_text())["test_storms"]}


def jobs() -> list[Job]:
    test = sorted(reserved_storms())
    out: list[Job] = [("test", st, arm, "b3", 1) for st in test for arm in ("quiet", "baseline")]
    dev = [(g, st, arm) for g, st, arm in negative_jobs()
           if g != "latency" and arm != "handover"]  # fmt: skip
    out += [(g, st, arm, v, 1) for g, st, arm in dev for v in VARIANTS]
    out += [("test", st, arm, v, s) for st in test for arm in TEST_ARMS for s in TEST_SEEDS
            for v in VARIANTS]  # fmt: skip
    return out


def config(job: Job) -> dict[str, Any]:
    group, storm, arm, variant, seed = job
    if group == "test":
        s = reserved_storms()[storm]
        planner = B3 if variant == "b3" else "rule_b4"
        raw = raw_config(ROOT / s["series_file"], s["epoch_utc"], planner,
                         "quiet" if arm == "quiet" else "baseline", seed)  # fmt: skip
        raw["scenario_id"] = f"RESERVED_{storm}_{arm}"
        if arm != "quiet":
            raw = arm_config(raw, arm)
    else:
        if seed != 1 or variant == "b3":
            raise ValueError(f"development jobs are B4 seed 1 only: {job!r}")
        raw = dev_config((group, storm, arm), Path("."))
    if variant == "b4_resync":
        raw = copy.deepcopy(raw)
        raw["agents"]["ownership_sync"] = dict(SYNC)
    return raw


def _protection_digest(run: Any) -> str:
    st = run.summary.get("storm", {})
    rec = {"transitions": run.summary["protection"]["transitions"],
           "hazard_s": st.get("hazard_s"),
           "unprotected": st.get("unprotected_hazard_intervals")}  # fmt: skip
    return hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()


def run_one(job: Job) -> dict[str, Any]:
    from astramesh.agents.supervisor import TASKING_MODES
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    cfg = parse_scenario(config(job))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    wall = time.perf_counter() - t0
    ids = sorted(run.agents)
    t_s = np.asarray(run.formation.trajectory.t_ns, dtype=np.int64) / 1e9
    tr = run.summary["protection"]["transitions"]
    tasking = {a: mode_mask(tr[a], t_s, tuple(TASKING_MODES)) for a in ids}
    completed = sorted(g.task_id for g in run.segments if g.outcome == "completed")
    done = set(completed)
    available = sorted(t.task_id for t in run.catalog if t.task_id not in done
                       and classify([(w.spacecraft, w.first_tick, w.last_tick)
                                     for w in t.windows], tasking) == AVAILABLE[0])  # fmt: skip
    split = []
    if ids and run.agents[ids[0]]._public:
        for tid in sorted(run.agents[ids[0]]._public):
            owners = {run.agents[a]._public[tid].owner for a in ids}
            if len(owners) > 1:
                split.append(tid)
    ops = run.summary["operations"]
    g, s, a, v, seed = job
    return {"group": g, "storm": s, "arm": a, "variant": v, "seed": seed,
            "config_hash": cfg.config_hash(), "utility": ops["utility"],
            "n_completed": ops["n_completed"], "n_duplicates": ops["n_duplicates"],
            "bytes_sent": run.summary["network"]["bytes_sent"],
            "protection_digest": _protection_digest(run),
            "completed": completed, "not_done_available": available, "split": split,
            "wall_s": round(wall, 1)}  # fmt: skip


def pairs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """B4 vs re-sync per (group, storm, arm, seed); lost-while-available against that
    storm and seed's B4 QUIET."""
    by = {(r["group"], r["storm"], r["arm"], r["variant"], r["seed"]): r for r in rows}
    out = []
    for (g, s, a, v, seed), b in sorted(by.items()):
        if v != "b4":
            continue
        r = by[(g, s, a, "b4_resync", seed)]
        q = by[(g, s, "quiet", "b4", seed)]
        quiet_done = set(q["completed"])
        row: dict[str, Any] = {"group": g, "storm": s, "arm": a, "seed": seed,
                               "quiet_utility": q["utility"]}  # fmt: skip
        for tag, x in (("b4", b), ("resync", r)):
            lost = [t for t in x["not_done_available"] if t in quiet_done]
            row.update({f"{tag}_utility": x["utility"], f"{tag}_split": len(x["split"]),
                        f"{tag}_lost_available": len(lost),
                        f"{tag}_lost_available_split": len(set(lost) & set(x["split"])),
                        f"{tag}_duplicates": x["n_duplicates"],
                        f"{tag}_bytes": x["bytes_sent"]})  # fmt: skip
        row["retention_change"] = round((r["utility"] - b["utility"]) / q["utility"], 6)
        row["protection_identical"] = r["protection_digest"] == b["protection_digest"]
        row["bytes_ratio"] = round(r["bytes_sent"] / b["bytes_sent"], 4)
        out.append(row)
    return out


def expectations(prs: list[dict[str, Any]]) -> dict[str, Any]:
    """R1 - R6 (DL-122), each for the test and the development storms separately."""
    out: dict[str, Any] = {}
    for scope in ("test", "development"):
        sel = [p for p in prs if (p["group"] == "test") == (scope == "test")]
        storm = [p for p in sel if p["arm"] != "quiet"]
        quiet = [p for p in sel if p["arm"] == "quiet"]
        fails = {
            "R1_no_split_task_lost_while_available":
                [p for p in sel if p["resync_lost_available_split"] > 0],
            "R2_utility_not_below_b4": [p for p in storm if p["resync_utility"] < p["b4_utility"]],
            "R3_no_duplicates": [p for p in sel if p["resync_duplicates"] > 0],
            "R4_protection_identical": [p for p in sel if not p["protection_identical"]],
            "R5_quiet_unchanged": [p for p in quiet if p["resync_utility"] != p["b4_utility"]],
            "R6_bytes_at_most_20_percent_more":
                [p for p in sel if p["bytes_ratio"] > BYTES_LIMIT],
        }  # fmt: skip
        out[scope] = {k: {"held": not v, "n_pairs": len(storm if k.startswith("R2") else
                                                         quiet if k.startswith("R5") else sel),
                          "failures": [f"{p['storm']}/{p['arm']}/seed{p['seed']}" for p in v]}
                      for k, v in fails.items()}  # fmt: skip
    return out


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with path.open("w", newline="") as f:
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
            pf.write(json.dumps({k: r[k] for k in ("group", "storm", "arm", "variant", "seed",
                                                   "utility", "wall_s")}) + "\n")  # fmt: skip
            pf.flush()
    order = {j: i for i, j in enumerate(todo)}
    rows.sort(key=lambda r: order[(r["group"], r["storm"], r["arm"], r["variant"], r["seed"])])
    prs = pairs([r for r in rows if r["variant"] != "b3"])
    exp = expectations(prs)
    flat = [{k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()
             if k not in ("completed", "not_done_available")} for r in rows]  # fmt: skip
    _write(args.out / "resync_runs.csv", flat)
    _write(args.out / "resync_pairs.csv", prs)
    git = git_state(ROOT)
    meta = {
        "experiment": "B4 ownership re-sync against B4 (DL-122)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "reserved_selection_sha256": hashlib.sha256(RESERVED.read_bytes()).hexdigest(),
        "ownership_sync": SYNC, "n_runs": len(rows), "expectations": exp,
        "config_hashes": {"/".join(map(str, (r["group"], r["storm"], r["arm"], r["variant"],
                                             f"seed{r['seed']}"))): r["config_hash"]
                          for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "resync_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(exp))
    print(json.dumps({"runs": len(rows), "git_dirty": git["dirty"]}))


if __name__ == "__main__":
    main()

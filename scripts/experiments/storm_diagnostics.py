"""Diagnostics behind the DL-100 and DL-104 explanations, and the 18 Jul 2023 onset (DL-106 F1).

Planner B4, seed 1, the DL-100 setup (``protection_comparison.config``):

* ``lost_tasks``: for 23 Mar 2024 and 18 Jul 2023 (baseline) and 23 Mar 2024 (the DL-103
  shorter protection), the tasks completed in QUIET but not in the arm, classed by whether
  some spacecraft with a window was in a tasking mode for the whole window ("a spacecraft
  fully available"), for part of it, or never;
* ``protection``: hours with all four spacecraft outside the tasking modes at once, and
  the protected spans (PROTECTIVE entry to leaving PROTECTIVE / RECOVERY) with their entry
  reasons, for the 23 Mar baseline and shorter protection;
* ``onset``: the unprotected-hazard intervals of the 18 Jul 2023 baseline (start, end,
  mode, the radiation input the supervisor saw and the true flux at the start) and each
  spacecraft's transitions from 2 h before its first interval to 2 h after its last.

Writes ``storm_diagnostics.json`` to ``--out``.

    uv run python scripts/experiments/storm_diagnostics.py --out /tmp/diag
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_storm_comparison import STORMS, series  # noqa: E402
from protection_comparison import FROZEN  # noqa: E402
from protection_comparison import config as pc_config  # noqa: E402
from spread_formation import non_tasking_mask  # noqa: E402

PLANNER = "rule_b4"
SEED = 1
RUNS = (("mar23_2024", "quiet"), ("mar23_2024", "baseline"), ("mar23_2024", "candidate"),
        ("jul18_2023", "quiet"), ("jul18_2023", "baseline"))  # fmt: skip
CLASSES = ("a spacecraft fully available", "only partly available", "none in a tasking mode")


def run_one(job: tuple[str, str]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    storm, arm = job
    cfg = parse_scenario(pc_config(storm, PLANNER, arm, SEED))
    assert isinstance(cfg, NominalOperationsScenario)
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    t_s = np.asarray(run.formation.trajectory.t_ns, dtype=np.int64) / 1e9
    tr = run.summary["protection"]["transitions"]
    out = {a: non_tasking_mask(tr[a], t_s) for a in sorted(tr)}
    windows = {t.task_id: [(w.spacecraft, w.first_tick, w.last_tick) for w in t.windows]
               for t in run.catalog}  # fmt: skip
    return {
        "storm": storm, "arm": arm, "config_hash": cfg.config_hash(),
        "step_s": cfg.time.time_step_s, "epoch_utc": cfg.time.epoch_utc.isoformat(),
        "completed": sorted(g.task_id for g in run.segments if g.outcome == "completed"),
        "windows": windows, "non_tasking": {a: m.tolist() for a, m in out.items()},
        "transitions": tr, "storm_summary": run.summary.get("storm", {}),
    }  # fmt: skip


def classify(task_windows: list[tuple[str, int, int]], non_tasking: dict[str, Any]) -> str:
    """Class of a lost task by the best spacecraft availability over its windows."""
    free = []
    for sc, first, last in task_windows:
        m = np.asarray(non_tasking[sc][first : last + 1], dtype=bool)
        free.append((int((~m).sum()), len(m)))
    if any(f == n for f, n in free):
        return CLASSES[0]
    return CLASSES[1] if any(f > 0 for f, _ in free) else CLASSES[2]


def lost_tasks(quiet: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any]:
    lost = sorted(set(quiet["completed"]) - set(arm["completed"]))
    cls = Counter(classify(arm["windows"][t], arm["non_tasking"]) for t in lost)
    return {"n_lost": len(lost), "classes": {c: cls.get(c, 0) for c in CLASSES}, "lost": lost}


def all_out_h(run: dict[str, Any]) -> float:
    m = np.logical_and.reduce([np.asarray(v, dtype=bool) for v in run["non_tasking"].values()])
    return round(float(m.sum()) * run["step_s"] / 3600, 2)


def spans(transitions: list[dict[str, Any]]) -> dict[str, Any]:
    """Protected spans: PROTECTIVE entry until the spacecraft leaves PROTECTIVE / RECOVERY."""
    lens, reasons, start = [], Counter(), None
    for x in transitions:
        if x["to"] == "PROTECTIVE":
            reasons[x["reason"]] += 1
            if start is None:
                start = x["t_s"]
        elif x["from"] in ("PROTECTIVE", "RECOVERY") and x["to"] not in ("PROTECTIVE", "RECOVERY"):
            if start is not None:
                lens.append((x["t_s"] - start) / 60)
                start = None
    return {"n_spans": len(lens),
            "median_min": round(float(np.median(lens)), 1) if lens else None,
            "max_min": round(max(lens), 1) if lens else None,
            "entry_reasons": dict(reasons)}  # fmt: skip


def onset(run: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime

    epoch = datetime.fromisoformat(run["epoch_utc"])
    iv = run["storm_summary"]["unprotected_hazard_intervals"]
    out: dict[str, Any] = {}
    for sc, items in sorted(iv.items()):
        if not items:
            continue
        lo, hi = items[0]["start_s"] - 7200, items[-1]["end_s"] + 7200
        out[sc] = {
            "intervals": [{**x, "start_utc": (epoch + timedelta(seconds=x["start_s"])).isoformat(),
                           "duration_s": x["end_s"] - x["start_s"]} for x in items],
            "transitions_near": [
                {**x, "utc": (epoch + timedelta(seconds=x["t_s"])).isoformat()}
                for x in run["transitions"][sc] if lo <= x["t_s"] <= hi],
        }  # fmt: skip
    return out


def main() -> None:
    from astramesh.evaluation.manifest import git_state

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(len(RUNS)) as ex:
        runs = {(r["storm"], r["arm"]): r for r in ex.map(run_one, RUNS)}
    mar_b, mar_c = runs[("mar23_2024", "baseline")], runs[("mar23_2024", "candidate")]
    mar_q = runs[("mar23_2024", "quiet")]
    lost_b, lost_c = lost_tasks(mar_q, mar_b), lost_tasks(mar_q, mar_c)
    git = git_state(ROOT)
    result = {
        "experiment": "Storm diagnostics behind DL-100 / DL-104 and the 18 Jul 2023 onset (DL-106)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "planner": PLANNER, "seed": SEED, "shorter": FROZEN,
        "series_sha256": {st: hashlib.sha256(series(st).read_bytes()).hexdigest()
                          for st in STORMS},
        "config_hashes": {f"{s}/{a}": r["config_hash"] for (s, a), r in runs.items()},
        "lost_tasks": {
            "mar23_2024/baseline": {k: v for k, v in lost_b.items() if k != "lost"},
            "mar23_2024/shorter": {k: v for k, v in lost_c.items() if k != "lost"},
            "mar23_2024/lost_in_both": len(set(lost_b["lost"]) & set(lost_c["lost"])),
            "jul18_2023/baseline": {k: v for k, v in lost_tasks(
                runs[("jul18_2023", "quiet")], runs[("jul18_2023", "baseline")]).items()
                if k != "lost"},
        },
        "protection": {
            "mar23_2024/baseline": {"all_four_out_h": all_out_h(mar_b), **{
                sc: spans(t) for sc, t in sorted(mar_b["transitions"].items())}},
            "mar23_2024/shorter": {"all_four_out_h": all_out_h(mar_c), **{
                sc: spans(t) for sc, t in sorted(mar_c["transitions"].items())}},
        },
        "onset": {"jul18_2023/baseline": onset(runs[("jul18_2023", "baseline")])},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "storm_diagnostics.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("lost_tasks", "git_dirty", "total_wall_s")}))
    print(json.dumps({k: v["all_four_out_h"] for k, v in result["protection"].items()}))


if __name__ == "__main__":
    main()

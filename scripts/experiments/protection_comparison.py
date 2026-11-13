"""Frozen shorter protection against the baseline on the four evaluation storms (DL-101).

The DL-099 storms and setup (``multi_storm_comparison.config``: per-spacecraft risk,
tolerances 100 / 100 / 50 / 200 pfu, no outage, P-B median), planners B3 + timeout and
B4, seeds 1-3. Arms: baseline and QUIET (identical to the DL-100 runs) and the candidate
with the setting frozen from ``protection_tuning`` (``FROZEN`` below, set in the
tuning-results commit). Nothing is tuned here.

Hypothesis (DL-101): rejected for a planner if the pooled 95 % t-interval of the
retention gain over the four storms includes 0 or lies below it, or if on any storm any
spacecraft's unprotected hazard exceeds the baseline's by more than 600 s on any seed.
Writes ``protection_runs.csv``, ``protection_summary.csv`` and ``protection_meta.json``
to ``--out``.

    uv run python scripts/experiments/protection_comparison.py --out /tmp/pc
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_storm_comparison import PLANNERS, SEEDS, STORMS, TOLERANCES, _interval, series  # noqa: E402
from multi_storm_comparison import config as storm_config  # noqa: E402
from protection_tuning import (  # noqa: E402
    MAX_EXTRA_UNPROTECTED_S,
    apply_protection,
    extra_unprotected_s,
    storm_metrics,
)

FROZEN: dict[str, Any] | None = None  # set from protection_tuning in the results commit
ARMS = ("baseline", "candidate", "quiet")


def config(storm: str, planner: str, arm: str, seed: int) -> dict[str, Any]:
    if arm in ("baseline", "quiet"):
        return storm_config(storm, planner, arm, seed)  # the DL-100 runs, byte for byte
    if FROZEN is None:
        raise ValueError("FROZEN is not set (DL-101 tuning)")
    raw = storm_config(storm, planner, "baseline", seed)
    raw["scenario_id"] = f"PT_MULTI_{storm}_candidate"
    return apply_protection(raw, FROZEN)


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
        "storm": storm,
        "planner": planner,
        "arm": arm,
        "seed": seed,
        **storm_metrics(run),
        "config_hash": cfg.config_hash(),
        "wall_s": round(time.perf_counter() - t0, 1),
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by = {(r["storm"], r["planner"], r["arm"], r["seed"]): r for r in rows}
    out: list[dict[str, Any]] = []
    for pl in PLANNERS:
        gains: dict[str, list[float]] = {"utility": [], "utility_dup_charged": []}
        worst_extra = 0.0
        for st in STORMS:
            row: dict[str, Any] = {"scope": st, "planner": pl}
            for util in gains:
                d = [(by[(st, pl, "candidate", s)][util] - by[(st, pl, "baseline", s)][util])
                     / by[(st, pl, "quiet", s)]["utility"] for s in SEEDS]  # fmt: skip
                row[f"gain_{util}"] = round(float(np.mean(d)), 6)
                row[f"gain_{util}_seed_spread"] = round(float(np.ptp(d)), 6)
                gains[util].append(float(np.mean(d)))
            extra = max(
                extra_unprotected_s(by[(st, pl, "candidate", s)], by[(st, pl, "baseline", s)])
                for s in SEEDS
            )
            worst_extra = max(worst_extra, extra)
            row["max_extra_unprotected_s"] = extra
            row["baseline_retention"] = round(float(np.mean(
                [by[(st, pl, "baseline", s)]["utility"] / by[(st, pl, "quiet", s)]["utility"]
                 for s in SEEDS])), 6)  # fmt: skip
            out.append(row)
        for util, g in gains.items():
            iv = _interval(g)
            safe = worst_extra <= MAX_EXTRA_UNPROTECTED_S
            out.append(
                {
                    "scope": f"pooled over storms ({util})",
                    "planner": pl,
                    **iv,
                    "max_extra_unprotected_s": worst_extra,
                    "verdict": "not rejected" if iv["ci_lo"] > 0 and safe else "rejected",
                }
            )
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
        raise SystemExit("FROZEN is not set (DL-101 tuning)")
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    todo = [(st, pl, arm, s) for pl in PLANNERS for st in STORMS for arm in ARMS for s in SEEDS]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = list(ex.map(run_one, todo))
    summary = summarize(rows)
    _write(args.out / "protection_runs.csv", rows)
    _write(args.out / "protection_summary.csv", summary)
    git = git_state(ROOT)
    meta = {
        "experiment": "Frozen shorter protection on the four evaluation storms (DL-101)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "frozen": FROZEN, "storms": STORMS,
        "series_sha256": {st: hashlib.sha256(series(st).read_bytes()).hexdigest()
                          for st in STORMS},
        "tolerances_pfu": TOLERANCES, "seeds": list(SEEDS), "n_runs": len(rows),
        "max_extra_unprotected_s": MAX_EXTRA_UNPROTECTED_S,
        "config_hashes": {f"{r['storm']}/{r['planner']}/{r['arm']}/seed{r['seed']}":
                          r["config_hash"] for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "protection_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for r in summary:
        print(r, flush=True)
    print(json.dumps({"runs": len(rows), "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

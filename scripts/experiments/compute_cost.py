"""Compute cost: onboard CPU time and peak memory per baseline (DL-134, DL-135).

Run:  uv run python scripts/experiments/compute_cost.py --out docs/results
          [--workers 4] [--repeats 3]

Spec §10.2 lists algorithm CPU time and peak memory; Phases 2 - 6 did not measure them.
This script reruns recorded configurations unchanged and measures them; nothing in
``src/`` changes.

* **Onboard CPU.** ``SpacecraftAgent.receive_messages`` and ``SpacecraftAgent.step``
  are wrapped with ``time.process_time_ns``, per agent and per call: the planner,
  health beliefs and supervisor each spacecraft runs. **Ground planning** (the B0 /
  B4 static plan and B1's centralised plan) is timed separately. **Run CPU** is the
  whole simulation, including dynamics, network and bookkeeping.
* **Memory.** Every run is a fresh worker process (``max_tasks_per_child=1``).
  ``ru_maxrss`` is read after the imports and the config (baseline) and after the run
  (peak). It is whole-process memory and includes the simulator.
* **Unchanged behaviour.** Each run's utility, completions, messages and bytes, and its
  config hash, must equal the recorded run's (``fault_comparison.csv``,
  ``handover_runs.csv``). The S00 loss runs were recorded in Phase 2, before fields
  were renamed to ``*_fraction`` / ``*_probability`` (DL-075), so for
  ``s00_loss_comparison.csv`` the hash is not compared, only the behaviour. B3 +
  timeout and B4 at 30 % loss have no recorded run, so their repeats must agree with
  each other instead. Any mismatch stops the script.

Configurations (seed 1): S00 at the base 1 % loss under B0 - B4; S01 and S10 under
B3 + timeout and B4 (``fault_comparison.py``); S00 at 30 % loss under all six
(``s00_loss_comparison.py``); the May 2024 storm, S11-H with forecast P-B, baseline
arm, under B3 + timeout and B4 (``handover_comparison.py``, 8 days, one repeat).

Measured on one machine, in Python: not portable across hardware, and not
representative of flight processors. Outputs in ``--out``: ``compute_cost.csv`` (one
row per run), ``compute_cost_summary.csv`` (median and range over repeats) and
``compute_cost_meta.json`` (commit, dirty flag, lockfile hash, platform, settings).
"""

from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import json
import os
import platform
import resource
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "docs" / "results"
sys.path.insert(0, str(Path(__file__).resolve().parent))

ALL = ("static_b0", "centralized_b1", "auction_b2", "cbba_b3", "cbba_b3_timeout", "rule_b4")
PAIR = ("cbba_b3_timeout", "rule_b4")
LONG = "S11-H storm"

#: (case, method, repeat); the case names the recorded source.
Job = tuple[str, str, int]


def cases(repeats: int) -> list[Job]:
    out: list[Job] = []
    for rep in range(1, repeats + 1):
        out += [("S00 1% loss", m, rep) for m in ALL]
        out += [("S01", m, rep) for m in PAIR]
        out += [("S10", m, rep) for m in PAIR]
        out += [("S00 30% loss", m, rep) for m in ALL]
    out += [(LONG, m, 1) for m in PAIR]
    return out


def build(case: str, method: str) -> dict[str, Any]:
    """The recorded configuration, built by the script that recorded it."""
    if case in ("S00 1% loss", "S01", "S10"):
        import fault_comparison

        return fault_comparison.scenario_config(case.split()[0], method, 1, 24.0)
    if case == "S00 30% loss":
        import s00_loss_comparison

        return s00_loss_comparison._config(method, 0.30, 1, 24.0)
    if case == LONG:
        import handover_comparison
        from storm_replay_comparison import SERIES

        sha = hashlib.sha256(SERIES.read_bytes()).hexdigest()
        return handover_comparison.config("S11-H", "P-B", method, "baseline", 1, sha)
    raise ValueError(case)


def _maxrss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # KiB on Linux


def run_one(job: Job) -> dict[str, Any]:
    from astramesh.agents import agent as agent_mod
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios import nominal_operations as ops

    case, method, rep = job
    cfg = parse_scenario(build(case, method))
    assert isinstance(cfg, NominalOperationsScenario)

    onboard: dict[str, list[int]] = defaultdict(list)  # agent -> per-call ns
    ground: list[int] = []

    def per_agent(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapped(self: Any, *a: Any, **k: Any) -> Any:
            t = time.process_time_ns()
            try:
                return fn(self, *a, **k)
            finally:
                onboard[self.agent_id].append(time.process_time_ns() - t)

        return wrapped

    def timed(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapped(*a: Any, **k: Any) -> Any:
            t = time.process_time_ns()
            try:
                return fn(*a, **k)
            finally:
                ground.append(time.process_time_ns() - t)

        return wrapped

    cls = agent_mod.SpacecraftAgent
    cls.receive_messages = per_agent(cls.receive_messages)  # type: ignore[method-assign]
    cls.step = per_agent(cls.step)  # type: ignore[method-assign]
    ops.plan_static = timed(ops.plan_static)  # type: ignore[assignment]
    ops.plan_centralized = timed(ops.plan_centralized)  # type: ignore[assignment]

    rss_base = _maxrss_mb()
    c0, w0 = time.process_time_ns(), time.perf_counter()
    run = ops.run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    run_cpu_ns, wall = time.process_time_ns() - c0, time.perf_counter() - w0
    rss_peak = _maxrss_mb()

    per_sc = {a: sum(v) for a, v in onboard.items()}
    calls = [x for v in onboard.values() for x in v]
    total = sum(per_sc.values())
    return {
        "case": case, "method": method, "repeat": rep,
        "utility": run.summary["operations"]["utility"],
        "n_completed": run.summary["operations"]["n_completed"],
        "messages_sent": run.summary["network"]["sent"],
        "bytes_sent": run.summary["network"]["bytes_sent"],
        "config_hash": cfg.config_hash(),
        "duration_s": cfg.time.duration_s,
        "run_cpu_s": round(run_cpu_ns / 1e9, 3),
        "onboard_cpu_s": round(total / 1e9, 3),
        "onboard_share": round(total / run_cpu_ns, 4) if run_cpu_ns else 0.0,
        "onboard_cpu_s_max_sc": round(max(per_sc.values(), default=0) / 1e9, 3),
        "onboard_cpu_ms_per_sim_h_per_sc": round(
            total / 1e6 / max(len(per_sc), 1) / (cfg.time.duration_s / 3600), 3),
        "calls": len(calls),
        "call_us_mean": round(total / 1e3 / len(calls), 2) if calls else 0.0,
        "call_ms_max": round(max(calls, default=0) / 1e6, 3),
        "ground_plan_cpu_s": round(sum(ground) / 1e9, 3),
        "rss_baseline_mb": round(rss_base, 1),
        "rss_peak_mb": round(rss_peak, 1),
        "rss_growth_mb": round(rss_peak - rss_base, 1),
        "wall_s": round(wall, 2),
        "per_sc_cpu_s": json.dumps({a: round(v / 1e9, 3) for a, v in sorted(per_sc.items())}),
    }  # fmt: skip


BEHAVIOUR = ("utility", "n_completed", "messages_sent", "bytes_sent")


def _recorded() -> dict[tuple[str, str], dict[str, str]]:
    """(case, method) -> recorded behaviour fields (and config hash where comparable)."""
    rec: dict[tuple[str, str], dict[str, str]] = {}

    def rows(name: str) -> list[dict[str, str]]:
        with (RESULTS / name).open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def pick(r: dict[str, str], *, with_hash: bool) -> dict[str, str]:
        keys = BEHAVIOUR + (("config_hash",) if with_hash else ())
        return {k: str(int(float(r[k]))) if k != "config_hash" else r[k] for k in keys}

    for r in rows("fault_comparison.csv"):
        if r["seed"] == "1" and (
            r["scenario"] == "S00" or (r["scenario"] in ("S01", "S10") and r["method"] in PAIR)
        ):
            case = "S00 1% loss" if r["scenario"] == "S00" else r["scenario"]
            rec[(case, r["method"])] = pick(r, with_hash=True)
    for r in rows("s00_loss_comparison.csv"):
        if r["seed"] == "1" and float(r["loss"]) == 0.30:
            rec[("S00 30% loss", r["method"])] = pick(r, with_hash=False)
    for r in rows("handover_runs.csv"):
        if (r["scenario"], r["forecast"], r["arm"], r["seed"]) == ("S11-H", "P-B", "baseline", "1"):
            rec[(LONG, r["planner"])] = pick(r, with_hash=True)
    return rec


def check(rows: list[dict[str, Any]]) -> list[str]:
    """Each run equals its recorded run; unrecorded configurations agree across repeats."""
    rec, bad = _recorded(), []
    groups: dict[tuple[str, str], set[tuple[str, ...]]] = defaultdict(set)
    for r in rows:
        groups[(r["case"], r["method"])].add(tuple(str(r[k]) for k in (*BEHAVIOUR, "config_hash")))
        want = rec.get((r["case"], r["method"]))
        if want is None:
            continue
        got = {k: str(r[k]) for k in want}
        if got != want:
            bad.append(f"{r['case']} {r['method']} rep {r['repeat']}: {got} != recorded {want}")
    bad += [f"{k}: repeats differ {v}" for k, v in groups.items() if len(v) != 1]
    return bad


SUMMED = ("run_cpu_s", "onboard_cpu_s", "onboard_share", "onboard_cpu_s_max_sc",
          "onboard_cpu_ms_per_sim_h_per_sc", "call_us_mean", "call_ms_max",
          "ground_plan_cpu_s", "rss_peak_mb", "rss_growth_mb", "wall_s")  # fmt: skip


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    keys = list(dict.fromkeys((r["case"], r["method"]) for r in rows))
    for case, method in keys:
        sel = [r for r in rows if r["case"] == case and r["method"] == method]
        rec: dict[str, Any] = {"case": case, "method": method, "n_repeats": len(sel),
                               "utility": sel[0]["utility"], "calls": sel[0]["calls"]}  # fmt: skip
        for m in SUMMED:
            xs = [float(r[m]) for r in sel]
            rec[f"{m}_median"] = round(statistics.median(xs), 4)
            rec[f"{m}_min"] = round(min(xs), 4)
            rec[f"{m}_max"] = round(max(xs), 4)
        out.append(rec)
    return out


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="\n", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def main() -> int:
    from astramesh.evaluation.manifest import git_state

    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    git = git_state(ROOT)
    todo = cases(args.repeats)
    todo.sort(key=lambda j: j[0] != LONG)  # the 8-day runs first
    t0 = time.perf_counter()
    with ProcessPoolExecutor(args.workers, max_tasks_per_child=1) as ex:
        rows = list(ex.map(run_one, todo))
    order = {c: i for i, c in enumerate(dict.fromkeys(j[0] for j in cases(1)))}
    rows.sort(key=lambda r: (order[r["case"]], ALL.index(r["method"]), r["repeat"]))
    bad = check(rows)
    if bad:
        raise SystemExit("behaviour changed:\n" + "\n".join(bad))
    args.out.mkdir(parents=True, exist_ok=True)
    _write(args.out / "compute_cost.csv", rows)
    _write(args.out / "compute_cost_summary.csv", summarize(rows))
    meta = {
        "experiment": "Compute cost per baseline (DL-134, DL-135)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "platform": {"cpu": _cpu_model(), "logical_cpus": os.cpu_count(),
                     "os": platform.platform(), "python": platform.python_version()},
        "workers": args.workers, "repeats": args.repeats, "n_runs": len(rows),
        "config_hashes": {f"{r['case']}/{r['method']}": r["config_hash"]
                          for r in rows if r["repeat"] == 1},
        "checked_against_recorded": sorted({f"{c}/{m}" for c, m in _recorded()}),
        "total_wall_s": round(time.perf_counter() - t0, 1),
        "note": ("measured on one machine in Python; CPU and memory are not portable and "
                 "not representative of flight processors; rss is whole-process"),
    }  # fmt: skip
    (args.out / "compute_cost_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

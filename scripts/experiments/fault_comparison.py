"""Phase 3 increment 5: B0-B4 across fault scenarios S01-S10 (DL-058).

Run:  uv run python scripts/experiments/fault_comparison.py [--workers 8] [--seeds 10]
          [--hours 24] [--out docs/results]

Every run starts from ``configs/experiments/nominal_ops_b0_24h.yaml`` and changes only
``operations.algorithm``, ``random.seed``, and the scenario's ``faults`` / ``environment``.
For each seed the fault parameters are drawn once from the seed's ``faults`` random
stream and reused for every method (paired comparison):

* ``a`` = affected spacecraft, ``b`` = a second, different spacecraft;
* ``t0`` = start time on the 10 s grid, uniform in [4 h, 10 h].

Scenarios (spec §10.1; S06 deferred, S11 is Phase 4):

====  ==============================================================================
S00   no faults (healthy reference for retention)
S01   ``a`` permanently unavailable from t0
S02   ``a`` unavailable from t0, ``b`` unavailable from t0 + 6 h (both permanent)
S03   ``a`` payload degraded for 12 h from t0
S04   ``a`` radio off (comms outage) for 3 h from t0 (false outage)
S05   partition {a, b} | others for 6 h from t0, then reconnect
S07   ``a`` radiation risk 1.2 x tolerance for 6 h from t0 (prolonged)
S08   ``a`` radiation risk 1.1 x tolerance for 10 min from t0 (brief false alert)
S09   S07 + S05 at the same t0
S10   S07 + critical fault on ``a`` from t0 + 1 h for 2 h
====  ==============================================================================

Outputs (in ``--out``): ``fault_comparison.csv`` (per run), ``fault_comparison_summary.csv``
(per scenario and method: mean, sd, 95% t-interval), ``fault_comparison_meta.json``
(commit, dirty flag, lockfile and config hashes, settings). Wall time is the only
non-deterministic column. Synthetic faults and hazards; not data-informed.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import yaml
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "configs" / "experiments" / "nominal_ops_b0_24h.yaml"
METHODS = ("static_b0", "centralized_b1", "auction_b2", "cbba_b3", "cbba_b3_timeout", "rule_b4")
SCENARIOS = ("S00", "S01", "S02", "S03", "S04", "S05", "S07", "S08", "S09", "S10")
METRICS = ("utility", "retention", "n_completed", "n_duplicates", "n_invalid_payload",
           "protected_payload_steps", "confirmed_while_available", "detection_latency_s",
           "false_unavailable_s", "messages_sent", "bytes_sent")  # fmt: skip
H = 3600
IDS = ("sc00", "sc01", "sc02", "sc03")


def draws(seed: int) -> dict[str, Any]:
    """Per-seed fault parameters from the seed's ``faults`` stream (same for all methods)."""
    from astramesh.core.rng import RandomStreams

    rng = RandomStreams(seed)["faults"]
    a, b = (IDS[int(i)] for i in rng.choice(len(IDS), size=2, replace=False))
    t0 = int(rng.integers(4 * H // 10, 10 * H // 10 + 1)) * 10
    return {"a": a, "b": b, "t0_s": t0}


def _fault(fid: str, kind: str, start: int, end: int | None, **kw: Any) -> dict[str, Any]:
    f = {"fault_id": fid, "type": kind, "start_s": start, "end_s": end,
         "cause": f"Synthetic {kind} (fault comparison, DL-058)",
         "observability": "effects_only", "consequences": "see DL-058"}  # fmt: skip
    f.update(kw)
    return f


def _hazard(sc: str, start: int, end: int, ratio: float) -> dict[str, Any]:
    return {"background_exposure_ratio": 0.1, "forecasts": [
        {"forecast_id": "HZ", "dimension": "radiation", "spacecraft": [sc], "start_s": start,
         "end_s": end, "exposure_ratio": ratio}]}  # fmt: skip


def scenario_config(scenario: str, algorithm: str, seed: int, hours: float) -> dict[str, Any]:
    raw = yaml.safe_load(BASE.read_text(encoding="utf-8"))
    cfg: dict[str, Any] = copy.deepcopy(raw)
    cfg["scenario_id"] = f"{scenario}_{algorithm.upper()}"
    cfg["operations"]["algorithm"] = algorithm
    cfg["random"]["seed"] = seed
    cfg["time"]["duration_s"] = int(hours * H)
    d = draws(seed)
    a, b, t0 = d["a"], d["b"], d["t0_s"]
    others = [s for s in IDS if s not in (a, b)]
    faults: list[dict[str, Any]] = []
    env: dict[str, Any] | None = None
    if scenario == "S01":
        faults = [_fault("F1", "unavailable", t0, None, spacecraft=[a])]
    elif scenario == "S02":
        faults = [_fault("F1", "unavailable", t0, None, spacecraft=[a]),
                  _fault("F2", "unavailable", t0 + 6 * H, None, spacecraft=[b])]  # fmt: skip
    elif scenario == "S03":
        faults = [_fault("F1", "payload_degraded", t0, t0 + 12 * H, spacecraft=[a])]
    elif scenario == "S04":
        faults = [_fault("F1", "comms_outage", t0, t0 + 3 * H, spacecraft=[a])]
    elif scenario == "S05":
        faults = [_fault("F1", "partition", t0, t0 + 6 * H, groups=[[a, b], others])]
    elif scenario == "S07":
        env = _hazard(a, t0, t0 + 6 * H, 1.2)
    elif scenario == "S08":
        env = _hazard(a, t0, t0 + 600, 1.1)
    elif scenario == "S09":
        env = _hazard(a, t0, t0 + 6 * H, 1.2)
        faults = [_fault("F1", "partition", t0, t0 + 6 * H, groups=[[a, b], others])]
    elif scenario == "S10":
        env = _hazard(a, t0, t0 + 6 * H, 1.2)
        faults = [_fault("F1", "critical_fault", t0 + H, t0 + 3 * H, spacecraft=[a])]
    elif scenario != "S00":
        raise ValueError(f"unknown scenario {scenario}")
    cfg["faults"] = faults
    if env is not None:
        cfg["environment"] = env
    return cfg


def run_one(job: tuple[str, str, int, float]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    scenario, algorithm, seed, hours = job
    cfg = parse_scenario(scenario_config(scenario, algorithm, seed, hours))
    assert isinstance(cfg, NominalOperationsScenario)
    t_start = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    wall = time.perf_counter() - t_start
    o, n, h = run.summary["operations"], run.summary["network"], run.summary["health"]
    p = run.summary["protection"]
    lat = [v for v in h["detection_latency_s"].values() if v is not None]
    catalog = [(t.task_id, t.priority, tuple((w.spacecraft, w.first_tick, w.last_tick)
                                             for w in t.windows)) for t in run.catalog]  # fmt: skip
    d = draws(seed)
    return {
        "scenario": scenario, "method": algorithm, "seed": seed,
        "affected": d["a"], "second": d["b"], "t0_s": d["t0_s"],
        "utility": o["utility"], "utility_all_tasks": o["utility_all_tasks"],
        "n_completed": o["n_completed"], "n_duplicates": o["n_duplicates"],
        "n_invalid_payload": o.get("n_invalid_payload", 0),
        "protected_payload_steps": sum(p["payload_steps_in_protected_modes"].values()),
        "confirmed_while_available": h["confirmed_while_available"],
        "detection_latency_s": max(lat) if lat else "",
        "false_unavailable_s": h["false_unavailable_s"],
        "messages_sent": n["sent"], "bytes_sent": n["bytes_sent"],
        "catalog_sha256": hashlib.sha256(json.dumps(catalog).encode()).hexdigest(),
        "config_hash": cfg.config_hash(), "wall_s": round(wall, 2),
    }  # fmt: skip


def add_retention(rows: list[dict[str, Any]]) -> None:
    healthy = {(r["method"], r["seed"]): r["utility"] for r in rows if r["scenario"] == "S00"}
    for r in rows:
        ref = healthy.get((r["method"], r["seed"]))
        r["retention"] = round(r["utility"] / ref, 6) if ref else ""


def summarize(
    rows: list[dict[str, Any]], metrics: tuple[str, ...] = METRICS
) -> list[dict[str, Any]]:
    out = []
    for scenario in SCENARIOS:
        for method in METHODS:
            sel = [r for r in rows if r["scenario"] == scenario and r["method"] == method]
            if not sel:
                continue
            rec: dict[str, Any] = {"scenario": scenario, "method": method, "n_runs": len(sel)}
            for m in metrics:
                xs = [float(r[m]) for r in sel if r.get(m, "") != ""]
                n = len(xs)
                if n == 0:
                    rec.update({f"{m}_mean": "", f"{m}_sd": "", f"{m}_ci95_lo": "",
                                f"{m}_ci95_hi": "", f"{m}_n": 0})  # fmt: skip
                    continue
                mean = sum(xs) / n
                sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
                half = float(stats.t.ppf(0.975, n - 1)) * sd / math.sqrt(n) if n > 1 else 0.0
                rec.update({f"{m}_mean": round(mean, 6), f"{m}_sd": round(sd, 6),
                            f"{m}_ci95_lo": round(mean - half, 6),
                            f"{m}_ci95_hi": round(mean + half, 6), f"{m}_n": n})  # fmt: skip
            rec["runs_with_duplicates"] = sum(1 for r in sel if r["n_duplicates"] > 0)
            out.append(rec)
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="\n", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--scenarios", nargs="*", default=list(SCENARIOS))
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "results")
    args = ap.parse_args()
    scen = list(dict.fromkeys(["S00", *args.scenarios]))  # S00 is the retention reference
    jobs = [(s, m, seed, args.hours) for s in scen for seed in range(1, args.seeds + 1)
            for m in METHODS]  # fmt: skip
    jobs.sort(key=lambda j: j[1] not in ("cbba_b3", "cbba_b3_timeout"))  # long ones first
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs))
    rows.sort(key=lambda r: (SCENARIOS.index(r["scenario"]), r["seed"], METHODS.index(r["method"])))
    for s in scen:  # identical tasks across methods (Gate P2/P3 fairness)
        for seed in range(1, args.seeds + 1):
            cats = {r["catalog_sha256"] for r in rows if r["scenario"] == s and r["seed"] == seed}
            if len(cats) != 1:
                raise RuntimeError(f"catalogue differs between methods ({s}, seed {seed})")
    bad = [r for r in rows if r["protected_payload_steps"] or r["confirmed_while_available"]]
    if bad:
        raise RuntimeError(f"safety invariant violated in {len(bad)} runs")
    add_retention(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out / "fault_comparison.csv", rows)
    _write_csv(args.out / "fault_comparison_summary.csv", summarize(rows))

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True,
                              check=False).stdout.strip()  # fmt: skip

    meta = {
        "experiment": "Phase 3 fault-scenario comparison (DL-058)",
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "base_config": str(BASE.relative_to(ROOT)),
        "base_config_sha256": hashlib.sha256(BASE.read_bytes()).hexdigest(),
        "methods": list(METHODS), "scenarios": scen, "seeds": list(range(1, args.seeds + 1)),
        "hours": args.hours, "n_runs": len(rows),
        "draws": {seed: draws(seed) for seed in range(1, args.seeds + 1)},
        "total_wall_s": round(time.perf_counter() - t0, 1),
        "note": "synthetic faults and hazards; wall_s is the only non-deterministic column",
    }  # fmt: skip
    (args.out / "fault_comparison_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ("git_commit", "git_dirty", "n_runs", "total_wall_s")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

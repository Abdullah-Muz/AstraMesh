"""Tune shorter, pass-following protection on the February 2024 storm (DL-101).

The DL-096 tuning setup (``handover_tuning.config``: out-of-sample fold forecasts in
``configs/data/tuning_feb2024_series.json``, P-B median, 8 Feb 2024 00:10 UT for 690 600 s,
position-based access, the age rule, tolerances 100 / 100 / 50 / 200 pfu, no outage),
planner B4, seeds 1-3. Arms: QUIET and the baseline (both identical to the DL-096 runs),
and the grid look-ahead H (``environment.replay.access.horizon_s``) in {300, 600, 1200} s
x release dwell D (``supervisor.release_dwell_s``) in {300, 600} s x entry margin in
{none, ``supervisor.protect_exposure_ratio`` 0.9, the P-B q90 forecast}.

Selection (fixed in DL-101 before any run; owner choice): among the arms whose
unprotected hazard exceeds the baseline's by at most 600 s on every spacecraft and seed,
the largest mean retention (utility / QUIET); ties go to the longer H, then the longer D,
then the more conservative margin (q90, then 0.9, then none). Nothing is chosen if no arm
qualifies or the best one does not beat the baseline. Writes ``protection_tuning.csv``,
``protection_tuning_summary.csv`` and ``protection_tuning_meta.json`` to ``--out``.

    uv run python scripts/experiments/protection_tuning.py --out /tmp/pt
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_tuning import EPOCH, SERIES, TOLERANCES  # noqa: E402
from handover_tuning import config as tuning_config  # noqa: E402

HORIZONS_S = (300.0, 600.0, 1200.0)
RELEASE_DWELLS_S = (300.0, 600.0)
MARGINS = ("none", "ratio_0.9", "q90")  # least to most conservative
SEEDS = (1, 2, 3)
PLANNER = "rule_b4"
MAX_EXTRA_UNPROTECTED_S = 600.0  # per spacecraft and seed (DL-101, owner choice)
ARMS = ["quiet", "baseline"] + [
    f"pt:{h:g}:{d:g}:{m}" for h in HORIZONS_S for d in RELEASE_DWELLS_S for m in MARGINS
]


def setting_of(arm: str) -> dict[str, Any]:
    _, h, d, m = arm.split(":")
    return {"horizon_s": float(h), "release_dwell_s": float(d), "margin": m}


def apply_protection(raw: dict[str, Any], setting: dict[str, Any]) -> dict[str, Any]:
    """Return ``raw`` with a protection setting applied (H, D, entry margin)."""
    replay = raw["environment"]["replay"]
    replay["access"] = {**replay.get("access", {}), "horizon_s": float(setting["horizon_s"])}
    sup = raw.setdefault("supervisor", {})
    sup["release_dwell_s"] = float(setting["release_dwell_s"])
    margin = setting["margin"]
    if margin == "ratio_0.9":
        sup["protect_exposure_ratio"] = 0.9
    elif margin == "q90":
        if replay["forecast"] != "P-B/q50":
            raise ValueError(f"q90 margin expects the P-B median, got {replay['forecast']}")
        replay["forecast"] = "P-B/q90"
    elif margin != "none":
        raise ValueError(f"unknown margin {margin!r}")
    return raw


def config(arm: str, seed: int, sha: str) -> dict[str, Any]:
    if arm in ("quiet", "baseline"):
        return tuning_config(arm, seed, sha)  # the DL-096 runs, byte for byte
    raw = tuning_config("baseline", seed, sha)
    raw["scenario_id"] = "PT_TUNE_FEB2024"
    return apply_protection(raw, setting_of(arm))


def run_one(job: tuple[str, int, str]) -> dict[str, Any]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    arm, seed, sha = job
    cfg = parse_scenario(config(arm, seed, sha))
    assert isinstance(cfg, NominalOperationsScenario)
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    return {
        "arm": arm,
        "seed": seed,
        **storm_metrics(run),
        "config_hash": cfg.config_hash(),
        "wall_s": round(time.perf_counter() - t0, 1),
    }


def storm_metrics(run: Any) -> dict[str, Any]:
    """Science and protection metrics of one run (per spacecraft as sorted JSON)."""
    s, p = run.summary, run.summary["protection"]
    st = s.get("storm", {})
    hz = st.get("hazard_s", {})
    pri = {t.task_id: t.priority for t in run.catalog}
    u = s["operations"]["utility"]
    dup = sum(pri[g.task_id] for g in run.segments if g.outcome == "duplicate")

    def per_sc(d: dict[str, float]) -> str:
        return json.dumps({a: round(v, 1) for a, v in d.items()}, sort_keys=True)

    return {
        "utility": u, "utility_dup_charged": u - dup,
        "n_tasks": s["operations"]["n_tasks"], "n_completed": s["operations"]["n_completed"],
        "n_duplicates": s["operations"]["n_duplicates"],
        "hazard_s": per_sc(hz),
        "unprotected_hazard_s": per_sc({a: hz[a] - st["protected_in_hazard_s"][a] for a in hz}),
        "protected_outside_hazard_s": per_sc(st.get("protected_outside_hazard_s", {})),
        "exposure_s": sum(st.get("exposed_s", {}).values()),
        "protected_s": per_sc({a: sum(m.get(k, 0.0) for k in ("PROTECTIVE", "RECOVERY"))
                               for a, m in p["time_in_mode_s"].items()}),
        "protective_entries": json.dumps(
            {a: sum(1 for x in tr if x["to"] == "PROTECTIVE")
             for a, tr in sorted(p["transitions"].items())}),
        "payload_steps_in_protected_modes": sum(p["payload_steps_in_protected_modes"].values()),
    }  # fmt: skip


def extra_unprotected_s(arm_row: dict[str, Any], base_row: dict[str, Any]) -> float:
    """Largest excess of unprotected hazard over the baseline, over spacecraft [s]."""
    a, b = json.loads(arm_row["unprotected_hazard_s"]), json.loads(base_row["unprotected_hazard_s"])
    if set(a) != set(b):
        raise ValueError("spacecraft sets differ")
    return max((a[k] - b[k] for k in a), default=0.0)


def summarize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    by = {(r["arm"], r["seed"]): r for r in rows}
    out = []
    for arm in ARMS[1:]:
        ret = [by[(arm, s)]["utility"] / by[("quiet", s)]["utility"] for s in SEEDS]
        extra = [extra_unprotected_s(by[(arm, s)], by[("baseline", s)]) for s in SEEDS]
        out.append(
            {
                "arm": arm,
                "mean_retention": round(sum(ret) / len(ret), 6),
                "max_extra_unprotected_s": max(extra),
                "eligible": arm == "baseline" or max(extra) <= MAX_EXTRA_UNPROTECTED_S,
            }
        )
    return out, choose(out)


def choose(summary: list[dict[str, Any]]) -> str | None:
    """The DL-101 selection rule over a summary (see the module docstring)."""
    base = next(r for r in summary if r["arm"] == "baseline")
    ok = [r for r in summary if r["arm"] != "baseline" and r["eligible"]]
    if not ok:
        return None

    def key(r: dict[str, Any]) -> tuple[float, float, float, int]:
        st = setting_of(r["arm"])
        return (r["mean_retention"], st["horizon_s"], st["release_dwell_s"],
                MARGINS.index(st["margin"]))  # fmt: skip

    best = max(ok, key=key)
    return str(best["arm"]) if best["mean_retention"] > base["mean_retention"] else None


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    from astramesh.evaluation.manifest import git_state

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(SERIES.read_bytes()).hexdigest()
    t0 = time.perf_counter()
    jobs = [(a, s, sha) for a in ARMS for s in SEEDS]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = list(ex.map(run_one, jobs))
    summary, chosen = summarize(rows)
    _write(args.out / "protection_tuning.csv", rows)
    _write(args.out / "protection_tuning_summary.csv", summary)
    git = git_state(ROOT)
    meta = {
        "experiment": "Shorter protection tuning on 8-16 Feb 2024 (DL-101)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "series_sha256": sha, "epoch_utc": EPOCH, "planner": PLANNER, "seeds": list(SEEDS),
        "tolerances_pfu": TOLERANCES, "horizons_s": list(HORIZONS_S),
        "release_dwells_s": list(RELEASE_DWELLS_S), "margins": list(MARGINS),
        "selection": "max mean retention among arms with at most "
                     f"{MAX_EXTRA_UNPROTECTED_S:g} s more unprotected hazard than the baseline "
                     "on every spacecraft and seed; ties: longer H, longer D, more "
                     "conservative margin; none unless it beats the baseline",
        "chosen": setting_of(chosen) if chosen else None,
        "config_hashes": {f"{r['arm']}/seed{r['seed']}": r["config_hash"] for r in rows},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "protection_tuning_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for r in summary:
        print(r, flush=True)
    print(json.dumps({"chosen": meta["chosen"], "git_dirty": git["dirty"],
                      "wall_s": meta["total_wall_s"]}))  # fmt: skip


if __name__ == "__main__":
    main()

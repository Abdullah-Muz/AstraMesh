"""Negative-result analysis: recorded diagnostics N1 - N6 (DL-119 design, DL-120 code).

Planner B4, seed 1 (protection does not depend on the planner and seeds change no outcome;
DL-108, DL-115). Every run uses a recorded configuration (DL-100, DL-103, DL-106 and
DL-113 configs, built by those scripts) except the N6 latency variants. Nothing is tuned.

* **N1 / N2 owner views.** ``SpacecraftAgent._respond_to_loss`` (the only place an agent
  changes its view of a task's owner) is wrapped read-only in each worker: every call that
  changes a view or skips a take-over is recorded with the agent's own mode and its view of
  each peer. Per run: the tasks whose four owner views disagree at the end, and those of
  them completed in the storm's QUIET but not in the run. For the tasks of interest (split,
  or lost while a spacecraft was in a tasking mode for a whole window) the owner-view
  timeline, the time the views last diverged, and the changes around it.
* **N3 - N5 hazard placement.** The per-step hazard is rebuilt from the run's own inputs
  (truth flux, the truth cutoff, each spacecraft's tolerance) and checked against the
  run's hazard and unprotected-hazard totals exactly. Each unprotected interval is placed
  in its hazard episode: ``onset`` (it starts with the episode) or ``after_release`` (it
  starts later, so the spacecraft was protected earlier in that episode: inside an
  episode every step that is not unprotected is protected). Protected spans are classed
  by whether they start and end inside hazard.
* **N6 latency.** The baseline with the series latency at 0, 300, 900 and 1 200 s (600 s is
  the recorded run) on the storms whose baseline has unprotected hazard. Each variant
  series differs from the pinned one only in ``latency_s``; it is written to ``--out``
  with its own SHA-256 and not committed. 0 s is non-causal (the 5-min average is not yet
  complete) and is a bound only.

Writes ``negative_results.json`` (everything), ``negative_runs.csv`` (one row per run)
and ``negative_results_meta.json`` to ``--out``.

    uv run python scripts/experiments/negative_results.py --out /tmp/negative
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ablation_study import ABLATIONS, MAY  # noqa: E402
from ablation_study import config as ablation_config  # noqa: E402
from handover_comparison import config as may_config  # noqa: E402
from heldout_comparison import config as heldout_config  # noqa: E402
from heldout_comparison import held_out_storms  # noqa: E402
from multi_storm_comparison import STORMS as EVAL_STORMS  # noqa: E402
from multi_storm_comparison import config as multi_config  # noqa: E402
from protection_comparison import config as shorter_config  # noqa: E402
from spread_formation import config as spread_config  # noqa: E402
from storm_replay_comparison import SERIES as MAY_SERIES  # noqa: E402

PLANNER = "rule_b4"
SEED = 1
PHASE5 = (*EVAL_STORMS, MAY)
SPREAD_KM = (2000.0, 5000.0)
LATENCY_STORMS = ("jul18_2023", "20240606", "20250330", "20260117")
LATENCIES_S = (0, 300, 900, 1200)
RECORDED_LATENCY_S = 600
DL115_RUNS = (("20241007", "no_lookahead"), ("20260117", "no_lookahead"))
DL100_RUNS = (("jul18_2023", "baseline"), ("mar23_2024", "baseline"))
AVAILABLE = ("a spacecraft fully available", "only partly available", "none in a tasking mode")
Job = tuple[str, str, str]  # (group, storm, arm); arm carries the spacing or latency


def jobs() -> list[Job]:
    out: list[Job] = []
    for st in PHASE5:
        out += [("phase5", st, a) for a in ("quiet", "baseline", *ABLATIONS)]
        out.append(("phase5", st, "handover"))
        if st != MAY:
            out.append(("phase5", st, "shorter"))
    for st in sorted(held_out_storms()):
        out += [("heldout", st, a) for a in ("quiet", "baseline", "handover", "shorter",
                                              *ABLATIONS)]  # fmt: skip
    out += [("spread", f"{km:g}km", a) for km in SPREAD_KM for a in ("quiet", "baseline")]
    out += [("latency", st, f"{lat}s") for st in LATENCY_STORMS for lat in LATENCIES_S]
    return out


def _may_sha() -> str:
    return hashlib.sha256(MAY_SERIES.read_bytes()).hexdigest()


def variant_series(storm: str, latency_s: int, folder: Path) -> tuple[Path, str]:
    """The storm's pinned series with only ``latency_s`` changed; (path, sha256)."""
    src = (ROOT / f"configs/data/fold_{storm}_series.json" if storm in EVAL_STORMS
           else ROOT / held_out_storms()[storm]["series_file"])  # fmt: skip
    text = src.read_bytes()
    old = f'"latency_s":{RECORDED_LATENCY_S}'.encode()
    if text.count(old) != 1:
        raise ValueError(f"{src}: expected one {old!r}")
    data = text.replace(old, f'"latency_s":{latency_s}'.encode())
    path = folder / f"{storm}_latency{latency_s}s_series.json"
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def config(job: Job, folder: Path) -> dict[str, Any]:
    group, storm, arm = job
    if group == "phase5":
        if arm in ("quiet", "baseline", *ABLATIONS):
            return ablation_config(storm, PLANNER, arm, SEED)
        if arm == "shorter":
            return shorter_config(storm, PLANNER, "candidate", SEED)
        if arm == "handover":
            if storm == MAY:
                return may_config("S11-H", "P-B", PLANNER, "candidate", SEED, _may_sha())
            return multi_config(storm, PLANNER, "candidate", SEED)
    elif group == "heldout":
        return heldout_config(storm, PLANNER, arm, SEED)
    elif group == "spread":
        return spread_config(float(storm.removesuffix("km")), arm, SEED)
    elif group == "latency":
        base = (ablation_config(storm, PLANNER, "baseline", SEED) if storm in EVAL_STORMS
                else heldout_config(storm, PLANNER, "baseline", SEED))  # fmt: skip
        path, sha = variant_series(storm, int(arm.removesuffix("s")), folder)
        base["scenario_id"] = f"{base['scenario_id']}_latency{arm}"
        base["environment"]["replay"].update(series_file=str(path), series_sha256=sha)
        return base
    raise ValueError(f"unknown job {job!r}")


# -- pure helpers (tested on synthetic data) --------------------------------------------
def runs_of(mask: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
    """[start, stop) index ranges where ``mask`` is True."""
    m = np.concatenate(([False], np.asarray(mask, dtype=bool), [False]))
    d = np.flatnonzero(np.diff(m.astype(np.int8)))
    return [(int(a), int(b)) for a, b in zip(d[::2], d[1::2], strict=True)]


def mode_mask(transitions: list[dict[str, Any]], t_s: npt.NDArray[np.float64],
              modes: tuple[str, ...]) -> npt.NDArray[np.bool_]:  # fmt: skip
    """True where the spacecraft's mode (start NOMINAL) is one of ``modes``."""
    if not transitions:
        return np.full(len(t_s), "NOMINAL" in modes)
    t = np.array([x["t_s"] for x in transitions])
    inside = np.array([x["to"] in modes for x in transitions])
    i = np.searchsorted(t, t_s, side="right") - 1
    return np.where(i >= 0, inside[np.clip(i, 0, None)], "NOMINAL" in modes)


def place(hazard: npt.NDArray[np.bool_], protected: npt.NDArray[np.bool_],
          unprotected: npt.NDArray[np.bool_]) -> list[dict[str, Any]]:  # fmt: skip
    """Each unprotected interval placed in its hazard episode (indices are steps)."""
    out = []
    for a, b in runs_of(hazard):
        for u0, u1 in runs_of(unprotected[a:b]):
            s, e = a + u0, a + u1
            if s > a and not protected[s - 1]:
                raise ValueError("unprotected must be hazard and not protected")
            kind = "onset" if s == a else "after_release"
            out.append({"start": s, "stop": e, "episode": [a, b], "place": kind})
    return out


def span_classes(hazard: npt.NDArray[np.bool_],
                 protected: npt.NDArray[np.bool_]) -> dict[str, Any]:  # fmt: skip
    """Protected spans by where they start and end, with span and gap lengths (steps)."""
    spans = runs_of(protected)
    cls: Counter[str] = Counter()
    for a, b in spans:
        cls[f"start_{'in' if hazard[a] else 'out'}_end_{'in' if hazard[b - 1] else 'out'}"] += 1
    lens = [b - a for a, b in spans]
    gaps = [c - b for (_, b), (c, _) in itertools.pairwise(spans)]
    return {"n_spans": len(spans), "classes": dict(sorted(cls.items())),
            "median_span": float(np.median(lens)) if lens else None,
            "median_gap": float(np.median(gaps)) if gaps else None}  # fmt: skip


Timeline = list[tuple[float, tuple[Any, ...]]]


def views_timeline(changes: list[dict[str, Any]], agents: list[str],
                   final: dict[str, str | None]) -> Timeline:  # fmt: skip
    """Owner views (one per agent) after each change of one task, from its change log.

    ``changes``: time-ordered {"t_s", "agent", "old", "new"}. An agent's view before its
    first change is that change's ``old``; an agent that never changed keeps ``final``."""
    first = {}
    for c in changes:
        first.setdefault(c["agent"], c["old"])
    view = {a: first.get(a, final[a]) for a in agents}
    out = [(float("-inf"), tuple(view[a] for a in agents))]
    for c in changes:
        view[c["agent"]] = c["new"]
        out.append((c["t_s"], tuple(view[a] for a in agents)))
    return out


def last_divergence(timeline: Timeline) -> float | None:
    """Time after which the views never agree again; None if they agree at the end."""
    if len(set(timeline[-1][1])) == 1:
        return None
    t: float | None = None
    for when, v in timeline:
        if len(set(v)) == 1:
            t = None
        elif t is None:
            t = when
    return t


def seconds_by_place(items: list[dict[str, Any]], step_s: float) -> dict[str, float]:
    """Unprotected time [s] by place."""
    out = dict.fromkeys(("onset", "after_release"), 0.0)
    for x in items:
        out[x["place"]] += (x["stop"] - x["start"]) * step_s
    return out


def extra_by_place(arm: list[dict[str, Any]], base: list[dict[str, Any]],
                   step_s: float) -> dict[str, float]:  # fmt: skip
    """Unprotected time [s] in ``arm`` that is not unprotected in ``base``, by its place
    in ``arm``."""
    covered = {k for x in base for k in range(x["start"], x["stop"])}
    out = dict.fromkeys(("onset", "after_release"), 0.0)
    for x in arm:
        out[x["place"]] += sum(1 for k in range(x["start"], x["stop"]) if k not in covered) * step_s
    return out


def tasking_spell(transitions: list[dict[str, Any]], t_s: float,
                  tasking: tuple[str, ...]) -> float | None:  # fmt: skip
    """Length [s] of the last tasking spell that ended at or before ``t_s`` (from entering a
    tasking mode, or the start, to leaving it); None if none ended by then."""
    exit_i = None
    for i, x in enumerate(transitions):
        if x["t_s"] > t_s:
            break
        if x["from"] in tasking and x["to"] not in tasking:
            exit_i = i
    if exit_i is None:
        return None
    start = 0.0
    for x in reversed(transitions[:exit_i]):
        if x["to"] in tasking and x["from"] not in tasking:
            start = x["t_s"]
            break
    return float(transitions[exit_i]["t_s"] - start)


def classify(task_windows: list[tuple[str, int, int]],
             tasking: dict[str, npt.NDArray[np.bool_]]) -> str:  # fmt: skip
    free = [(int(tasking[sc][a : b + 1].sum()), b + 1 - a) for sc, a, b in task_windows]
    if any(f == n for f, n in free):
        return AVAILABLE[0]
    return AVAILABLE[1] if any(f > 0 for f, _ in free) else AVAILABLE[2]


# -- worker ------------------------------------------------------------------------------
def _hazard(cfg: Any, run: Any, geo: Any) -> npt.NDArray[np.bool_]:
    """Per-step hazard (n_ticks, n_sc), as the run computes it (DL-090 access, DL-091)."""
    from astramesh.dynamics.geomagnetic import decimal_year, dipole_axis, invariant_latitude_deg
    from astramesh.forecast.access import CutoffModel
    from astramesh.forecast.replay import StormSeries

    rp = cfg.environment.replay
    series = StormSeries.load(rp.series_file, rp.series_sha256)
    epoch_ns = int(cfg.time.epoch_utc.timestamp()) * 10**9
    t_ns = np.asarray(run.formation.trajectory.t_ns, dtype=np.int64)
    n_sc = cfg.formation.n_spacecraft
    acc = rp.access
    cut = CutoffModel(acc.quiet_cutoff_deg, acc.storm_slope_deg_per_nt, acc.max_shift_deg)
    lam = invariant_latitude_deg(geo.r_itrs, dipole_axis(decimal_year(cfg.time.epoch_utc)))
    truth_cut = np.array([cut.cutoff_deg(series.sym_h_truth(epoch_ns + int(t))) for t in t_ns])
    access = lam >= truth_cut[:, None]
    flux = np.array([np.nan if (f := series.truth(epoch_ns + int(t))) is None else f
                     for t in t_ns])  # fmt: skip
    hz = np.zeros((len(t_ns), n_sc), dtype=bool)
    for j in range(n_sc):
        f = np.where(access[:, j], flux, 0.0)
        hz[:, j] = np.nan_to_num(f, nan=-np.inf) >= rp.tolerance_pfu(j)
    hz[-1] = False  # no step after the final tick
    return hz


def run_one(job: Job, folder: str) -> dict[str, Any]:
    from astramesh.agents.agent import SpacecraftAgent
    from astramesh.agents.supervisor import PROTECTIVE, RECOVERY, TASKING_MODES
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios import nominal_operations as nops

    cfg = parse_scenario(config(job, Path(folder)))
    assert isinstance(cfg, NominalOperationsScenario)
    trace: list[dict[str, Any]] = []
    captured: dict[str, Any] = {}
    orig, orig_geo = SpacecraftAgent._respond_to_loss, nops.geometry_products

    def traced(self: Any, peer: str, now_ns: int, before_ns: int | None = None) -> None:
        before = {tid: t.owner for tid, t in self._public.items()}
        n_log = len(self._log)
        orig(self, peer, now_ns, before_ns)
        changed = {tid: [before.get(tid), t.owner] for tid, t in self._public.items()
                   if before.get(tid) != t.owner}  # fmt: skip
        skipped = [e["task"] for e in self._log[n_log:] if e.get("kind") == "takeover_skipped"]
        if changed or skipped:
            beliefs = self._health.beliefs() if self._health is not None else {}
            trace.append({"t_s": now_ns / 1e9, "agent": self.agent_id, "peer": peer,
                          "window": before_ns is not None, "own_mode": self.mode,
                          "peers": {p: [r.reported_mode, beliefs.get(p)]
                                    for p, r in sorted(self._peer_table.items())},
                          "changed": changed, "skipped": skipped})  # fmt: skip

    def geo_capture(*a: Any, **k: Any) -> Any:
        captured["geo"] = orig_geo(*a, **k)
        return captured["geo"]

    SpacecraftAgent._respond_to_loss = traced  # type: ignore[method-assign]
    nops.geometry_products = geo_capture
    try:
        t0 = time.perf_counter()
        run = nops.run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
        wall = time.perf_counter() - t0
    finally:
        SpacecraftAgent._respond_to_loss = orig  # type: ignore[method-assign]
        nops.geometry_products = orig_geo

    ids = sorted(run.agents)
    step = cfg.time.time_step_s
    t_s = np.asarray(run.formation.trajectory.t_ns, dtype=np.int64) / 1e9
    tr = run.summary["protection"]["transitions"]
    tasking = {a: mode_mask(tr[a], t_s, tuple(TASKING_MODES)) for a in ids}
    completed = sorted(g.task_id for g in run.segments if g.outcome == "completed")
    out: dict[str, Any] = {"job": list(job), "config_hash": cfg.config_hash(),
                           "wall_s": round(wall, 1),
                           "utility": run.summary["operations"]["utility"],
                           "n_tasks": len(run.catalog), "completed": completed}  # fmt: skip
    views = {tid: [run.agents[a]._public[tid].owner if tid in run.agents[a]._public else None
                   for a in ids] for tid in sorted(run.agents[ids[0]]._public)}  # fmt: skip
    split = {tid: v for tid, v in views.items() if len(set(v)) > 1}
    done = set(completed)
    windows = {t.task_id: [(w.spacecraft, w.first_tick, w.last_tick) for w in t.windows]
               for t in run.catalog}  # fmt: skip
    not_done = {tid: classify(windows[tid], tasking) for tid in windows if tid not in done}
    watch = set(split) | {tid for tid, c in not_done.items() if c == AVAILABLE[0]}
    out.update(split_views=split, not_completed_class=not_done,
               watch_trace=[{**e, "changed": {k: v for k, v in e["changed"].items() if k in watch},
                             "skipped": [k for k in e["skipped"] if k in watch]}
                            for e in trace if watch & (set(e["changed"]) | set(e["skipped"]))],
               windows={tid: windows[tid] for tid in watch},
               window_sc_fully_tasking={tid: {a: bool(tasking[a][w0 : w1 + 1].all())
                                         for a, w0, w1 in windows[tid]} for tid in watch},
               agents=ids, transitions=tr, tasking_modes=sorted(TASKING_MODES),
               status_interval_s=cfg.agents.status_interval_s)  # fmt: skip
    if cfg.environment is None:
        return out
    hz = _hazard(cfg, run, captured["geo"])
    st = run.summary["storm"]
    prot = {a: mode_mask(tr[a], t_s, (PROTECTIVE, RECOVERY)) for a in ids}
    per_sc = {}
    for j, a in enumerate(ids):
        unp = hz[:, j] & ~prot[a]
        unp[-1] = False
        iv = [(round(x["start_s"] / step), round(x["end_s"] / step))
              for x in st["unprotected_hazard_intervals"][a]]  # fmt: skip
        if float(hz[:, j].sum()) * step != st["hazard_s"][a] or runs_of(unp) != iv:
            raise ValueError(f"{job} {a}: rebuilt hazard does not match the run")
        per_sc[a] = {"hazard_steps": runs_of(hz[:, j]), "protected_steps": runs_of(prot[a]),
                     "unprotected": place(hz[:, j], prot[a], unp),
                     "spans": span_classes(hz[:, j], prot[a]),
                     "entries_first_hour": sum(1 for x in tr[a] if x["to"] == PROTECTIVE
                                               and x["t_s"] < 3600)}  # fmt: skip
    out["per_sc"] = per_sc
    out["step_s"] = step
    return out


# -- analysis ----------------------------------------------------------------------------
def _key(r: dict[str, Any]) -> tuple[str, str, str]:
    g, s, a = r["job"]
    return g, s, a


def owner_details(r: dict[str, Any], tid: str) -> dict[str, Any]:
    ch = [{"t_s": e["t_s"], "agent": e["agent"], "old": e["changed"][tid][0],
           "new": e["changed"][tid][1], "peer": e["peer"], "window": e["window"],
           "own_mode": e["own_mode"], "peers": e["peers"]}
          for e in r["watch_trace"] if tid in e["changed"]]  # fmt: skip
    final = dict(zip(r["agents"], r["split_views"].get(tid, [None] * len(r["agents"])),
                     strict=True))  # fmt: skip
    if tid not in r["split_views"]:
        final = {a: (ch[-1]["new"] if ch else None) for a in r["agents"]}
    tl = views_timeline(ch, r["agents"], final)
    t_div = last_divergence(tl)
    tasking = tuple(r["tasking_modes"])
    near = [{**c, "peer_tasking_spell_s": tasking_spell(r["transitions"][c["peer"]], c["t_s"],
                                                         tasking)}
            for c in ch if t_div is not None and t_div - 600 <= c["t_s"] <= t_div]  # fmt: skip
    skipped = [{"t_s": e["t_s"], "agent": e["agent"]} for e in r["watch_trace"]
               if tid in e["skipped"]]  # fmt: skip
    return {"task": tid, "final_views": list(tl[-1][1]),
            "n_changes": len(ch),
            "last_divergence_s": "never agreed" if t_div == float("-inf") else t_div,
            "changes_near": near,
            "takeover_skipped": skipped, "windows": r["windows"].get(tid),
            "window_sc_fully_tasking": r["window_sc_fully_tasking"].get(tid)}  # fmt: skip


def analyse(results: list[dict[str, Any]]) -> dict[str, Any]:
    by = {_key(r): r for r in results}
    quiet = {(g, s): set(r["completed"]) for (g, s, a), r in by.items() if a == "quiet"}
    prevalence = []
    for (g, s, a), r in sorted(by.items()):
        if a == "quiet" or g == "latency":
            continue
        q = quiet.get((g, s), set())
        split_lost = [t for t in r["split_views"] if t in q and t not in r["completed"]]
        prevalence.append({"group": g, "storm": s, "arm": a, "utility": r["utility"],
                           "split_tasks": len(r["split_views"]),
                           "split_lost_vs_quiet": len(split_lost),
                           "lost_while_available": sum(
                               1 for t, c in r["not_completed_class"].items()
                               if c == AVAILABLE[0] and t in q)})  # fmt: skip
    n1 = {}
    for storm, arm in DL115_RUNS:
        r = by[("heldout", storm, arm)]
        q = quiet[("heldout", storm)]
        lost = sorted(t for t in r["split_views"] if t in q and t not in r["completed"])
        details = [owner_details(r, t) for t in lost]
        when = Counter(d["last_divergence_s"] for d in details).most_common()
        spells = Counter(c["peer_tasking_spell_s"] for d in details for c in d["changes_near"])
        n1[f"{storm}/{arm}"] = {"n_split_lost": len(lost), "last_divergence_s": when,
                                "status_interval_s": r["status_interval_s"],
                                "peer_tasking_spell_s": spells.most_common(),
                                "details": details}  # fmt: skip
    n2 = {}
    for storm, arm in DL100_RUNS:
        r = by[("phase5", storm, arm)]
        q = quiet[("phase5", storm)]
        tasks = sorted(t for t, c in r["not_completed_class"].items()
                       if c == AVAILABLE[0] and t in q)  # fmt: skip
        n2[f"{storm}/{arm}"] = [{**owner_details(r, t), "split": t in r["split_views"]}
                                for t in tasks]  # fmt: skip

    def placement(group: str, storm: str, arm: str,
                  base: tuple[str, str, str] | None = None) -> dict[str, Any]:  # fmt: skip
        r = by[(group, storm, arm)]
        out = {}
        for a, v in r["per_sc"].items():
            out[a] = {"unprotected_s": seconds_by_place(v["unprotected"], r["step_s"]),
                      "unprotected": v["unprotected"], "spans": v["spans"],
                      "entries_first_hour": v["entries_first_hour"]}  # fmt: skip
            if base is not None:
                b = by[base]["per_sc"][a]["unprotected"]
                out[a]["extra_s"] = extra_by_place(v["unprotected"], b, r["step_s"])
        return out

    storms = [("phase5", s) for s in PHASE5] + [("heldout", s) for s in sorted(held_out_storms())]
    n3 = {f"{g}/{s}": {"baseline": placement(g, s, "baseline"),
                       "no_forecast": placement(g, s, "no_forecast", (g, s, "baseline"))}
          for g, s in storms}  # fmt: skip
    n4 = {f"{g}/{s}": {"baseline": placement(g, s, "baseline"),
                       "no_lookahead": placement(g, s, "no_lookahead", (g, s, "baseline"))}
          for g, s in storms}  # fmt: skip
    n5 = {f"{km:g}km": placement("spread", f"{km:g}km", "baseline") for km in SPREAD_KM}
    n5["20km"] = placement("phase5", "mar23_2024", "baseline")
    n6 = {}
    for st in LATENCY_STORMS:
        g = "phase5" if st in EVAL_STORMS else "heldout"
        rows = {f"{RECORDED_LATENCY_S}s": placement(g, st, "baseline")}
        rows.update({f"{lat}s": placement("latency", st, f"{lat}s") for lat in LATENCIES_S})
        n6[st] = rows
    return {"prevalence": prevalence, "N1": n1, "N2": n2, "N3": n3, "N4": n4, "N5": n5,
            "N6": n6}  # fmt: skip


def main() -> None:
    from astramesh.evaluation.manifest import git_state

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    series_dir = args.out / "latency_series"
    series_dir.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    todo = jobs()
    results = []
    with ProcessPoolExecutor(args.workers) as ex:
        futs = {ex.submit(run_one, j, str(series_dir)): j for j in todo}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            print("/".join(r["job"]), r["utility"], r["wall_s"], "s", flush=True)
    results.sort(key=lambda r: todo.index(_key(r)))
    out = analyse(results)
    (args.out / "negative_results.json").write_text(json.dumps(out, indent=1) + "\n")
    with (args.out / "negative_runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out["prevalence"][0]), lineterminator="\n")
        w.writeheader()
        w.writerows(out["prevalence"])
    git = git_state(ROOT)
    meta = {
        "experiment": "Negative-result analysis N1 - N6 (DL-119)",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "planner": PLANNER, "seed": SEED, "n_runs": len(results),
        "latency_series_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(series_dir.glob("*.json"))},
        "config_hashes": {"/".join(r["job"]): r["config_hash"] for r in results},
        "total_wall_s": round(time.perf_counter() - t0, 1),
    }  # fmt: skip
    (args.out / "negative_results_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"runs": len(results), "git_dirty": git["dirty"]}))


if __name__ == "__main__":
    main()

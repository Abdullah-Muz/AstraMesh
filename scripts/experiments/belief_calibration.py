"""Calibration of the agents' health beliefs (design DL-142, code DL-143).

Run:  uv run python scripts/experiments/belief_calibration.py --out <dir> [--workers 6]

Spec §10.2 lists calibration; Phases 2 - 6 measured it for the anomaly detector and the
forecasts but not for the agents' own beliefs. This script reruns every non-H-A run of
the recorded health comparison (``health_comparison.py``, DL-066 / DL-067) unchanged and
compares the probabilities the agents hold with the simulator's truth. Nothing in
``src/`` changes.

* **Peer (H-B, and the H-B part of H-C).** After every ``SpacecraftAgent.step`` (the
  10 s grid; the simulator steps only spacecraft that are available, so a dead observer
  is never sampled), for each of the observer's peers: the tracker's
  ``p_unavailable(peer, t)`` against ``FaultSchedule.unavailable(peer, t)``. A peer whose
  radio is off, or which is only silent, is *available* (S04 tests false alarms).
* **Payload (H-C).** After every ``PayloadCheck`` an agent observes (one detector check
  every 300 s): its ``PayloadBelief.p`` against ``not FaultSchedule.payload_valid``.
* The truth comes from the run's own fault schedule (captured when the run builds it);
  agents never see it. Wrappers only read, and are removed after each run.
* Samples are reduced in the worker to sums: count, sum of p, sum of outcomes, sum of
  squared errors, and the same per bin (10 equal-width bins of p). Raw samples are not
  stored.

**Unchanged behaviour.** Each run's utility, completions, messages, bytes and config
hash must equal its row in ``docs/results/health_comparison.csv``. Rows are written
before the check, and any mismatch stops the script.

Outputs in ``--out``: ``belief_calibration.csv`` (one row per run and kind: the sums and
the run's scores), ``belief_calibration_summary.csv`` (per model, kind, planner and
scenario, and pooled over the model's scenarios: per-seed scores, mean and 95 %
t-interval over seeds), ``belief_calibration_bins.csv`` (reliability tables, seeds
pooled) and ``belief_calibration_meta.json``. Synthetic faults; the H-C detector's
scores are real (OPS-SAT-AD).
"""

from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import json
import math
import subprocess
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import health_comparison as hc
from fault_comparison import scenario_config

ROOT = Path(__file__).resolve().parents[2]
RECORDED = ROOT / "docs" / "results" / "health_comparison.csv"
BINS = 10
MIN_BIN = 30  # bins with fewer samples are shown but not interpreted (DL-142)
KINDS = ("peer", "payload")
PLAN = tuple((m, s) for m, s in hc.PLAN if m != "H-A")  # H-A holds no probability
BEHAVIOUR = ("utility", "n_completed", "messages_sent", "bytes_sent", "config_hash")

#: (scenario, planner, model, seed, hours, agents.health)
Job = tuple[str, str, str, int, float, dict[str, Any]]


def jobs(sensor_sha: str, seeds: list[int], hours: float = 24.0) -> list[Job]:
    health = hc.models(sensor_sha)
    return [(s, p, m, seed, hours, health[m]) for m, scs in PLAN for s in scs
            for p in hc.PLANNERS for seed in seeds]  # fmt: skip


def build(job: Job) -> dict[str, Any]:
    """The recorded configuration, exactly as ``health_comparison.run_one`` builds it."""
    scenario, planner, _, seed, hours, health = job
    raw = scenario_config(scenario, planner, seed, hours)
    raw["agents"]["health"] = health
    return raw


@dataclass
class Acc:
    """Sums for the Brier score and a reliability table of one set of samples."""

    n: int = 0
    sum_p: float = 0.0
    sum_y: int = 0
    sum_sq: float = 0.0
    bins: list[list[float]] = field(default_factory=lambda: [[0, 0.0, 0] for _ in range(BINS)])

    def add(self, p: float, y: bool) -> None:
        e = p - y
        self.n += 1
        self.sum_p += p
        self.sum_y += y
        self.sum_sq += e * e
        b = self.bins[min(int(p * BINS), BINS - 1)]
        b[0] += 1
        b[1] += p
        b[2] += y

    def merge(self, other: Acc) -> None:
        self.n += other.n
        self.sum_p += other.sum_p
        self.sum_y += other.sum_y
        self.sum_sq += other.sum_sq
        for b, o in zip(self.bins, other.bins, strict=True):
            for i in range(3):
                b[i] += o[i]

    def scores(self) -> dict[str, float | str]:
        """Base rate, Brier, Brier skill against the base rate, ECE ('' if undefined)."""
        if self.n == 0:
            return {"base_rate": "", "brier": "", "brier_skill": "", "ece": ""}
        rate = self.sum_y / self.n
        brier = self.sum_sq / self.n
        ref = rate * (1.0 - rate)
        ece = sum(n / self.n * abs(sp / n - sy / n) for n, sp, sy in self.bins if n)
        return {"base_rate": rate, "brier": brier,
                "brier_skill": 1.0 - brier / ref if ref > 0 else "", "ece": ece}  # fmt: skip

    def to_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {"n": self.n, "sum_p": self.sum_p, "sum_y": self.sum_y,
                               "sum_sq": self.sum_sq}  # fmt: skip
        for i, (n, sp, sy) in enumerate(self.bins):
            row |= {f"b{i}_n": int(n), f"b{i}_sum_p": sp, f"b{i}_sum_y": int(sy)}
        return row

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> Acc:
        a = cls(int(r["n"]), float(r["sum_p"]), int(r["sum_y"]), float(r["sum_sq"]))
        a.bins = [[int(r[f"b{i}_n"]), float(r[f"b{i}_sum_p"]), int(r[f"b{i}_sum_y"])]
                  for i in range(BINS)]  # fmt: skip
        return a


def peer_truth(faults: Any, peer: str, t_ns: int) -> bool:
    """True if ``peer`` is unavailable; a silent or radio-off peer is available."""
    return bool(faults.unavailable(peer, t_ns))


def payload_truth(faults: Any, sc: str, t_ns: int) -> bool:
    """True if ``sc``'s payload is degraded (its observations are invalid)."""
    return not faults.payload_valid(sc, t_ns)


@contextmanager
def sampling(acc: dict[str, Acc]) -> Iterator[None]:
    """Record beliefs against truth during one run; restore everything afterwards."""
    from astramesh.agents import agent as agent_mod
    from astramesh.agents.packets import PayloadCheck
    from astramesh.scenarios import nominal_operations as ops

    cls = agent_mod.SpacecraftAgent
    orig_step, orig_observe, orig_faults = cls.step, cls.observe, ops.fault_schedule
    faults: list[Any] = []

    @functools.wraps(orig_faults)
    def capture(*a: Any, **k: Any) -> Any:
        faults.append(orig_faults(*a, **k))
        return faults[-1]

    @functools.wraps(orig_step)
    def step(self: Any, now_ns: int) -> Any:
        out = orig_step(self, now_ns)
        h = self._health
        if h is not None and h.settings.bayes is not None:
            for peer in self.peers:
                acc["peer"].add(h.p_unavailable(peer, now_ns), peer_truth(faults[-1], peer, now_ns))
        return out

    @functools.wraps(orig_observe)
    def observe(self: Any, packet: Any) -> Any:
        out = orig_observe(self, packet)
        if isinstance(packet, PayloadCheck) and self._payload is not None:
            y = payload_truth(faults[-1], self.agent_id, packet.t_ns)
            acc["payload"].add(self._payload.p, y)
        return out

    cls.step, cls.observe = step, observe  # type: ignore[method-assign]
    ops.fault_schedule = capture  # type: ignore[assignment]
    try:
        yield
    finally:
        cls.step, cls.observe = orig_step, orig_observe  # type: ignore[method-assign]
        ops.fault_schedule = orig_faults  # type: ignore[assignment]


def run_one(job: Job) -> list[dict[str, Any]]:
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    scenario, planner, model, seed, _, _ = job
    cfg = parse_scenario(build(job))
    assert isinstance(cfg, NominalOperationsScenario)
    acc = {k: Acc() for k in KINDS}
    t0 = time.perf_counter()
    with sampling(acc):
        run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())
    wall = time.perf_counter() - t0
    o, n = run.summary["operations"], run.summary["network"]
    base = {"scenario": scenario, "planner": planner, "model": model, "seed": seed,
            "utility": o["utility"], "n_completed": o["n_completed"],
            "messages_sent": n["sent"], "bytes_sent": n["bytes_sent"],
            "config_hash": cfg.config_hash(), "wall_s": round(wall, 2)}  # fmt: skip
    return [base | {"kind": k} | a.scores() | a.to_row() for k, a in acc.items() if a.n]


def recorded() -> dict[tuple[str, str, str, int], dict[str, str]]:
    with RECORDED.open(encoding="utf-8") as fh:
        return {(r["scenario"], r["planner"], r["model"], int(r["seed"])):
                {k: r[k] for k in BEHAVIOUR} for r in csv.DictReader(fh)}  # fmt: skip


def check(rows: list[dict[str, Any]], expected_runs: int) -> list[str]:
    """Every run equals its recorded run; every run is present."""
    rec, bad, seen = recorded(), [], set()
    for r in rows:
        key = (r["scenario"], r["planner"], r["model"], int(r["seed"]))
        if key in seen:
            continue
        seen.add(key)
        want = rec.get(key)
        got = {k: str(r[k]) for k in BEHAVIOUR}
        if want is None:
            bad.append(f"{key}: no recorded run")
        elif got != want:
            bad.append(f"{key}: {got} != recorded {want}")
    if len(seen) != expected_runs:
        bad.append(f"{len(seen)} runs with samples, expected {expected_runs}")
    return bad


def _t_interval(xs: list[float]) -> tuple[float, float, float]:
    k = len(xs)
    mean = sum(xs) / k
    if k < 2:
        return mean, mean, mean
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (k - 1))
    half = float(stats.t.ppf(0.975, k - 1)) * sd / math.sqrt(k)
    return mean, mean - half, mean + half


def groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], dict[int, Acc]]:
    """(model, kind, planner, scenario or 'pooled') -> seed -> summed samples."""
    out: dict[tuple[str, str, str, str], dict[int, Acc]] = {}
    for r in rows:
        a = Acc.from_row(r)
        for scope in (r["scenario"], "pooled"):
            per_seed = out.setdefault((r["model"], r["kind"], r["planner"], scope), {})
            per_seed.setdefault(int(r["seed"]), Acc()).merge(a)
    return out


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (model, kind, planner, scope), per_seed in groups(rows).items():
        rec: dict[str, Any] = {"model": model, "kind": kind, "planner": planner,
                               "scenario": scope, "n_seeds": len(per_seed),
                               "n_samples": sum(a.n for a in per_seed.values())}  # fmt: skip
        scores = [a.scores() for a in per_seed.values()]
        for m in ("base_rate", "brier", "brier_skill", "ece"):
            xs = [float(s[m]) for s in scores if s[m] != ""]
            if not xs:
                rec |= {f"{m}_mean": "", f"{m}_ci95_lo": "", f"{m}_ci95_hi": "", f"{m}_n": 0}
                continue
            mean, lo, hi = _t_interval(xs)
            rec |= {f"{m}_mean": mean, f"{m}_ci95_lo": lo, f"{m}_ci95_hi": hi, f"{m}_n": len(xs)}
        out.append(rec)
    return out


def reliability(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (model, kind, planner, scope), per_seed in groups(rows).items():
        total = Acc()
        for a in per_seed.values():
            total.merge(a)
        for i, (n, sp, sy) in enumerate(total.bins):
            out.append({"model": model, "kind": kind, "planner": planner, "scenario": scope,
                        "bin": i, "p_lo": i / BINS, "p_hi": (i + 1) / BINS, "n": int(n),
                        "share": n / total.n if total.n else "",
                        "mean_p": sp / n if n else "", "observed": sy / n if n else "",
                        "interpreted": n >= MIN_BIN})  # fmt: skip
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    def fmt(v: Any) -> Any:
        return f"{v:.9g}" if isinstance(v, float) else v

    with path.open("w", newline="\n", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows({k: fmt(v) for k, v in r.items()} for r in rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=10)
    args = ap.parse_args(argv)

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()  # fmt: skip

    commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    sensor_sha = hashlib.sha256(hc.SENSOR.read_bytes()).hexdigest()
    seeds = list(range(1, args.seeds + 1))
    todo = jobs(sensor_sha, seeds)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [r for rs in pool.map(run_one, todo) for r in rs]
    args.out.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out / "belief_calibration.csv", rows)  # before the check (DL-135)
    bad = check(rows, len(todo))
    meta: dict[str, Any] = {
        "experiment": "Calibration of the agents' health beliefs (DL-142, DL-143)",
        "git_commit": commit,
        "git_dirty": dirty,
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "recorded_runs": str(RECORDED.relative_to(ROOT)),
        "recorded_sha256": hashlib.sha256(RECORDED.read_bytes()).hexdigest(),
        "sensor_sha256": sensor_sha,
        "plan": {m: list(s) for m, s in PLAN},
        "planners": list(hc.PLANNERS),
        "seeds": seeds,
        "bins": BINS,
        "min_bin_samples": MIN_BIN,
        "n_runs": len(todo),
        "n_checked": len(todo) - len(bad),
        "check_failures": bad,
        "workers": args.workers,
        "total_wall_s": round(time.time() - t0, 1),
    }
    (args.out / "belief_calibration_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    if bad:
        print("\n".join(bad), file=sys.stderr)
        raise SystemExit(f"behaviour check failed for {len(bad)} item(s); rows kept")
    _write_csv(args.out / "belief_calibration_summary.csv", summarize(rows))
    _write_csv(args.out / "belief_calibration_bins.csv", reliability(rows))
    print(json.dumps({k: meta[k] for k in ("git_commit", "git_dirty", "n_runs", "total_wall_s")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

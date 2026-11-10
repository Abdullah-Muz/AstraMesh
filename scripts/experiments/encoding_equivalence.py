"""Digest one simulation run, to show that a performance change leaves outputs identical (DL-074).

Prints one JSON line: sha256 of the run summary, of the full send/delivery trace and of the
event log, plus the counted bytes and the wall time. Run it with the old and the new code
(e.g. from a git worktree of the old commit, with this file copied in) and compare the lines;
every field except ``wall_s`` must match.

    cd <repo> && E=scripts/experiments/encoding_equivalence.py
    uv run python $E config configs/experiments/nominal_ops_b3_24h.yaml
    uv run python $E s11 P-B cbba_b3_timeout 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from astramesh.core.config import parse_scenario
from astramesh.core.events import EventLog, canonical_json
from astramesh.core.rng import RandomStreams
from astramesh.scenarios.nominal_operations import run_nominal_operations

ROOT = Path(__file__).resolve().parents[2]


def _sha(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="kind", required=True)
    cfg_p = sub.add_parser("config", help="a scenario config file")
    cfg_p.add_argument("path")
    s11_p = sub.add_parser("s11", help="one S11 job, as in storm_replay_comparison.py")
    s11_p.add_argument("variant")
    s11_p.add_argument("planner")
    s11_p.add_argument("seed", type=int)
    args = ap.parse_args()

    if args.kind == "s11":
        sys.path.insert(0, str(ROOT / "scripts" / "experiments"))
        import storm_replay_comparison as s11

        sha = hashlib.sha256(s11.SERIES.read_bytes()).hexdigest()
        raw = s11.scenario_config(args.variant, args.planner, args.seed, sha)
        job = ["s11", args.variant, args.planner, args.seed]
    else:
        raw = yaml.safe_load((ROOT / args.path).read_text())
        job = ["config", args.path]

    cfg = parse_scenario(raw)
    log = EventLog()
    t0 = time.perf_counter()
    run = run_nominal_operations(cfg, RandomStreams(cfg.random.seed), log)
    wall = time.perf_counter() - t0
    print(json.dumps({
        "job": job,
        "config_hash": cfg.config_hash(),
        "summary": _sha(run.summary),
        "trace": _sha(run.trace),
        "events": log.sha256(),
        "n_trace": len(run.trace),
        "bytes_sent": run.summary.get("network", {}).get("bytes_sent"),
        "wall_s": round(wall, 1),
    }))  # fmt: skip


if __name__ == "__main__":
    main()

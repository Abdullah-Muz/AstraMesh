"""Gate P1: the 24 h four-spacecraft J2 baseline completes and replays identically.

The digests pin the deterministic artifacts of ``configs/experiments/formation_24h_j2.yaml``.
They depend on libm (initial elements -> state) and ERFA (epoch pole), so they
are expected to hold on the reference platform (Ubuntu 24.04 x86_64: WSL2 and
CI); see docs/DECISION_LOG.md DL-029. If they change, either the dynamics or
initialization changed deliberately (update with a decision-log entry) or
replay broke.
"""

from __future__ import annotations

import json
from pathlib import Path

from astramesh.evaluation.manifest import sha256_file
from astramesh.evaluation.runner import SUMMARY_FILE, run_scenario
from astramesh.scenarios.formation_dynamics import TRAJECTORY_FILE

GOLDEN_TRAJECTORY_SHA256 = "452950d89c6814ae1334f8e9e431610ad3d5ce64374f2fa9b73687b22b6b46ae"
GOLDEN_EVENTS_SHA256 = "21e8a5021e68a78b4dc742678376bc9895f01eaa54b4934faf7146484f0917dc"


def test_24h_j2_baseline_completes_and_matches_golden(
    formation_config_path: Path, tmp_path: Path
) -> None:
    result = run_scenario(formation_config_path, tmp_path / "run")
    summary = json.loads((tmp_path / "run" / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["n_steps"] == 8640
    sep = summary["adjacent_separation_km"]
    assert sep["min"] > 19.9  # formation intact after 24 h
    assert sep["max"] < 20.1
    assert result.events_sha256 == GOLDEN_EVENTS_SHA256
    assert sha256_file(tmp_path / "run" / TRAJECTORY_FILE) == GOLDEN_TRAJECTORY_SHA256

"""Gate P1: the 24 h mission-geometry baseline replays identically.

Digests pin ``configs/experiments/mission_geometry_24h.yaml``. Like the formation
baseline they depend on libm and ERFA but not on the CPU model (no BLAS or NumPy
transcendental functions on the scenario path, DL-031); see DL-029 for scope.
The trajectory must equal the formation_dynamics baseline byte for byte: both
scenarios share the same dynamics.
"""

from __future__ import annotations

import json
from pathlib import Path

from astramesh.evaluation.manifest import sha256_file
from astramesh.evaluation.runner import SUMMARY_FILE, run_scenario
from astramesh.scenarios.formation_dynamics import TRAJECTORY_FILE
from astramesh.scenarios.mission_geometry import OPPORTUNITIES_FILE

GOLDEN_EVENTS_SHA256 = "c6c67589072d042e76457b3071be0d3d31535a5c91ae33724bba5fb9f7a8127c"
GOLDEN_OPPORTUNITIES_SHA256 = "cc76a1ca132674f07be84e14646f3631ed0ad536aaeb3ecab8ebfda14b3554cc"
# Same value as GOLDEN_TRAJECTORY_SHA256 in test_formation_baseline.py (shared dynamics).
FORMATION_TRAJECTORY_SHA256 = "80a1651bc2ac0c893ea2254b55340f5985f60c06ee262cfcdb5f3d878d988fa8"


def test_24h_mission_geometry_matches_golden(mission_config_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = run_scenario(mission_config_path, out)
    summary = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["science"]["n_opportunities"] == 43
    assert sha256_file(out / OPPORTUNITIES_FILE) == GOLDEN_OPPORTUNITIES_SHA256
    assert result.events_sha256 == GOLDEN_EVENTS_SHA256
    assert sha256_file(out / TRAJECTORY_FILE) == FORMATION_TRAJECTORY_SHA256

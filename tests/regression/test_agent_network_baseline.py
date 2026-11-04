"""Gate P2 (replay): the 24 h agent-network baseline replays identically.

Pins events, the message trace and the summary of
``configs/experiments/agent_network_24h.yaml``. Loss/duplication come from the
``comms`` stream and navigation noise from ``sensors`` (seed 1). The trajectory
equals the formation baseline's (shared dynamics). Scope as DL-029/DL-034.
"""

from __future__ import annotations

import json
from pathlib import Path

from astramesh.evaluation.manifest import sha256_file
from astramesh.evaluation.runner import SUMMARY_FILE, run_scenario
from astramesh.scenarios.agent_network import MESSAGES_FILE
from astramesh.scenarios.formation_dynamics import TRAJECTORY_FILE

GOLDEN_EVENTS_SHA256 = "bf0a8aa83f38b2d8a8f763deee5627f70a5a5a505f5d023763dc36e18e04e64b"
GOLDEN_MESSAGES_SHA256 = "b05a90cdf3499aa4207ab5841b8cf576072c0fba37f11f80235e743375f3dcfb"
GOLDEN_SUMMARY_SHA256 = "cd70b92f16e4d588b8c620e828930a479d365973fbc40718c45a8f66c1a9a246"
FORMATION_TRAJECTORY_SHA256 = "80a1651bc2ac0c893ea2254b55340f5985f60c06ee262cfcdb5f3d878d988fa8"


def test_24h_agent_network_matches_golden(network_config_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = run_scenario(network_config_path, out)
    summary = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["network"]["sent"] == 4 * 2881
    assert result.events_sha256 == GOLDEN_EVENTS_SHA256
    assert sha256_file(out / MESSAGES_FILE) == GOLDEN_MESSAGES_SHA256
    assert sha256_file(out / SUMMARY_FILE) == GOLDEN_SUMMARY_SHA256
    assert sha256_file(out / TRAJECTORY_FILE) == FORMATION_TRAJECTORY_SHA256

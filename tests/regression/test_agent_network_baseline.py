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

GOLDEN_EVENTS_SHA256 = "a7c39464d6c9e5e0be2504989a03c54c728c6e6c352eb80b832c247cc6899c4f"
GOLDEN_MESSAGES_SHA256 = "df06deca06f33a9f288b25fa29e76b9155a75e59bda8a98d182189348cf467cc"
GOLDEN_SUMMARY_SHA256 = "8ba8ab3403f30840f10f5d43c2fe995d95ff9b21197fea2296bb9a1f16aa1f38"
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

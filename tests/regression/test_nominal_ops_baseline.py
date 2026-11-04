"""Gate P2 (replay): the 24 h S00 nominal-operations baseline with B0 replays identically.

B0 adds no messages, so the message trace must equal the agent-network
baseline's (same network, agents and random streams).
"""

from __future__ import annotations

import json
from pathlib import Path

from astramesh.evaluation.manifest import sha256_file
from astramesh.evaluation.runner import SUMMARY_FILE, run_scenario
from astramesh.scenarios.agent_network import MESSAGES_FILE
from astramesh.scenarios.nominal_operations import OBSERVATIONS_FILE, PLAN_FILE

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = {
    "events": "0979857b066fea04cf807ec11cf58e2bf5482ce4418a4e99f365759e5bb9718c",
    PLAN_FILE: "3145f63b6accce67a075bcb5ce45ce38a66fb0c723973425256a8828019ede66",
    OBSERVATIONS_FILE: "39d73e9613fec90023c66c18fb9e8875b849a0a86285ca24f4d6e58b533315de",
    SUMMARY_FILE: "26f2cd24b5b2a121b1e842ac17761f520b0c5f77f5ca614304c00a7ef0de8316",
}
AGENT_NETWORK_MESSAGES_SHA256 = "df06deca06f33a9f288b25fa29e76b9155a75e59bda8a98d182189348cf467cc"


def test_24h_nominal_ops_b0_matches_golden(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = run_scenario(ROOT / "configs/experiments/nominal_ops_b0_24h.yaml", out)
    ops = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))["operations"]
    assert (ops["n_completed"], ops["utility"], ops["n_duplicates"]) == (43, 144, 0)
    assert result.events_sha256 == GOLDEN["events"]
    for name in (PLAN_FILE, OBSERVATIONS_FILE, SUMMARY_FILE):
        assert sha256_file(out / name) == GOLDEN[name], name
    assert sha256_file(out / MESSAGES_FILE) == AGENT_NETWORK_MESSAGES_SHA256

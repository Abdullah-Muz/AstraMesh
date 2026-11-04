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
    "events": "4cb17eaf4d85d62e991cac2fdb849fe7e9025eb4d95fbc5ff90932b52fa025c2",
    PLAN_FILE: "d5bc2908554bdc3761ac84bf9e1d16566665a2d59dd0f3a4fd5f199385f89214",
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


GOLDEN_B1 = {
    "events": "9e671235785eafc15134eccc2b9c75e08f9d119b2dcf18a3c97972d1874d8b70",
    PLAN_FILE: "202a41e58156f06a9621a6e381aae5de1af4db97fca88843c2443dae07d43733",
    OBSERVATIONS_FILE: "25b9a1697e33ce0a8d5a2c00346beb173ca994d8c939ca42361ad3dd318df279",
    SUMMARY_FILE: "98c645ac9ce615988277a322ce2a1a71b5e6edba939f5cb24489b633f83446b6",
}


def test_24h_nominal_ops_b1_matches_golden(tmp_path: Path) -> None:
    """B1 (privileged MILP reference): same tasks and network as B0; lexicographic
    tie-break makes the plan identical on every CPU (verified under two code paths)."""
    out = tmp_path / "run"
    result = run_scenario(ROOT / "configs/experiments/nominal_ops_b1_24h.yaml", out)
    ops = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))["operations"]
    assert ops["privileged_information"] is True
    assert (ops["n_completed"], ops["utility"], ops["n_duplicates"]) == (43, 144, 0)
    assert result.events_sha256 == GOLDEN_B1["events"]
    for name in (PLAN_FILE, OBSERVATIONS_FILE, SUMMARY_FILE):
        assert sha256_file(out / name) == GOLDEN_B1[name], name
    assert sha256_file(out / MESSAGES_FILE) == AGENT_NETWORK_MESSAGES_SHA256

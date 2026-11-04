"""Gate P2 (replay): the 24 h S00 nominal-operations baseline with B0 replays identically.

B0 adds no messages, so the message trace must equal the agent-network
baseline's (same network, agents and random streams).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from astramesh.evaluation.manifest import sha256_file
from astramesh.evaluation.runner import SUMMARY_FILE, run_scenario
from astramesh.scenarios.agent_network import MESSAGES_FILE
from astramesh.scenarios.nominal_operations import OBSERVATIONS_FILE, PLAN_FILE

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = {
    "events": "4df5f6ba9b0752b801871a8f57f1173ef42b8b60172bdfd950943913b6397e85",
    PLAN_FILE: "d5bc2908554bdc3761ac84bf9e1d16566665a2d59dd0f3a4fd5f199385f89214",
    OBSERVATIONS_FILE: "39d73e9613fec90023c66c18fb9e8875b849a0a86285ca24f4d6e58b533315de",
    SUMMARY_FILE: "a230147c0592fefa23606d3d57631d937e3594b8b92cdfbf6ce6c077b6700978",
}
AGENT_NETWORK_MESSAGES_SHA256 = "306167036138cf929514f9bff579436c1507913289800af683e52a1bdf7fa1ae"


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
    "events": "15bdb09061c1c30b50a347f377ad7c7c933808524bdd2aa9e7b78a9dbb5d1add",
    PLAN_FILE: "202a41e58156f06a9621a6e381aae5de1af4db97fca88843c2443dae07d43733",
    OBSERVATIONS_FILE: "25b9a1697e33ce0a8d5a2c00346beb173ca994d8c939ca42361ad3dd318df279",
    SUMMARY_FILE: "d899c03a0fa7dd06e3babf1b3dc61e1e148cc668ead23108eaf02864978ce576",
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


B1_OBSERVATIONS_SHA256 = GOLDEN_B1[OBSERVATIONS_FILE]
GOLDEN_DECENTRALIZED = {
    "nominal_ops_b2_24h.yaml": {
        "events": "759bed130b2df2506cffc133542216b161a6a5bbf1cf9b2ac696dd8ca2c342cc",
        PLAN_FILE: "bda4c39d3c1eccb0b0db788b3ef1a248dfb7756f8a6f5adc74d1f6df8efdd18f",
        SUMMARY_FILE: "4e7208815a57ad46e3f23ca1d56a70642030a391c248fa9806a06c069f2bf0b0",
        MESSAGES_FILE: "2b2df08395d12e9ea265671f3977f8909f26c56a6cbae91a06b98840d8380fea",
    },
    "nominal_ops_b3_24h.yaml": {
        "events": "8cf1d597fdef6f199ae0350e4897b30eced193acf85725c5bad83ee47d6b0e75",
        PLAN_FILE: "5190f5f2cd3be4c35232d088b25a868f8b141e717936482a06e3b237928bb448",
        SUMMARY_FILE: "7dba63f71456cc4b2503d0e5f78887fbde7f610c1fc145206599d49277268d61",
        MESSAGES_FILE: "06192094c2fe8becadd3a2ad7f3efc36db0bba3327f4e918b6965e374d6e55f5",
    },
}


@pytest.mark.parametrize("config_name", sorted(GOLDEN_DECENTRALIZED))
def test_24h_decentralized_baselines_match_golden(config_name: str, tmp_path: Path) -> None:
    """B2/B3 24 h: pinned digests; executed observations equal B1's (with equal scores and
    ties to the lower ID, every method gives every task to sc00 with the same slots)."""
    out = tmp_path / "run"
    result = run_scenario(ROOT / "configs/experiments" / config_name, out)
    ops = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))["operations"]
    assert ops["decentralized"] is True
    assert (ops["n_completed"], ops["utility"], ops["n_duplicates"]) == (43, 144, 0)
    golden = GOLDEN_DECENTRALIZED[config_name]
    assert result.events_sha256 == golden["events"]
    for name in (PLAN_FILE, SUMMARY_FILE, MESSAGES_FILE):
        assert sha256_file(out / name) == golden[name], name
    assert sha256_file(out / OBSERVATIONS_FILE) == B1_OBSERVATIONS_SHA256

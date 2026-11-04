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
    "events": "4cb17eaf4d85d62e991cac2fdb849fe7e9025eb4d95fbc5ff90932b52fa025c2",
    PLAN_FILE: "d5bc2908554bdc3761ac84bf9e1d16566665a2d59dd0f3a4fd5f199385f89214",
    OBSERVATIONS_FILE: "39d73e9613fec90023c66c18fb9e8875b849a0a86285ca24f4d6e58b533315de",
    SUMMARY_FILE: "726d5d89e37ff4a14c6fd97a09f960cb528f7ba105500cef8dae081dad2dbe85",
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
    SUMMARY_FILE: "9cbcca2dab9b0011e0299131c4a9c8097d772d27f7f263cb4220cb12cfeb9d88",
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
        "events": "cd364ae2809ea16e94460ba3d5e97e588c32cd0067aab69f898f47710faceac3",
        PLAN_FILE: "bda4c39d3c1eccb0b0db788b3ef1a248dfb7756f8a6f5adc74d1f6df8efdd18f",
        SUMMARY_FILE: "c48e9cafb4bcf9cd5e11d408b89f1e41dc1d3c7277cd03117eb69aabdce38f93",
        MESSAGES_FILE: "ceb228e79defcfc9df7d4adb14d4103b6babaf8a540f74a7362830ac1f402a90",
    },
    "nominal_ops_b3_24h.yaml": {
        "events": "fd976630010561050d701e03de3933ed1c7df8f68fc4d67f66ac52dd0d7d8c58",
        PLAN_FILE: "5190f5f2cd3be4c35232d088b25a868f8b141e717936482a06e3b237928bb448",
        SUMMARY_FILE: "0cc16503f3cbe9de088e97c7ed15b870604520c192e65fac0ee533955e9ad6bb",
        MESSAGES_FILE: "1426562c5ae403bf30f0cc52376e46d4a7a04816262418c89e1f82828844bcee",
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

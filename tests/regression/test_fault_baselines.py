"""Phase 3 increment 1: pinned fault-scenario baseline (S01, B3, no health awareness).

The dead spacecraft (sc00, lost at 6 h) held every task under the tie rule; without
health beliefs the others never take its tasks over, so utility drops to 34/144.
Its frozen final belief keeps the nominal B3 plan on record (same plan.json digest).
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
    "events": "146b7afcce03e6ea6a0862b556bde790adadb3662e2ea117df5de661fdccab84",
    PLAN_FILE: "5190f5f2cd3be4c35232d088b25a868f8b141e717936482a06e3b237928bb448",
    OBSERVATIONS_FILE: "22459a064bc069d057b4d4f5276f3ad311599d458a49c205df1e5d802d0c9c98",
    SUMMARY_FILE: "e58a33e9bfb690d62f1eba336bae2c8727da5273a26eec66f0ff7ea950682244",
    MESSAGES_FILE: "ec4417ddb4d46f02faa1d6d0b1454c8dcfd746535c9194c74a8c0514cd083c57",
}


def test_s01_b3_matches_golden(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = run_scenario(ROOT / "configs/experiments/faults/s01_unavailable.yaml", out)
    ops = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))["operations"]
    assert (ops["utility"], ops["n_completed"]) == (34, 10)
    assert ops["faults"][0]["fault_id"] == "F01"
    assert result.events_sha256 == GOLDEN["events"]
    for name in (PLAN_FILE, OBSERVATIONS_FILE, SUMMARY_FILE, MESSAGES_FILE):
        assert sha256_file(out / name) == GOLDEN[name], name


GOLDEN_B4 = {
    "events": "e904e37f6f50c360bf9ae423cc212be6853269fe30b879e52e4635e20fdb0f28",
    PLAN_FILE: "97b9663b98bcf83f2b98b11af8a718a70f24a4d4d17e4dae7f0e3aa8664516f3",
    OBSERVATIONS_FILE: "1832f341743d34b690cc09e15700d779e48c978f755a4738b82f5233c76d1091",
    SUMMARY_FILE: "abf53cc3960950b6b49551d673048a57c62604c17a8630d59c27d6f63227c082",
    MESSAGES_FILE: "7c5d6bc9a8fdaad99de87177a887e7ad1b040112755ab0bd6d6e4fba4734c20a",
}


def test_s01_b4_recovers_and_matches_golden(tmp_path: Path) -> None:
    """B4 detects the loss after ~280 s and redistributes sc00's future tasks: 144/144."""
    out = tmp_path / "run"
    result = run_scenario(ROOT / "configs/experiments/faults/s01_unavailable_b4.yaml", out)
    s = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert (s["operations"]["utility"], s["operations"]["n_duplicates"]) == (144, 0)
    assert s["health"]["confirmed_while_available"] == 0
    assert set(s["health"]["detection_latency_s"].values()) == {280.0}
    assert result.events_sha256 == GOLDEN_B4["events"]
    for name in (PLAN_FILE, OBSERVATIONS_FILE, SUMMARY_FILE, MESSAGES_FILE):
        assert sha256_file(out / name) == GOLDEN_B4[name], name


GOLDEN_HAZARD = {
    "events": "857ffd083336aa5f396a7eef5d4499da486d97edbbc20a1286429bfdc5d73f5a",
    PLAN_FILE: "8675f3491fb8324c6c615bdbe224e26309f855d76c748e7401f4d31dbc4cb62f",
    OBSERVATIONS_FILE: "1adbbf751cab3e955bf8180e8dcd970a63cbac3745fda0938badfc64e6e781f6",
    SUMMARY_FILE: "7091a9ade81ff1693a41b2a8734953845696dcfa52c4236374c44e90f9b45c40",
    MESSAGES_FILE: "3a1c93d9a8b1d292ef6106754c6b99d5400d4dfa80f67fb77592e2433a658b24",
}


def test_protective_hazard_b3_matches_golden(tmp_path: Path) -> None:
    """sc00 PROTECTIVE 6.0-9.5 h (30 min release dwell); CBBA re-auctions its claims."""
    out = tmp_path / "run"
    result = run_scenario(ROOT / "configs/experiments/faults/protective_hazard.yaml", out)
    s = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert (s["operations"]["utility"], s["operations"]["n_duplicates"]) == (144, 0)
    assert sum(s["protection"]["payload_steps_outside_nominal"].values()) == 0
    assert [t["to"] for t in s["protection"]["transitions"]["sc00"]] == ["PROTECTIVE", "NOMINAL"]
    assert result.events_sha256 == GOLDEN_HAZARD["events"]
    for name in (PLAN_FILE, OBSERVATIONS_FILE, SUMMARY_FILE, MESSAGES_FILE):
        assert sha256_file(out / name) == GOLDEN_HAZARD[name], name

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
    SUMMARY_FILE: "6518ffc9a6a5647ea59f205ad929ad420136efc4bda894269e9f22aa264b5fd9",
    MESSAGES_FILE: "f44393b61bc111f7971b132998fdd8a26dc40a3a6db8027cb7d38733d2578396",
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
    SUMMARY_FILE: "f6ff3e352dd67a4c6115d44cc5e613bd116c8001b68fa8f3c69124995f6c4124",
    MESSAGES_FILE: "bc649f665e29560e523554c5af4fab0a21280dc662a4afb62b26da6b36c38d75",
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

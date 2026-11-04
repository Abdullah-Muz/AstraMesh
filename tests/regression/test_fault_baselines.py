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
    "events": "442a750678e57b2264b9168717806efe88bb20ee859f8da6fed344230a8f983d",
    PLAN_FILE: "5190f5f2cd3be4c35232d088b25a868f8b141e717936482a06e3b237928bb448",
    OBSERVATIONS_FILE: "22459a064bc069d057b4d4f5276f3ad311599d458a49c205df1e5d802d0c9c98",
    SUMMARY_FILE: "cd7c970fae12af5036641c070142a3b15822f64e9f7d5b31c53852aa7ec8c124",
    MESSAGES_FILE: "e180503829c340aeb1f29b81278dfc754f47b3234d03f6120920997c5159b714",
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

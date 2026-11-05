"""H-A / H-B / H-C in short fault scenarios with planning held fixed (DL-066)."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from astramesh.core.config import NominalOperationsScenario, parse_scenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.scenarios.nominal_operations import run_nominal_operations

ROOT = Path(__file__).resolve().parents[2]
H = 3600
SHA = hashlib.sha256((ROOT / "configs/data/opssat_score_sensor.json").read_bytes()).hexdigest()
MODELS: dict[str, dict[str, Any] | None] = {
    "none": None,
    "H-A": {"model": "timeout"},
    "H-B": {"model": "bayes"},
    "H-C": {"model": "bayes", "payload_check": {"sensor_sha256": SHA}},
}
LOSS = {"type": "unavailable", "spacecraft": ["sc00"], "start_s": H}
PAYLOAD = {"type": "payload_degraded", "spacecraft": ["sc00"], "start_s": H, "end_s": 5 * H}


def _run(fault: dict[str, Any], algorithm: str, model: str, hours: float) -> Any:
    raw = yaml.safe_load((ROOT / "configs/experiments/nominal_ops_b0_24h.yaml").read_text())
    cfg = copy.deepcopy(raw)
    cfg["time"]["duration_s"] = int(hours * H)
    cfg["operations"]["algorithm"] = algorithm
    cfg["faults"] = [{"fault_id": "F1", "observability": "effects_only", "cause": "test",
                      "consequences": "test", **fault}]  # fmt: skip
    if MODELS[model] is not None:
        cfg["agents"]["health"] = MODELS[model]
    parsed = parse_scenario(cfg)
    assert isinstance(parsed, NominalOperationsScenario)
    return run_nominal_operations(parsed, RandomStreams(parsed.random.seed), EventLog())


def test_explicit_h_a_behaves_exactly_like_the_default() -> None:
    a = _run(LOSS, "rule_b4", "none", 4)
    b = _run(LOSS, "rule_b4", "H-A", 4)
    assert a.summary["operations"] == b.summary["operations"]
    assert a.summary["network"] == b.summary["network"]
    ha, hb = a.summary["health"], dict(b.summary["health"])
    for k in ("model", "payload_check", "payload"):
        hb.pop(k)
    assert ha == hb


def test_h_b_detects_a_real_loss_sooner_than_the_timeout() -> None:
    lat_a = _run(LOSS, "rule_b4", "H-A", 3).summary["health"]["detection_latency_s"]
    lat_b = _run(LOSS, "rule_b4", "H-B", 3).summary["health"]["detection_latency_s"]
    assert all(v is not None and v >= 270 for v in lat_a.values())
    assert all(v is not None and v <= 200 for v in lat_b.values())


@pytest.mark.parametrize("algorithm", ["rule_b4", "cbba_b3_timeout"])
def test_h_c_detects_a_degraded_payload_and_stops_wasting_observations(algorithm: str) -> None:
    a = _run(PAYLOAD, algorithm, "H-A", 8)
    c = _run(PAYLOAD, algorithm, "H-C", 8)
    pa, pc = a.summary["health"]["payload"], c.summary["health"]["payload"]
    assert pa["detection_latency_s"] == {"F1:sc00": None}  # H-A has no payload evidence
    lat = pc["detection_latency_s"]["F1:sc00"]
    assert lat is not None
    assert lat <= 1800
    oa, oc = a.summary["operations"], c.summary["operations"]
    assert oa["n_invalid_payload"] > 0
    assert oc["n_invalid_payload"] < oa["n_invalid_payload"]
    assert oc["utility"] >= oa["utility"]
    assert c.summary["health"]["confirmed_while_available"] == 0
    assert sum(c.summary["protection"]["payload_steps_in_protected_modes"].values()) == 0

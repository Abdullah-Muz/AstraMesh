"""Health beliefs in short fault scenarios: detection, response, false outage, ground
confirmation (DL-052, Gate P3: a false outage is not a confirmed failure)."""

from __future__ import annotations

import copy
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
BASE = {"cause": "test", "consequences": "test"}


def _run(fault: dict[str, Any], algorithm: str, hours: float = 8) -> tuple[Any, list[Any]]:
    raw = yaml.safe_load((ROOT / "configs/experiments/nominal_ops_b0_24h.yaml").read_text())
    cfg = copy.deepcopy(raw)
    cfg["time"]["duration_s"] = int(hours * H)
    cfg["operations"]["algorithm"] = algorithm
    cfg["faults"] = [{"fault_id": "F1", "observability": "effects_only", **BASE, **fault}]
    parsed = parse_scenario(cfg)
    assert isinstance(parsed, NominalOperationsScenario)
    log = EventLog()
    return run_nominal_operations(parsed, RandomStreams(parsed.random.seed), log), list(log)


LOSS = {"type": "unavailable", "spacecraft": ["sc00"], "start_s": H}


@pytest.mark.parametrize(("reactive", "passive"), [("rule_b4", "static_b0"),
                                                   ("cbba_b3_timeout", "cbba_b3")])  # fmt: skip
def test_detection_and_reassignment_recover_science(reactive: str, passive: str) -> None:
    good, _ = _run(LOSS, reactive)
    bad, _ = _run(LOSS, passive)
    assert good.summary["operations"]["utility"] > bad.summary["operations"]["utility"]
    lat = good.summary["health"]["detection_latency_s"]
    assert lat
    assert all(v is not None and 270 <= v <= 330 for v in lat.values())  # ~300 s timeout
    assert good.summary["health"]["confirmed_while_available"] == 0


def test_false_outage_is_never_confirmed_failure() -> None:
    """Gate P3: sc00's radio is off for 1 h but it keeps working."""
    for algo in ("rule_b4", "cbba_b3_timeout"):
        run, events = _run({"type": "comms_outage", "spacecraft": ["sc00"], "start_s": H,
                            "end_s": 2 * H}, algo, hours=4)  # fmt: skip
        h = run.summary["health"]
        assert h["confirmed_while_available"] == 0
        assert h["false_unavailable_s"] > 0  # it was (wrongly) believed lost for a while
        assert not [
            e for e in events if e.kind == "belief_changed" and e.data["to"] == "CONFIRMED_FAILED"
        ]
        finals = [b for obs in h["final_beliefs"].values() for b in obs.values()]
        assert set(finals) <= {"HEALTHY", "RECOVERING"}  # everyone recovered after reconnect


def test_ground_confirmation_is_the_only_route_to_confirmed() -> None:
    run, events = _run({**LOSS, "observability": "ground_confirmed",
                        "ground_confirmation_s": 2 * H}, "rule_b4", hours=3)  # fmt: skip
    notices = [e for e in events if e.kind == "failure_confirmed"]
    assert [(e.time_ns, e.data["spacecraft"]) for e in notices] == [(2 * H * 10**9, ["sc00"])]
    confirmed = [
        e for e in events if e.kind == "belief_changed" and e.data["to"] == "CONFIRMED_FAILED"
    ]
    assert {e.source for e in confirmed} == {"sc01", "sc02", "sc03"}
    assert all(e.time_ns == 2 * H * 10**9 for e in confirmed)
    assert run.summary["health"]["confirmed_while_available"] == 0

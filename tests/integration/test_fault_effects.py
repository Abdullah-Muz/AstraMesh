"""Truth effects of each fault type in short operations runs (DL-050)."""

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
NS = 10**9
BASE = {"cause": "test", "observability": "effects_only", "consequences": "test"}


def _run(fault: dict[str, Any], *, algorithm: str = "cbba_b3", hours: float = 4) -> Any:
    raw = yaml.safe_load((ROOT / "configs/experiments/nominal_ops_b0_24h.yaml").read_text())
    cfg = copy.deepcopy(raw)
    cfg["time"]["duration_s"] = int(hours * H)
    cfg["operations"]["algorithm"] = algorithm
    cfg["faults"] = [{"fault_id": "F1", **BASE, **fault}]
    parsed = parse_scenario(cfg)
    assert isinstance(parsed, NominalOperationsScenario)
    log = EventLog()
    run = run_nominal_operations(parsed, RandomStreams(parsed.random.seed), log)
    return run, list(log)


def test_unavailable_spacecraft_goes_silent_and_stops_observing() -> None:
    run, events = _run({"type": "unavailable", "spacecraft": ["sc00"], "start_s": H})
    t0 = H * NS
    assert not [e for e in run.trace if e["event"] == "send" and e["sender"] == "sc00"
                and e["t_ns"] >= t0]  # fmt: skip
    assert not [e for e in run.trace if e["event"] == "deliver" and e["receiver"] == "sc00"
                and e["t_ns"] >= t0]  # fmt: skip
    assert not [s for s in run.segments if s.spacecraft == "sc00" and s.start_tick * 10 * NS >= t0]
    started = [e for e in events if e.kind == "fault_started"]
    assert len(started) == 1
    assert started[0].time_ns == t0
    assert started[0].source == "faults"


def test_comms_outage_suppresses_sends_and_resumes() -> None:
    run, events = _run({"type": "comms_outage", "spacecraft": ["sc01"], "start_s": H,
                        "end_s": 2 * H})  # fmt: skip
    win = range(H * NS, 2 * H * NS)
    sends = [e for e in run.trace if e["sender"] == "sc01" and e["event"].startswith("send")]
    assert all(e["event"] == "send_suppressed" for e in sends if e["t_ns"] in win)
    assert any(e["event"] == "send" for e in sends if e["t_ns"] >= 2 * H * NS)
    assert run.summary["network"]["suppressed_radio_off"] > 0
    got = [e for e in run.trace if e["event"] == "deliver" and e["receiver"] == "sc01"
           and e["t_ns"] in win and e["result"] == "accepted"]  # fmt: skip
    assert not got
    assert [e.kind for e in events if e.source == "faults"] == ["fault_started", "fault_ended"]


def test_partition_blocks_only_cross_group_messages() -> None:
    run, events = _run({"type": "partition", "groups": [["sc00", "sc01"], ["sc02", "sc03"]],
                        "start_s": H, "end_s": 2 * H})  # fmt: skip
    a, b = {"sc00", "sc01"}, {"sc02", "sc03"}
    win = range(H * NS + NS, 2 * H * NS)  # deliveries arrive 1 s after sending
    cross = [e for e in run.trace if e["event"] == "deliver" and e["t_ns"] in win
             and ((e["sender"] in a) != (e["receiver"] in a))]  # fmt: skip
    inside = [e for e in run.trace if e["event"] == "deliver" and e["t_ns"] in win
              and ((e["sender"] in b) == (e["receiver"] in b))]  # fmt: skip
    assert not cross
    assert inside
    assert any(e.kind == "link_down" for e in events)
    assert any(e.kind == "link_up" for e in events)


def test_payload_degradation_invalidates_observations() -> None:
    run, _ = _run(
        {"type": "payload_degraded", "spacecraft": ["sc00"], "start_s": 0}, algorithm="static_b0"
    )  # permanent: sc00's first B0 slot is at 3.9 h
    bad = [s for s in run.segments if s.spacecraft == "sc00"]
    assert bad
    assert all(s.outcome == "invalid_payload" for s in bad)
    o = run.summary["operations"]
    assert o["n_invalid_payload"] == len(bad)
    assert o["utility"] == sum(t.priority for t in run.catalog if any(
        s.task_id == t.task_id and s.outcome == "completed" for s in run.segments))  # fmt: skip


@pytest.mark.parametrize("severity", [0.0, 0.5])
def test_power_degradation_reduces_generation(severity: float) -> None:
    nominal, _ = _run({"type": "power_degraded", "spacecraft": ["sc01"], "start_s": 0,
                       "severity_fraction": 1.0})  # fmt: skip
    degraded, _ = _run({"type": "power_degraded", "spacecraft": ["sc00"], "start_s": 0,
                        "severity_fraction": severity})  # fmt: skip
    nom = nominal.summary["operations"]["final_battery_wh"]["sc00"]
    deg = degraded.summary["operations"]["final_battery_wh"]["sc00"]
    assert deg < nom
    assert degraded.summary["operations"]["final_battery_wh"]["sc01"] == pytest.approx(
        nominal.summary["operations"]["final_battery_wh"]["sc01"]
    )


def test_agents_cannot_reach_the_fault_schedule() -> None:
    import sys

    from astramesh.faults.schedule import Fault, FaultSchedule

    sys.path.insert(0, str(ROOT / "tests" / "agent_isolation"))
    from test_isolation import FORBIDDEN, _reachable

    run, _ = _run({"type": "comms_outage", "spacecraft": ["sc01"], "start_s": H,
                   "end_s": 2 * H}, hours=2.5)  # fmt: skip
    for agent in run.agents.values():
        for obj in _reachable(agent):
            assert not isinstance(obj, (*FORBIDDEN, FaultSchedule, Fault)), type(obj).__name__

"""Fault schedule queries and fault configuration validation."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from astramesh.core.config import ConfigError, parse_scenario
from astramesh.faults.schedule import Fault, FaultSchedule

IDS = ["sc00", "sc01", "sc02", "sc03"]


def _f(fid: str, kind: str, sc: tuple[str, ...] = (), groups: tuple[tuple[str, ...], ...] = (),
       start: int = 10, end: int | None = 20, sev: float = 1.0) -> Fault:  # fmt: skip
    return Fault(fid, kind, sc or tuple(m for g in groups for m in g), groups, start, end, sev,
                 "c", "effects_only", end is not None, "q")  # fmt: skip


def test_activity_window_and_queries() -> None:
    fs = FaultSchedule([
        _f("A", "unavailable", ("sc00",), start=10, end=None),
        _f("B", "comms_outage", ("sc01",), start=10, end=20),
        _f("C", "partition", groups=(("sc00", "sc01"), ("sc02",)), start=0, end=5),
        _f("D", "payload_degraded", ("sc02",)),
        _f("E", "power_degraded", ("sc03",), sev=0.5),
        _f("F", "power_degraded", ("sc03",), sev=0.2, start=15, end=20),
    ], IDS)  # fmt: skip
    assert not fs.unavailable("sc00", 9)
    assert fs.unavailable("sc00", 10)
    assert fs.unavailable("sc00", 10**15)  # permanent
    assert not fs.radio_up("sc00", 10)  # unavailable implies radio off
    assert not fs.radio_up("sc01", 19)
    assert fs.radio_up("sc01", 20)  # end is exclusive
    assert fs.link_cut("sc00", "sc02", 0)
    assert fs.link_cut("sc01", "sc03", 0)  # unlisted spacecraft form their own group
    assert not fs.link_cut("sc00", "sc01", 0)
    assert not fs.link_cut("sc00", "sc02", 5)
    assert not fs.payload_valid("sc02", 15)
    assert fs.payload_valid("sc02", 25)
    assert fs.generation_factor("sc03", 12) == 0.5
    assert fs.generation_factor("sc03", 16) == 0.2  # the most severe active fault wins
    assert fs.generation_factor("sc02", 16) == 1.0


def test_transitions_are_time_ordered_and_bounded() -> None:
    fs = FaultSchedule([_f("A", "comms_outage", ("sc00",), start=10, end=30),
                        _f("B", "unavailable", ("sc01",), start=30, end=None)], IDS)  # fmt: skip
    tr = [(t, k, f.fault_id) for t, k, f in fs.transitions(100)]
    assert tr == [(10, "fault_started", "A"), (30, "fault_ended", "A"), (30, "fault_started", "B")]
    assert fs.transitions(20) == [(10, "fault_started", fs.faults[0])]
    assert not FaultSchedule([], IDS)


def test_schedule_rejects_unknown_type_or_spacecraft() -> None:
    with pytest.raises(ValueError, match="unknown fault type"):
        FaultSchedule([_f("A", "meteor", ("sc00",))], IDS)
    with pytest.raises(ValueError, match="unknown spacecraft"):
        FaultSchedule([_f("A", "unavailable", ("sc09",))], IDS)


ROOT = Path(__file__).resolve().parents[2]


def _ops(faults: list[dict[str, Any]]) -> dict[str, Any]:
    raw = yaml.safe_load((ROOT / "configs/experiments/nominal_ops_b0_24h.yaml").read_text())
    cfg = copy.deepcopy(raw)
    cfg["faults"] = faults
    return cfg  # type: ignore[no-any-return]


BASE = {"fault_id": "F1", "cause": "c", "observability": "effects_only", "consequences": "q",
        "start_s": 600}  # fmt: skip


@pytest.mark.parametrize(
    "fault",
    [
        {**BASE, "type": "unavailable", "spacecraft": ["sc09"]},
        {**BASE, "type": "unavailable", "spacecraft": []},
        {**BASE, "type": "unavailable", "spacecraft": ["sc00"], "end_s": 600},
        {**BASE, "type": "unavailable", "spacecraft": ["sc00"], "start_s": 605},
        {**BASE, "type": "unavailable", "spacecraft": ["sc00"], "severity_fraction": 0.5},
        {**BASE, "type": "partition", "groups": [["sc00"], ["sc00", "sc01"]]},
        {**BASE, "type": "partition", "groups": [["sc00"]], "spacecraft": ["sc01"]},
        {**BASE, "type": "comms_outage", "spacecraft": ["sc00"], "observability": "magic"},
        {**BASE, "type": "comms_outage", "spacecraft": ["sc00"], "cause": ""},
        {
            **BASE,
            "type": "unavailable",
            "spacecraft": ["sc00"],
            "observability": "ground_confirmed",
        },
        {**BASE, "type": "unavailable", "spacecraft": ["sc00"], "ground_confirmation_s": 900},
        {
            **BASE,
            "type": "unavailable",
            "spacecraft": ["sc00"],
            "observability": "ground_confirmed",
            "ground_confirmation_s": 300,
        },
    ],
)
def test_invalid_fault_configs_rejected(fault: dict[str, Any]) -> None:
    with pytest.raises(ConfigError):
        parse_scenario(_ops([fault]))


def test_duplicate_fault_ids_rejected() -> None:
    f = {**BASE, "type": "comms_outage", "spacecraft": ["sc00"]}
    with pytest.raises(ConfigError, match="duplicate fault_id"):
        parse_scenario(_ops([f, dict(f)]))


def test_fault_configs_in_repo_are_valid() -> None:
    paths = sorted((ROOT / "configs/experiments/faults").glob("*.yaml"))
    assert len(paths) >= 6
    for p in paths:
        cfg = parse_scenario(yaml.safe_load(p.read_text()))
        assert cfg.faults or cfg.environment, p.name  # type: ignore[union-attr]

"""S00 nominal operations end to end: replay, scoring rules, resource stress, isolation."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from astramesh.core.config import NominalOperationsScenario, parse_scenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.evaluation.runner import EVENTS_FILE, SUMMARY_FILE, run_config
from astramesh.scenarios.agent_network import MESSAGES_FILE
from astramesh.scenarios.nominal_operations import (
    OBSERVATIONS_FILE,
    PLAN_FILE,
    run_nominal_operations,
)


def _cfg(base: dict[str, Any], hours: float = 6, **changes: Any) -> NominalOperationsScenario:
    cfg = copy.deepcopy(base)
    cfg["time"]["duration_s"] = int(hours * 3600)
    for path, value in changes.items():
        sec, key = path.split("__")
        cfg[sec][key] = value
    parsed = parse_scenario(cfg)
    assert isinstance(parsed, NominalOperationsScenario)
    return parsed


def _run(cfg: NominalOperationsScenario) -> Any:
    return run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())


def test_replay_and_artifacts(ops_config_dict: dict[str, Any], tmp_path: Path) -> None:
    cfg = _cfg(ops_config_dict)
    run_config(cfg, tmp_path / "a")
    run_config(cfg, tmp_path / "b")
    for name in (EVENTS_FILE, SUMMARY_FILE, MESSAGES_FILE, PLAN_FILE, OBSERVATIONS_FILE):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_nominal_scoring_is_consistent(ops_config_dict: dict[str, Any]) -> None:
    run = _run(_cfg(ops_config_dict))
    o = run.summary["operations"]
    by_id = {t.task_id: t for t in run.catalog}
    completed = [s for s in run.segments if s.outcome == "completed"]
    assert o["n_completed"] == len(completed) == len({s.task_id for s in completed})
    assert o["utility"] == sum(by_id[s.task_id].priority for s in completed)
    assert o["n_completed"] == len(run.plan.assignments) - len(
        [s for s in run.segments if s.outcome != "completed"]
    )
    for s in completed:  # truth check: inside the observer's own window, long enough
        w = by_id[s.task_id].window_of(s.spacecraft)
        assert w is not None
        assert w.first_tick <= s.start_tick
        assert s.stop_tick - 1 <= w.last_tick
        assert s.stop_tick - s.start_tick >= 6


def test_high_reserve_makes_agents_decline(ops_config_dict: dict[str, Any]) -> None:
    run = _run(_cfg(ops_config_dict, operations__battery_reserve_fraction=0.9))
    o = run.summary["operations"]
    declined = [r for d in o["declined"].values() for r in d.values()]
    assert declined
    assert set(declined) == {"battery_reserve"}  # 80% initial charge < 90% reserve at first
    assert o["n_completed"] + len(declined) == o["n_assigned"]


def test_storage_limit_leaves_tasks_unassigned(ops_config_dict: dict[str, Any]) -> None:
    run = _run(_cfg(ops_config_dict, spacecraft__storage_capacity_mb=0.2))  # 2 x 0.075 MB each
    o = run.summary["operations"]
    assert o["unassigned"]
    assert all(v <= 0.2 for v in o["storage_used_mb"].values())
    assert o["n_completed"] == o["n_assigned"] <= 8


def test_starved_battery_aborts_are_not_credited(ops_config_dict: dict[str, Any]) -> None:
    starved = {
        "spacecraft__solar_generation_w": 0.0,
        "spacecraft__battery_capacity_wh": 10.0,
        "operations__battery_reserve_fraction": 0.0,
    }
    run = _run(_cfg(ops_config_dict, hours=12, **starved))
    o = run.summary["operations"]
    assert sum(o["deficit_steps"].values()) > 0
    aborted = [s for s in run.segments if s.aborted == "power"]
    assert aborted
    assert all(s.outcome == "aborted_power" for s in aborted)
    assert o["utility"] == sum(
        t.priority for t in run.catalog
        if any(s.task_id == t.task_id and s.outcome == "completed" for s in run.segments)
    )  # fmt: skip


@pytest.fixture
def ops_config_dict() -> dict[str, Any]:
    import yaml

    root = Path(__file__).resolve().parents[2]
    data = yaml.safe_load((root / "configs/experiments/nominal_ops_b0_24h.yaml").read_text())
    assert isinstance(data, dict)
    return data


def test_operations_agents_stay_isolated(ops_config_dict: dict[str, Any]) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent_isolation"))
    from test_isolation import FORBIDDEN, _reachable

    from astramesh.agents.agent import SpacecraftAgent

    run = _run(_cfg(ops_config_dict, hours=1))
    for agent in run.agents.values():
        for obj in _reachable(agent):
            assert not isinstance(obj, FORBIDDEN), type(obj).__name__
            assert not isinstance(obj, SpacecraftAgent) or obj is agent
    summary = json.dumps(run.summary)
    assert "privileged_information" in summary


def test_b1_reference_never_aborts_for_power_and_matches_or_beats_b0(
    ops_config_dict: dict[str, Any],
) -> None:
    """With truth illumination B1 excludes observations the battery cannot support,
    so none aborts for power, and its utility is at least B0's on identical tasks."""
    starved = {
        "spacecraft__solar_generation_w": 0.0,
        "spacecraft__battery_capacity_wh": 10.0,
        "operations__battery_reserve_fraction": 0.2,
    }
    b1 = _run(_cfg(ops_config_dict, hours=12, operations__algorithm="centralized_b1", **starved))
    b0 = _run(_cfg(ops_config_dict, hours=12, **starved))
    assert b1.plan.privileged_information
    assert b1.plan.excluded
    assert not [s for s in b1.segments if s.aborted == "power"]
    assert not any(b1.summary["operations"]["declined"].values())
    assert b1.summary["operations"]["utility"] >= b0.summary["operations"]["utility"]
    assert [t.task_id for t in b1.catalog] == [t.task_id for t in b0.catalog]

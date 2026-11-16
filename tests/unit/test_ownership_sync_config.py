"""B4 ownership re-sync configuration (DL-122): absent leaves recorded configurations
unchanged, B4 only, validation, and a short storm-free run unchanged by the re-sync."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from astramesh.core.config import ConfigError, NominalOperationsScenario, parse_scenario

ROOT = Path(__file__).resolve().parents[2]
BLOCK = {"horizon_s": 10800.0, "grace_status_intervals": 2}


def _heldout() -> ModuleType:
    path = ROOT / "scripts/experiments/heldout_comparison.py"
    spec = importlib.util.spec_from_file_location("heldout_comparison", path)
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _raw(planner: str = "rule_b4", arm: str = "baseline") -> dict[str, Any]:
    raw: dict[str, Any] = _heldout().config("20240606", planner, arm, 1)
    return raw


def test_absent_or_null_keeps_the_recorded_hash() -> None:
    recorded = json.loads((ROOT / "docs/results/heldout_meta.json").read_text())
    want = recorded["config_hashes"]["20240606/rule_b4/baseline/seed1"]
    raw = _raw()
    assert parse_scenario(raw).config_hash() == want
    raw["agents"]["ownership_sync"] = None
    assert parse_scenario(raw).config_hash() == want
    raw["agents"]["ownership_sync"] = BLOCK
    assert parse_scenario(raw).config_hash() != want


def test_b4_only_and_validated() -> None:
    raw = _raw("cbba_b3_timeout")
    raw["agents"]["ownership_sync"] = BLOCK
    with pytest.raises(ConfigError, match="rule_b4 only"):
        parse_scenario(raw)
    for bad in ({"horizon_s": 0, "grace_status_intervals": 2},
                {"horizon_s": 10800, "grace_status_intervals": 0},
                {"horizon_s": 10800}):  # fmt: skip
        raw = _raw()
        raw["agents"]["ownership_sync"] = bad
        with pytest.raises(ConfigError):
            parse_scenario(raw)


def test_a_storm_free_run_is_unchanged_by_the_resync() -> None:
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios.nominal_operations import run_nominal_operations

    base = _raw(arm="quiet")
    base["time"]["duration_s"] = 6 * 3600
    on = copy.deepcopy(base)
    on["agents"]["ownership_sync"] = BLOCK
    out = []
    for raw in (base, on):
        cfg = parse_scenario(raw)
        assert isinstance(cfg, NominalOperationsScenario)
        out.append(run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog()))
    done = [sorted(g.task_id for g in r.segments if g.outcome == "completed") for r in out]
    assert done[0] == done[1]
    assert done[0]
    ops = [r.summary["operations"] for r in out]
    assert ops[0]["utility"] == ops[1]["utility"]
    assert ops[1]["n_duplicates"] == 0
    sent = [r.summary["network"]["bytes_sent"] for r in out]
    assert sent[1] > sent[0]  # claims add bytes

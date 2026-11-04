"""Scenario builder of scripts/experiments/fault_comparison.py (DL-058)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from astramesh.core.config import NominalOperationsScenario, parse_scenario

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/experiments/fault_comparison.py"


def _mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fault_comparison", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_draws_are_deterministic_distinct_and_in_range() -> None:
    m = _mod()
    for seed in range(1, 21):
        d = m.draws(seed)
        assert d == m.draws(seed)
        assert d["a"] != d["b"]
        assert {d["a"], d["b"]} <= set(m.IDS)
        assert 4 * 3600 <= d["t0_s"] <= 10 * 3600
        assert d["t0_s"] % 10 == 0


@pytest.mark.parametrize("scenario", ["S00", "S01", "S02", "S03", "S04", "S05", "S07", "S08",
                                      "S09", "S10"])  # fmt: skip
def test_every_scenario_builds_a_valid_config_paired_across_methods(scenario: str) -> None:
    m = _mod()
    faults = set()
    for method in m.METHODS:
        cfg = parse_scenario(m.scenario_config(scenario, method, 3, 24.0))
        assert isinstance(cfg, NominalOperationsScenario)
        assert cfg.operations.algorithm == method
        faults.add((str(cfg.faults), str(cfg.environment)))
    assert len(faults) == 1  # same faults and hazards for every method of a seed


def test_unknown_scenario_rejected() -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        _mod().scenario_config("S06", "static_b0", 1, 24.0)


def test_retention_uses_same_method_and_seed() -> None:
    m = _mod()
    rows = [{"scenario": "S00", "method": "x", "seed": 1, "utility": 100},
            {"scenario": "S01", "method": "x", "seed": 1, "utility": 75},
            {"scenario": "S01", "method": "y", "seed": 1, "utility": 75}]  # fmt: skip
    m.add_retention(rows)
    assert rows[1]["retention"] == 0.75
    assert rows[2]["retention"] == ""  # no healthy reference for method y

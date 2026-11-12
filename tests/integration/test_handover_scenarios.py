"""Handover candidate in operations runs (DL-094): HO-01 configuration and no-storm
identity, HO-04 identical modes and hazard per run, HO-05 no B4 protection duplicates."""

from __future__ import annotations

import copy
import functools
import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from astramesh.core.config import NominalOperationsScenario, parse_scenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.scenarios.nominal_operations import OperationsRun, run_nominal_operations

ROOT = Path(__file__).parents[2]
BASE = ROOT / "configs" / "experiments" / "nominal_ops_b0_24h.yaml"
SERIES = ROOT / "configs" / "data" / "s11_storm_series.json"
RULE = {"window_threshold_ratio": 0.7, "lead_s": 3600.0}


def _raw(planner: str, storm: bool, duration_s: int) -> dict[str, Any]:
    raw: dict[str, Any] = copy.deepcopy(yaml.safe_load(BASE.read_text()))
    raw["operations"]["algorithm"] = planner
    raw["time"]["duration_s"] = duration_s
    if storm:  # 12 h over the first onset >= 100 pfu (10 May 17:20 UT)
        raw["time"]["epoch_utc"] = "2024-05-10T12:00:00Z"
        raw["environment"] = {"background_exposure_ratio": 0.0, "replay": {
            "series_sha256": hashlib.sha256(SERIES.read_bytes()).hexdigest(),
            "forecast": "P-B/q50", "access": {}, "forecast_max_age_s": 3600.0,
            "radiation_tolerance_pfu": [100.0, 100.0, 50.0, 200.0]}}  # fmt: skip
    return raw


@functools.cache
def _run(planner: str, storm: bool, candidate: bool, duration_s: int) -> OperationsRun:
    raw = _raw(planner, storm, duration_s)
    if candidate:
        raw["agents"]["handover"] = dict(RULE)
    cfg = parse_scenario(raw)
    assert isinstance(cfg, NominalOperationsScenario)
    return run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())


def test_ho01_absent_handover_leaves_the_hash_unchanged() -> None:
    plain = parse_scenario(_raw("rule_b4", False, 21_600))
    explicit = _raw("rule_b4", False, 21_600)
    explicit["agents"]["handover"] = None
    assert parse_scenario(explicit).config_hash() == plain.config_hash()
    with_rule = _raw("rule_b4", False, 21_600)
    with_rule["agents"]["handover"] = dict(RULE)
    assert parse_scenario(with_rule).config_hash() != plain.config_hash()


@pytest.mark.parametrize("planner", ["rule_b4", "cbba_b3_timeout"])
def test_ho01_without_a_storm_both_arms_are_identical(planner: str) -> None:
    base, cand = _run(planner, False, False, 21_600), _run(planner, False, True, 21_600)
    assert cand.summary["operations"] == base.summary["operations"]
    assert cand.summary["protection"] == base.summary["protection"]


@pytest.mark.parametrize("planner", ["rule_b4", "cbba_b3_timeout"])
def test_ho04_candidate_keeps_modes_and_hazard_identical(planner: str) -> None:
    base, cand = _run(planner, True, False, 43_200), _run(planner, True, True, 43_200)
    assert (
        cand.summary["protection"]["time_in_mode_s"] == base.summary["protection"]["time_in_mode_s"]
    )
    assert cand.summary["protection"]["transitions"] == base.summary["protection"]["transitions"]
    for key in ("hazard_s", "protected_in_hazard_s", "exposed_s"):
        assert cand.summary["storm"][key] == base.summary["storm"][key]
    assert sum(cand.summary["protection"]["payload_steps_in_protected_modes"].values()) == 0


def test_ho05_b4_has_no_protection_duplicates() -> None:
    for candidate in (False, True):
        run = _run("rule_b4", True, candidate, 43_200)
        modes = run.summary["protection"]["time_in_mode_s"]
        assert any(m["PROTECTIVE"] > 0 for m in modes.values())
        assert run.summary["operations"]["n_duplicates"] == 0

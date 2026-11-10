"""``dynamics.drag`` configuration (DL-080/081): hashes, validation, and a drag run."""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from astramesh.core.config import ConfigError, FormationScenarioBase, parse_scenario
from astramesh.core.events import EventLog
from astramesh.dynamics.forces import specific_energy
from astramesh.scenarios.formation_dynamics import run_formation_dynamics

BASE = Path(__file__).parents[2] / "configs" / "experiments" / "formation_24h_j2.yaml"


def _raw() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(BASE.read_text())
    return raw


def _with_drag(b: list[float], **time: float) -> dict[str, Any]:
    raw = copy.deepcopy(_raw())
    raw["dynamics"]["drag"] = {"ballistic_m2pkg": b}
    raw["time"].update(time)
    return raw


def test_absent_drag_leaves_the_hash_unchanged() -> None:
    plain = parse_scenario(_raw())
    explicit = copy.deepcopy(_raw())
    explicit["dynamics"]["drag"] = None
    assert parse_scenario(explicit).config_hash() == plain.config_hash()
    assert parse_scenario(_with_drag([0.0092])).config_hash() != plain.config_hash()


def test_drag_validation() -> None:
    parse_scenario(_with_drag([0.0092]))
    parse_scenario(_with_drag([0.0092, 0.0092, 0.0184, 0.0092]))
    with pytest.raises(ConfigError, match="1 or 4 ballistic coefficients"):
        parse_scenario(_with_drag([0.0092, 0.0092]))
    with pytest.raises(ConfigError, match=r"time_step_s <= 10"):
        parse_scenario(_with_drag([0.0092], time_step_s=20))
    with pytest.raises(ConfigError):
        parse_scenario(_with_drag([-0.1]))


def test_drag_run_decays_and_reports_its_model() -> None:
    raw = _with_drag([0.0092], duration_s=6000)
    raw["output"]["trajectory_sample_interval_s"] = 600
    cfg = parse_scenario(raw)
    assert isinstance(cfg, FormationScenarioBase)
    run = run_formation_dynamics(cfg, EventLog())
    assert run.trajectory.model_id == "D1-j2-rk4+drag-ussa76"
    plain = parse_scenario({**raw, "dynamics": {"model": "j2"}})
    assert isinstance(plain, FormationScenarioBase)
    ref = run_formation_dynamics(plain, EventLog())
    np.testing.assert_array_equal(run.trajectory.y[0], ref.trajectory.y[0])  # same start
    gravity = replace(run.trajectory.forces, drag=None)  # J2 energy, conserved without drag
    e = specific_energy(run.trajectory.y[-1], gravity)
    e_ref = specific_energy(ref.trajectory.y[-1], gravity)
    assert np.all(e < e_ref)  # drag removed energy from every spacecraft

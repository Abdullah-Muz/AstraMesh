"""``control.formation_keeping`` configuration (DL-087): hashes, validation, helpers."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from astramesh.control.formation_keeping import (
    Command,
    KeepingResult,
    control_interval_steps,
)
from astramesh.core.config import ConfigError, MissionScenarioBase, parse_scenario
from astramesh.dynamics.constants import GM_EARTH_M3PS2, R_EARTH_EQ_M

EXPERIMENTS = Path(__file__).parents[2] / "configs" / "experiments"


def _raw(name: str = "mission_geometry_24h.yaml") -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((EXPERIMENTS / name).read_text())
    return raw


def _with_control(**fk: float) -> dict[str, Any]:
    raw = copy.deepcopy(_raw())
    raw["control"] = {"formation_keeping": dict(fk)}
    return raw


def test_absent_control_leaves_the_hash_unchanged() -> None:
    plain = parse_scenario(_raw())
    explicit = copy.deepcopy(_raw())
    explicit["control"] = None
    assert parse_scenario(explicit).config_hash() == plain.config_hash()
    assert parse_scenario(_with_control()).config_hash() != plain.config_hash()
    assert "control" not in plain.canonical_dict()


def test_defaults_are_the_dl087_values() -> None:
    cfg = parse_scenario(_with_control())
    assert isinstance(cfg, MissionScenarioBase)
    assert cfg.control is not None
    fk = cfg.control.formation_keeping
    assert (fk.deadband_km, fk.time_constant_s, fk.navigation_sigma_m) == (0.5, 86_400.0, 10.0)


def test_nominal_operations_accepts_control() -> None:
    raw = _raw("nominal_ops_b3_24h.yaml")
    raw["control"] = {"formation_keeping": {}}
    assert isinstance(parse_scenario(raw), MissionScenarioBase)


def test_control_validation() -> None:
    with pytest.raises(ConfigError):
        parse_scenario(_with_control(deadband_km=0.0))
    with pytest.raises(ConfigError):
        parse_scenario(_with_control(navigation_sigma_m=-1.0))
    with pytest.raises(ConfigError):
        parse_scenario(_with_control(gain=1.0))  # unknown keys are rejected
    single = _with_control()
    single["formation"]["n_spacecraft"] = 1
    with pytest.raises(ConfigError, match="at least two spacecraft"):
        parse_scenario(single)
    formation_only = _raw("formation_24h_j2.yaml")
    formation_only["control"] = {"formation_keeping": {}}
    with pytest.raises(ConfigError):  # needs the spacecraft (propulsion) section
        parse_scenario(formation_only)


def test_control_interval_is_one_nominal_orbit() -> None:
    # 525 km: T = 2 pi sqrt(a^3 / mu) = 5708 s -> 571 steps of 10 s
    assert control_interval_steps(525.0, GM_EARTH_M3PS2, R_EARTH_EQ_M, 10.0) == 571
    assert control_interval_steps(525.0, GM_EARTH_M3PS2, R_EARTH_EQ_M, 1e6) == 1


def test_keeping_summary_arithmetic() -> None:
    on = np.zeros((5, 2), dtype=np.bool_)
    on[1:4, 1] = True
    res = KeepingResult(
        ids=("sc00", "sc01"), step_s=10.0, thrust_on=on, delta_v_mps=(0.0, 0.00125),
        propellant_kg=(0.0, 2e-5), commands=(Command("sc01", "sc00", 0, 3, -600.0, 0.0, 0.0),),
        held=(0, 2),
    )  # fmt: skip
    sc01 = res.summary(thruster_power_w=2.0)["per_spacecraft"]["sc01"]
    assert sc01["thrust_s"] == 30.0
    assert sc01["thruster_energy_wh"] == pytest.approx(30.0 * 2.0 / 3600.0)
    assert (sc01["commands"], sc01["held_decisions"]) == (1, 2)

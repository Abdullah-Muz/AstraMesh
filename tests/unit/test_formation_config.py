"""Formation-dynamics scenario schema (PA-05: units explicit; invalid values rejected)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from astramesh.core.config import (
    ConfigError,
    FormationDynamicsScenario,
    MissionGeometryScenario,
    parse_scenario,
    scenario_json_schema,
)

UNIT_SUFFIXES = ("_s", "_ns", "_m", "_km", "_mps", "_kg", "_w", "_wh", "_j", "_n", "_mn",
                 "_rad", "_deg", "_mb", "_gb", "_probability", "_fraction", "_kbps")  # fmt: skip
# Non-physical (dimensionless, identifiers, or explicitly unit-less) fields.
UNITLESS_OK = {"schema_version", "seed", "n_spacecraft", "n_nodes", "priority",
               "health_recover_messages"}  # fmt: skip


def _with(base: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    node = cfg
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[key]
    node[leaf] = value
    return cfg


def test_baseline_config_is_valid(formation_config_dict: dict[str, Any]) -> None:
    cfg = parse_scenario(formation_config_dict)
    assert isinstance(cfg, FormationDynamicsScenario)
    assert cfg.time.clock_spec().n_steps == 8640
    assert cfg.dynamics.model == "j2"


def test_pa05_every_numeric_field_carries_a_unit_suffix() -> None:
    schema = scenario_json_schema()
    offenders = []
    for name, model in schema["$defs"].items():
        for field, spec in model.get("properties", {}).items():
            types = {spec.get("type")} | {s.get("type") for s in spec.get("anyOf", [])}
            numeric = bool(types & {"number", "integer"})
            if numeric and field not in UNITLESS_OK and not field.endswith(UNIT_SUFFIXES):
                offenders.append(f"{name}.{field}")
    assert not offenders, offenders


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("dynamics.model", "j3"),
        ("reference_orbit.mean_altitude_km", 100),  # below the supported LEO range
        ("reference_orbit.mean_altitude_km", float("nan")),
        ("reference_orbit.mean_inclination_deg", 181),
        ("reference_orbit.raan_deg", 360),
        ("formation.n_spacecraft", 0),
        ("formation.along_track_spacing_km", 0),
        ("output.trajectory_sample_interval_s", 15),  # not a multiple of the 10 s step
        ("output.trajectory_sample_interval_s", 70),  # 86400 s not a multiple of 70 s
    ],
)
def test_invalid_values_rejected(
    formation_config_dict: dict[str, Any], path: str, value: Any
) -> None:
    with pytest.raises(ConfigError):
        parse_scenario(_with(formation_config_dict, path, value))


def test_unknown_and_unitless_keys_rejected(formation_config_dict: dict[str, Any]) -> None:
    with pytest.raises(ConfigError, match="Extra inputs"):
        parse_scenario(_with(formation_config_dict, "reference_orbit.altitude", 525))
    bad = copy.deepcopy(formation_config_dict)
    bad["toy_heartbeat"] = {"n_nodes": 2}
    with pytest.raises(ConfigError, match="Extra inputs"):
        parse_scenario(bad)


def test_mission_geometry_config_is_valid(mission_config_dict: dict[str, Any]) -> None:
    cfg = parse_scenario(mission_config_dict)
    assert isinstance(cfg, MissionGeometryScenario)
    assert len(cfg.science.regions) == 16
    assert cfg.science.min_elevation_deg == 20.0


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("science.min_elevation_deg", 90.0),
        ("science.min_elevation_deg", -1.0),
        ("science.regions", []),
        ("science.unknown_key", 1),
    ],
)
def test_mission_geometry_rejects_invalid_science(
    mission_config_dict: dict[str, Any], path: str, value: Any
) -> None:
    with pytest.raises(ConfigError):
        parse_scenario(_with(mission_config_dict, path, value))


@pytest.mark.parametrize(
    ("field", "value"),
    [("latitude_deg", 90.5), ("longitude_deg", 181.0), ("priority", 0), ("priority", 6),
     ("region_id", "bad id")],
)  # fmt: skip
def test_mission_geometry_rejects_invalid_region(
    mission_config_dict: dict[str, Any], field: str, value: Any
) -> None:
    cfg = copy.deepcopy(mission_config_dict)
    cfg["science"]["regions"][0][field] = value
    with pytest.raises(ConfigError):
        parse_scenario(cfg)


def test_mission_geometry_rejects_duplicate_region_ids(
    mission_config_dict: dict[str, Any],
) -> None:
    cfg = copy.deepcopy(mission_config_dict)
    cfg["science"]["regions"][1]["region_id"] = cfg["science"]["regions"][0]["region_id"]
    with pytest.raises(ConfigError, match="unique"):
        parse_scenario(cfg)


@pytest.mark.parametrize(
    ("field", "value"),
    [("mass_kg", 0.0), ("battery_initial_fraction", 1.2), ("charge_efficiency_fraction", 0.0),
     ("bus_power_w", -1.0), ("specific_impulse_s", 0.0), ("delta_v_budget_mps", -0.1)],
)  # fmt: skip
def test_mission_geometry_rejects_invalid_spacecraft(
    mission_config_dict: dict[str, Any], field: str, value: float
) -> None:
    with pytest.raises(ConfigError):
        parse_scenario(_with(mission_config_dict, f"spacecraft.{field}", value))


def test_mission_geometry_requires_spacecraft(mission_config_dict: dict[str, Any]) -> None:
    cfg = copy.deepcopy(mission_config_dict)
    del cfg["spacecraft"]
    with pytest.raises(ConfigError, match="spacecraft"):
        parse_scenario(cfg)

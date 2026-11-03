from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from astramesh.core.config import ConfigError, load_scenario, parse_scenario, scenario_json_schema


def test_toy_config_is_valid(toy_config_path: Path) -> None:
    config = load_scenario(toy_config_path)
    assert config.scenario_id == "TOY_HEARTBEAT"
    assert config.time.clock_spec().n_steps == 60


def _with(base: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    node = cfg
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[key]
    node[leaf] = value
    return cfg


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("schema_version", 2),
        ("scenario_id", "bad id with spaces"),
        ("scenario_type", "unknown"),
        ("time.duration_s", -10),
        ("time.time_step_s", 0),
        ("time.duration_s", 605),  # not a multiple of the 10 s step
        ("time.epoch_utc", "2025-06-01T00:00:00"),  # naive: no UTC designator
        ("time.epoch_utc", "2025-06-01T00:00:00+03:00"),  # not UTC
        ("random.seed", -1),
        ("random.seed", "1"),  # strings are not silently coerced to seeds
        ("random.seed", 1.5),
        ("random.stream_seeds", {"weather": 3}),
        ("toy_heartbeat.packet_loss_probability", 1.5),
        ("toy_heartbeat.n_nodes", 1),
        ("toy_heartbeat.heartbeat_interval_s", 15),  # not a multiple of the 10 s step
    ],
)
def test_invalid_values_rejected(toy_config_dict: dict[str, Any], path: str, value: Any) -> None:
    with pytest.raises(ConfigError):
        parse_scenario(_with(toy_config_dict, path, value))


def test_unknown_keys_rejected(toy_config_dict: dict[str, Any]) -> None:
    with pytest.raises(ConfigError, match="Extra inputs"):
        parse_scenario(_with(toy_config_dict, "time.duraton_s", 600))


def test_hash_ignores_formatting_but_tracks_values(toy_config_dict: dict[str, Any]) -> None:
    base = parse_scenario(toy_config_dict).config_hash()
    reordered = dict(reversed(list(copy.deepcopy(toy_config_dict).items())))
    assert parse_scenario(reordered).config_hash() == base
    int_vs_float = _with(toy_config_dict, "time.duration_s", 600.0)
    assert parse_scenario(int_vs_float).config_hash() == base
    changed = _with(toy_config_dict, "random.seed", 2)
    assert parse_scenario(changed).config_hash() != base


@given(seed=st.integers(0, 2**63 - 1))
def test_hash_is_injective_on_seed(seed: int) -> None:
    base: dict[str, Any] = {
        "schema_version": 1,
        "scenario_id": "T",
        "description": "d",
        "scenario_type": "toy_heartbeat",
        "time": {"epoch_utc": "2025-06-01T00:00:00Z", "duration_s": 60, "time_step_s": 10},
        "random": {"seed": seed},
        "toy_heartbeat": {"n_nodes": 2, "heartbeat_interval_s": 10, "packet_loss_probability": 0},
    }
    other = _with(base, "random.seed", seed + 1 if seed < 2**63 - 1 else seed - 1)
    assert parse_scenario(base).config_hash() != parse_scenario(other).config_hash()


def test_load_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_scenario(path)


def test_load_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_scenario(tmp_path / "missing.yaml")


def test_json_schema_exports() -> None:
    schema = scenario_json_schema()
    assert schema["title"] == "ScenarioConfig"
    assert set(schema["discriminator"]["mapping"]) == {"toy_heartbeat", "formation_dynamics"}
    for name in ("ToyHeartbeatScenario", "FormationDynamicsScenario"):
        assert "time" in schema["$defs"][name]["properties"]

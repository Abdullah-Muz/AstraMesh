"""Agent-network scenario end to end: replay, conservation of message counts, rejections."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from astramesh.core.config import AgentNetworkScenario, ConfigError, parse_scenario
from astramesh.evaluation.runner import EVENTS_FILE, MANIFEST_FILE, SUMMARY_FILE, run_config
from astramesh.scenarios.agent_network import MESSAGES_FILE


def _cfg(base: dict[str, Any], **net: float) -> AgentNetworkScenario:
    cfg = copy.deepcopy(base)
    cfg["time"]["duration_s"] = 2 * 3600
    cfg["network"].update(net)
    parsed = parse_scenario(cfg)
    assert isinstance(parsed, AgentNetworkScenario)
    return parsed


def test_replay_is_byte_identical(network_config_dict: dict[str, Any], tmp_path: Path) -> None:
    cfg = _cfg(network_config_dict, duplicate_probability=0.05)
    run_config(cfg, tmp_path / "a")
    run_config(cfg, tmp_path / "b")
    for name in (EVENTS_FILE, SUMMARY_FILE, MESSAGES_FILE):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name
    manifest = json.loads((tmp_path / "a" / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert MESSAGES_FILE in {a["path"] for a in manifest["artifacts"]}
    assert manifest["stream_seeds"]["comms"] == 1


def test_counts_are_conserved_and_duplicates_rejected(
    network_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    run_config(_cfg(network_config_dict, duplicate_probability=0.05, loss_probability=0.1),
               tmp_path / "r")  # fmt: skip
    s = json.loads((tmp_path / "r" / SUMMARY_FILE).read_text(encoding="utf-8"))
    n = s["network"]
    assert n["unreachable"] == 0  # 20-60 km in-train spacing, 100 km range
    assert n["sent"] * 3 == n["linked"]
    assert (
        n["linked"] - n["lost"] + n["duplicates_injected"] == n["delivered"] + n["in_flight_at_end"]
    )
    assert s["rejected_total"]["duplicate"] == n["duplicates_injected"]
    other = {k: v for k, v in s["rejected_total"].items() if k != "duplicate"}
    assert set(other.values()) == {0}
    accepted = sum(a["accepted"] for a in s["agents"].values())
    assert accepted == n["delivered"] - n["duplicates_injected"]
    assert all(a["plan_version"] == 0 for a in s["agents"].values())
    trace = [json.loads(x) for x in (tmp_path / "r" / MESSAGES_FILE).read_text().splitlines()]
    times = [e["t_ns"] for e in trace]
    assert times == sorted(times)


def test_short_range_partitions_the_formation(
    network_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    """With a 15 km range nobody is linked (spacing 20 km): everything is unreachable."""
    run_config(_cfg(network_config_dict, crosslink_range_km=15), tmp_path / "r")
    n = json.loads((tmp_path / "r" / SUMMARY_FILE).read_text(encoding="utf-8"))["network"]
    assert n["delivered"] == 0
    assert n["unreachable"] == 3 * n["sent"]
    assert n["fully_connected_epochs"] == 0


@pytest.mark.parametrize(
    ("path", "value"),
    [("network.loss_probability", 1.5), ("agents.status_interval_s", 15),
     ("agents.nav_fix_interval_s", 0), ("network.delay_s", 1e-10)],
)  # fmt: skip
def test_invalid_network_config(network_config_dict: dict[str, Any], path: str, value: Any) -> None:
    cfg = copy.deepcopy(network_config_dict)
    sec, key = path.split(".")
    cfg[sec][key] = value
    with pytest.raises(ConfigError):
        parse_scenario(cfg)

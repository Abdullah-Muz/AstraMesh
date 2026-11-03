"""Formation-dynamics scenario end to end: run, replay, artifacts, plots (Gate P1)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from astramesh.core.config import FormationDynamicsScenario, parse_scenario
from astramesh.evaluation.runner import (
    EVENTS_FILE,
    MANIFEST_FILE,
    RESOLVED_CONFIG_FILE,
    SUMMARY_FILE,
    run_config,
)
from astramesh.scenarios.formation_dynamics import TRAJECTORY_FILE
from astramesh.visualization.formation_plots import FIGURE_FILES, load_trajectory, plot_run

DETERMINISTIC = (EVENTS_FILE, SUMMARY_FILE, RESOLVED_CONFIG_FILE, TRAJECTORY_FILE)


def _short(base: dict[str, Any], model: str = "j2") -> FormationDynamicsScenario:
    cfg = copy.deepcopy(base)
    cfg["time"]["duration_s"] = 7200
    cfg["dynamics"]["model"] = model
    parsed = parse_scenario(cfg)
    assert isinstance(parsed, FormationDynamicsScenario)
    return parsed


def test_replay_is_byte_identical(formation_config_dict: dict[str, Any], tmp_path: Path) -> None:
    cfg = _short(formation_config_dict)
    run_config(cfg, tmp_path / "a")
    run_config(cfg, tmp_path / "b")
    for name in DETERMINISTIC:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_manifest_lists_all_artifacts_and_model(
    formation_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    result = run_config(_short(formation_config_dict), tmp_path / "r")
    manifest = json.loads((tmp_path / "r" / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["dynamics_model"] == "D1-j2-rk4"
    assert {a["path"] for a in manifest["artifacts"]} == set(DETERMINISTIC)
    assert "astropy-iers-data" in manifest["software"]["packages"]
    summary = json.loads((tmp_path / "r" / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert len(summary["pole_gcrs"]) == 3
    assert result.n_events == 1 + 4 + 1  # start, 4 initial orbits, end


def test_two_body_model_runs(formation_config_dict: dict[str, Any], tmp_path: Path) -> None:
    run_config(_short(formation_config_dict, "two_body"), tmp_path / "r")
    summary = json.loads((tmp_path / "r" / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["dynamics_model"] == "D0-two-body-rk4"
    sep = summary["adjacent_separation_km"]
    assert sep["max"] - sep["min"] < 1e-6  # two-body: rigid in-train formation


def test_trajectory_file_and_plots(formation_config_dict: dict[str, Any], tmp_path: Path) -> None:
    run_config(_short(formation_config_dict), tmp_path / "r")
    t_ns, ids, _ = load_trajectory(tmp_path / "r")
    assert ids == ["sc00", "sc01", "sc02", "sc03"]
    assert len(t_ns) == 7200 // 60 + 1
    assert t_ns[-1] == 7200 * 10**9  # final state recorded
    written = plot_run(tmp_path / "r")
    assert sorted(p.name for p in written) == sorted(FIGURE_FILES)
    assert all(p.stat().st_size > 1000 for p in written)

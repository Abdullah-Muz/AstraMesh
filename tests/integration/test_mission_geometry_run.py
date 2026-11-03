"""Mission-geometry scenario end to end: run, replay, artifacts, events, plots."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from astramesh.core.config import MissionGeometryScenario, parse_scenario
from astramesh.evaluation.runner import EVENTS_FILE, MANIFEST_FILE, SUMMARY_FILE, run_config
from astramesh.scenarios.mission_geometry import OPPORTUNITIES_FILE
from astramesh.visualization.formation_plots import FIGURE_FILES, OPPORTUNITY_FIGURE, plot_run


def _short(base: dict[str, Any]) -> MissionGeometryScenario:
    cfg = copy.deepcopy(base)
    cfg["time"]["duration_s"] = 4 * 3600
    parsed = parse_scenario(cfg)
    assert isinstance(parsed, MissionGeometryScenario)
    return parsed


def test_mission_geometry_run_replays_and_records(
    mission_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    cfg = _short(mission_config_dict)
    run_config(cfg, tmp_path / "a")
    run_config(cfg, tmp_path / "b")
    for name in (EVENTS_FILE, SUMMARY_FILE, OPPORTUNITIES_FILE):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name
    manifest = json.loads((tmp_path / "a" / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert OPPORTUNITIES_FILE in {a["path"] for a in manifest["artifacts"]}
    records = json.loads((tmp_path / "a" / OPPORTUNITIES_FILE).read_text(encoding="ascii"))
    events = [json.loads(x) for x in (tmp_path / "a" / EVENTS_FILE).read_text().splitlines()]
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "scenario_start"
    assert kinds[-1] == "scenario_end"
    assert kinds.count("opportunity_open") == kinds.count("opportunity_close") == len(records)
    assert "eclipse_entry" in kinds
    times = [e["t_ns"] for e in events]
    assert times == sorted(times)
    summary = json.loads((tmp_path / "a" / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["science"]["n_opportunities"] == len(records) > 0
    assert 0.0 < summary["illumination"]["eclipse_fraction"]["sc00"] < 0.5
    res = summary["resources"]
    assert res["energy_payload_all_eligible"]["sc00"]["deficit_wh"] == 0.0
    assert res["propulsion"]["delta_v_used_mps"] == 0.0
    assert all(r["payload_energy_wh"] > 0 and r["storage_mb"] > 0 for r in records)


def test_mission_geometry_plots(mission_config_dict: dict[str, Any], tmp_path: Path) -> None:
    run_config(_short(mission_config_dict), tmp_path / "r")
    written = plot_run(tmp_path / "r")
    assert sorted(p.name for p in written) == sorted([*FIGURE_FILES, OPPORTUNITY_FIGURE])

"""Increment 5 scripts (DL-106): ablation study, spread formation and storm diagnostics.
Baselines identical to the recorded runs; each arm changes only its named setting."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from astramesh.core.config import NominalOperationsScenario, parse_scenario

ROOT = Path(__file__).resolve().parents[2]


def _mod(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/experiments/{name}.py")
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _parse(raw: dict[str, Any]) -> NominalOperationsScenario:
    cfg = parse_scenario(raw)
    assert isinstance(cfg, NominalOperationsScenario)
    return cfg


def _dump(raw: dict[str, Any]) -> dict[str, Any]:
    d = _parse(raw).model_dump(mode="json")
    d.pop("scenario_id")
    return d


def test_ablation_baselines_are_the_recorded_runs() -> None:
    m = _mod("ablation_study")
    ms = json.loads((ROOT / "docs/results/multi_storm_meta.json").read_text())["config_hashes"]
    ho = json.loads((ROOT / "docs/results/handover_meta.json").read_text())["config_hashes"]
    for storm in m.STORMS:
        for planner in m.PLANNERS:
            for arm in ("baseline", "quiet"):
                for seed in m.SEEDS:
                    got = _parse(m.config(storm, planner, arm, seed)).config_hash()
                    if storm == m.MAY:
                        assert got == ho[f"S11-H/P-B/{planner}/{arm}/{seed}"]
                    else:
                        assert got == ms[f"{storm}/{planner}/{arm}/seed{seed}"]


@pytest.mark.parametrize("storm", ["jul18_2023", "may2024"])
def test_each_ablation_changes_only_its_setting(storm: str) -> None:
    m = _mod("ablation_study")
    base = m.config(storm, "rule_b4", "baseline", 1)
    for arm in m.ABLATIONS:
        raw = m.config(storm, "rule_b4", arm, 1)
        expect = copy.deepcopy(base)
        replay = expect["environment"]["replay"]
        if arm == "no_lookahead":
            replay["access"] = {**replay["access"], "horizon_s": 10.0}
        elif arm == "no_forecast":
            replay["forecast"] = "P-A"
        else:
            expect.setdefault("supervisor", {}).update(
                release_exposure_ratio=0.99, release_dwell_s=0.0, watch_release_dwell_s=0.0,
                recovery_min_dwell_s=0.0)  # fmt: skip
        assert _dump(raw) == _dump(expect)
        assert _dump(raw) != _dump(base)
    b0 = _dump(m.config(storm, m.B0, "baseline", 1))
    b4 = _dump(base)
    assert b0["operations"].pop("algorithm") == "static_b0"
    assert b4["operations"].pop("algorithm") == "rule_b4"
    assert b0 == b4


def test_ablation_arguments_and_job_order() -> None:
    m = _mod("ablation_study")
    with pytest.raises(ValueError, match="unknown arm"):
        m.config("jul18_2023", "rule_b4", "no_planner", 1)
    with pytest.raises(ValueError, match="B0"):
        m.config("jul18_2023", m.B0, "no_forecast", 1)
    jobs = m.jobs()
    assert len(jobs) == len(set(jobs)) == 180
    first_b3 = next(i for i, j in enumerate(jobs) if j[1] == "cbba_b3_timeout")
    assert all(j[1] == "cbba_b3_timeout" for j in jobs[first_b3:])
    assert jobs[first_b3][2] == "no_hysteresis"


def test_ablation_summary_on_synthetic_rows() -> None:
    m = _mod("ablation_study")
    rows = []
    for st in m.STORMS:
        for pl in (*m.PLANNERS, m.B0):
            arms = ("baseline", "quiet") if pl == m.B0 else m.ARMS
            for arm in arms:
                for s in m.SEEDS:
                    u = {"quiet": 1000, "no_lookahead": 950}.get(arm, 900)
                    rows.append({"storm": st, "planner": pl, "arm": arm, "seed": s, "utility": u,
                                 "unprotected_hazard_s": json.dumps({"sc00": 60.0 if arm ==
                                                                     "no_lookahead" else 0.0}),
                                 "protected_s": json.dumps({"sc00": 3600.0}),
                                 "protective_entries": json.dumps({"sc00": 2})})  # fmt: skip
    out = m.summarize(rows)
    pooled = {(r["planner"], r["ablation"]): r for r in out if r["scope"] == "pooled over storms"}
    assert len(pooled) == 2 * 4
    assert pooled[("rule_b4", "no_lookahead")]["mean"] == pytest.approx(0.05)
    assert pooled[("rule_b4", "no_lookahead")]["max_extra_unprotected_s"] == 60.0
    assert pooled[("rule_b4", "no_reconciliation")]["mean"] == 0.0


def test_spread_configs() -> None:
    m = _mod("spread_formation")
    ms = json.loads((ROOT / "docs/results/multi_storm_meta.json").read_text())["config_hashes"]
    for sp in m.SPACINGS_KM:
        for arm in m.ARMS:
            cfg = _parse(m.config(sp, arm, 1))
            assert cfg.formation.along_track_spacing_km == sp
            assert cfg.network.crosslink_range_km == m.LINK_RANGE_KM
    # the 20 km baseline is the recorded DL-100 run apart from the crosslink range
    raw = m.config(20.0, "baseline", 1)
    raw["network"]["crosslink_range_km"] = 100.0
    rec = _mod("multi_storm_comparison").config(m.STORM, m.PLANNER, "baseline", 1)
    assert _dump(raw) == _dump(rec)
    assert _parse(rec).config_hash() == ms[f"{m.STORM}/{m.PLANNER}/baseline/seed1"]
    short = _parse(m.config(5000.0, "shorter", 1))
    assert short.supervisor.release_dwell_s == 600.0
    with pytest.raises(ValueError, match="unknown arm"):
        m.config(20.0, "candidate", 1)


def test_non_tasking_mask_and_all_out() -> None:
    m = _mod("spread_formation")
    tr = [{"t_s": 20.0, "from": "NOMINAL", "to": "STORM_WATCH"},
          {"t_s": 30.0, "from": "STORM_WATCH", "to": "PROTECTIVE"},
          {"t_s": 60.0, "from": "PROTECTIVE", "to": "RECOVERY"},
          {"t_s": 80.0, "from": "RECOVERY", "to": "NOMINAL"}]  # fmt: skip
    grid = np.arange(0.0, 100.0, 10.0)
    got = m.non_tasking_mask(tr, grid)
    assert got.tolist() == [False, False, False, True, True, True, True, True, False, False]
    assert not m.non_tasking_mask([], grid).any()


def test_diagnostic_helpers() -> None:
    m = _mod("storm_diagnostics")
    nt = {"sc00": [True] * 5 + [False] * 5, "sc01": [True] * 10}
    assert m.classify([("sc00", 5, 9), ("sc01", 5, 9)], nt) == m.CLASSES[0]
    assert m.classify([("sc00", 3, 7)], nt) == m.CLASSES[1]
    assert m.classify([("sc01", 0, 9)], nt) == m.CLASSES[2]
    tr = [{"t_s": 0.0, "from": "STORM_WATCH", "to": "PROTECTIVE", "reason": "radiation>=1.0"},
          {"t_s": 1200.0, "from": "PROTECTIVE", "to": "RECOVERY", "reason": "x"},
          {"t_s": 1500.0, "from": "RECOVERY", "to": "PROTECTIVE", "reason": "radiation>=1.0"},
          {"t_s": 2400.0, "from": "PROTECTIVE", "to": "RECOVERY", "reason": "x"},
          {"t_s": 3000.0, "from": "RECOVERY", "to": "NOMINAL", "reason": "x"}]  # fmt: skip
    sp = m.spans(tr)
    assert sp["n_spans"] == 1
    assert sp["max_min"] == 50.0
    assert sp["entry_reasons"] == {"radiation>=1.0": 2}
    quiet = {"completed": ["a", "b", "c"]}
    arm = {"completed": ["a"], "windows": {"b": [("sc00", 0, 4)], "c": [("sc00", 5, 9)]},
           "non_tasking": nt}  # fmt: skip
    lt = m.lost_tasks(quiet, arm)
    assert lt["n_lost"] == 2
    assert lt["classes"] == {m.CLASSES[0]: 1, m.CLASSES[1]: 0, m.CLASSES[2]: 1}

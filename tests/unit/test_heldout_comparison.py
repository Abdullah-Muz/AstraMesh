"""Phase 6 held-out comparison (DL-113): arms equal their Phase 5 definitions, test-storm
series are pinned and disjoint, the reserve has no files, and the expectation rules."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from astramesh.core.config import NominalOperationsScenario, parse_scenario
from astramesh.forecast.replay import StormSeries

ROOT = Path(__file__).resolve().parents[2]
DAY_NS = 86_400 * 10**9
S11_END_NS = int(np.datetime64("2024-05-16", "ns").astype(np.int64))


def _mod(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/experiments/{name}.py")
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _dump(raw: dict[str, Any]) -> dict[str, Any]:
    cfg = parse_scenario(raw)
    assert isinstance(cfg, NominalOperationsScenario)
    d = cfg.model_dump(mode="json")
    d.pop("scenario_id")
    return d


@pytest.mark.parametrize("planner", ["cbba_b3_timeout", "rule_b4", "static_b0"])
def test_arms_equal_their_phase5_definitions(planner: str) -> None:
    m, ms = _mod("heldout_comparison"), _mod("multi_storm_comparison")
    storm = "mar23_2024"
    path, epoch = ms.series(storm), ms.STORMS[storm]
    for arm in ("baseline", "quiet"):
        got = m.raw_config(path, epoch, planner, arm, 2)
        assert _dump(got) == _dump(ms.config(storm, planner, arm, 2))
    if planner == "static_b0":
        return
    base = m.raw_config(path, epoch, planner, "baseline", 2)
    pc, ab = _mod("protection_comparison"), _mod("ablation_study")
    expect = {"handover": ms.config(storm, planner, "candidate", 2),
              "shorter": pc.config(storm, planner, "candidate", 2),
              **{a: ab.config(storm, planner, a, 2) for a in m.ABLATIONS}}  # fmt: skip
    for arm, ref in expect.items():
        got = m.arm_config(copy.deepcopy(base), arm)
        assert _dump(got) == _dump(ref), arm
        assert _dump(got) != _dump(base)


def test_test_storm_series_are_pinned_disjoint_and_after_may_2024() -> None:
    m = _mod("heldout_comparison")
    sel = json.loads(m.SELECTION.read_text())
    storms = m.held_out_storms()
    assert len(storms) == len(sel["test_storms"]) >= 6
    spans = []
    for name, s in storms.items():
        path = ROOT / s["series_file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == s["series_sha256"]
        series = StormSeries.load(s["series_file"], s["series_sha256"])
        assert len(series.truth_pfu) == 8 * 288
        assert series.start_ns == int(np.datetime64(s["window_start_utc"], "ns").astype(np.int64))
        assert max(v for v in series.truth_pfu if v == v) >= 100.0
        raw = m.config(name, "rule_b4", "baseline", 1)
        assert raw["environment"]["replay"]["series_sha256"] == s["series_sha256"]
        assert raw["time"]["epoch_utc"] == s["epoch_utc"]
        spans.append(series.start_ns)
    spans.sort()
    assert spans[0] >= S11_END_NS
    assert all(b - a >= 8 * DAY_NS for a, b in itertools.pairwise(spans))
    for day in sel["reserved_window_starts_utc"]:
        assert not (ROOT / f"configs/data/heldout_{day.replace('-', '')}_series.json").exists()
        assert day not in {s["window_start_utc"] for s in storms.values()}
    assert len(sel["reserved_window_starts_utc"]) == sel["n_qualifying"] // 3


def test_arguments_and_jobs() -> None:
    m = _mod("heldout_comparison")
    name = sorted(m.held_out_storms())[0]
    with pytest.raises(ValueError, match="unknown arm"):
        m.config(name, "rule_b4", "no_planner", 1)
    with pytest.raises(ValueError, match="B0"):
        m.config(name, m.B0, "shorter", 1)
    jobs = m.jobs(sorted(m.held_out_storms()))
    n = len(m.held_out_storms())
    assert len(jobs) == len(set(jobs)) == n * 3 * (7 + 7 + 2)
    first_b3 = next(i for i, j in enumerate(jobs) if j[1] == "cbba_b3_timeout")
    assert all(j[1] == "cbba_b3_timeout" for j in jobs[first_b3:])


def _rows(m: ModuleType, storms: list[str], util: dict[str, float],
          extra: dict[str, float]) -> list[dict[str, Any]]:  # fmt: skip
    rows = []
    for st in storms:
        for pl in (*m.PLANNERS, m.B0):
            for arm in ("baseline", "quiet") if pl == m.B0 else m.ARMS:
                key = "no_reconciliation" if pl == m.B0 and arm == "baseline" else arm
                for s in m.SEEDS:
                    u = 1000.0 if arm == "quiet" else 900.0 + util.get(key, 0.0)
                    rows.append({"storm": st, "planner": pl, "arm": arm, "seed": s,
                                 "utility": u, "utility_dup_charged": u,
                                 "unprotected_hazard_s": json.dumps({"sc00": extra.get(key, 0.0)}),
                                 "protected_s": json.dumps({"sc00": 3600.0}),
                                 "protective_entries": json.dumps({"sc00": 2})})  # fmt: skip
    return rows


def test_summary_and_expectation_rules_on_synthetic_rows() -> None:
    m = _mod("heldout_comparison")
    storms = ["a", "b", "c", "d"]
    proc = {"a": "v3-0-2", "b": "v3-0-2", "c": "v3-0-2", "d": "v3-0-3"}
    rows = _rows(
        m,
        storms,
        {"no_reconciliation": -50.0, "no_lookahead": 5.0},
        {"no_lookahead": 60.0, "no_forecast": 30.0},
    )
    summary = m.summarize(rows, proc)
    pooled = {(r["scope"], r["planner"], r["compared"]): r for r in summary
              if r["scope"].startswith("pooled")}  # fmt: skip
    p = pooled[("pooled: all test storms", "rule_b4", "no_lookahead")]
    assert p["mean"] == pytest.approx(0.005)
    assert p["storms_with_extra_unprotected"] == 4
    one = pooled[("pooled: v3-0-3", "rule_b4", "no_lookahead")]
    assert one["n"] == 1
    assert one["ci_lo"] is None
    exp = m.expectations(summary, rows)
    assert exp["E1_handover_no_reliable_gain"]["held"]
    assert exp["E2_shorter_no_reliable_gain"]["held"]
    assert exp["E3_reconciliation_costs_science"]["held"]
    assert exp["E4_ablations_add_hazard_on_most_storms"]["held"] == {
        "no_lookahead": True,
        "no_forecast": True,
        "no_hysteresis": False,
    }
    assert exp["E5_seeds_change_no_outcome"]["held"]
    rows[0]["utility"] += 1  # one seed of one group differs
    assert not m.expectations(summary, rows)["E5_seeds_change_no_outcome"]["held"]


def test_e1_not_held_when_a_gain_is_reliable() -> None:
    m = _mod("heldout_comparison")
    storms = ["a", "b", "c"]
    rows = _rows(m, storms, {"handover": 3.0}, {})
    rows = [r if not (r["storm"] == "c" and r["arm"] == "handover")
            else {**r, "utility": r["utility"] + 1} for r in rows]  # fmt: skip
    summary = m.summarize(rows, dict.fromkeys(storms, "v3-0-2"))
    exp = m.expectations(summary, rows)
    assert not exp["E1_handover_no_reliable_gain"]["held"]

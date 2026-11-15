"""Negative-result diagnostics (DL-119, DL-120): every run reuses a recorded configuration,
the latency variants change only the latency, and the interval, span and owner-view helpers
on synthetic data."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from astramesh.core.config import parse_scenario
from astramesh.forecast.replay import StormSeries

ROOT = Path(__file__).resolve().parents[2]
TASKING = ("NOMINAL", "STORM_WATCH")


def _mod() -> ModuleType:
    path = ROOT / "scripts/experiments/negative_results.py"
    spec = importlib.util.spec_from_file_location("negative_results", path)
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _recorded(name: str) -> dict[str, str]:
    out: dict[str, str] = json.loads((ROOT / f"docs/results/{name}").read_text())["config_hashes"]
    return out


def test_jobs_reuse_recorded_configurations(tmp_path: Path) -> None:
    m = _mod()
    jobs = m.jobs()
    assert len(jobs) == len(set(jobs)) == 34 + 42 + 4 + 16
    abl, prot = _recorded("ablation_meta.json"), _recorded("protection_meta.json")
    multi, ho = _recorded("multi_storm_meta.json"), _recorded("handover_meta.json")
    held, spread = _recorded("heldout_meta.json"), _recorded("spread_meta.json")
    n = 0
    for job in jobs:
        group, storm, arm = job
        if group == "latency":
            continue
        got = parse_scenario(m.config(job, tmp_path)).config_hash()
        if group == "phase5" and arm == "shorter":
            want = prot[f"{storm}/rule_b4/candidate/seed1"]
        elif group == "phase5" and arm == "handover":
            want = (ho["S11-H/P-B/rule_b4/candidate/1"] if storm == m.MAY
                    else multi[f"{storm}/rule_b4/candidate/seed1"])  # fmt: skip
        elif group == "phase5":
            want = abl[f"{storm}/rule_b4/{arm}/seed1"]
        elif group == "heldout":
            want = held[f"{storm}/rule_b4/{arm}/seed1"]
        else:
            want = spread[f"{storm}/{arm}/seed1"]
        assert got == want, job
        n += 1
    assert n == 80


def test_latency_variants_change_only_the_latency(tmp_path: Path) -> None:
    m = _mod()
    raw = m.config(("latency", "20240606", "300s"), tmp_path)
    rp = raw["environment"]["replay"]
    path, sha300 = Path(rp["series_file"]), rp["series_sha256"]
    assert path.parent == tmp_path
    assert hashlib.sha256(path.read_bytes()).hexdigest() == rp["series_sha256"]
    pinned = json.loads((ROOT / "configs/data/heldout_20240606_series.json").read_text())
    variant = json.loads(path.read_text())
    assert variant.pop("latency_s") == 300
    assert pinned.pop("latency_s") == 600
    assert variant == pinned
    series = StormSeries.load(rp["series_file"], rp["series_sha256"])
    assert series.latency_ns == 300 * 10**9
    base = m.config(("heldout", "20240606", "baseline"), tmp_path)
    del raw["environment"]["replay"]["series_file"], raw["environment"]["replay"]["series_sha256"]
    del base["environment"]["replay"]["series_file"], base["environment"]["replay"]["series_sha256"]
    raw.pop("scenario_id")
    base.pop("scenario_id")
    assert raw == base
    _, sha0 = m.variant_series("jul18_2023", 0, tmp_path)
    assert sha0 != sha300


def test_runs_and_mode_masks() -> None:
    m = _mod()
    assert m.runs_of(np.array([0, 1, 1, 0, 1], dtype=bool)) == [(1, 3), (4, 5)]
    assert m.runs_of(np.zeros(3, dtype=bool)) == []
    tr = [{"t_s": 20.0, "from": "NOMINAL", "to": "PROTECTIVE"},
          {"t_s": 40.0, "from": "PROTECTIVE", "to": "RECOVERY"},
          {"t_s": 60.0, "from": "RECOVERY", "to": "NOMINAL"}]  # fmt: skip
    t = np.arange(0.0, 80.0, 10.0)
    prot = m.mode_mask(tr, t, ("PROTECTIVE", "RECOVERY"))
    np.testing.assert_array_equal(prot, [0, 0, 1, 1, 1, 1, 0, 0])
    np.testing.assert_array_equal(m.mode_mask(tr, t, TASKING), ~prot)
    np.testing.assert_array_equal(m.mode_mask([], t, TASKING), np.ones(8, dtype=bool))


def test_unprotected_intervals_are_placed_in_their_episode() -> None:
    m = _mod()
    hazard = np.array([0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0], dtype=bool)
    prot = np.array([0, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0], dtype=bool)
    unp = hazard & ~prot
    placed = m.place(hazard, prot, unp)
    assert [(x["start"], x["stop"], x["place"]) for x in placed] == [
        (1, 2, "onset"), (4, 6, "after_release"), (8, 9, "onset")]  # fmt: skip
    prot2 = np.array([0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0], dtype=bool)  # late, never released
    assert [x["place"] for x in m.place(hazard, prot2, hazard & ~prot2)][:1] == ["onset"]
    bad = np.zeros(11, dtype=bool)
    bad[3] = True  # unprotected after an unprotected, unrecorded gap: not a valid input
    with pytest.raises(ValueError, match="hazard and not protected"):
        m.place(hazard, np.zeros(11, dtype=bool), bad)
    assert m.seconds_by_place(placed, 10.0) == {"onset": 20.0, "after_release": 20.0}
    base = [{"start": 1, "stop": 2, "place": "onset"}]
    assert m.extra_by_place(placed, base, 10.0) == {"onset": 10.0, "after_release": 20.0}


def test_protected_spans_by_where_they_start_and_end() -> None:
    m = _mod()
    hazard = np.array([0, 1, 1, 1, 0, 0, 1, 1, 0, 0], dtype=bool)
    prot = np.array([0, 1, 1, 0, 0, 1, 1, 1, 1, 0], dtype=bool)
    out = m.span_classes(hazard, prot)
    assert out["n_spans"] == 2
    assert out["classes"] == {"start_in_end_in": 1, "start_out_end_out": 1}
    assert out["median_span"] == 3.0
    assert out["median_gap"] == 2.0
    assert m.span_classes(hazard, np.zeros(10, dtype=bool))["median_span"] is None


def test_owner_views_timeline_and_last_divergence() -> None:
    m = _mod()
    agents = ["sc00", "sc01", "sc02", "sc03"]
    changes = [
        {"t_s": 10.0, "agent": "sc00", "old": "sc02", "new": "sc03"},
        {"t_s": 10.0, "agent": "sc01", "old": "sc02", "new": "sc03"},
        {"t_s": 12.0, "agent": "sc02", "old": "sc02", "new": "sc03"},
        {"t_s": 12.0, "agent": "sc03", "old": "sc02", "new": "sc03"},  # all agree: sc03
        {"t_s": 50.0, "agent": "sc03", "old": "sc03", "new": "sc01"},  # only sc03 hands on
    ]
    final = {"sc00": "sc03", "sc01": "sc03", "sc02": "sc03", "sc03": "sc01"}
    tl = m.views_timeline(changes, agents, final)
    assert tl[0][1] == ("sc02",) * 4
    assert tl[4][1] == ("sc03",) * 4
    assert tl[-1][1] == ("sc03", "sc03", "sc03", "sc01")
    assert m.last_divergence(tl) == 50.0
    assert m.last_divergence(tl[:5]) is None
    never = m.views_timeline([], agents, {"sc00": "a", "sc01": "b", "sc02": "a", "sc03": "a"})
    assert m.last_divergence(never) == float("-inf")


def test_tasking_spell_and_availability_class() -> None:
    m = _mod()
    tr = [{"t_s": 100.0, "from": "NOMINAL", "to": "PROTECTIVE"},
          {"t_s": 200.0, "from": "PROTECTIVE", "to": "RECOVERY"},
          {"t_s": 300.0, "from": "RECOVERY", "to": "NOMINAL"},
          {"t_s": 320.0, "from": "NOMINAL", "to": "PROTECTIVE"}]  # fmt: skip
    assert m.tasking_spell(tr, 99.0, TASKING) is None
    assert m.tasking_spell(tr, 150.0, TASKING) == 100.0  # from the start
    assert m.tasking_spell(tr, 400.0, TASKING) == 20.0  # a 20 s spell
    tasking = {
        "sc00": np.array([1, 1, 1, 0], dtype=bool),
        "sc01": np.array([0, 1, 0, 0], dtype=bool),
    }
    assert m.classify([("sc00", 0, 2)], tasking) == m.AVAILABLE[0]
    assert m.classify([("sc00", 1, 3), ("sc01", 0, 2)], tasking) == m.AVAILABLE[1]
    assert m.classify([("sc01", 2, 3)], tasking) == m.AVAILABLE[2]


@pytest.mark.parametrize("storm", ["jul18_2023", "20260117"])
def test_variant_series_rejects_an_unexpected_latency(
    storm: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = _mod()
    path, _ = m.variant_series(storm, 900, tmp_path)
    assert b'"latency_s":900' in path.read_bytes()
    monkeypatch.setattr(m, "RECORDED_LATENCY_S", 300)
    with pytest.raises(ValueError, match="expected one"):
        m.variant_series(storm, 0, tmp_path)


def test_b4_eligibility_is_computed_as_the_agent_does() -> None:
    from types import SimpleNamespace as NS

    m = _mod()
    slots = (NS(spacecraft="sc00", start_ns=50), NS(spacecraft="sc01", start_ns=200),
             NS(spacecraft="sc02", start_ns=300))  # fmt: skip
    agent = NS(
        _plan_algorithm="B4-rule-redistribution",
        _public={"T1": NS(owner="sc01", slots=slots), "T2": NS(owner="sc02", slots=slots),
                 "T3": NS(owner="sc01", slots=slots[:1])},
        _can_take=lambda sc, beliefs, start: sc != "sc01" and beliefs.get(sc) == "HEALTHY",
    )  # fmt: skip
    beliefs = {"sc00": "HEALTHY", "sc01": "HEALTHY", "sc02": "HEALTHY"}
    # slots must start after now (100 ns): sc00's has passed; T3 has none left
    assert m.eligible(agent, "sc01", 100, None, beliefs) == {"T1": ["sc02"], "T3": []}
    # window hand-on: only tasks the owner would start before before_ns
    assert m.eligible(agent, "sc01", 100, 150, beliefs) == {}
    assert m.eligible(agent, "sc01", 100, 250, beliefs) == {"T1": ["sc02"]}
    assert m.eligible(NS(_plan_algorithm="B3"), "sc01", 0, None, beliefs) == {}


def test_mode_at() -> None:
    m = _mod()
    tr = [{"t_s": 10.0, "to": "PROTECTIVE"}, {"t_s": 20.0, "to": "RECOVERY"}]
    assert [m.mode_at(tr, t) for t in (5.0, 10.0, 15.0, 30.0)] == [
        "NOMINAL", "PROTECTIVE", "PROTECTIVE", "RECOVERY"]  # fmt: skip

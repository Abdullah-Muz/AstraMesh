"""Belief-calibration script (DL-142, DL-143): scores, truth rules, the recorded
configurations, and a short run showing the sampling wrappers change nothing."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType

import pytest

from astramesh.core.config import NominalOperationsScenario, parse_scenario
from astramesh.faults.schedule import Fault, FaultSchedule

ROOT = Path(__file__).resolve().parents[2]


def _mod() -> ModuleType:
    path = ROOT / "scripts/experiments/belief_calibration.py"
    spec = importlib.util.spec_from_file_location("belief_calibration", path)
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m  # dataclasses look their module up here
    spec.loader.exec_module(m)
    return m


BC = _mod()
SENSOR_SHA = hashlib.sha256(BC.hc.SENSOR.read_bytes()).hexdigest()


def test_scores_match_hand_computation() -> None:
    acc = BC.Acc()
    samples = [(0.05, False), (0.05, True), (0.95, True), (0.95, True), (0.5, False)]
    for p, y in samples:
        acc.add(p, y)
    s = acc.scores()
    rate = 3 / 5
    brier = sum((p - y) ** 2 for p, y in samples) / 5
    assert s["base_rate"] == pytest.approx(rate)
    assert s["brier"] == pytest.approx(brier)
    assert s["brier_skill"] == pytest.approx(1 - brier / (rate * (1 - rate)))
    # bins: [0.0, 0.1): mean p 0.05, observed 1/2; [0.5, 0.6): 0.5 vs 0; [0.9, 1.0]: 0.95 vs 1
    ece = 2 / 5 * abs(0.05 - 0.5) + 1 / 5 * 0.5 + 2 / 5 * 0.05
    assert s["ece"] == pytest.approx(ece)
    assert [int(b[0]) for b in acc.bins] == [2, 0, 0, 0, 0, 1, 0, 0, 0, 2]


def test_p_of_one_goes_in_the_top_bin_and_undefined_scores_are_blank() -> None:
    acc = BC.Acc()
    acc.add(1.0, False)
    assert acc.bins[-1][0] == 1
    assert acc.scores()["brier_skill"] == ""  # base rate 0: no reference variance
    assert BC.Acc().scores() == {"base_rate": "", "brier": "", "brier_skill": "", "ece": ""}


def test_sums_survive_the_csv_round_trip_and_merge() -> None:
    a, b = BC.Acc(), BC.Acc()
    for p, y in [(0.2, False), (0.97, True)]:
        a.add(p, y)
    b.add(0.6, True)
    row = {k: str(v) for k, v in a.to_row().items()}
    back = BC.Acc.from_row(row)
    back.merge(b)
    assert back.n == 3
    assert back.sum_y == 2
    assert back.sum_sq == pytest.approx(0.2**2 + 0.03**2 + 0.4**2)


def _fault(kind: str, sc: str, start: int, end: int | None) -> Fault:
    return Fault(f"f-{kind}", kind, (sc,), (), start, end, 1.0, "test", "test", True, "test")


def test_truth_rules() -> None:
    sched = FaultSchedule([_fault("comms_outage", "sc01", 0, 100),
                           _fault("unavailable", "sc02", 50, None),
                           _fault("payload_degraded", "sc03", 0, 100)],
                          ["sc00", "sc01", "sc02", "sc03"])  # fmt: skip
    assert BC.peer_truth(sched, "sc01", 10) is False  # radio off: silent, still available
    assert BC.peer_truth(sched, "sc02", 10) is False
    assert BC.peer_truth(sched, "sc02", 50) is True
    assert BC.payload_truth(sched, "sc03", 99) is True
    assert BC.payload_truth(sched, "sc03", 100) is False


def test_jobs_are_every_recorded_probabilistic_run_with_the_recorded_hash() -> None:
    todo = BC.jobs(SENSOR_SHA, list(range(1, 11)))
    keys = [(s, p, m, seed) for s, p, m, seed, _, _ in todo]
    assert len(keys) == len(set(keys)) == 360
    rec = BC.recorded()
    assert set(keys) == {k for k in rec if k[2] != "H-A"}
    for job in todo:
        cfg = parse_scenario(BC.build(job))
        assert isinstance(cfg, NominalOperationsScenario)
        assert cfg.config_hash() == rec[job[:4]]["config_hash"]


def test_sampling_changes_nothing_and_counts_every_sample() -> None:
    """S01 under H-C for 6 h, seed 1: ``a`` is unavailable from 4.1 h (t0 = 14 810 s)."""
    from astramesh.agents.agent import SpacecraftAgent
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.scenarios import nominal_operations as ops

    health = BC.hc.models(SENSOR_SHA)["H-C"]
    job = ("S01", "rule_b4", "H-C", 1, 6.0, health)
    cfg = parse_scenario(BC.build(job))
    assert isinstance(cfg, NominalOperationsScenario)
    plain = ops.run_nominal_operations(cfg, RandomStreams(1), EventLog())
    originals = (SpacecraftAgent.step, SpacecraftAgent.observe, ops.fault_schedule)
    acc = {k: BC.Acc() for k in BC.KINDS}
    with BC.sampling(acc):
        sampled = ops.run_nominal_operations(cfg, RandomStreams(1), EventLog())
    assert (SpacecraftAgent.step, SpacecraftAgent.observe, ops.fault_schedule) == originals
    assert json.dumps(sampled.summary, sort_keys=True, default=str) == json.dumps(
        plain.summary, sort_keys=True, default=str
    )

    t0, step, end = 14_810 * 10**9, 10 * 10**9, 6 * 3600 * 10**9
    ticks = range(0, end + 1, step)
    down = sum(1 for t in ticks if t >= t0)
    assert acc["peer"].n == 3 * (4 * len(ticks) - down)  # the dead spacecraft is not stepped
    assert acc["peer"].sum_y == 3 * down  # three live observers see it down at each tick
    checks = [t for t in range(300 * 10**9, end + 1, 300 * 10**9)]
    assert acc["payload"].n == 4 * len(checks) - sum(1 for t in checks if t >= t0)
    assert acc["payload"].sum_y == 0  # no payload fault in S01
    late = acc["peer"].bins[-1]
    assert late[2] / late[0] > 0.5  # most confident 'unavailable' samples are true here
    assert math.isfinite(acc["peer"].sum_sq)

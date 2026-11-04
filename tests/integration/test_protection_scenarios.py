"""Supervisor in short operations runs: hazard -> PROTECTIVE and back, critical fault ->
SAFE and exit, invalid forecasts held; the payload is never on outside NOMINAL."""

from __future__ import annotations

import copy
import itertools
from pathlib import Path
from typing import Any

import pytest
import yaml

from astramesh.core.config import NominalOperationsScenario, parse_scenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.scenarios.nominal_operations import run_nominal_operations

ROOT = Path(__file__).resolve().parents[2]
H = 3600


def _run(algorithm: str, hours: float = 6, **extra: Any) -> tuple[Any, list[Any]]:
    raw = yaml.safe_load((ROOT / "configs/experiments/nominal_ops_b0_24h.yaml").read_text())
    cfg = copy.deepcopy(raw)
    cfg["time"]["duration_s"] = int(hours * H)
    cfg["operations"]["algorithm"] = algorithm
    cfg.update(copy.deepcopy(extra))
    parsed = parse_scenario(cfg)
    assert isinstance(parsed, NominalOperationsScenario)
    log = EventLog()
    return run_nominal_operations(parsed, RandomStreams(parsed.random.seed), log), list(log)


HAZARD: dict[str, Any] = {"environment": {"background_exposure_ratio": 0.1, "forecasts": [
    {"forecast_id": "HZ", "spacecraft": ["sc00"], "start_s": 0, "end_s": 2 * H,
     "exposure_ratio": 1.2}]}}  # fmt: skip


@pytest.mark.parametrize("algo", ["static_b0", "cbba_b3", "rule_b4", "cbba_b3_timeout"])
def test_hazard_makes_sc00_protective_and_payload_never_runs_outside_nominal(algo: str) -> None:
    run, events = _run(algo, **HAZARD)
    p = run.summary["protection"]
    assert sum(p["payload_steps_in_protected_modes"].values()) == 0
    tr = [(x["to"], x["t_s"]) for x in p["transitions"]["sc00"]]
    # DL-056: watch and protect in one step; RECOVERY after the 30 min release dwell;
    # NOMINAL after the 5 min minimum recovery once the checks pass.
    assert tr == [("STORM_WATCH", 0.0), ("PROTECTIVE", 0.0), ("RECOVERY", 2 * H + 1800.0),
                  ("NOMINAL", 2 * H + 2100.0)]  # fmt: skip
    assert not [s for s in run.segments if s.spacecraft == "sc00" and s.start_tick * 10 < 2.5 * H]
    assert any(e.kind == "mode_changed" and e.source == "sc00" for e in events)


def test_cbba_reassigns_protected_spacecraft_tasks() -> None:
    hazard_b3, _ = _run("cbba_b3", hours=8, **HAZARD)
    nominal_b3, _ = _run("cbba_b3", hours=8)
    assert hazard_b3.summary["operations"]["utility"] == nominal_b3.summary["operations"]["utility"]
    others = {s.spacecraft for s in hazard_b3.segments if s.outcome == "completed"}
    assert others - {"sc00"}  # someone else did the work while sc00 was protected


def test_invalid_forecast_is_held_not_zero() -> None:
    env = {"environment": {"background_exposure_ratio": 0.1, "forecasts": [
        {"forecast_id": "HZ", "spacecraft": ["sc00"], "start_s": 0, "end_s": H,
         "exposure_ratio": 1.5},
        {"forecast_id": "BAD", "spacecraft": ["sc00"], "start_s": H, "end_s": 3 * H,
         "exposure_ratio": None}]}}  # fmt: skip
    run, events = _run("static_b0", hours=4, **env)
    tr = [(x["to"], x["t_s"]) for x in run.summary["protection"]["transitions"]["sc00"]]
    # Invalid data from 1 h to 3 h: stays PROTECTIVE; RECOVERY only 30 min after valid data.
    assert tr == [("STORM_WATCH", 0.0), ("PROTECTIVE", 0.0), ("RECOVERY", 3 * H + 1800.0),
                  ("NOMINAL", 3 * H + 2100.0)]  # fmt: skip
    notes = [e for e in events if e.kind == "supervisor_note" and e.source == "sc00"]
    assert [e.data["note"] for e in notes] == ["forecast_invalid:radiation"]


def test_critical_fault_forces_safe_and_exit_waits_for_dwell() -> None:
    fault = {"faults": [{"fault_id": "F1", "type": "critical_fault", "spacecraft": ["sc01"],
                         "start_s": H, "end_s": 2 * H, "cause": "test",
                         "observability": "effects_only", "consequences": "test"}]}  # fmt: skip
    run, _ = _run("cbba_b3", hours=4, **fault)
    tr = [
        (x["to"], x["t_s"], x["reason"]) for x in run.summary["protection"]["transitions"]["sc01"]
    ]
    assert tr == [
        ("SAFE", H, "critical_flag:F1"),
        ("RECOVERY", 2 * H + 600.0, "safe_exit_conditions_met"),
        ("NOMINAL", 2 * H + 900.0, "recovery_checks_passed"),
    ]
    assert sum(run.summary["protection"]["payload_steps_in_protected_modes"].values()) == 0


def test_navcomms_risk_gives_storm_watch_with_science_and_faster_status() -> None:
    env = {"environment": {"background_exposure_ratio": 0.1, "forecasts": [
        {"forecast_id": "NC", "dimension": "navcomms", "spacecraft": ["sc00"], "start_s": 0,
         "end_s": H, "exposure_ratio": 0.9}]}}  # fmt: skip
    run, _ = _run("static_b0", hours=3, **env)
    tr = [(x["to"], x["t_s"]) for x in run.summary["protection"]["transitions"]["sc00"]]
    assert tr == [("STORM_WATCH", 0.0), ("NOMINAL", H + 1800.0)]  # never PROTECTIVE
    sends = [e["t_ns"] for e in run.trace if e["event"] == "send" and e["sender"] == "sc00"
             and e["type"] == "status"]  # fmt: skip
    in_watch = [t for t in sends if t < H * 10**9]
    gaps = {b - a for a, b in itertools.pairwise(in_watch)}
    assert gaps == {10 * 10**9}  # STORM_WATCH status every 10 s (DL-056)
    assert sum(run.summary["protection"]["payload_steps_in_protected_modes"].values()) == 0

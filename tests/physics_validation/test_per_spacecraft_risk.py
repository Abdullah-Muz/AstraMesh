"""Per-spacecraft risk (Phase 5 increment 3; DL-090, values DL-091): RK-01 to RK-06."""

from __future__ import annotations

import copy
import functools
import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.agent import AgentSettings, SpacecraftAgent
from astramesh.agents.packets import Housekeeping, RiskForecast
from astramesh.core.config import ConfigError, NominalOperationsScenario, parse_scenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.dynamics.geomagnetic import (
    R_REF_M,
    decimal_year,
    dipole_axis,
    dipole_latitude_deg,
    invariant_latitude_deg,
    pole_lat_lon_deg,
)
from astramesh.faults.schedule import Fault, FaultSchedule
from astramesh.forecast.access import CutoffModel, forward_window_max
from astramesh.scenarios.nominal_operations import OperationsRun, run_nominal_operations

ROOT = Path(__file__).parents[2]
BASE = ROOT / "configs" / "experiments" / "nominal_ops_b0_24h.yaml"
SERIES = ROOT / "configs" / "data" / "s11_storm_series.json"
R_525 = (6_378_137.0 + 525_000.0) / R_REF_M  # circular 525 km orbit in IGRF radii
MP_MEV = 938.272  # proton rest energy
S = 10**9


# --- RK-01 dipole and invariant latitude ----------------------------------------------


def test_rk01_pole_matches_the_published_2025_geomagnetic_pole() -> None:
    # NOAA NCEI "Wandering geomagnetic poles": 2025.0 north geomagnetic pole at
    # 80.79 N geocentric, 72.76 W, axis tilted 9.21 deg (WMM2025 dipole terms).
    lat, lon = pole_lat_lon_deg(2025.0)
    assert lat == pytest.approx(80.79, abs=0.01)
    assert lon == pytest.approx(-72.76, abs=0.01)
    assert 90.0 - lat == pytest.approx(9.21, abs=0.01)


def test_rk01_decimal_year() -> None:
    import datetime as dt

    assert decimal_year(dt.datetime(2024, 1, 1, tzinfo=dt.UTC)) == 2024.0
    mid = decimal_year(dt.datetime(2024, 5, 8, 0, 10, tzinfo=dt.UTC))
    assert mid == pytest.approx(2024 + (128 * 86400 + 600) / (366 * 86400), abs=1e-12)


def test_rk01_invariant_latitude_reference_points() -> None:
    m = dipole_axis(2024.4)
    equator = np.cross(m, [0.0, 0.0, 1.0])
    equator /= np.linalg.norm(equator)
    assert invariant_latitude_deg(R_REF_M * m, m) == pytest.approx(90.0, abs=1e-6)
    assert invariant_latitude_deg(R_REF_M * equator, m) == pytest.approx(0.0, abs=1e-6)
    # dipole equator at 525 km: cos^2(Lambda) = 1 / r
    expected = math.degrees(math.acos(math.sqrt(1.0 / R_525)))
    assert invariant_latitude_deg(R_525 * R_REF_M * equator, m) == pytest.approx(expected)


@settings(max_examples=200, deadline=None)
@given(st.floats(-1, 1), st.floats(-1, 1), st.floats(-1, 1), st.floats(1.0, 1.2))
def test_rk01_invariant_latitude_is_at_least_dipole_latitude(
    x: float, y: float, z: float, r: float
) -> None:
    v = np.array([x, y, z])
    if np.linalg.norm(v) < 1e-3:
        return
    pos = r * R_REF_M * v / np.linalg.norm(v)
    m = dipole_axis(2024.4)
    assert invariant_latitude_deg(pos, m) >= abs(dipole_latitude_deg(pos, m)) - 1e-9


# --- RK-02 Stormer cross-check (R09) ---------------------------------------------------


def _rigidity_gv(kinetic_mev: float) -> float:
    return math.sqrt(kinetic_mev * (kinetic_mev + 2 * MP_MEV)) / 1000.0


def test_rk02_stormer_forms_place_10_mev_far_poleward_of_the_measured_cutoff() -> None:
    p10 = _rigidity_gv(10.0)
    assert p10 == pytest.approx(0.137, abs=5e-4)
    # R09 eq. 6.17, vertical: P = 14.9 cos^4(lambda) / R^2 GV, at 525 km
    lam = math.degrees(math.acos((p10 * R_525**2 / 14.9) ** 0.25))
    assert lam == pytest.approx(71.2, abs=0.05)
    # R09 eq. 6.18: P = 16.0 / L^2 GV -> L and invariant latitude
    big_l = math.sqrt(16.0 / p10)
    assert big_l == pytest.approx(10.8, abs=0.05)
    lam_inv = math.degrees(math.acos(math.sqrt(1.0 / big_l)))
    assert lam_inv == pytest.approx(72.3, abs=0.05)
    # Both lie outside R09's stated domain (L <= 4) and 6-7 deg poleward of the
    # measured quiet cutoff that the model uses (DL-091).
    assert big_l > 4.0
    quiet = CutoffModel().quiet_deg
    assert 6.0 <= lam_inv - quiet <= 7.5


# --- RK-03 storm-time cutoff -----------------------------------------------------------


def test_rk03_cutoff_values() -> None:
    m = CutoffModel()
    assert (m.quiet_deg, m.max_shift_deg) == (65.2, 15.0)
    assert m.cutoff_deg(0.0) == m.cutoff_deg(40.0) == 65.2  # no poleward shift modelled
    assert m.cutoff_deg(-191.1) == pytest.approx(55.2)  # R08: Dst / 19.11
    # R08: "a change in Dst by 200 nT ... moves the cutoff latitude by ~8-10 deg"
    assert 8.0 <= 65.2 - m.cutoff_deg(-200.0) <= 10.5
    assert m.cutoff_deg(-1000.0) == pytest.approx(50.2)  # cap: R08's 15 deg extrapolation
    assert m.cutoff_deg(None) == pytest.approx(50.2)  # missing: whole cap (conservative)
    free = CutoffModel(max_shift_deg=None)
    assert free.cutoff_deg(-497.0) == pytest.approx(65.2 - 497.0 / 19.11)
    assert free.cutoff_deg(None) == 0.0
    assert free.cutoff_deg(-5000.0) == 0.0


@settings(max_examples=200, deadline=None)
@given(st.floats(-2000, 200), st.floats(-2000, 200), st.sampled_from([None, 8.0, 15.0]))
def test_rk03_cutoff_is_monotone_and_capped(a: float, b: float, cap: float | None) -> None:
    m = CutoffModel(max_shift_deg=cap)
    lo, hi = sorted((a, b))
    assert m.cutoff_deg(lo) <= m.cutoff_deg(hi) <= m.quiet_deg
    if cap is not None:
        assert m.cutoff_deg(lo) >= m.quiet_deg - cap


@settings(max_examples=100, deadline=None)
@given(st.lists(st.floats(-90, 90), min_size=1, max_size=60), st.integers(1, 20))
def test_rk03_forward_window_max_matches_brute_force(xs: list[float], w: int) -> None:
    x = np.array(xs)
    got = forward_window_max(x, w)
    assert np.array_equal(got, np.array([x[i : i + w].max() for i in range(len(x))]))
    two = np.stack([x, -x], axis=1)
    assert np.array_equal(forward_window_max(two, w)[:, 1], forward_window_max(-x, w))


# --- RK-05 age rule (agent side) -------------------------------------------------------


def _agent(max_age_s: int | None) -> SpacecraftAgent:
    age = None if max_age_s is None else max_age_s * S
    st_ = AgentSettings(status_interval_ns=30 * S, status_lifetime_ns=60 * S,
                        forecast_max_age_ns=age)  # fmt: skip
    return SpacecraftAgent("sc00", ("sc01",), st_)


def _tick(a: SpacecraftAgent, t_s: int) -> str:
    a.observe(Housekeeping(t_s * S, 80.0, 100.0, 0.0, 10.0, ()))
    a.payload_command(t_s * S, 10 * S, 0.1)
    return a.mode


def test_rk05_expired_inputs_are_invalid_never_zero_risk() -> None:
    a = _agent(3600)
    a.observe(RiskForecast(0, 0.1, 0.1, 0.1, issued_ns=0))
    assert _tick(a, 0) == "NOMINAL"
    assert _tick(a, 3600) == "NOMINAL"  # exactly at the limit: still valid
    assert _tick(a, 3610) == "NOMINAL"  # expired: invalid, watch only after 600 s
    assert _tick(a, 4210) == "NOMINAL"
    assert _tick(a, 4220) == "STORM_WATCH"
    a.observe(RiskForecast(5000 * S, 5.0, 0.1, 0.1, issued_ns=0))  # high but expired
    assert _tick(a, 5000) == "STORM_WATCH"  # invalid inputs never trigger PROTECTIVE


def test_rk05_without_a_limit_or_issue_time_inputs_never_expire() -> None:
    for agent, issued in ((_agent(None), 0), (_agent(3600), None)):
        agent.observe(RiskForecast(0, 0.1, 0.1, 0.1, issued_ns=issued))
        assert _tick(agent, 100_000) == "NOMINAL"


def test_rk05_expired_high_risk_does_not_release_protection() -> None:
    a = _agent(3600)
    a.observe(RiskForecast(0, 2.0, 0.1, 0.1, issued_ns=0))
    assert _tick(a, 0) == "PROTECTIVE"
    for t in range(3610, 3610 + 4 * 3600, 600):
        assert _tick(a, t) == "PROTECTIVE"


# --- RK-06 forecast faults and configuration -------------------------------------------


def _fault(kind: str, delay_ns: int = 0) -> Fault:
    return Fault(f"f_{kind}", kind, ("sc01",), (), 100 * S, 200 * S, 1.0, "test",
                 "effects_only", True, "test", None, delay_ns)  # fmt: skip


def test_rk06_fault_schedule_queries() -> None:
    fs = FaultSchedule([_fault("forecast_outage"), _fault("forecast_delay", 1800 * S)],
                       ["sc00", "sc01"])  # fmt: skip
    assert fs.forecast_delivered("sc01", 99 * S)
    assert not fs.forecast_delivered("sc01", 100 * S)
    assert fs.forecast_delivered("sc00", 150 * S)
    assert fs.forecast_delivered("sc01", 200 * S)
    assert fs.forecast_delay_ns("sc01", 150 * S) == 1800 * S
    assert fs.forecast_delay_ns("sc01", 250 * S) == 0 == fs.forecast_delay_ns("sc00", 150 * S)
    assert "delay_ns" not in _fault("forecast_outage").record()
    with pytest.raises(ValueError, match="delay_ns"):
        FaultSchedule([_fault("forecast_delay")], ["sc00", "sc01"])
    with pytest.raises(ValueError, match="delay_ns"):
        FaultSchedule([_fault("forecast_outage", S)], ["sc00", "sc01"])


def _s11(epoch: str = "2024-05-10T12:00:00Z", duration_s: int = 43_200) -> dict[str, Any]:
    raw: dict[str, Any] = copy.deepcopy(yaml.safe_load(BASE.read_text()))
    raw["time"].update(epoch_utc=epoch, duration_s=duration_s)
    raw["faults"] = []
    raw["environment"] = {"background_exposure_ratio": 0.0, "replay": {
        "series_sha256": hashlib.sha256(SERIES.read_bytes()).hexdigest(),
        "forecast": "P-B/q50"}}  # fmt: skip
    return raw


OUTAGE = {"fault_id": "out1", "type": "forecast_outage", "spacecraft": ["sc01"],
          "start_s": 15_000, "end_s": 40_000, "cause": "missed uplinks",
          "observability": "effects_only", "consequences": "inputs expire"}  # fmt: skip


def test_rk06_new_blocks_are_validated_and_hash_neutral_when_absent() -> None:
    plain = parse_scenario(_s11())
    explicit = _s11()
    explicit["environment"]["replay"].update(access=None, forecast_max_age_s=None)
    assert parse_scenario(explicit).config_hash() == plain.config_hash()
    with_fault = _s11()
    with_fault["faults"] = [{**OUTAGE, "type": "comms_outage"}]
    with_null = copy.deepcopy(with_fault)
    with_null["faults"][0]["delay_s"] = None
    assert parse_scenario(with_null).config_hash() == parse_scenario(with_fault).config_hash()
    bad = _s11()
    bad["environment"]["replay"]["radiation_tolerance_pfu"] = [100.0, 50.0]
    with pytest.raises(ConfigError, match="one value per spacecraft"):
        parse_scenario(bad)
    bad = _s11()
    bad["faults"] = [{**OUTAGE, "type": "forecast_delay"}]
    with pytest.raises(ConfigError, match="delay_s"):
        parse_scenario(bad)
    bad = _s11()
    bad["faults"] = [{**OUTAGE, "delay_s": 600.0}]
    with pytest.raises(ConfigError, match="delay_s"):
        parse_scenario(bad)
    bad = _s11()
    del bad["environment"]
    bad["faults"] = [OUTAGE]
    with pytest.raises(ConfigError, match=r"needs environment\.replay"):
        parse_scenario(bad)


@functools.cache
def _run(case: str) -> OperationsRun:
    raw = _s11()
    rp = raw["environment"]["replay"]
    if case != "phase4":
        rp.update(access={}, forecast_max_age_s=3600.0)
    if case == "outage":
        raw["faults"] = [OUTAGE]
    cfg = parse_scenario(raw)
    assert isinstance(cfg, NominalOperationsScenario)
    return run_nominal_operations(cfg, RandomStreams(cfg.random.seed), EventLog())


def test_rk04_option_a_keeps_every_decision_and_moves_only_the_hazard() -> None:
    ref, pos = _run("phase4"), _run("position")
    for key in ("operations", "protection", "network"):
        assert pos.summary[key] == ref.summary[key]
    st_ref, st_pos = ref.summary["storm"], pos.summary["storm"]
    assert sum(st_ref["hazard_s"].values()) > 0.0
    for a in st_pos["hazard_s"]:
        assert st_pos["hazard_s"][a] <= st_ref["hazard_s"][a]
        assert st_pos["hazard_s"][a] <= st_pos["in_access_s"][a]  # hazard only in the caps
        assert 0.0 < st_pos["in_access_s"][a] < 43_200.0
    spread = max(st_pos["in_access_s"].values()) - min(st_pos["in_access_s"].values())
    assert spread <= 60.0  # neighbours 2.6 s apart: a few ticks at most (DL-082)


def test_rk06_outage_starves_only_the_listed_spacecraft() -> None:
    out, pos = _run("outage"), _run("position")
    modes = out.summary["protection"]["time_in_mode_s"]
    ref = pos.summary["protection"]["time_in_mode_s"]
    for a in ("sc00", "sc02", "sc03"):
        assert modes[a] == ref[a]
    assert modes["sc01"]["PROTECTIVE"] < ref["sc01"]["PROTECTIVE"]  # expired: cannot protect
    st_out = out.summary["storm"]
    unprotected = st_out["hazard_s"]["sc01"] - st_out["protected_in_hazard_s"]["sc01"]
    assert unprotected > 0.0

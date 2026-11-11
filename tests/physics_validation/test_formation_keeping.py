"""Formation keeping (DL-087/088), MK-01 to MK-05.

MK-01 controller configured but never burning: bit-identical propagation.
MK-02 constant tangential thrust, two-body: the semi-major axis follows
      d(a^-1/2)/dt = -a_t / sqrt(mu) (Gauss, circular orbit) within 1 %.
MK-03 RK4 with thrust switched at step boundaries stays fourth order.
MK-04 ledgers: delta-v, propellant and thruster energy match PropulsionBudget and
      the energy ledger; no burn once the budget is spent.
MK-05 checks: no burn in eclipse, under a blocking fault, or while cut off from
      the reference; closed loop holds the slot under differential drag.
"""

from __future__ import annotations

import copy
import functools
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from numpy.typing import NDArray

from astramesh.core.config import MissionGeometryScenario, MissionScenarioBase, parse_scenario
from astramesh.core.events import EventLog
from astramesh.dynamics.constants import GM_EARTH_M3PS2, R_EARTH_EQ_M
from astramesh.dynamics.elements import KeplerElements
from astramesh.dynamics.forces import ForceModel
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.sun import in_shadow, sun_direction_gcrs
from astramesh.dynamics.twobody import propagate, specific_energy
from astramesh.faults.schedule import Fault, FaultSchedule
from astramesh.resources.ledgers import PropulsionBudget, simulate_energy
from astramesh.scenarios.formation_dynamics import FormationRun, run_formation_dynamics
from astramesh.scenarios.mission_geometry import run_mission_geometry

MU = GM_EARTH_M3PS2
NS = 10**9
B = 0.0092
BASE = Path(__file__).parents[2] / "configs" / "experiments" / "mission_geometry_24h.yaml"
IDS = ["sc00", "sc01", "sc02", "sc03"]


def _config(
    duration_s: int, *, b_sc01: float | None = None, control: bool = True, **fk: Any
) -> MissionScenarioBase:
    raw: dict[str, Any] = copy.deepcopy(yaml.safe_load(BASE.read_text()))
    raw["time"]["duration_s"] = duration_s
    raw["output"]["trajectory_sample_interval_s"] = 600
    if b_sc01 is not None:
        raw["dynamics"]["drag"] = {"ballistic_m2pkg": [B, b_sc01, B, B]}
    if control:
        raw["control"] = {"formation_keeping": fk}
    cfg = parse_scenario(raw)
    assert isinstance(cfg, MissionScenarioBase)
    return cfg


def _run(cfg: MissionScenarioBase, faults: FaultSchedule | None = None) -> FormationRun:
    return run_formation_dynamics(cfg, EventLog(), faults=faults)


@functools.cache
def _base() -> tuple[MissionScenarioBase, FormationRun]:
    """16 h, B x4 on sc01 (USSA 1976): sc01 burns within the run; shared by MK-04/05."""
    cfg = _config(57_600, b_sc01=4 * B)
    return cfg, _run(cfg)


def _sep_km(run: FormationRun) -> NDArray[np.float64]:
    r = run.trajectory.y[:, :, :3]
    out: NDArray[np.float64] = np.linalg.norm(np.diff(r, axis=1), axis=2) / 1e3
    return out


class _Constant:
    """Fixed tangential acceleration for spacecraft 0, optionally switched by time."""

    def __init__(self, accel: float, block_s: float | None = None) -> None:
        self.accel, self.block_s = accel, block_s

    def thrust(self, k: int, t_ns: int, y: NDArray[np.float64]) -> NDArray[np.float64]:
        a = self.accel
        if self.block_s is not None:
            phase = int(t_ns // round(self.block_s * NS)) % 3
            a = (a, 0.0, -a)[phase]  # prograde, coast, retrograde
        return np.array([a])


def _circular(alt_km: float = 525.0) -> CartesianState:
    el = KeplerElements(R_EARTH_EQ_M + alt_km * 1e3, 0.0, math.radians(97.5), 0.0, 0.0, 0.0)
    r, v = el.to_rv(MU)
    return CartesianState(Frame.GCRS, datetime(2025, 6, 1, tzinfo=UTC), 0, r, v)


# --------------------------------------------------------------------- MK-01 ----
def test_mk01_idle_controller_is_bit_identical() -> None:
    cfg = _config(86_400)
    plain = _run(_config(86_400, control=False))
    run = _run(cfg)
    assert run.keeping is not None
    assert plain.keeping is None
    assert not run.keeping.thrust_on.any()
    assert not run.keeping.commands
    assert np.array_equal(run.trajectory.y, plain.trajectory.y)
    assert "formation_keeping" in run.summary
    assert "formation_keeping" not in plain.summary
    assert run.keeping.delta_v_mps == (0.0, 0.0, 0.0, 0.0)


# --------------------------------------------------------------------- MK-02 ----
@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_mk02_tangential_thrust_follows_gauss(sign: float) -> None:
    a_t = sign * 0.5e-3 / 12.0  # spec §3.3: 0.5 mN on 12 kg
    s0 = _circular()
    n_steps, h = 2160, 10  # 6 h
    traj = propagate([s0], step_ns=h * NS, n_steps=n_steps, forces=ForceModel.two_body(),
                     controller=_Constant(a_t))  # fmt: skip
    a_num = -MU / (2.0 * specific_energy(traj.y[:, 0], MU))
    t = np.arange(n_steps + 1) * h
    a0 = float(a_num[0])
    a_ref = (a0**-0.5 - a_t * t / math.sqrt(MU)) ** -2
    change = a_ref[-1] - a0
    assert abs(change) > 1e3  # 0.9 m/s in 6 h: about 1.6 km (2 dv / n)
    assert np.max(np.abs(a_num - a_ref)) < 0.01 * abs(change)


# --------------------------------------------------------------------- MK-03 ----
def test_mk03_switched_thrust_keeps_rk4_fourth_order() -> None:
    s0 = _circular()
    duration, block = 21_600, 600.0
    final = {}
    for h in (120, 60, 30):
        ctrl = _Constant(1e-4, block)
        traj = propagate([s0], step_ns=h * NS, n_steps=duration // h,
                         forces=ForceModel.two_body(), controller=ctrl)  # fmt: skip
        final[h] = traj.y[-1, 0, :3]
    e1 = np.linalg.norm(final[120] - final[60])
    e2 = np.linalg.norm(final[60] - final[30])
    order = math.log2(e1 / e2)
    assert 3.5 <= order <= 5.5, order


# --------------------------------------------------------------------- MK-04 ----
def test_mk04_ledgers_match_the_propulsion_budget() -> None:
    cfg, run = _base()
    sc = cfg.spacecraft
    res = run.keeping
    assert res is not None
    assert res.thrust_on[:, 1].any()
    assert not res.thrust_on[:, 0].any()  # the leader never burns
    for j in range(4):
        replica = PropulsionBudget(sc.mass_kg, sc.thrust_mn * 1e-3, sc.specific_impulse_s,
                                   sc.delta_v_budget_mps)  # fmt: skip
        for _ in range(int(res.thrust_on[:, j].sum())):
            replica.used_mps += replica.thrust_n / replica.current_mass_kg * res.step_s
        assert res.delta_v_mps[j] == pytest.approx(replica.used_mps, rel=1e-12, abs=0.0)
        ve = sc.specific_impulse_s * 9.80665
        expected_kg = sc.mass_kg * -math.expm1(-res.delta_v_mps[j] / ve)
        assert res.propellant_kg[j] == pytest.approx(expected_kg, rel=1e-12, abs=0.0)
    per = run.summary["formation_keeping"]["per_spacecraft"]["sc01"]
    steps = int(res.thrust_on[:, 1].sum())
    assert per["thrust_s"] == steps * 10.0
    assert per["thruster_energy_wh"] == pytest.approx(steps * 10.0 * sc.thruster_power_w / 3600)


def test_mk04_mission_geometry_charges_the_battery() -> None:
    raw: dict[str, Any] = copy.deepcopy(yaml.safe_load(BASE.read_text()))
    raw["time"]["duration_s"] = 57_600
    raw["dynamics"]["drag"] = {"ballistic_m2pkg": [B, 4 * B, B, B]}
    raw["control"] = {"formation_keeping": {}}
    cfg = parse_scenario(raw)
    assert isinstance(cfg, MissionGeometryScenario)
    run = run_mission_geometry(cfg, EventLog())
    prop = run.summary["resources"]["propulsion"]
    assert prop["delta_v_used_mps"]["sc01"] > 0.0
    assert prop["delta_v_used_mps"]["sc00"] == 0.0
    plain = run_formation_dynamics(cfg, EventLog())
    assert plain.keeping is not None
    sunlit = ~in_shadow(np.ascontiguousarray(plain.trajectory.y[:, :, :3]),
                        sun_direction_gcrs(cfg.time.epoch_utc, plain.trajectory.t_ns))  # fmt: skip
    sc = cfg.spacecraft
    common = dict(
        sunlit=sunlit[:, 1], payload_on=np.zeros(sunlit.shape[0], dtype=np.bool_), step_s=10.0,
        capacity_wh=sc.battery_capacity_wh, initial_fraction=sc.battery_initial_fraction,
        charge_efficiency=sc.charge_efficiency_fraction, generation_w=sc.solar_generation_w,
        bus_w=sc.bus_power_w, payload_w=sc.payload_power_w,
    )  # fmt: skip
    with_thrust = simulate_energy(**common, thruster_on=plain.keeping.thrust_on[:, 1],  # type: ignore[arg-type]
                                  thruster_w=sc.thruster_power_w)  # fmt: skip
    without = simulate_energy(**common)  # type: ignore[arg-type]
    steps = int(plain.keeping.thrust_on[:-1, 1].sum())
    assert with_thrust.consumed_wh - without.consumed_wh == pytest.approx(
        steps * 10.0 * sc.thruster_power_w / 3600, rel=1e-9
    )
    bus = run.summary["resources"]["energy_bus_only"]["sc01"]
    assert bus["consumed_wh"] == pytest.approx(with_thrust.consumed_wh, rel=1e-12)


def test_mk04_no_burn_after_the_budget_is_spent() -> None:
    raw: dict[str, Any] = copy.deepcopy(yaml.safe_load(BASE.read_text()))
    raw["time"]["duration_s"] = 57_600
    raw["output"]["trajectory_sample_interval_s"] = 600
    raw["dynamics"]["drag"] = {"ballistic_m2pkg": [B, 4 * B, B, B]}
    raw["spacecraft"]["delta_v_budget_mps"] = 0.002  # about five 10 s steps
    raw["control"] = {"formation_keeping": {}}
    cfg = parse_scenario(raw)
    assert isinstance(cfg, MissionScenarioBase)
    res = _run(cfg).keeping
    assert res is not None
    step_dv = 0.5e-3 / 12.0 * 10.0
    assert 0.002 - step_dv < res.delta_v_mps[1] <= 0.002
    assert int(res.thrust_on[:, 1].sum()) == 4


# --------------------------------------------------------------------- MK-05 ----
def test_mk05_burns_only_in_sunlight() -> None:
    cfg, run = _base()
    assert run.keeping is not None
    traj = run.trajectory
    sunlit = ~in_shadow(np.ascontiguousarray(traj.y[:, :, :3]),
                        sun_direction_gcrs(cfg.time.epoch_utc, traj.t_ns))  # fmt: skip
    on = run.keeping.thrust_on
    assert on.any()
    assert not (on & ~sunlit).any()


def _fault(kind: str, start_s: int, end_s: int) -> Fault:
    groups = (("sc00",), ("sc01", "sc02", "sc03")) if kind == "partition" else ()
    return Fault(
        fault_id=f"F-{kind}", fault_type=kind,
        spacecraft=tuple(m for g in groups for m in g) or ("sc01",), groups=groups,
        start_ns=start_s * NS, end_ns=end_s * NS,
        severity_fraction=0.5 if kind == "power_degraded" else 1.0, cause="test",
        observability="effects_only", recoverable=True, consequences="test",
    )  # fmt: skip


@pytest.mark.parametrize(
    "kind", ["partition", "comms_outage", "unavailable", "critical_fault", "power_degraded"]
)
def test_mk05_no_burn_under_a_blocking_fault(kind: str) -> None:
    cfg, base_run = _base()
    base = base_run.keeping
    assert base is not None
    burns_s = np.flatnonzero(base.thrust_on[:, 1]) * 10
    start, end = int(burns_s[0]) - 6000, int(burns_s[0]) + 12_000
    assert ((burns_s >= start) & (burns_s < end)).any()  # the window would see burns
    res = _run(cfg, FaultSchedule([_fault(kind, start, end)], IDS)).keeping
    assert res is not None
    window = slice(start // 10, end // 10)
    assert not res.thrust_on[window, 1].any()
    if kind in ("partition", "comms_outage", "unavailable"):
        assert res.held[1] > 0  # no fresh measurement: decisions held
    if kind == "partition":  # sc02 and sc03 cannot hear sc00: sc01 is their reference
        inside = [c for c in res.commands if start * NS <= c.t_ns < end * NS]
        assert all(c.reference != "sc00" for c in inside)


def test_mk05_closed_loop_holds_the_slots_under_differential_drag() -> None:
    cfg = _config(86_400, b_sc01=4 * B)  # 1 day, B x4 on sc01, USSA 1976
    free = _run(_config(86_400, b_sc01=4 * B, control=False))
    run = _run(cfg)
    assert run.keeping is not None
    sep, sep_free = _sep_km(run), _sep_km(free)
    assert np.abs(sep_free - 20.0).max() > 1.0  # uncontrolled: drifts more than 1 km
    assert np.abs(sep - 20.0).max() < 2.0  # DL-087 pass band
    assert run.keeping.delta_v_mps[2] == 0.0
    assert run.keeping.delta_v_mps[3] == 0.0

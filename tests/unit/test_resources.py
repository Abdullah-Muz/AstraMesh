"""Resource ledgers: hand-computed energy cases, data volume, delta-v budget."""

from __future__ import annotations

import math

import numpy as np
import pytest

from astramesh.resources.ledgers import (
    G0_MPS2,
    PropulsionBudget,
    data_volume_mb,
    energy_wh,
    simulate_energy,
)


def _run(sunlit: list[bool], payload: list[bool] | None = None, **kw: float):  # type: ignore[no-untyped-def]
    args = {
        "step_s": 360.0, "capacity_wh": 10.0, "initial_fraction": 0.5,
        "charge_efficiency": 0.8, "generation_w": 20.0, "bus_w": 10.0, "payload_w": 5.0,
    }  # fmt: skip
    args.update(kw)
    return simulate_energy(
        sunlit=np.array(sunlit),
        payload_on=np.array(payload if payload is not None else [False] * len(sunlit)),
        **args,  # type: ignore[arg-type]
    )


def test_charging_applies_efficiency_and_curtails_at_capacity() -> None:
    # 0.1 h steps, net +10 W -> +1 Wh delivered, 0.8 Wh stored per step; start 5 Wh.
    r = _run([True] * 8)
    np.testing.assert_allclose(r.stored_wh, [5.0, 5.8, 6.6, 7.4, 8.2, 9.0, 9.8, 10.0], atol=1e-12)
    assert r.curtailed_wh == pytest.approx((10.6 - 10.0) / 0.8, abs=1e-12)
    assert r.deficit_wh == 0.0
    assert r.generated_wh == pytest.approx(14.0)
    assert r.consumed_wh == pytest.approx(7.0)


def test_discharge_is_lossless_and_deficit_is_reported() -> None:
    # Dark, bus 10 W + payload 5 W -> -1.5 Wh per step from 5 Wh.
    r = _run([False] * 6, [True] * 6)
    np.testing.assert_allclose(r.stored_wh, [5.0, 3.5, 2.0, 0.5, 0.0, 0.0], atol=1e-12)
    assert r.deficit_steps == 2
    assert r.deficit_wh == pytest.approx(1.0 + 1.5)
    assert r.min_wh == 0.0
    assert r.min_tick == 4
    assert r.max_drawdown_wh == pytest.approx(5.0)


def test_left_endpoint_rule_and_final_tick_unused() -> None:
    # Only the state at ticks 0..n-2 matters; the last tick's flags have no step.
    a = _run([True, False, True], [False, True, False])
    b = _run([True, False, False], [False, True, True])
    np.testing.assert_array_equal(a.stored_wh, b.stored_wh)


def test_energy_identity() -> None:
    rng = np.random.default_rng(3)
    sun = (rng.random(500) > 0.3).tolist()
    pay = (rng.random(500) > 0.7).tolist()
    r = _run(sun, pay, capacity_wh=3.0)
    dt_h = 0.1
    charged = discharged = 0.0
    for s, p in zip(sun[:-1], pay[:-1], strict=True):
        net = (20.0 if s else 0.0) - 10.0 - (5.0 if p else 0.0)
        if net >= 0:
            charged += net * dt_h
        else:
            discharged += -net * dt_h
    expected = 1.5 + 0.8 * (charged - r.curtailed_wh) - discharged + r.deficit_wh
    assert r.final_wh == pytest.approx(expected, abs=1e-9)
    assert r.generated_wh - r.consumed_wh == pytest.approx(charged - discharged, abs=1e-9)


@pytest.mark.parametrize(
    "kw",
    [{"initial_fraction": 0.0}, {"charge_efficiency": 1.5}, {"capacity_wh": 0.0}, {"step_s": 0.0}],
)
def test_energy_rejects_invalid_parameters(kw: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must be"):
        _run([True, True], None, **kw)


def test_energy_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        simulate_energy(
            sunlit=np.ones(3, dtype=bool), payload_on=np.ones(2, dtype=bool), step_s=1.0,
            capacity_wh=1.0, initial_fraction=1.0, charge_efficiency=1.0,
            generation_w=1.0, bus_w=1.0, payload_w=1.0,
        )  # fmt: skip


def test_data_volume_and_energy_units() -> None:
    assert data_volume_mb(100, 10.0, 8.0) == pytest.approx(1.0)  # 8 kbit/s x 1000 s = 1 MB
    assert energy_wh(36, 10.0, 5.0) == pytest.approx(0.5)


def _budget() -> PropulsionBudget:
    return PropulsionBudget(mass_kg=12.0, thrust_n=5e-4, specific_impulse_s=70.0, budget_mps=5.0)


def test_tsiolkovsky_and_burn_time() -> None:
    b = _budget()
    ve = 70.0 * G0_MPS2
    assert b.propellant_kg(5.0) == pytest.approx(12.0 * (1 - math.exp(-5.0 / ve)), rel=1e-15)
    # Exact burn time = propellant * ve / F; constant-mass approximation is m dv / F.
    assert b.burn_time_s(5.0) == pytest.approx(b.propellant_kg(5.0) * ve / 5e-4, rel=1e-14)
    assert b.burn_time_s(5.0) < 12.0 * 5.0 / 5e-4


def test_burns_are_path_independent_and_refused_over_budget() -> None:
    b = _budget()
    used = b.burn(2.0) + b.burn(3.0)
    assert used == pytest.approx(_budget().propellant_kg(5.0), rel=1e-14)
    assert b.remaining_mps == pytest.approx(0.0)
    with pytest.raises(ValueError, match="exceeds the remaining budget"):
        b.burn(1e-6)
    with pytest.raises(ValueError, match="dv_mps"):
        _budget().burn(-1.0)


def test_budget_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="thrust_n"):
        PropulsionBudget(mass_kg=12.0, thrust_n=0.0, specific_impulse_s=70.0, budget_mps=5.0)
    with pytest.raises(ValueError, match="budget_mps"):
        PropulsionBudget(mass_kg=12.0, thrust_n=1e-3, specific_impulse_s=70.0, budget_mps=-1.0)

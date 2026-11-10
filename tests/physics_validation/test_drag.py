"""Nominal drag (D1) validation, DR-01 to DR-05 (DL-080).

DR-01 density table: source values at the nodes, monotone, smooth scale height.
DR-02 circular-orbit decay rate against da/dt = -rho B sqrt(mu a) (no J2, no rotation).
DR-03 specific energy falls at the rate a_drag . v.
DR-04 RK4 step refinement converges at fourth order with J2, drag and rotation.
DR-05 co-rotation scales an equatorial prograde decay by (1 - omega r / v)^2.

All runs use the scenarios' 10 s step (NUMERICAL_MISSION_DESIGN.md §B.2) and subtract a
drag-free run with the same step: RK4 alone lowers the semi-major axis by about 0.003 m
per day at 10 s (0.7 m at 30 s, 23 m at 60 s), against about 15 m per day from drag.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from astramesh.dynamics.constants import GM_EARTH_M3PS2, OMEGA_EARTH_RADPS, R_EARTH_EQ_M
from astramesh.dynamics.drag import (
    USSA76_TABLE,
    DensityRangeError,
    DragModel,
    altitude,
    density,
    drag_acceleration,
)
from astramesh.dynamics.forces import ForceModel, specific_energy
from astramesh.dynamics.state import CartesianState, Frame, NonPhysicalStateError
from astramesh.dynamics.twobody import propagate

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
NS = 10**9
DAY_S = 86_400
MU = GM_EARTH_M3PS2
B = 0.0092  # DL-080 nominal ballistic coefficient [m^2/kg]
POLE = (0.0, 0.0, 1.0)


def _circular(h_m: float, incl_rad: float = 0.0) -> CartesianState:
    r = R_EARTH_EQ_M + h_m
    v = math.sqrt(MU / r)
    return CartesianState(
        Frame.GCRS, EPOCH, 0,
        np.array([r, 0.0, 0.0]),
        np.array([0.0, v * math.cos(incl_rad), v * math.sin(incl_rad)]),
    )  # fmt: skip


def _semi_major_axis(y: np.ndarray) -> np.ndarray:
    return -MU / (2.0 * specific_energy(y, ForceModel(mu=MU)))


STEP = 10


def _drag_decay(s: CartesianState, drag: DragModel, seconds: int = DAY_S) -> np.ndarray:
    """Semi-major-axis change [m] from drag alone (a drag-free run with the same step
    is subtracted, removing the integrator's own drift), one value per spacecraft."""
    out = []
    for d in (DragModel((0.0,), corotating=drag.corotating), drag):
        fm = ForceModel(mu=MU, pole=POLE, drag=d)
        y = propagate([s] * len(drag.ballistic_m2pkg), step_ns=STEP * NS,
                      n_steps=seconds // STEP, forces=fm).y  # fmt: skip
        out.append(np.array([_semi_major_axis(y[:, i, :]) for i in range(y.shape[1])]))
    change: np.ndarray = (out[1][:, -1] - out[1][:, 0]) - (out[0][:, -1] - out[0][:, 0])
    return change


# -- DR-01 ---------------------------------------------------------------------------
def test_dr01_table_values_order_and_smoothness() -> None:
    h = np.array([1000.0 * a for a, _ in USSA76_TABLE])
    rho = np.array([r for _, r in USSA76_TABLE])
    np.testing.assert_allclose(density(h), rho, rtol=1e-12)
    assert np.all(np.diff(rho) < 0)
    scale = np.diff(h) / -np.diff(np.log(rho))  # local scale height [m]
    assert scale.min() > 60e3
    assert scale.max() < 90e3
    assert np.max(np.abs(np.diff(scale))) < 2e3  # a misread digit would jump far more
    with pytest.raises(DensityRangeError):
        density(np.array([470e3]))
    with pytest.raises(DensityRangeError):
        density(np.array([710e3]))


def test_altitude_uses_the_ellipsoid() -> None:
    r_eq = np.array([[R_EARTH_EQ_M + 525e3, 0.0, 0.0]])
    assert altitude(r_eq, POLE)[0] == pytest.approx(525e3, abs=1e-6)
    r_pole = np.array([[0.0, 0.0, R_EARTH_EQ_M + 525e3]])
    flattening_drop = R_EARTH_EQ_M / 298.257223563  # about 21.4 km
    assert altitude(r_pole, POLE)[0] == pytest.approx(525e3 + flattening_drop, abs=1.0)


# -- DR-02 ---------------------------------------------------------------------------
def test_dr02_circular_decay_matches_analytic_rate() -> None:
    numeric = float(_drag_decay(_circular(525e3), DragModel((B,), corotating=False))[0])
    a_mid = R_EARTH_EQ_M + 525e3 + 0.5 * numeric
    rho = density(np.array([a_mid - R_EARTH_EQ_M]))[0]
    analytic = -rho * B * math.sqrt(MU * a_mid) * DAY_S
    assert 10.0 < -numeric < 20.0  # about 15 m/day at 525 km (DL-080)
    assert numeric == pytest.approx(analytic, rel=0.01)


# -- DR-03 ---------------------------------------------------------------------------
def test_dr03_energy_falls_at_drag_power() -> None:
    drag = DragModel((B,))
    fm = ForceModel(mu=MU, pole=POLE, drag=drag)
    s = _circular(525e3, 0.9)
    y = propagate([s], step_ns=STEP * NS, n_steps=360, forces=fm).y[:, 0, :]
    free = propagate([s], step_ns=STEP * NS, n_steps=360, forces=ForceModel(mu=MU)).y[:, 0, :]
    e = specific_energy(y, ForceModel(mu=MU))
    e_free = specific_energy(free, ForceModel(mu=MU))
    power = np.einsum("ij,ij->i", drag_acceleration(y, drag, POLE), y[:, 3:])
    assert np.all(power < 0)
    integral = float(np.sum(0.5 * (power[1:] + power[:-1])) * STEP)
    assert (e[-1] - e[0]) - (e_free[-1] - e_free[0]) == pytest.approx(integral, rel=1e-4)


# -- DR-04 ---------------------------------------------------------------------------
def test_dr04_rk4_step_refinement_is_fourth_order() -> None:
    fm = ForceModel(mu=MU, j2=1.08262e-3, pole=POLE, drag=DragModel((B,)))
    s = _circular(525e3, 1.7)
    end = {}
    for h in (40, 20, 10):
        end[h] = propagate([s], step_ns=h * NS, n_steps=DAY_S // h, forces=fm).y[-1, 0, :3]
    e1 = np.linalg.norm(end[40] - end[20])
    e2 = np.linalg.norm(end[20] - end[10])
    assert 3.5 < math.log2(e1 / e2) < 5.5  # order band as PA-03 (§B.5.2)


# -- DR-05 ---------------------------------------------------------------------------
def test_dr05_corotation_factor_for_equatorial_orbit() -> None:
    s = _circular(525e3)
    decay = {c: float(_drag_decay(s, DragModel((B,), corotating=c))[0]) for c in (False, True)}
    r = R_EARTH_EQ_M + 525e3
    factor = (1.0 - OMEGA_EARTH_RADPS * r / math.sqrt(MU / r)) ** 2
    assert decay[True] / decay[False] == pytest.approx(factor, rel=0.01)


# -- model plumbing ------------------------------------------------------------------
def test_drag_off_is_bit_identical_and_ids() -> None:
    s = _circular(525e3, 0.9)
    plain = ForceModel(mu=MU, j2=1.08262e-3, pole=POLE)
    a = propagate([s], step_ns=30 * NS, n_steps=200, forces=plain).y
    b = propagate([s], step_ns=30 * NS, n_steps=200, forces=ForceModel(
        mu=MU, j2=1.08262e-3, pole=POLE, drag=None)).y  # fmt: skip
    assert np.array_equal(a, b)
    assert plain.model_id == "D1-j2-rk4"
    assert ForceModel(mu=MU, j2=1.08262e-3, pole=POLE,
                      drag=DragModel((B,))).model_id == "D1-j2-rk4+drag-ussa76"  # fmt: skip


def test_per_spacecraft_coefficients_and_validation() -> None:
    d1, d2 = _drag_decay(_circular(525e3), DragModel((B, 2 * B)))  # same start, 2x coefficient
    assert d2 / d1 == pytest.approx(2.0, rel=0.01)  # slightly above 2: denser air lower down
    with pytest.raises(NonPhysicalStateError):
        DragModel((-1.0,))
    with pytest.raises(ValueError, match="3 ballistic coefficients for 2 states"):
        DragModel((B, B, B)).coefficients(2)

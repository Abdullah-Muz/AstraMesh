"""Mean-element initialization (DL-026): reference orbit and formation under J2.

Tolerances come from ``scripts/studies/mean_init_reference.py`` as recorded in
``docs/NUMERICAL_MISSION_DESIGN.md`` §B.6 (rule DL-019). The pole is a literal
vector so results do not depend on ERFA's last bits.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from astramesh.dynamics.constants import GM_EARTH_M3PS2, J2_EARTH, R_EARTH_EQ_M
from astramesh.dynamics.elements import rv_to_elements
from astramesh.dynamics.forces import ForceModel, equatorial_basis
from astramesh.dynamics.mean_elements import (
    initialize_from_mean,
    mean_matched_formation,
    measure_mean_elements,
)
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.twobody import propagate

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
NS = 10**9
POLE = (0.002474555351741926, 3.4444800955196655e-05, 0.9999969376899945)
FM = ForceModel.with_j2(POLE)
MEAN_A = R_EARTH_EQ_M + 525e3
MEAN_I = math.radians(97.5)

# §B.6 tolerances
REMEASURE_A_M = 6e-3  # observed 2.8e-3 m
REMEASURE_I_RAD = 9e-13  # observed 4.1e-13 rad
REMEASURE_E = 2e-11  # observed 7.8e-12
PRECESSION_REL = 2e-3  # PA-08 tolerance (approved, §B.5); observed -6.7e-4
FORMATION_MEAN_A_DIFF_M = 2e-4  # observed 7.1e-5 m
FORMATION_TREND_M_PER_ORBIT = 0.06  # observed 0.028 m/orbit (worst start angle)
FORMATION_SWING_M = 40.0  # observed 18.2 m in-orbit separation swing
FORMATION_MEAN_SEP_DEV_M = 40.0  # observed worst |mean separation - 20 km| = 17.7 m


@pytest.fixture(scope="module")
def reference() -> tuple[np.ndarray, np.ndarray, int]:
    orb = initialize_from_mean(
        mean_a_m=MEAN_A, mean_i_rad=MEAN_I, raan_rad=0.0, u_rad=0.0, forces=FM, epoch_utc=EPOCH
    )
    assert abs(orb.mean.a_m - MEAN_A) <= 1e-4  # convergence criteria
    assert abs(orb.mean.i_rad - MEAN_I) <= 1e-10
    assert math.hypot(orb.mean.ex, orb.mean.ey) <= 1e-9
    return orb.r_m, orb.v_mps, orb.iterations


def test_reference_initialization_is_deterministic(
    reference: tuple[np.ndarray, np.ndarray, int],
) -> None:
    again = initialize_from_mean(
        mean_a_m=MEAN_A, mean_i_rad=MEAN_I, raan_rad=0.0, u_rad=0.0, forces=FM, epoch_utc=EPOCH
    )
    np.testing.assert_array_equal(again.r_m, reference[0])
    np.testing.assert_array_equal(again.v_mps, reference[1])
    assert reference[2] <= 10


def test_mean_elements_are_constant_along_the_trajectory(
    reference: tuple[np.ndarray, np.ndarray, int],
) -> None:
    s = CartesianState(Frame.GCRS, EPOCH, 0, reference[0], reference[1])
    traj = propagate([s], step_ns=10 * NS, n_steps=8640, forces=FM)
    for hours in (1, 6, 12, 23):
        row = traj.y[hours * 360, 0, :]
        m = measure_mean_elements(row[:3], row[3:], FM, epoch_utc=EPOCH)
        assert abs(m.a_m - MEAN_A) <= REMEASURE_A_M
        assert abs(m.i_rad - MEAN_I) <= REMEASURE_I_RAD
        assert math.hypot(m.ex, m.ey) <= REMEASURE_E


def test_pa08_precession_of_mean_initialized_reference(
    reference: tuple[np.ndarray, np.ndarray, int],
) -> None:
    s = CartesianState(Frame.GCRS, EPOCH, 0, reference[0], reference[1])
    traj = propagate([s], step_ns=10 * NS, n_steps=8640, forces=FM)
    rot = equatorial_basis(POLE)
    raan = [rv_to_elements(rot @ r[:3], rot @ r[3:]).raan_rad for r in traj.y[:, 0, :]]
    rate = float(np.polyfit(traj.t_ns / NS, np.unwrap(raan), 1)[0])
    n = math.sqrt(GM_EARTH_M3PS2 / MEAN_A**3)
    analytic = -1.5 * n * J2_EARTH * (R_EARTH_EQ_M / MEAN_A) ** 2 * math.cos(MEAN_I)
    assert abs(rate - analytic) <= PRECESSION_REL * abs(analytic)


@pytest.mark.parametrize("u0_deg", [0.0, 45.0])
def test_mean_matched_formation_holds_together_under_j2(u0_deg: float) -> None:
    """45 deg was the worst start angle for equal-osculating initialization (7.7 km/day)."""
    members = mean_matched_formation(
        mean_a_m=MEAN_A,
        mean_i_rad=MEAN_I,
        raan_rad=0.0,
        u0_rad=math.radians(u0_deg),
        n_spacecraft=4,
        spacing_m=20_000.0,
        forces=FM,
        epoch_utc=EPOCH,
    )
    assert max(abs(m.mean.a_m - members[0].mean.a_m) for m in members) <= FORMATION_MEAN_A_DIFF_M
    states = [CartesianState(Frame.GCRS, EPOCH, 0, m.r_m, m.v_mps) for m in members]
    y = propagate(states, step_ns=10 * NS, n_steps=3 * 8640, forces=FM).y
    sep = np.linalg.norm(y[:, 1:, :3] - y[:, :-1, :3], axis=2)
    k = round(2 * math.pi / math.sqrt(GM_EARTH_M3PS2 / MEAN_A**3) / 10)
    avg = np.array([sep[i : i + k].mean(axis=0) for i in range(0, len(sep) - k, k)])
    for j in range(3):
        trend = float(np.polyfit(np.arange(len(avg)), avg[:, j], 1)[0])
        assert abs(trend) <= FORMATION_TREND_M_PER_ORBIT
    assert float(np.ptp(sep[:k], axis=0).max()) <= FORMATION_SWING_M
    assert float(np.max(np.abs(avg[0] - 20_000.0))) <= FORMATION_MEAN_SEP_DEV_M


def test_invalid_requests_raise() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        initialize_from_mean(
            mean_a_m=MEAN_A, mean_i_rad=MEAN_I, osc_i_rad=MEAN_I, raan_rad=0.0, u_rad=0.0,
            forces=FM, epoch_utc=EPOCH,
        )  # fmt: skip
    with pytest.raises(ValueError, match="n_spacecraft"):
        mean_matched_formation(
            mean_a_m=MEAN_A, mean_i_rad=MEAN_I, raan_rad=0.0, u0_rad=0.0, n_spacecraft=0,
            spacing_m=20e3, forces=FM, epoch_utc=EPOCH,
        )  # fmt: skip
    with pytest.raises(ValueError, match="half an orbit"):
        mean_matched_formation(
            mean_a_m=MEAN_A, mean_i_rad=MEAN_I, raan_rad=0.0, u0_rad=0.0, n_spacecraft=4,
            spacing_m=8_000e3, forces=FM, epoch_utc=EPOCH,
        )  # fmt: skip

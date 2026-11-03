"""PA-07: Clohessy-Wiltshire cross-check, only within its assumptions.

Tolerances and bands come from ``scripts/studies/formation_cw_reference_errors.py``
as recorded in ``docs/NUMERICAL_MISSION_DESIGN.md`` §B.4 (rule DL-019).
"""

from __future__ import annotations

import itertools
import math
from datetime import UTC, datetime

import numpy as np
import pytest

from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.elements import KeplerElements
from astramesh.dynamics.frames import eci_to_ric, ric_to_eci
from astramesh.dynamics.relative import cw_propagate, cw_state_transition
from astramesh.dynamics.state import CartesianState, Frame, NonPhysicalStateError
from astramesh.dynamics.twobody import propagate_two_body

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
NS = 10**9
HORIZON_S = 5700  # ~1 orbit
REFERENCE = KeplerElements.from_degrees(
    a_m=R_EARTH_EQ_M + 525e3, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=0.0
)
N_RAD = REFERENCE.mean_motion_radps()

# §B.4.3
NONLINEARITY_ORDER_BAND = (1.9, 2.1)  # observed 1.9987-2.0010; theory 2
IN_TRAIN_RESIDUAL_M = 2e-5  # CW-minus-truth vs analytic curvature error; observed 9.4e-6 m


def _truth_ric(rel0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    chief = CartesianState(Frame.GCRS, EPOCH, 0, *REFERENCE.to_rv())
    dep = ric_to_eci(chief, CartesianState(Frame.RIC, EPOCH, 0, rel0[:3], rel0[3:]))
    traj = propagate_two_body([chief, dep], step_ns=10 * NS, n_steps=HORIZON_S // 10)
    out = np.empty((len(traj.t_ns), 6))
    for k in range(len(traj.t_ns)):
        rel = eci_to_ric(traj.state(k, 0), traj.state(k, 1))
        out[k, :3], out[k, 3:] = rel.r_m, rel.v_mps
    return traj.t_ns.astype(np.float64) / NS, out


def _max_cw_error(rel0: np.ndarray) -> float:
    t, truth = _truth_ric(rel0)
    cw = cw_propagate(rel0, N_RAD, t)
    return float(np.max(np.linalg.norm(cw[:, :3] - truth[:, :3], axis=1)))


@pytest.mark.parametrize(
    ("pos_dir", "vel_dir"),
    [
        ((0.0, 1.0, 0.0), (0.0, 0.0, 0.0)),  # pure in-track offset
        ((1.0, 0.0, 0.0), (0.0, -2.0, 0.0)),  # bounded (2:1 ellipse) initial condition
        ((0.6, 0.0, 0.8), (0.3, -0.5, 0.4)),  # generic
    ],
)
def test_pa07_cw_error_is_second_order_in_separation(
    pos_dir: tuple[float, float, float], vel_dir: tuple[float, float, float]
) -> None:
    """Within its assumptions, CW is exact to first order: error scales as rho^2."""
    errors = []
    for rho in (250.0, 500.0, 1000.0):
        rel0 = np.concatenate((rho * np.array(pos_dir), rho * N_RAD * np.array(vel_dir)))
        errors.append(_max_cw_error(rel0))
    for small, large in itertools.pairwise(errors):
        order = math.log2(large / small)
        assert NONLINEARITY_ORDER_BAND[0] <= order <= NONLINEARITY_ORDER_BAND[1], errors


def test_pa07_in_train_20km_cw_error_is_the_known_curvature_error() -> None:
    """At 20 km in-train, CW - truth equals the analytic linearization error.

    A neighbour on the same circular orbit has rectilinear radial offset
    x0 = -a(1 - cos du); CW then predicts dx = 3(1-cos nt) x0 and
    dy = 6(sin nt - nt) x0 relative to the (stationary) truth.
    """
    a = REFERENCE.a_m
    du = 20_000.0 / a
    x0 = -a * (1 - math.cos(du))
    rel0 = np.array([x0, -a * math.sin(du), 0.0, 0.0, 0.0, 0.0])
    t, truth = _truth_ric(rel0)
    cw = cw_propagate(rel0, N_RAD, t)
    nt = N_RAD * t
    predicted = np.stack(
        (3 * (1 - np.cos(nt)) * x0, 6 * (np.sin(nt) - nt) * x0, np.zeros_like(t)), axis=1
    )
    residual = (cw[:, :3] - truth[:, :3]) - predicted
    assert np.max(np.linalg.norm(residual, axis=1)) <= IN_TRAIN_RESIDUAL_M
    # The error itself is large: ~1.1 km after one orbit (documented limitation).
    assert np.linalg.norm(cw[-1, :3] - truth[-1, :3]) > 1000.0


def test_cw_stm_identity_and_composition() -> None:
    np.testing.assert_array_equal(cw_state_transition(N_RAD, 0.0), np.eye(6))
    a = cw_state_transition(N_RAD, 1234.0)
    b = cw_state_transition(N_RAD, 765.0)
    np.testing.assert_allclose(b @ a, cw_state_transition(N_RAD, 1999.0), rtol=0, atol=1e-9)


def test_cw_rejects_invalid_input() -> None:
    with pytest.raises(NonPhysicalStateError):
        cw_state_transition(0.0, 1.0)
    with pytest.raises(NonPhysicalStateError):
        cw_state_transition(N_RAD, math.inf)
    with pytest.raises(NonPhysicalStateError):
        cw_propagate([math.nan, 0, 0, 0, 0, 0], N_RAD, 1.0)

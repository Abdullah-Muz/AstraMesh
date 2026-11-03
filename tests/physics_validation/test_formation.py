"""PA-06: formation initialization from consistent orbital elements.

Tolerances come from ``scripts/studies/formation_cw_reference_errors.py`` as
recorded in ``docs/NUMERICAL_MISSION_DESIGN.md`` §B.4 (rule DL-019).
"""

from __future__ import annotations

import itertools
import math
from datetime import UTC, datetime

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.elements import KeplerElements, rv_to_elements
from astramesh.dynamics.formation import along_track_formation
from astramesh.dynamics.frames import eci_to_ric
from astramesh.dynamics.state import CartesianState, Frame, NonPhysicalStateError
from astramesh.dynamics.twobody import propagate_two_body

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
EPS = float(np.finfo(np.float64).eps)
SPACING_M = 20_000.0
REFERENCE = KeplerElements.from_degrees(
    a_m=R_EARTH_EQ_M + 525e3, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=0.0
)

# §B.4.1 element round trips (Hypothesis-searched: ~5x margin)
RT_POS_EPS_R = 60.0  # observed 10.1
RT_VEL_EPS_V = 60.0  # observed 9.9
RT_A_REL = 1e-14
RT_E_ABS = 6e-15
RT_I_RAD = 3e-15
RT_RAAN_X_SIN_I = 5e-15
RT_U_X_SIN_I = 2e-14
# §B.4.2 formation geometry (deterministic inputs: 2x rule)
CHORD_T0_M = 3e-11
RIC_POS_T0_M = 3e-9  # all three pairs; observed 1.38e-9 m
RIC_VEL_T0_MPS = 2e-12  # all three pairs; observed 7.8e-13 m/s
SEP_CHANGE_24H_M = 5e-5
RIC_POS_CHANGE_24H_M = 5e-5
RIC_VEL_24H_MPS = 2e-8

angles = st.floats(0.0, 2 * math.pi, allow_nan=False)
elements = st.builds(
    KeplerElements,
    a_m=st.floats(R_EARTH_EQ_M + 200e3, R_EARTH_EQ_M + 2000e3),
    e=st.one_of(st.just(0.0), st.floats(0.0, 0.02)),
    i_rad=st.floats(0.01, math.pi - 0.01),
    raan_rad=angles,
    argp_rad=angles,
    nu_rad=angles,
)


def _wrap(x: float) -> float:
    return abs(math.remainder(x, 2 * math.pi))


@given(el=elements)
def test_pa06_state_elements_state_round_trip(el: KeplerElements) -> None:
    r, v = el.to_rv()
    r2, v2 = rv_to_elements(r, v).to_rv()
    assert np.linalg.norm(r2 - r) <= RT_POS_EPS_R * EPS * np.linalg.norm(r)
    assert np.linalg.norm(v2 - v) <= RT_VEL_EPS_V * EPS * np.linalg.norm(v)


@given(el=elements)
def test_pa06_elements_state_elements_round_trip(el: KeplerElements) -> None:
    back = rv_to_elements(*el.to_rv())
    sin_i = math.sin(el.i_rad)
    assert abs(back.a_m - el.a_m) <= RT_A_REL * el.a_m
    assert abs(back.e - el.e) <= RT_E_ABS
    assert abs(back.i_rad - el.i_rad) <= RT_I_RAD
    assert _wrap(back.raan_rad - el.raan_rad) * sin_i <= RT_RAAN_X_SIN_I
    u_err = _wrap(back.argp_rad + back.nu_rad - el.argp_rad - el.nu_rad)
    assert u_err * sin_i <= RT_U_X_SIN_I


def test_rv_to_elements_rejects_unbound_and_degenerate() -> None:
    r = [R_EARTH_EQ_M + 525e3, 0.0, 0.0]
    with pytest.raises(NonPhysicalStateError, match="not on a bound orbit"):
        rv_to_elements(r, [0.0, 0.0, 12_000.0])
    with pytest.raises(NonPhysicalStateError, match="rectilinear"):
        rv_to_elements(r, [100.0, 0.0, 0.0])


def _formation() -> tuple[KeplerElements, ...]:
    return along_track_formation(REFERENCE, n_spacecraft=4, spacing_m=SPACING_M)


def test_pa06_formation_elements_are_consistent() -> None:
    els = _formation()
    assert len(els) == 4
    for el in els:
        assert (el.a_m, el.e, el.i_rad, el.raan_rad, el.argp_rad) == (
            REFERENCE.a_m,
            REFERENCE.e,
            REFERENCE.i_rad,
            REFERENCE.raan_rad,
            REFERENCE.argp_rad,
        )
        assert el.period_s() == REFERENCE.period_s()  # equal periods: no secular drift
    du = SPACING_M / REFERENCE.a_m
    for k, el in enumerate(els):  # trailing by k * du (e = 0: true = mean anomaly)
        assert _wrap(el.nu_rad - (REFERENCE.nu_rad - k * du)) <= 4 * EPS


def test_pa06_formation_geometry_at_t0() -> None:
    a = REFERENCE.a_m
    du = SPACING_M / a
    states = [CartesianState(Frame.GCRS, EPOCH, 0, *el.to_rv()) for el in _formation()]
    chord = 2 * a * math.sin(du / 2)  # independent geometric expectation
    for lead, follow in itertools.pairwise(states):
        assert abs(np.linalg.norm(follow.r_m - lead.r_m) - chord) <= CHORD_T0_M
        rel = eci_to_ric(lead, follow)
        expected = np.array([-a * (1 - math.cos(du)), -a * math.sin(du), 0.0])
        assert np.linalg.norm(rel.r_m - expected) <= RIC_POS_T0_M
        assert np.linalg.norm(rel.v_mps) <= RIC_VEL_T0_MPS


def test_pa06_no_relative_drift_over_24h_two_body() -> None:
    states = [CartesianState(Frame.GCRS, EPOCH, 0, *el.to_rv()) for el in _formation()]
    traj = propagate_two_body(states, step_ns=10 * 10**9, n_steps=8640)
    y = traj.y
    sep = np.linalg.norm(y[:, 1:, :3] - y[:, :-1, :3], axis=2)
    assert np.max(np.abs(sep - sep[0])) <= SEP_CHANGE_24H_M
    ric0 = eci_to_ric(traj.state(0, 0), traj.state(0, 1))
    for k in range(0, len(traj.t_ns), 360):  # every hour
        rel = eci_to_ric(traj.state(k, 0), traj.state(k, 1))
        assert np.linalg.norm(rel.r_m - ric0.r_m) <= RIC_POS_CHANGE_24H_M
        assert np.linalg.norm(rel.v_mps) <= RIC_VEL_24H_MPS


def test_formation_rejects_invalid_requests() -> None:
    with pytest.raises(ValueError, match="n_spacecraft must be >= 1"):
        along_track_formation(REFERENCE, n_spacecraft=0, spacing_m=SPACING_M)
    with pytest.raises(TypeError):
        along_track_formation(REFERENCE, n_spacecraft=4.0, spacing_m=SPACING_M)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="spacing_m must be positive"):
        along_track_formation(REFERENCE, n_spacecraft=4, spacing_m=-1.0)
    with pytest.raises(ValueError, match="more than half"):
        along_track_formation(REFERENCE, n_spacecraft=4, spacing_m=8_000e3)

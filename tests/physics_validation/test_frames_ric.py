"""PA-04 (RIC part): ECI -> RIC -> ECI round trips, plus RIC convention checks.

Round-trip tolerance is set from the float64 round-off study in
``docs/NUMERICAL_MISSION_DESIGN.md`` §B.2.5 (observed worst case 0.077 eps|x|
over 20 000 samples; tolerance 0.5 eps|x| because Hypothesis searches inputs
adversarially). The ITRS part of PA-04 is not implemented yet.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.elements import KeplerElements
from astramesh.dynamics.frames import eci_to_ric, ric_basis, ric_to_eci
from astramesh.dynamics.state import CartesianState, Frame, FrameError

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
EPS = float(np.finfo(np.float64).eps)
ROUNDTRIP_TOL_EPS = 0.5  # §B.2.5

angles = st.floats(0.0, 2 * math.pi, allow_nan=False)
chief_elements = st.builds(
    KeplerElements,
    a_m=st.floats(R_EARTH_EQ_M + 200e3, R_EARTH_EQ_M + 2000e3),
    e=st.floats(0.0, 0.02),
    i_rad=st.floats(0.0, math.pi),
    raan_rad=angles,
    argp_rad=angles,
    nu_rad=angles,
)
offsets = st.lists(st.floats(-100e3, 100e3), min_size=3, max_size=3)
vel_offsets = st.lists(st.floats(-100.0, 100.0), min_size=3, max_size=3)


def _gcrs(r: np.ndarray, v: np.ndarray, t_ns: int = 0) -> CartesianState:
    return CartesianState(Frame.GCRS, EPOCH, t_ns, r, v)


@given(el=chief_elements, dr=offsets, dv=vel_offsets)
def test_pa04_eci_ric_eci_round_trip(el: KeplerElements, dr: list[float], dv: list[float]) -> None:
    rc, vc = el.to_rv()
    chief = _gcrs(rc, vc)
    deputy = _gcrs(rc + np.array(dr), vc + np.array(dv))
    back = ric_to_eci(chief, eci_to_ric(chief, deputy))
    assert back.frame is Frame.GCRS
    assert np.linalg.norm(back.r_m - deputy.r_m) <= ROUNDTRIP_TOL_EPS * EPS * np.linalg.norm(rc)
    assert np.linalg.norm(back.v_mps - deputy.v_mps) <= ROUNDTRIP_TOL_EPS * EPS * np.linalg.norm(vc)


@given(el=chief_elements)
def test_ric_basis_is_right_handed_orthonormal(el: KeplerElements) -> None:
    a = ric_basis(*el.to_rv())
    np.testing.assert_allclose(a @ a.T, np.eye(3), atol=4 * EPS)
    assert np.linalg.det(a) == pytest.approx(1.0, abs=4 * EPS)


def test_ric_axes_on_circular_orbit() -> None:
    el = KeplerElements.from_degrees(
        a_m=R_EARTH_EQ_M + 525e3, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=0.0
    )
    rc, vc = el.to_rv()
    chief = _gcrs(rc, vc)
    # A deputy displaced purely along the chief's velocity lies on +I.
    deputy = _gcrs(rc + 1000.0 * vc / np.linalg.norm(vc), vc)
    rel = eci_to_ric(chief, deputy)
    np.testing.assert_allclose(rel.r_m, [0.0, 1000.0, 0.0], atol=1e-6)
    # A co-moving deputy displaced radially has zero inertial velocity offset but,
    # in the rotating frame, appears to move backwards along -I at n * dr.
    deputy = _gcrs(rc * (1 + 1000.0 / np.linalg.norm(rc)), vc)
    rel = eci_to_ric(chief, deputy)
    n = el.mean_motion_radps()
    np.testing.assert_allclose(rel.r_m, [1000.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(rel.v_mps, [0.0, -n * 1000.0, 0.0], atol=1e-9)


def test_ric_rejects_mismatched_frames_and_times() -> None:
    rc = np.array([R_EARTH_EQ_M + 525e3, 0.0, 0.0])
    vc = np.array([0.0, 7600.0, 0.0])
    chief = _gcrs(rc, vc)
    with pytest.raises(FrameError, match="different times"):
        eci_to_ric(chief, _gcrs(rc, vc, t_ns=1))
    rel = CartesianState(Frame.RIC, EPOCH, 0, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    with pytest.raises(FrameError, match="expected a state in GCRS"):
        eci_to_ric(chief, rel)
    with pytest.raises(FrameError, match="expected a state in RIC"):
        ric_to_eci(chief, chief)

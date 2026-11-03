"""PA-04 (ITRS part): GCRS <-> ITRS round trips and independent external checks.

Tolerances come from ``scripts/studies/itrs_reference_errors.py`` as recorded in
``docs/NUMERICAL_MISSION_DESIGN.md`` §B.3, using the approved rule (DL-019).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.earth_frames import (
    earth_pole_gcrs,
    gcrs_to_itrs,
    itrs_to_gcrs,
    state_to_gcrs,
    state_to_itrs,
)
from astramesh.dynamics.elements import KeplerElements
from astramesh.dynamics.kepler import kepler_propagate
from astramesh.dynamics.state import CartesianState, Frame, FrameError, NonPhysicalStateError
from astramesh.dynamics.timescales import scenario_time

EPOCHS = (datetime(2025, 6, 1, tzinfo=UTC), datetime(2024, 5, 10, tzinfo=UTC))
SPAN_NS = 30 * 86_400 * 10**9
EPS = float(np.finfo(np.float64).eps)
ARCSEC = math.pi / (180 * 3600)

# §B.3 tolerances
ROUNDTRIP_POS_EPS_R = 20.0  # observed worst 3.8 eps|r|; Hypothesis-searched -> ~5x margin
ROUNDTRIP_VEL_MPS = 5e-8  # observed worst 9.6e-9 m/s; Hypothesis-searched -> ~5x margin
ROTATION_ANGLE_RAD = 2e-7  # observed worst 9.4e-8 rad
POLE_OFFSET_ARCSEC = 5.0  # observed worst |2.39|"; analytic nutation bound ~8"
FD_VELOCITY_MPS = 5e-5  # observed worst 2.3e-5 m/s (finite-difference truncation)

angles = st.floats(0.0, 2 * math.pi, allow_nan=False)
orbits = st.builds(
    KeplerElements,
    a_m=st.floats(R_EARTH_EQ_M + 200e3, R_EARTH_EQ_M + 2000e3),
    e=st.floats(0.0, 0.02),
    i_rad=st.floats(0.0, math.pi),
    raan_rad=angles,
    argp_rad=angles,
    nu_rad=angles,
)


@settings(max_examples=50)
@given(el=orbits, epoch=st.sampled_from(EPOCHS), t_ns=st.integers(0, SPAN_NS))
def test_pa04_gcrs_itrs_gcrs_round_trip(el: KeplerElements, epoch: datetime, t_ns: int) -> None:
    r, v = el.to_rv()
    ri, vi = gcrs_to_itrs(epoch, t_ns, r, v)
    rb, vb = itrs_to_gcrs(epoch, t_ns, ri, vi)
    assert np.linalg.norm(rb - r) <= ROUNDTRIP_POS_EPS_R * EPS * np.linalg.norm(r)
    assert np.linalg.norm(vb - v) <= ROUNDTRIP_VEL_MPS
    # Earth-fixed position has the same length (rotation only).
    assert np.linalg.norm(ri) == pytest.approx(np.linalg.norm(r), rel=8 * EPS)


def _grid(epoch: datetime, n: int = 97) -> np.ndarray:
    return np.linspace(0, SPAN_NS, n).astype(np.int64)


@pytest.mark.parametrize("epoch", EPOCHS)
def test_earth_rotation_angle_matches_iers_formula(epoch: datetime) -> None:
    """ITRS longitude of the GCRS x-axis equals -ERA (IERS 2010 eq. 5.15), UT1-based."""
    t_ns = _grid(epoch)
    probe = np.tile([R_EARTH_EQ_M, 0.0, 0.0], (len(t_ns), 1))
    xi, _ = gcrs_to_itrs(epoch, t_ns, probe, np.zeros_like(probe))
    t = scenario_time(epoch, t_ns).ut1
    du = (t.jd1 - 2451545.0) + t.jd2
    era = 2 * math.pi * np.mod(0.7790572732640 + 1.00273781191135448 * du, 1.0)
    diff = np.angle(np.exp(1j * (np.arctan2(xi[:, 1], xi[:, 0]) + era)))
    assert np.max(np.abs(diff)) <= ROTATION_ANGLE_RAD


@pytest.mark.parametrize("epoch", EPOCHS)
def test_pole_offset_matches_iau2006_precession(epoch: datetime) -> None:
    """Angle between GCRS and ITRS z-axes vs the IAU 2006 CIP X, Y polynomial."""
    t_ns = _grid(epoch)
    probe = np.tile([0.0, 0.0, R_EARTH_EQ_M], (len(t_ns), 1))
    zi, _ = gcrs_to_itrs(epoch, t_ns, probe, np.zeros_like(probe))
    angle_arcsec = np.arccos(np.clip(zi[:, 2] / np.linalg.norm(zi, axis=1), -1, 1)) / ARCSEC
    t = scenario_time(epoch, t_ns).tt
    tc = ((t.jd1 - 2451545.0) + t.jd2) / 36525.0
    x = -0.016617 + 2004.191898 * tc - 0.4297829 * tc**2 - 0.19861834 * tc**3
    y = -0.006951 - 0.025896 * tc - 22.4072747 * tc**2 + 0.00190059 * tc**3
    assert np.max(np.abs(angle_arcsec - np.hypot(x, y))) <= POLE_OFFSET_ARCSEC


@pytest.mark.parametrize("epoch", EPOCHS)
def test_itrs_velocity_matches_finite_difference(epoch: datetime) -> None:
    el = KeplerElements.from_degrees(
        a_m=R_EARTH_EQ_M + 525e3, e=0.0, i_deg=97.5, raan_deg=10.0, argp_deg=0.0, nu_deg=0.0
    )
    r0, v0 = el.to_rv()
    h_ns = 100_000_000
    zero = np.zeros(3)
    for t_ns in (0, 6 * 3600 * 10**9, 29 * 86_400 * 10**9):
        r, v = kepler_propagate(r0, v0, t_ns / 1e9)
        _, vi = gcrs_to_itrs(epoch, t_ns, r, v)
        rp, _ = kepler_propagate(r, v, h_ns / 1e9)
        rm, _ = kepler_propagate(r, v, -h_ns / 1e9)
        rip, _ = gcrs_to_itrs(epoch, t_ns + h_ns, rp, zero)
        rim, _ = gcrs_to_itrs(epoch, t_ns - h_ns, rm, zero)
        fd = (rip - rim) / (2 * h_ns / 1e9)
        assert np.linalg.norm(fd - vi) <= FD_VELOCITY_MPS


def test_state_wrappers_tag_frames() -> None:
    epoch = EPOCHS[0]
    r, v = KeplerElements(7e6, 0.0, 1.7, 0.0, 0.0, 0.0).to_rv()
    s = CartesianState(Frame.GCRS, epoch, 123, r, v)
    si = state_to_itrs(s)
    assert si.frame is Frame.ITRS
    assert si.t_ns == 123
    sb = state_to_gcrs(si)
    assert sb.frame is Frame.GCRS
    with pytest.raises(FrameError):
        state_to_itrs(si)
    with pytest.raises(FrameError):
        state_to_gcrs(s)


def test_vectorized_matches_scalar() -> None:
    epoch = EPOCHS[0]
    t_ns = np.array([0, 10**12, 2 * 10**12], dtype=np.int64)
    r = np.array([[7e6, 0, 0], [0, 7e6, 0], [0, 0, 7e6]], dtype=np.float64)
    v = np.array([[0, 7.5e3, 0], [0, 0, 7.5e3], [7.5e3, 0, 0]], dtype=np.float64)
    rv, vv = gcrs_to_itrs(epoch, t_ns, r, v)
    for k in range(3):
        rs, vs = gcrs_to_itrs(epoch, int(t_ns[k]), r[k], v[k])
        np.testing.assert_allclose(rv[k], rs, rtol=0, atol=1e-6)
        np.testing.assert_allclose(vv[k], vs, rtol=0, atol=1e-9)


def test_invalid_inputs_raise() -> None:
    epoch = EPOCHS[0]
    with pytest.raises(NonPhysicalStateError, match="finite"):
        gcrs_to_itrs(epoch, 0, [math.nan, 0, 0], [0, 0, 0])
    with pytest.raises(NonPhysicalStateError, match="shape"):
        gcrs_to_itrs(epoch, 0, [1.0, 2.0], [0, 0])
    with pytest.raises(ValueError, match="entries"):
        gcrs_to_itrs(epoch, np.array([0, 1]), np.ones((3, 3)), np.ones((3, 3)))


@pytest.mark.parametrize("epoch", EPOCHS)
@pytest.mark.parametrize("t_ns", [0, 3 * 86_400 * 10**9])
def test_erfa_pole_matches_astropy_transform(epoch: datetime, t_ns: int) -> None:
    """DL-031: the BLAS-free ERFA pole is the same vector Astropy's ITRS->GCRS gives.

    Round-off only (observed <= 1.1e-16 on unit vectors), so the bound is ~10x.
    """
    r, _ = itrs_to_gcrs(epoch, t_ns, [0.0, 0.0, 1.0], [0.0, 0.0, 0.0])
    pole = np.array(earth_pole_gcrs(epoch, t_ns))
    np.testing.assert_allclose(pole, r / np.linalg.norm(r), rtol=0, atol=1e-15)
    assert abs(float(np.linalg.norm(pole)) - 1.0) <= 1e-15

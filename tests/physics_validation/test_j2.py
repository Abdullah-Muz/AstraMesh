"""D1 (point mass + J2): PA-08 nodal precession and supporting checks.

Tolerances come from ``scripts/studies/j2_reference_errors.py`` as recorded in
``docs/NUMERICAL_MISSION_DESIGN.md`` §B.5 (rule DL-019).

The pole is a literal vector (the GCRS ITRS-z at 2025-06-01T00:00Z from
``earth_pole_gcrs``) so these tests do not depend on ERFA's last bits.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from astramesh.dynamics.constants import GM_EARTH_M3PS2, J2_EARTH, R_EARTH_EQ_M
from astramesh.dynamics.earth_frames import earth_pole_gcrs
from astramesh.dynamics.elements import KeplerElements, rv_to_elements
from astramesh.dynamics.forces import ForceModel, acceleration, potential, specific_energy
from astramesh.dynamics.state import CartesianState, Frame, NonPhysicalStateError
from astramesh.dynamics.twobody import Trajectory, propagate

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
NS = 10**9
DAY_S = 86_400
POLE = (0.002474555351741926, 3.4444800955196655e-05, 0.9999969376899945)
FM = ForceModel.with_j2(POLE)
CASES = {
    "ref_525km_circular": KeplerElements.from_degrees(
        a_m=R_EARTH_EQ_M + 525e3, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=0.0
    ),
    "eccentric_e0.1": KeplerElements.from_degrees(
        a_m=8_000e3, e=0.1, i_deg=51.6, raan_deg=40.0, argp_deg=30.0, nu_deg=10.0
    ),
}

# §B.5 tolerances
GRADIENT_REL = 5e-10  # observed 2.4e-10
POTENTIAL_REL = 2e-12  # observed 5.2e-13
#    (rel. energy drift, rel. pole-angular-momentum drift, max |r(10 s) - r(5 s)| [m])
INVARIANTS = {
    "ref_525km_circular": (9e-10, 5e-10, 0.9),  # observed 4.3e-10, 2.1e-10, 0.41 m
    "eccentric_e0.1": (4e-10, 2e-10, 0.5),  # observed 1.9e-10, 7.0e-11, 0.20 m
}
ORDER_BAND = (3.9, 5.1)  # observed 4.58 / 4.49 (same RK4 behaviour as D0, §B.2.3)
#                  relative difference, measured secular RAAN rate vs analytic (mean elements)
PRECESSION_REL = {"ref_525km_circular": 2e-3, "eccentric_e0.1": 4e-4}


def _j2_only_potential(r: np.ndarray) -> float:
    """Independent expression for the J2 part of the potential."""
    rn = float(np.linalg.norm(r))
    s = float(r @ np.array(POLE)) / rn
    return -GM_EARTH_M3PS2 / rn * J2_EARTH * (R_EARTH_EQ_M / rn) ** 2 * 0.5 * (3 * s * s - 1)


def _run(el: KeplerElements, step_s: float) -> Trajectory:
    step_ns = round(step_s * NS)
    s = CartesianState(Frame.GCRS, EPOCH, 0, *el.to_rv())
    return propagate([s], step_ns=step_ns, n_steps=DAY_S * NS // step_ns, forces=FM)


def test_pole_helper_matches_literal_and_precession_offset() -> None:
    pole = earth_pole_gcrs(EPOCH)
    assert np.linalg.norm(np.array(pole) - np.array(POLE)) <= 1e-12
    angle_arcsec = math.degrees(math.acos(pole[2])) * 3600
    assert 480 <= angle_arcsec <= 540  # ~510" of precession since J2000 (§B.3)


def test_j2_acceleration_is_gradient_of_independent_potential() -> None:
    rng = np.random.default_rng(1)
    point = ForceModel.two_body()
    h = 10.0
    for _ in range(300):
        d = rng.normal(size=3)
        r = d / np.linalg.norm(d) * rng.uniform(R_EARTH_EQ_M + 200e3, R_EARTH_EQ_M + 2000e3)
        a_j2 = acceleration(r[None], FM)[0] - acceleration(r[None], point)[0]
        grad = np.array(
            [
                (_j2_only_potential(r + h * e) - _j2_only_potential(r - h * e)) / (2 * h)
                for e in np.eye(3)
            ]
        )
        assert np.linalg.norm(grad - a_j2) <= GRADIENT_REL * np.linalg.norm(a_j2)
    r = np.array([4e6, 3e6, 4.5e6])
    j2_part = potential(r[None], FM)[0] - potential(r[None], point)[0]
    assert abs(j2_part - _j2_only_potential(r)) <= POTENTIAL_REL * abs(_j2_only_potential(r))


def test_zero_j2_reduces_to_point_mass_exactly() -> None:
    r = np.array([[7e6, 1e5, -3e5], [1e6, 6.5e6, 2e6]])
    np.testing.assert_array_equal(
        acceleration(r, ForceModel.two_body()), acceleration(r, ForceModel(j2=0.0, pole=POLE))
    )


@pytest.mark.parametrize("name", list(CASES))
def test_j2_invariants_and_step_convergence(name: str) -> None:
    """Invariants at 10 s; Richardson convergence from the 20/10/5 s runs."""
    tol_e, tol_h, tol_r = INVARIANTS[name]
    ys = {step: _run(CASES[name], step).y[:, 0, :] for step in (20.0, 10.0, 5.0)}
    y = ys[10.0]
    e = specific_energy(y, FM)
    hz = np.cross(y[:, :3], y[:, 3:]) @ np.array(POLE)
    assert np.max(np.abs((e - e[0]) / e[0])) <= tol_e
    assert np.max(np.abs((hz - hz[0]) / hz[0])) <= tol_h
    d1 = np.linalg.norm(ys[20.0][:, :3] - ys[10.0][::2, :3], axis=1)
    d2 = np.linalg.norm(ys[10.0][:, :3] - ys[5.0][::2, :3], axis=1)
    assert np.max(d2) <= tol_r  # ~ the 10 s error (Richardson)
    order = math.log2(float(d1[-1]) / float(d2[-1]))
    assert ORDER_BAND[0] <= order <= ORDER_BAND[1], order


def _pole_frame() -> np.ndarray:
    p = np.array(POLE)
    x = np.array([1.0, 0.0, 0.0]) - p[0] * p
    x /= np.linalg.norm(x)
    return np.stack((x, np.cross(p, x), p))


@pytest.mark.parametrize("name", list(CASES))
def test_pa08_nodal_precession_matches_analytic_j2_rate(name: str) -> None:
    """Secular RAAN rate about the pole vs -3/2 n J2 (R/p)^2 cos i (mean elements)."""
    el = CASES[name]
    traj = _run(el, 10.0)
    rot = _pole_frame()
    t = traj.t_ns.astype(np.float64) / NS
    osc = [rv_to_elements(rot @ row[:3], rot @ row[3:]) for row in traj.y[:, 0, :]]
    rate = float(np.polyfit(t, np.unwrap([o.raan_rad for o in osc]), 1)[0])
    a_mean = float(np.mean([o.a_m for o in osc]))
    i_mean = float(np.mean([o.i_rad for o in osc]))
    n = math.sqrt(GM_EARTH_M3PS2 / a_mean**3)
    p = a_mean * (1 - el.e**2)
    analytic = -1.5 * n * J2_EARTH * (R_EARTH_EQ_M / p) ** 2 * math.cos(i_mean)
    assert abs(rate - analytic) <= PRECESSION_REL[name] * abs(analytic)
    # Retrograde orbits precess eastward (positive rate), prograde westward.
    assert math.copysign(1.0, rate) == -math.copysign(1.0, math.cos(i_mean))


def test_force_model_rejects_invalid_parameters() -> None:
    with pytest.raises(NonPhysicalStateError, match="unit vector"):
        ForceModel(j2=J2_EARTH, pole=(0.0, 0.0, 2.0))
    with pytest.raises(NonPhysicalStateError, match="finite"):
        ForceModel(j2=math.nan, pole=POLE)
    with pytest.raises(NonPhysicalStateError):
        ForceModel(j2=-1e-3, pole=POLE)
    with pytest.raises(NonPhysicalStateError, match="3-vector"):
        ForceModel(j2=J2_EARTH, pole=(0.0, 1.0))  # type: ignore[arg-type]


def test_j2_propagation_into_earth_still_raises() -> None:
    s = CartesianState(Frame.GCRS, EPOCH, 0, [R_EARTH_EQ_M + 525e3, 0, 0], [-100.0, 0, 100.0])
    with pytest.raises(NonPhysicalStateError, match="below"):
        propagate([s], step_ns=10 * NS, n_steps=1000, forces=FM)


def test_model_ids() -> None:
    assert ForceModel.two_body().model_id == "D0-two-body-rk4"
    assert FM.model_id == "D1-j2-rk4"

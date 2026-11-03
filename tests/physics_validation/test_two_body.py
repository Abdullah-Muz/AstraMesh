"""Phase 1 physics acceptance tests PA-01, PA-02, PA-03 (D0 two-body).

Tolerances are NOT chosen here: each one is derived from the reference-error
study ``scripts/studies/d0_reference_errors.py`` as recorded in
``docs/NUMERICAL_MISSION_DESIGN.md`` §B.2. Rule used (§B.2.4): tolerance =
2 x the measured worst case at the nominal 10 s step over 24 h, rounded up to
one significant figure, and the analytic reference's own uncertainty must be
<= 1e-3 x the tolerance.
"""

from __future__ import annotations

import itertools
import math
from datetime import UTC, datetime

import numpy as np
import pytest

from astramesh.dynamics.constants import GM_EARTH_M3PS2, R_EARTH_EQ_M
from astramesh.dynamics.elements import KeplerElements
from astramesh.dynamics.kepler import kepler_propagate
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.twobody import (
    Trajectory,
    propagate_two_body,
    specific_angular_momentum,
    specific_energy,
)

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)  # docs/CONVENTIONS.md §2.3
HORIZON_S = 86_400  # 24 h nominal horizon (spec §3.2)
NOMINAL_STEP_NS = 10 * 10**9  # 10 s candidate step (spec §3.2)
NS = 10**9

# Must match CASES in scripts/studies/d0_reference_errors.py
CASES: dict[str, KeplerElements] = {
    "ref_525km_circular": KeplerElements.from_degrees(
        a_m=R_EARTH_EQ_M + 525e3, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=0.0
    ),
    "eccentric_e0.1": KeplerElements.from_degrees(
        a_m=8_000e3, e=0.1, i_deg=51.6, raan_deg=40.0, argp_deg=30.0, nu_deg=10.0
    ),
}


# Derived tolerances (docs/NUMERICAL_MISSION_DESIGN.md §B.2.4).
#                         (max |dr| m, max |dv| m/s, max rel. energy drift, max rel. |dh|)
TOLERANCES: dict[str, tuple[float, float, float, float]] = {
    "ref_525km_circular": (0.9, 1e-3, 9e-10, 5e-10),
    "eccentric_e0.1": (0.5, 4e-4, 4e-10, 2e-10),
}
# Analytic reference self-consistency (round-off only; §B.2.1).
REFERENCE_CONSISTENCY_M = 1e-5
# Observed-order band for PA-03 (§B.2.3): asymptotic order 4 (phase error),
# rising toward 5 where the h^5 energy-error-driven along-track drift dominates.
ORDER_BAND = (3.9, 5.1)
CONVERGENCE_STEPS_NS = (20 * NS, 10 * NS, 5 * NS)


def _initial(el: KeplerElements) -> CartesianState:
    r, v = el.to_rv()
    return CartesianState(Frame.GCRS, EPOCH, 0, r, v)


def _propagate(el: KeplerElements, step_ns: int) -> Trajectory:
    return propagate_two_body([_initial(el)], step_ns=step_ns, n_steps=HORIZON_S * NS // step_ns)


def _reference(el: KeplerElements, t_ns: np.ndarray) -> np.ndarray:
    r0, v0 = el.to_rv()
    out = np.empty((len(t_ns), 6))
    for k, t in enumerate(t_ns):
        out[k, :3], out[k, 3:] = kepler_propagate(r0, v0, int(t) / NS)
    return out


@pytest.fixture(scope="module", params=list(CASES))
def nominal(request: pytest.FixtureRequest) -> tuple[str, Trajectory, np.ndarray]:
    name: str = request.param
    traj = _propagate(CASES[name], NOMINAL_STEP_NS)
    return name, traj, _reference(CASES[name], traj.t_ns)


@pytest.mark.parametrize("name", list(CASES))
def test_analytic_references_agree(name: str) -> None:
    """Universal-variable propagation vs Kepler's-equation element advance (§B.2.1)."""
    el = CASES[name]
    r0, v0 = el.to_rv()
    for t in range(0, HORIZON_S + 1, 600):
        r_uv, _ = kepler_propagate(r0, v0, float(t))
        r_el, _ = el.advanced(float(t)).to_rv()
        assert np.linalg.norm(r_uv - r_el) <= REFERENCE_CONSISTENCY_M, t


@pytest.mark.parametrize("name", list(CASES))
def test_reference_uncertainty_is_negligible_vs_tolerance(name: str) -> None:
    assert TOLERANCES[name][0] >= 1e3 * REFERENCE_CONSISTENCY_M


def test_pa01_two_body_matches_analytic_reference(
    nominal: tuple[str, Trajectory, np.ndarray],
) -> None:
    name, traj, ref = nominal
    y = traj.y[:, 0, :]
    tol_r, tol_v, _, _ = TOLERANCES[name]
    assert np.max(np.linalg.norm(y[:, :3] - ref[:, :3], axis=1)) <= tol_r
    assert np.max(np.linalg.norm(y[:, 3:] - ref[:, 3:], axis=1)) <= tol_v


def test_pa02_invariants_conserved(nominal: tuple[str, Trajectory, np.ndarray]) -> None:
    name, traj, _ = nominal
    y = traj.y[:, 0, :]
    _, _, tol_e, tol_h = TOLERANCES[name]
    e = specific_energy(y, GM_EARTH_M3PS2)
    h = specific_angular_momentum(y)
    assert np.max(np.abs((e - e[0]) / e[0])) <= tol_e
    assert np.max(np.linalg.norm(h - h[0], axis=1)) / np.linalg.norm(h[0]) <= tol_h


@pytest.mark.parametrize("name", list(CASES))
def test_pa03_step_refinement_converges_at_rk4_order(name: str) -> None:
    el = CASES[name]
    errors = []
    for step_ns in CONVERGENCE_STEPS_NS:
        traj = _propagate(el, step_ns)
        ref = _reference(el, traj.t_ns[-1:])
        errors.append(float(np.linalg.norm(traj.y[-1, 0, :3] - ref[0, :3])))
    assert errors[0] > errors[1] > errors[2]
    for coarse, fine in itertools.pairwise(errors):
        order = math.log2(coarse / fine)
        assert ORDER_BAND[0] <= order <= ORDER_BAND[1], (errors, order)

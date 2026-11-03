"""PA-05 (explicit units/frames) and PA-10 (visible failure on invalid input)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pytest

from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.elements import KeplerElements, mean_to_true_anomaly, true_to_mean_anomaly
from astramesh.dynamics.kepler import kepler_propagate
from astramesh.dynamics.state import CartesianState, Frame, FrameError, NonPhysicalStateError
from astramesh.dynamics.twobody import propagate_two_body

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
R0 = [R_EARTH_EQ_M + 525e3, 0.0, 0.0]
V0 = [0.0, 0.0, 7600.0]


def _state(r: object = R0, v: object = V0, **kw: object) -> CartesianState:
    args: dict[str, object] = {"frame": Frame.GCRS, "epoch_utc": EPOCH, "t_ns": 0}
    args.update(kw)
    return CartesianState(r_m=r, v_mps=v, **args)  # type: ignore[arg-type]


# ----------------------------------------------------------------- PA-05 ----


def test_state_requires_frame_enum_and_integer_time() -> None:
    with pytest.raises(TypeError, match="frame must be a Frame"):
        _state(frame="GCRS")
    with pytest.raises(TypeError, match="t_ns must be an int"):
        _state(t_ns=0.0)
    with pytest.raises(ValueError, match="UTC"):
        _state(epoch_utc=datetime(2025, 6, 1))
    with pytest.raises(ValueError, match="offset of zero"):
        _state(epoch_utc=datetime(2025, 6, 1, tzinfo=timezone(timedelta(hours=1))))


def test_state_vectors_are_readonly_copies() -> None:
    r = np.array(R0)
    s = _state(r=r)
    r[0] = 0.0
    assert s.r_m[0] == R0[0]
    with pytest.raises(ValueError, match="read-only"):
        s.r_m[0] = 1.0


def test_elements_degrees_only_via_explicit_constructor() -> None:
    el = KeplerElements.from_degrees(
        a_m=7e6, e=0.0, i_deg=97.5, raan_deg=0.0, argp_deg=0.0, nu_deg=0.0
    )
    assert el.i_rad == pytest.approx(math.radians(97.5))
    with pytest.raises(NonPhysicalStateError, match=r"i_rad must be in \[0, pi\]"):
        KeplerElements(a_m=7e6, e=0.0, i_rad=97.5, raan_rad=0.0, argp_rad=0.0, nu_rad=0.0)


# ----------------------------------------------------------------- PA-10 ----


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_state_rejects_non_finite(bad: float) -> None:
    with pytest.raises(NonPhysicalStateError, match="finite"):
        _state(r=[bad, 0.0, 0.0])
    with pytest.raises(NonPhysicalStateError, match="finite"):
        _state(v=[0.0, bad, 0.0])


def test_state_rejects_wrong_shape() -> None:
    with pytest.raises(NonPhysicalStateError, match="shape"):
        _state(r=[1.0, 2.0])


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("a_m", -7e6, "a_m must be positive"),
        ("e", 1.0, "bound orbit"),
        ("e", 1.5, "bound orbit"),
        ("e", -0.1, "bound orbit"),
        ("a_m", math.nan, "finite"),
        ("a_m", R_EARTH_EQ_M - 1.0, "periapsis radius"),
    ],
)
def test_elements_reject_non_physical(field: str, value: float, match: str) -> None:
    kw = {"a_m": 7e6, "e": 0.0, "i_rad": 1.0, "raan_rad": 0.0, "argp_rad": 0.0, "nu_rad": 0.0}
    kw[field] = value
    with pytest.raises(NonPhysicalStateError, match=match):
        KeplerElements(**kw)


def test_elements_reject_periapsis_inside_earth() -> None:
    with pytest.raises(NonPhysicalStateError, match="periapsis radius"):
        KeplerElements(a_m=7e6, e=0.1, i_rad=1.0, raan_rad=0.0, argp_rad=0.0, nu_rad=0.0)


def test_kepler_reference_rejects_unbound_orbit() -> None:
    v_escape = math.sqrt(2 * 3.986004418e14 / R0[0])
    with pytest.raises(NonPhysicalStateError, match="not on a bound orbit"):
        kepler_propagate(R0, [0.0, 0.0, 1.01 * v_escape], 100.0)
    with pytest.raises(NonPhysicalStateError, match="finite"):
        kepler_propagate(R0, V0, math.nan)


def test_propagation_into_earth_raises_instead_of_continuing() -> None:
    # Nearly radial infall from 525 km altitude reaches the surface in minutes.
    s = _state(v=[-100.0, 0.0, 100.0])
    with pytest.raises(NonPhysicalStateError, match="below the Earth's equatorial radius"):
        propagate_two_body([s], step_ns=10 * 10**9, n_steps=1000)


def test_propagation_rejects_initial_state_inside_earth() -> None:
    with pytest.raises(NonPhysicalStateError, match="below"):
        propagate_two_body([_state(r=[1000.0, 0.0, 0.0])], step_ns=10**9, n_steps=1)


def test_propagation_rejects_mixed_frames_or_times() -> None:
    with pytest.raises(FrameError):
        propagate_two_body([_state(), _state(t_ns=1)], step_ns=10**9, n_steps=1)
    with pytest.raises(FrameError):
        propagate_two_body([_state(frame=Frame.RIC)], step_ns=10**9, n_steps=1)
    with pytest.raises(ValueError, match="step_ns must be positive"):
        propagate_two_body([_state()], step_ns=0, n_steps=1)
    with pytest.raises(ValueError, match="at least one"):
        propagate_two_body([], step_ns=10**9, n_steps=1)


@pytest.mark.parametrize("e", [0.0, 0.1, 0.5, 0.9, 0.99])
@pytest.mark.parametrize("nu", [-3.0, -1.0, 0.0, 0.5, 2.0, 3.1])
def test_kepler_equation_round_trip(e: float, nu: float) -> None:
    assert mean_to_true_anomaly(true_to_mean_anomaly(nu, e), e) == pytest.approx(nu, abs=1e-11)

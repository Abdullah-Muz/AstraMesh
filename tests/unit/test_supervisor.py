"""Protection supervisor rules (DL-054) and Gate P3 properties: SAFE always overrides,
invalid forecasts are not zero risk, no mode chatter under brief noise."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.supervisor import (
    MODES,
    NOMINAL,
    PROTECTIVE,
    SAFE,
    Supervisor,
    SupervisorSettings,
)

S = 10**9
STEP = 10 * S


def _sup() -> Supervisor:
    return Supervisor(SupervisorSettings())


def _feed(sup: Supervisor, t: int, *, batt: float = 0.8, flags: tuple[str, ...] = (),
          ratio: float | None = 0.1, enabled: bool = True) -> str:  # fmt: skip
    sup.update(t, battery_fraction=batt, critical_flags=flags, exposure_ratio=ratio,
               forecast_enabled=enabled)  # fmt: skip
    return sup.mode


def test_protective_entry_hysteresis_and_release_dwell() -> None:
    s = _sup()
    assert _feed(s, 0, ratio=0.99) == NOMINAL
    assert _feed(s, STEP, ratio=1.0) == PROTECTIVE
    assert _feed(s, 2 * STEP, ratio=0.9) == PROTECTIVE  # between release and protect: hold
    t0 = 3 * STEP
    for k in range(180):  # 30 min below release
        assert _feed(s, t0 + k * STEP, ratio=0.5) == PROTECTIVE
    assert _feed(s, t0 + 180 * STEP, ratio=0.5) == NOMINAL
    assert s.history[-1][3] == "exposure_released_after_dwell"


def test_release_dwell_restarts_on_spike_and_on_invalid_forecast() -> None:
    s = _sup()
    _feed(s, 0, ratio=1.5)
    t = STEP
    for _ in range(170):
        _feed(s, t, ratio=0.5)
        t += STEP
    _feed(s, t, ratio=0.85)  # back above release: dwell restarts
    t += STEP
    for _ in range(170):
        _feed(s, t, ratio=0.5)
        t += STEP
    _feed(s, t, ratio=None)  # invalid forecast: hold and restart dwell (never zero risk)
    t += STEP
    for _ in range(180):  # dwell starts at the first valid low sample: 180 intervals
        assert _feed(s, t, ratio=0.5) == PROTECTIVE
        t += STEP
    assert _feed(s, t, ratio=0.5) == NOMINAL


def test_invalid_forecast_holds_mode_and_is_logged_once_per_episode() -> None:
    s = _sup()
    for k in range(5):
        assert _feed(s, k * STEP, ratio=None) == NOMINAL  # not treated as zero, nor as high
    assert s.notes == [(0, "forecast_invalid_hold")]
    _feed(s, 5 * STEP, ratio=0.1)
    _feed(s, 6 * STEP, ratio=None)
    assert len(s.notes) == 2


@pytest.mark.parametrize("start_ratio", [0.1, 1.5])
def test_safe_overrides_from_any_mode(start_ratio: float) -> None:
    s = _sup()
    _feed(s, 0, ratio=start_ratio)
    assert _feed(s, STEP, flags=("F1",), ratio=start_ratio) == SAFE
    assert s.history[-1][3] == "critical_flag:F1"
    s2 = _sup()
    _feed(s2, 0, ratio=start_ratio)
    assert _feed(s2, STEP, batt=0.10, ratio=start_ratio) == SAFE  # battery_low (<= 10%)


def test_safe_exit_needs_clear_flags_battery_and_dwell_not_forecast() -> None:
    s = _sup()
    _feed(s, 0, flags=("F1",))
    t = STEP
    for _ in range(100):  # forecast excellent, but flag still set: stays SAFE
        assert _feed(s, t, flags=("F1",), ratio=0.0) == SAFE
        t += STEP
    for _ in range(100):  # flag clear but battery below 50%: stays SAFE
        assert _feed(s, t, batt=0.45, ratio=0.0) == SAFE
        t += STEP
    for _ in range(60):  # 10 min of good conditions
        assert _feed(s, t, batt=0.6, ratio=0.0) == SAFE
        t += STEP
    assert _feed(s, t, batt=0.6, ratio=0.0) == NOMINAL


def test_no_forecast_service_means_no_environmental_input() -> None:
    s = _sup()
    for k in range(10):
        assert _feed(s, k * STEP, ratio=None, enabled=False) == NOMINAL
    assert s.notes == []


def test_brief_noise_does_not_chatter() -> None:
    """Exposure jittering around both thresholds every step for 2 h: one entry, no release."""
    s = _sup()
    for k in range(720):
        _feed(s, k * STEP, ratio=1.01 if k % 2 else 0.79)
    assert [h[2] for h in s.history] == [PROTECTIVE]


inputs = st.lists(
    st.tuples(st.one_of(st.none(), st.floats(0.0, 1.0)),
              st.lists(st.sampled_from(["F1", "F2"]), max_size=2, unique=True),
              st.one_of(st.none(), st.floats(0.0, 3.0)), st.booleans()),
    max_size=400,
)  # fmt: skip


@settings(max_examples=200)
@given(inputs)
def test_properties_safe_wins_and_payload_only_in_nominal(
    seq: list[tuple[float | None, list[str], float | None, bool]],
) -> None:
    s = _sup()
    for k, (batt, flags, ratio, enabled) in enumerate(seq):
        s.update(k * STEP, battery_fraction=batt, critical_flags=tuple(flags),
                 exposure_ratio=ratio, forecast_enabled=enabled)  # fmt: skip
        assert s.mode in MODES
        assert s.allows_payload() == (s.mode == NOMINAL)
        if flags or (batt is not None and batt <= 0.10):
            assert s.mode == SAFE  # SAFE always overrides
    # Releases from PROTECTIVE are at least 30 min apart (no chatter).
    releases = [t for t, old, new, _ in s.history if old == PROTECTIVE and new == NOMINAL]
    entries = [t for t, old, new, _ in s.history if new == PROTECTIVE]
    for r in releases:
        assert any(r - e >= 1800 * S for e in entries if e < r)


@pytest.mark.parametrize(
    "kw",
    [{"safe_battery_fraction": 0.6}, {"release_ratio": 1.0}, {"release_ratio": 0.0},
     {"safe_exit_dwell_ns": -1}],
)  # fmt: skip
def test_settings_validated(kw: dict[str, float]) -> None:
    with pytest.raises(ValueError, match=r"need|dwell"):
        SupervisorSettings(**kw)  # type: ignore[arg-type]

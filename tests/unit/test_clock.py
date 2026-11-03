from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from astramesh.core.clock import NS_PER_S, ClockSpec, SimulationClock, seconds_to_ns

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("seconds", "expected_ns"),
    [
        (0, 0),
        (10, 10 * NS_PER_S),
        (0.5, 500_000_000),
        (0.1, 100_000_000),
        (1e-9, 1),
        (86400, 86_400 * NS_PER_S),
    ],
)
def test_seconds_to_ns_exact(seconds: float, expected_ns: int) -> None:
    assert seconds_to_ns(seconds) == expected_ns


@pytest.mark.parametrize("bad", [1.5e-10, 0.1234567891234])
def test_seconds_to_ns_rejects_sub_nanosecond(bad: float) -> None:
    with pytest.raises(ValueError, match="whole number of nanoseconds"):
        seconds_to_ns(bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_seconds_to_ns_rejects_nonfinite_and_negative(bad: float) -> None:
    with pytest.raises(ValueError, match=r"finite|non-negative"):
        seconds_to_ns(bad)


def test_seconds_to_ns_rejects_bool() -> None:
    with pytest.raises(TypeError):
        seconds_to_ns(True)


def test_clockspec_rejects_non_multiple_duration() -> None:
    with pytest.raises(ValueError, match="integer multiple"):
        ClockSpec.from_seconds(EPOCH, step_s=7, duration_s=60)


@pytest.mark.parametrize(
    "epoch",
    [datetime(2025, 6, 1), datetime(2025, 6, 1, tzinfo=timezone(timedelta(hours=3)))],
)
def test_clockspec_requires_utc_epoch(epoch: datetime) -> None:
    with pytest.raises(ValueError, match="UTC"):
        ClockSpec.from_seconds(epoch, step_s=10, duration_s=60)


def test_full_day_has_no_drift() -> None:
    """24 h at 10 s: the final time point is exactly 86 400 s (no float accumulation)."""
    clock = SimulationClock(ClockSpec.from_seconds(EPOCH, step_s=10, duration_s=86_400))
    ticks = list(clock.ticks())
    assert ticks == list(range(8_641))
    assert clock.time_ns == 86_400 * NS_PER_S
    assert clock.time_s == 86_400.0
    assert clock.at_end


def test_cannot_advance_past_end() -> None:
    clock = SimulationClock(ClockSpec.from_seconds(EPOCH, step_s=10, duration_s=20))
    clock.advance()
    clock.advance()
    with pytest.raises(RuntimeError):
        clock.advance()


def test_zero_duration_has_single_time_point() -> None:
    clock = SimulationClock(ClockSpec.from_seconds(EPOCH, step_s=10, duration_s=0))
    assert list(clock.ticks()) == [0]


@given(step_ns=st.integers(1, 10**12), n_steps=st.integers(0, 10_000))
def test_time_is_tick_times_step(step_ns: int, n_steps: int) -> None:
    spec = ClockSpec(epoch_utc=EPOCH, step_ns=step_ns, duration_ns=step_ns * n_steps)
    assert spec.n_steps == n_steps
    assert spec.time_ns(n_steps) == step_ns * n_steps
    with pytest.raises(ValueError, match="outside grid"):
        spec.time_ns(n_steps + 1)

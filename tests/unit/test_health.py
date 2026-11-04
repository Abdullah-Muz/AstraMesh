"""Health-belief rules (DL-052)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.health import (
    CONFIRMED,
    DEGRADED,
    HEALTHY,
    LOST,
    RECOVERING,
    SUSPECTED,
    UNKNOWN,
    HealthSettings,
    HealthTracker,
)

S = 10**9
CFG = HealthSettings(suspect_ns=90 * S, lost_ns=300 * S, recover_messages=2)


def _tracker() -> HealthTracker:
    return HealthTracker(CFG, ("a", "b"))


def test_timers_from_unknown_to_lost() -> None:
    h = _tracker()
    assert h.belief("a") == UNKNOWN
    h.tick(90 * S)
    assert h.belief("a") == UNKNOWN  # strictly more than 90 s needed
    h.tick(91 * S)
    assert h.belief("a") == SUSPECTED
    assert h.tick(301 * S) == ["a", "b"]
    assert h.belief("a") == LOST
    assert h.tick(400 * S) == []  # reported once


def test_heard_recovering_and_healthy_again() -> None:
    h = _tracker()
    h.heard("a", 10 * S, status=True, degraded=False)
    assert h.belief("a") == HEALTHY
    h.tick(400 * S)
    assert h.belief("a") == LOST
    h.heard("a", 401 * S, status=False, degraded=None)
    assert h.belief("a") == RECOVERING
    h.heard("a", 402 * S, status=False, degraded=None)  # non-status does not count
    h.heard("a", 430 * S, status=True, degraded=False)
    assert h.belief("a") == RECOVERING
    h.heard("a", 460 * S, status=True, degraded=True)
    assert h.belief("a") == DEGRADED  # self-reported degradation
    h.heard("a", 490 * S, status=True, degraded=False)
    assert h.belief("a") == HEALTHY
    assert [new for _, p, _, new in h.history if p == "a"] == [
        HEALTHY, LOST, RECOVERING, DEGRADED, HEALTHY,
    ]  # fmt: skip


def test_confirmed_failed_is_sticky_and_only_from_ground() -> None:
    h = _tracker()
    h.confirm_failed("b", 50 * S)
    assert h.belief("b") == CONFIRMED
    h.heard("b", 60 * S, status=True, degraded=False)
    h.tick(10_000 * S)
    assert h.belief("b") == CONFIRMED


@settings(max_examples=200)
@given(st.lists(st.tuples(st.booleans(), st.integers(0, 2000), st.booleans(),
                          st.sampled_from([None, True, False])), max_size=60))  # fmt: skip
def test_silence_and_messages_never_confirm_failure(
    ops: list[tuple[bool, int, bool, bool | None]],
) -> None:
    h = _tracker()
    t = 0
    for is_tick, dt, status, degraded in ops:
        t += dt * S
        if is_tick:
            h.tick(t)
        else:
            h.heard("a", t, status=status, degraded=degraded)
        assert h.belief("a") != CONFIRMED
        assert h.belief("b") != CONFIRMED


@pytest.mark.parametrize(("suspect", "lost", "rec"), [(0, 10, 1), (10, 10, 1), (10, 20, 0)])
def test_settings_validated(suspect: int, lost: int, rec: int) -> None:
    with pytest.raises(ValueError, match="suspect"):
        HealthSettings(suspect, lost, rec)

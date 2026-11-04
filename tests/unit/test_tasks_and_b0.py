"""Observation slots and the B0 static scheduler."""

from __future__ import annotations

import pytest

from astramesh.planning.static_b0 import plan_static
from astramesh.science.tasks import Task, TaskWindow, observation_slot, slots_overlap


def test_slot_centred_on_peak_and_shifted_inside_window() -> None:
    assert observation_slot(TaskWindow("a", 10, 30, 20), 6, 100) == (17, 23)
    assert observation_slot(TaskWindow("a", 10, 30, 11), 6, 100) == (10, 16)  # early peak
    assert observation_slot(TaskWindow("a", 10, 30, 30), 6, 100) == (25, 31)  # late peak
    assert observation_slot(TaskWindow("a", 10, 15, 12), 6, 100) == (10, 16)  # exact fit


def test_slot_impossible_when_window_short_or_at_scenario_end() -> None:
    assert observation_slot(TaskWindow("a", 10, 14, 12), 6, 100) is None
    # Last tick (99) has no step: window 94..99 holds only 5 usable steps.
    assert observation_slot(TaskWindow("a", 94, 99, 97), 6, 100) is None
    assert observation_slot(TaskWindow("a", 93, 99, 97), 6, 100) == (93, 99)
    with pytest.raises(ValueError, match="positive"):
        observation_slot(TaskWindow("a", 0, 10, 5), 0, 100)


def test_overlap() -> None:
    assert slots_overlap((0, 6), (5, 11))
    assert not slots_overlap((0, 6), (6, 12))


def _task(tid: str, prio: int, *windows: tuple[str, int, int]) -> Task:
    return Task(
        tid, f"R_{tid}", prio, tuple(TaskWindow(s, a, b, (a + b) // 2) for s, a, b in windows)
    )


def test_b0_priority_order_spread_and_one_task_at_a_time() -> None:
    catalog = (
        _task("T1", 1, ("s0", 0, 20), ("s1", 0, 20)),
        _task("T2", 5, ("s0", 0, 20)),  # only s0 can do it; higher priority goes first
        _task("T3", 3, ("s0", 2, 18), ("s1", 2, 18)),
    )
    plan = plan_static(catalog, ["s0", "s1"], n_steps=6, n_ticks=100,
                       storage_capacity_mb=10.0, data_mb_per_step=0.1)  # fmt: skip
    got = {a.task_id: a.spacecraft for a in plan.assignments}
    assert got["T2"] == "s0"
    assert got["T3"] == "s1"  # s0 busy at the same time (centred slots overlap)
    assert "T1" not in got  # both spacecraft busy in the overlapping slot
    assert plan.unassigned == ("T1",)
    assert not plan.privileged_information
    for sc in ("s0", "s1"):
        slots = [(a.start_tick, a.stop_tick) for a in plan.for_spacecraft(sc)]
        assert all(not slots_overlap(x, y) for i, x in enumerate(slots) for y in slots[i + 1 :])


def test_b0_respects_storage_and_is_deterministic() -> None:
    catalog = tuple(_task(f"T{i}", 1, ("s0", 20 * i, 20 * i + 10)) for i in range(5))
    kw = {"n_steps": 6, "n_ticks": 200, "storage_capacity_mb": 1.25, "data_mb_per_step": 0.1}
    plan = plan_static(catalog, ["s0"], **kw)  # type: ignore[arg-type]
    assert len(plan.assignments) == 2  # 0.6 MB each
    assert plan.unassigned == ("T2", "T3", "T4")
    assert plan == plan_static(catalog, ["s0"], **kw)  # type: ignore[arg-type]

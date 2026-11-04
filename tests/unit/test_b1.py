"""B1 centralized reference: optimality vs brute force, constraints, energy, determinism."""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.planning.centralized_b1 import EnergyModel, plan_centralized
from astramesh.planning.plans import Plan
from astramesh.planning.static_b0 import plan_static
from astramesh.science.tasks import Task, TaskWindow, observation_slot, slots_overlap

N_TICKS = 200
IDS = ["s0", "s1"]


def _energy(sunlit: bool = True, cap: float = 100.0, reserve: float = 0.0) -> EnergyModel:
    return EnergyModel(
        sunlit=np.full((N_TICKS, len(IDS)), sunlit), step_s=10.0, capacity_wh=cap,
        initial_fraction=1.0, charge_efficiency=1.0, generation_w=25.0, bus_w=8.0,
        payload_w=5.0, reserve_fraction=reserve,
    )  # fmt: skip


def _plan(catalog: tuple[Task, ...], storage: float = 100.0,
          energy: EnergyModel | None = None) -> Plan:  # fmt: skip
    return plan_centralized(
        catalog, IDS, n_steps=6, n_ticks=N_TICKS, storage_capacity_mb=storage,
        data_mb_per_step=0.1, energy=energy or _energy(),
    )  # fmt: skip


tasks_strategy = st.lists(
    st.tuples(
        st.integers(1, 5),  # priority
        st.lists(
            st.tuples(st.sampled_from(IDS), st.integers(0, 150), st.integers(5, 25)),
            min_size=1,
            max_size=2,
            unique_by=lambda w: w[0],
        ),
    ),
    min_size=1,
    max_size=6,
)


def _catalog(spec: list[tuple[int, list[tuple[str, int, int]]]]) -> tuple[Task, ...]:
    return tuple(
        Task(f"T{i}", f"R{i}", p, tuple(TaskWindow(s, a, a + n, a + n // 2) for s, a, n in ws))
        for i, (p, ws) in enumerate(spec)
    )


def _brute_force(catalog: tuple[Task, ...], storage: float) -> int:
    options = []
    for t in catalog:
        opts: list[tuple[str, tuple[int, int]] | None] = [None]
        for w in t.windows:
            slot = observation_slot(w, 6, N_TICKS)
            if slot is not None:
                opts.append((w.spacecraft, slot))
        options.append(opts)
    best = 0
    for combo in itertools.product(*options):
        used = [(t, c) for t, c in zip(catalog, combo, strict=True) if c is not None]
        no_overlap = all(
            not (a[1][0] == b[1][0] and slots_overlap(a[1][1], b[1][1]))
            for i, a in enumerate(used)
            for b in used[i + 1 :]
        )
        fits = all(sum(0.6 for _, c in used if c[0] == sc) <= storage + 1e-9 for sc in IDS)
        ok = no_overlap and fits
        if ok:
            best = max(best, sum(t.priority for t, _ in used))
    return best


@settings(max_examples=60, deadline=None)
@given(tasks_strategy, st.sampled_from([0.6, 1.2, 100.0]))
def test_b1_is_optimal_and_at_least_b0(
    spec: list[tuple[int, list[tuple[str, int, int]]]], storage: float
) -> None:
    catalog = _catalog(spec)
    plan = _plan(catalog, storage)
    done = {a.task_id for a in plan.assignments}
    value = sum(t.priority for t in catalog if t.task_id in done)
    assert value == _brute_force(catalog, storage)
    b0 = plan_static(catalog, IDS, n_steps=6, n_ticks=N_TICKS, storage_capacity_mb=storage,
                     data_mb_per_step=0.1)  # fmt: skip
    b0_value = sum(t.priority for t in catalog if t.task_id in {a.task_id for a in b0.assignments})
    assert value >= b0_value
    assert plan.privileged_information


def test_b1_is_deterministic_and_order_independent() -> None:
    catalog = _catalog([(2, [("s0", 10, 20), ("s1", 10, 20)]), (2, [("s0", 12, 20)]),
                        (1, [("s1", 60, 10), ("s0", 60, 10)])])  # fmt: skip
    p1 = _plan(catalog)
    p2 = _plan(tuple(reversed(catalog)))
    assert p1 == p2


def test_b1_energy_lazy_constraints_exclude_unpowered_observations() -> None:
    # Always dark, tiny battery: 8 W bus alone drains 1 Wh in 450 s; observations at
    # tick 60+ cannot start above the reserve, so B1 must exclude them.
    catalog = _catalog([(3, [("s0", 2, 10)]), (3, [("s0", 80, 10)])])
    plan = _plan(catalog, energy=_energy(sunlit=False, cap=1.0, reserve=0.2))
    got = {a.task_id for a in plan.assignments}
    assert got == {"T0"}
    assert plan.excluded == ("T1@s0",)


def test_b1_empty_catalog() -> None:
    plan = _plan(_catalog([(1, [("s0", 0, 3)])]))  # window too short for a 6-step slot
    assert plan.assignments == ()
    assert plan.unassigned == ("T0",)


@pytest.mark.parametrize("storage", [0.0, 0.59])
def test_b1_storage_too_small_for_any_observation(storage: float) -> None:
    plan = _plan(_catalog([(1, [("s0", 0, 20)])]), storage)
    assert plan.assignments == ()

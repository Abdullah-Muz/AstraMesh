"""Agents execute only their own uplinked plan, checked against their own housekeeping;
messages cannot change the plan (Gate P2)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.agent import AgentSettings, SpacecraftAgent
from astramesh.agents.packets import Housekeeping, PlannedObservation, PlanUplink
from astramesh.communications.messages import Delivery, Message, MessageType

STEP = 10
S = AgentSettings(status_interval_ns=30, status_lifetime_ns=60, battery_reserve_fraction=0.2)


def _agent(*obs: tuple[str, int, int]) -> SpacecraftAgent:
    a = SpacecraftAgent("sc00", ("sc01",), S)
    a.observe(PlanUplink(0, "B0", 1, tuple(PlannedObservation(*o) for o in obs)))
    return a


def _hk(t: int, wh: float = 80.0, used: float = 0.0, cap: float = 10.0) -> Housekeeping:
    return Housekeeping(t, wh, 100.0, used, cap)


def _run(a: SpacecraftAgent, ticks: range, **hk: float) -> list[str | None]:
    out = []
    for t in ticks:
        a.observe(_hk(t, **hk))
        out.append(a.payload_command(t, STEP, 0.1))
    return out


def test_executes_planned_interval_only() -> None:
    a = _agent(("T1", 20, 60))
    cmds = _run(a, range(0, 80, STEP))
    assert cmds == [None, None, "T1", "T1", "T1", "T1", None, None]
    assert a.execution_view()["believed_finished"] == 1


def test_declines_below_reserve_without_housekeeping_or_storage() -> None:
    a = _agent(("T1", 0, 30))
    assert a.payload_command(0, STEP, 0.1) is None  # no housekeeping yet
    assert a.execution_view()["declined"] == {"T1": "no_housekeeping"}
    b = _agent(("T1", 0, 30))
    assert _run(b, range(0, 30, STEP), wh=19.9) == [None, None, None]
    assert b.execution_view()["declined"] == {"T1": "battery_reserve"}
    c = _agent(("T1", 0, 30))
    assert _run(c, range(0, 30, STEP), used=9.8) == [None, None, None]  # needs 0.3 MB
    assert c.execution_view()["declined"] == {"T1": "storage"}


def test_stops_when_battery_empties_mid_observation() -> None:
    a = _agent(("T1", 0, 40))
    a.observe(_hk(0))
    assert a.payload_command(0, STEP, 0.1) == "T1"
    a.observe(_hk(10, wh=0.0))
    assert a.payload_command(10, STEP, 0.1) is None
    assert a.execution_view()["declined"] == {"T1": "resources_exhausted"}


def test_older_or_equal_plan_versions_are_rejected() -> None:
    a = _agent(("T1", 0, 30))
    a.observe(PlanUplink(5, "B0", 1, ()))
    assert a.plan_version == 1
    assert a.execution_view()["planned"] == 1
    assert a.drain_log()[-1] == {"kind": "plan_rejected", "reason": "not_newer", "version": 1}


msg = st.builds(
    lambda s, q, mt: Delivery(Message(s, q, 0, 10**6, mt, 99, {"plan": ["T9", 0, 100]}), "sc00", 5),
    st.sampled_from(["sc01", "sc00", "zz"]), st.integers(0, 20), st.sampled_from(list(MessageType)),
)  # fmt: skip


@settings(max_examples=200)
@given(st.lists(st.tuples(st.integers(0, 7), msg), max_size=30))
def test_messages_never_change_plan_or_commands(batch: list[tuple[int, Delivery]]) -> None:
    ref = _run(_agent(("T1", 20, 60)), range(0, 80, STEP))
    a = _agent(("T1", 20, 60))
    cmds = []
    for i, t in enumerate(range(0, 80, STEP)):
        a.receive_messages([d for k, d in batch if k == i])
        a.observe(_hk(t))
        cmds.append(a.payload_command(t, STEP, 0.1))
    assert cmds == ref
    assert a.plan_version == 1

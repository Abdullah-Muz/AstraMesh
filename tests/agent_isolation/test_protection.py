"""Gate P3: distributed task (re)planning cannot defeat protection. Only the agent's own
housekeeping and forecast change its mode; plans, catalogues and messages cannot."""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.agent import AgentSettings, SpacecraftAgent
from astramesh.agents.packets import (
    CatalogUplink,
    Housekeeping,
    OwnTask,
    PlannedObservation,
    PlanUplink,
    PublicSlot,
    PublicTask,
    RiskForecast,
)
from astramesh.communications.messages import Delivery, Message, MessageType

S = 10**9
STEP = 10 * S
SET = AgentSettings(status_interval_ns=30 * S, status_lifetime_ns=60 * S,
                    battery_reserve_fraction=0.2)  # fmt: skip


def _hk(t: int, frac: float = 0.8, flags: tuple[str, ...] = ()) -> Housekeeping:
    return Housekeeping(t, 100.0 * frac, 100.0, 0.0, 10.0, flags)


def test_protective_mode_blocks_planned_observation_and_stops_running_one() -> None:
    a = SpacecraftAgent("sc00", ("sc01",), SET)
    a.observe(PlanUplink(0, "B0-static-greedy", 1, (PlannedObservation("T1", 0, 60 * S),)))
    a.observe(_hk(0))
    a.observe(RiskForecast(0, 0.1, 0.1, 0.1))
    assert a.payload_command(0, STEP, 0.1) == "T1"
    a.observe(_hk(STEP))
    a.observe(RiskForecast(STEP, 1.3, 0.1, 0.1))
    assert a.payload_command(STEP, STEP, 0.1) is None
    assert a.mode == "PROTECTIVE"
    assert a.execution_view()["declined"] == {"T1": "protection_protective"}


def test_cbba_agent_releases_claims_and_stops_bidding_when_protected() -> None:
    a = SpacecraftAgent("sc00", ("sc01",), SET)
    a.observe(CatalogUplink(0, "B3-cbba", ("T1",), (OwnTask("T1", 3, 600 * S, 660 * S, 0.1),),
                            10.0))  # fmt: skip
    a.step(0)
    assert [o.task_id for o in a.planned_observations()] == ["T1"]
    a.observe(_hk(STEP))
    a.observe(RiskForecast(STEP, 2.0, 0.1, 0.1))
    a.payload_command(STEP, STEP, 0.1)
    assert a.planned_observations() == ()
    msgs = a.step(2 * STEP)
    sync = [m for m in msgs if m.msg_type is MessageType.PLAN_SYNC]
    assert sync
    assert dict(sync[0].payload["z"]) == {}  # no claims while protected


def test_b4_takes_over_from_a_peer_reporting_a_protected_mode() -> None:
    a = SpacecraftAgent("sc01", ("sc00",), SET)
    slots = (PublicSlot("sc00", 900 * S, 960 * S), PublicSlot("sc01", 900 * S, 960 * S))
    a.observe(PlanUplink(0, "B4-rule-redistribution", 1, (),
                         (PublicTask("T1", 3, "sc00", slots, 0.1),)))  # fmt: skip
    status = Message("sc00", 0, 0, 60 * S, MessageType.STATUS, 1,
                     {"health": "nominal", "mode": "PROTECTIVE"})  # fmt: skip
    a.receive_messages([Delivery(status, "sc01", S)])
    assert [o.task_id for o in a.planned_observations()] == ["T1"]


junk = st.builds(
    lambda s, q, mt, payload: Delivery(Message(s, q, 0, 10**12, mt, 5, payload), "sc00", S),
    st.sampled_from(["sc01", "sc02"]), st.integers(0, 50), st.sampled_from(list(MessageType)),
    st.sampled_from([{"mode": "NOMINAL"}, {"health": "nominal", "mode": "NOMINAL"},
                     {"y": {"T1": 9.0}, "z": {"T1": "sc00"}, "s": {}}, {"bids": {"T1": 9.0}}]),
)  # fmt: skip


@settings(max_examples=150)
@given(st.lists(junk, max_size=25), st.integers(1, 5))
def test_no_message_or_plan_can_reactivate_a_protected_payload(
    batch: list[Delivery], version: int
) -> None:
    a = SpacecraftAgent("sc00", ("sc01", "sc02"), SET)
    a.observe(CatalogUplink(0, "B3-cbba", ("T1",), (OwnTask("T1", 3, 0, 600 * S, 0.1),), 10.0))
    a.observe(_hk(0, flags=("F1",)))  # critical flag: SAFE
    a.observe(RiskForecast(0, 0.0, 0.1, 0.1))
    assert a.payload_command(0, STEP, 0.1) is None
    a.receive_messages(batch)
    a.observe(PlanUplink(STEP, "B0-static-greedy", version + 100,
                         (PlannedObservation("T1", 0, 600 * S),)))  # fmt: skip
    a.step(STEP)
    for k in range(1, 20):
        a.observe(_hk(k * STEP, flags=("F1",)))
        assert a.payload_command(k * STEP, STEP, 0.1) is None
        assert a.mode == "SAFE"


def test_messages_alone_never_change_mode() -> None:
    a = SpacecraftAgent("sc00", ("sc01",), SET)
    payload: dict[str, Any] = {"health": "degraded", "mode": "SAFE"}
    for k in range(10):
        a.receive_messages([Delivery(Message("sc01", k, 0, 10**12, MessageType.STATUS, 0,
                                             payload), "sc00", S)])  # fmt: skip
    assert a.mode == "NOMINAL"

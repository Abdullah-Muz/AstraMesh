"""Agent responses to beliefs (DL-052): B4 takeover, B3 claim forgetting, ground notices,
self-reported degradation. Only delivered messages and own packets drive them."""

from __future__ import annotations

from astramesh.agents.agent import AgentSettings, SpacecraftAgent
from astramesh.agents.health import CONFIRMED, LOST
from astramesh.agents.packets import (
    CatalogUplink,
    GroundNotice,
    Housekeeping,
    OwnTask,
    PlannedObservation,
    PlanUplink,
    PublicSlot,
    PublicTask,
)
from astramesh.communications.messages import Delivery, Message, MessageType

S = 10**9
SET = AgentSettings(status_interval_ns=30 * S, status_lifetime_ns=60 * S,
                    battery_reserve_fraction=0.2)  # fmt: skip


def _status(sender: str, seq: int, t: int, health: str = "nominal") -> Delivery:
    m = Message(sender, seq, t, t + 60 * S, MessageType.STATUS, 1, {"health": health})
    return Delivery(m, "sc01", t + S)


def _b4_agent() -> SpacecraftAgent:
    a = SpacecraftAgent("sc01", ("sc00", "sc02"), SET)
    slots = (PublicSlot("sc00", 1000 * S, 1060 * S), PublicSlot("sc01", 1000 * S, 1060 * S),
             PublicSlot("sc02", 1000 * S, 1060 * S))  # fmt: skip
    public = (PublicTask("T1", 3, "sc00", slots, 0.1),
              PublicTask("T2", 2, "sc02", slots[1:], 0.1))  # fmt: skip
    a.observe(PlanUplink(0, "B4-rule-redistribution", 1, (), public))
    return a


def test_b4_takes_over_a_lost_peers_future_tasks() -> None:
    a = _b4_agent()
    for k, t in enumerate(range(0, 400 * S, 30 * S)):  # sc02 keeps talking, sc00 never does
        a.receive_messages([_status("sc02", k, t)])
        a.step(t)
    assert a.health_beliefs()["sc00"] == LOST
    assert a.health_beliefs()["sc02"] != LOST
    assert [o.task_id for o in a.planned_observations()] == ["T1"]  # lowest available ID
    kinds = [e["kind"] for e in a.drain_log()]
    assert "task_taken_over" in kinds
    assert "belief_changed" in kinds


def test_non_redistributing_methods_do_not_react() -> None:
    a = SpacecraftAgent("sc01", ("sc00",), SET)
    a.observe(PlanUplink(0, "B0-static-greedy", 1, (PlannedObservation("T9", 900 * S, 960 * S),)))
    for t in range(0, 400 * S, 30 * S):
        a.step(t)
    assert a.health_beliefs()["sc00"] == LOST
    assert [o.task_id for o in a.planned_observations()] == ["T9"]


def test_cbba_timeout_forgets_lost_peer_claims_and_reclaims() -> None:
    a = SpacecraftAgent("sc01", ("sc00",), SET)
    a.observe(CatalogUplink(0, "B3-cbba+timeout", ("T1",), (OwnTask("T1", 3, 1000 * S, 1060 * S,
                                                                    0.1),), 10.0))  # fmt: skip
    claim = Message("sc00", 0, 0, 20 * S, MessageType.PLAN_SYNC, 0,
                    {"y": {"T1": 3.0}, "z": {"T1": "sc00"}, "s": {}})  # fmt: skip
    a.receive_messages([Delivery(claim, "sc01", S)])
    a.step(10 * S)
    assert a.planned_observations() == ()  # sc00 wins the tie
    for t in range(20 * S, 400 * S, 10 * S):
        a.step(t)
    assert a.health_beliefs()["sc00"] == LOST
    assert [o.task_id for o in a.planned_observations()] == ["T1"]  # re-auctioned to itself


def test_ground_notice_confirms_and_messages_do_not_undo_it() -> None:
    a = SpacecraftAgent("sc01", ("sc00",), SET)
    a.observe(GroundNotice(100 * S, ("sc00",)))
    a.receive_messages([_status("sc00", 0, 200 * S)])
    a.step(300 * S)
    assert a.health_beliefs()["sc00"] == CONFIRMED


def test_status_reports_own_degradation_from_housekeeping() -> None:
    a = SpacecraftAgent("sc01", ("sc00",), SET)
    a.observe(Housekeeping(0, 10.0, 100.0, 0.0, 10.0))  # 10% < 20% reserve
    (msg,) = a.step(0)
    assert msg.payload["health"] == "degraded"
    b = SpacecraftAgent("sc00", ("sc01",), SET)
    b.receive_messages([Delivery(msg, "sc00", S)])
    assert b.health_beliefs()["sc01"] == "DEGRADED"

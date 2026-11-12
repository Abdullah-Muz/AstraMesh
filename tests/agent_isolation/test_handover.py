"""Handover policy slot (DL-094): HO-02 rule, HO-03 window release and peer exclusion,
HO-04 the policy never changes a mode, HO-05 the B4 correction (agent level)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.agent import AgentSettings, SpacecraftAgent
from astramesh.agents.cbba import CbbaState
from astramesh.agents.handover import ForecastWindowRule, HandoverObservation
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
H = 3600 * S
RULE = ForecastWindowRule(0.7, H)


def _settings(policy: ForecastWindowRule | None = RULE, share: bool = True) -> AgentSettings:
    return AgentSettings(status_interval_ns=30 * S, status_lifetime_ns=60 * S,
                         handover=policy, share_window=share)  # fmt: skip


def _obs(ratio: float | None, mode: str = "NOMINAL") -> HandoverObservation:
    return HandoverObservation(100 * S, ratio, mode, (), {})


# --- HO-02 the rule -------------------------------------------------------------------


def test_ho02_rule_announces_exactly_at_threshold_or_while_protected() -> None:
    assert RULE.decide(_obs(0.69)).window_end_ns is None
    assert RULE.decide(_obs(0.7)).window_end_ns == 100 * S + H
    assert RULE.decide(_obs(None)).window_end_ns is None  # invalid inputs: no window
    assert RULE.decide(_obs(0.0, "PROTECTIVE")).window_end_ns == 100 * S + H
    assert RULE.decide(_obs(None, "RECOVERY")).window_end_ns == 100 * S + H
    assert RULE.decide(_obs(0.1, "SAFE")).window_end_ns is None


# --- HO-03 window release and peer exclusion (B4 and B3) ------------------------------


SLOTS = tuple(PublicSlot(sc, 1000 * S, 1060 * S) for sc in ("sc00", "sc01", "sc02"))


def _b4(me: str, owner: str, policy: ForecastWindowRule | None = RULE) -> SpacecraftAgent:
    peers = tuple(p for p in ("sc00", "sc01", "sc02") if p != me)
    a = SpacecraftAgent(me, peers, _settings(policy))
    mine = (PlannedObservation("T1", 1000 * S, 1060 * S),) if owner == me else ()
    a.observe(PlanUplink(0, "B4-rule-redistribution", 1, mine,
                         (PublicTask("T1", 3, owner, SLOTS, 0.1),)))  # fmt: skip
    a.observe(Housekeeping(0, 80.0, 100.0, 0.0, 10.0, ()))
    return a


def _status(sender: str, seq: int, t: int, window: int | None, receiver: str) -> Delivery:
    payload = {"health": "nominal", "mode": "STORM_WATCH", "window_end_ns": window}
    return Delivery(Message(sender, seq, t, t + 60 * S, MessageType.STATUS, 1, payload),
                    receiver, t + S)  # fmt: skip


def test_ho03_b4_announcer_hands_on_tasks_inside_its_window() -> None:
    a = _b4("sc01", "sc01")
    a.observe(RiskForecast(0, 0.8, 0.1, 0.1, issued_ns=0))  # STORM_WATCH, not protective
    a.payload_command(0, 10 * S, 0.1)
    msgs = a.step(0)
    assert a.mode == "STORM_WATCH"
    assert a.planned_observations() == ()  # T1 at 1000 s lies inside [0, 3600 s)
    status = next(m for m in msgs if m.msg_type is MessageType.STATUS)
    assert status.payload["window_end_ns"] == H


def test_ho03_b4_below_threshold_or_without_policy_keeps_its_task() -> None:
    for agent, ratio in ((_b4("sc01", "sc01"), 0.69), (_b4("sc01", "sc01", None), 0.8)):
        agent.observe(RiskForecast(0, ratio, 0.1, 0.1, issued_ns=0))
        agent.payload_command(0, 10 * S, 0.1)
        msgs = agent.step(0)
        assert [o.task_id for o in agent.planned_observations()] == ["T1"]
        status = next(m for m in msgs if m.msg_type is MessageType.STATUS)
        if agent.settings.handover is None:
            assert "window_end_ns" not in status.payload  # baseline messages unchanged


def test_ho03_b4_peer_takes_an_announced_task_and_skips_windowed_peers() -> None:
    taker = _b4("sc00", "sc01")
    taker.receive_messages([_status("sc01", 0, 0, H, "sc00")])
    assert [o.task_id for o in taker.planned_observations()] == ["T1"]  # lowest free ID
    skipper = _b4("sc02", "sc01")
    skipper.receive_messages([_status("sc00", 0, 0, H, "sc02")])  # sc00 is windowed too
    skipper.receive_messages([_status("sc01", 0, 0, H, "sc02")])
    assert [o.task_id for o in skipper.planned_observations()] == ["T1"]
    silent = _b4("sc00", "sc01")  # hears no window: behaves as the baseline
    silent.receive_messages([_status("sc01", 0, 0, None, "sc00")])
    assert silent.planned_observations() == ()


def test_ho03_cbba_releases_claims_and_does_not_bid_inside_the_window() -> None:
    cat = CatalogUplink(0, "B3-cbba", ("T1", "T2"),
                        (OwnTask("T1", 3, 1000 * S, 1060 * S, 0.1),
                         OwnTask("T2", 2, 2 * H, 2 * H + 60 * S, 0.1)), 10.0)  # fmt: skip
    c = CbbaState("sc01", cat)
    c.build_bundle(0)
    assert sorted(c.bundle) == ["T1", "T2"]
    assert c.release_before(H) == ("T1",)
    c.window_end_ns = H
    c.build_bundle(0)
    assert c.bundle == ["T2"]
    assert c.z["T1"] is None


# --- HO-04 the policy never changes a mode --------------------------------------------


@settings(max_examples=60, deadline=None)
@given(st.lists(st.one_of(st.none(), st.floats(0.0, 3.0)), min_size=5, max_size=40),
       st.floats(0.1, 1.5), st.integers(1, 7200))  # fmt: skip
def test_ho04_modes_are_identical_with_and_without_the_policy(
    ratios: list[float | None], theta: float, lead_s: int
) -> None:
    base = _b4("sc01", "sc01", None)
    cand = _b4("sc01", "sc01", ForecastWindowRule(theta, lead_s * S))
    for k, r in enumerate(ratios):
        t = k * 600 * S
        for a in (base, cand):
            a.observe(Housekeeping(t, 80.0, 100.0, 0.0, 10.0, ()))
            a.observe(RiskForecast(t, r, 0.1, 0.1, issued_ns=t))
            a.payload_command(t, 10 * S, 0.1)
            a.step(t)
        assert cand.mode == base.mode
    assert cand.mode_history() == base.mode_history()


# --- HO-05 the B4 correction ----------------------------------------------------------


def test_ho05_protected_b4_spacecraft_hands_its_tasks_on() -> None:
    a = _b4("sc01", "sc01", None)  # baseline: no handover policy
    a.observe(RiskForecast(0, 2.0, 0.1, 0.1))
    a.payload_command(0, 10 * S, 0.1)
    assert a.mode == "PROTECTIVE"
    assert a.planned_observations() == ()  # handed on to a peer and dropped (DL-094)

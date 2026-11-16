"""B4 ownership re-sync (DL-122): claims in status, orphan re-assignment after the grace
period, conflict resolution (in progress first, then lowest ID), the claim age limit,
tasking-only claims, and the switch-off behaviour (agent level)."""

from __future__ import annotations

import pytest

from astramesh.agents.agent import AgentSettings, OwnershipSync, SpacecraftAgent
from astramesh.agents.packets import (
    Housekeeping,
    PlannedObservation,
    PlanUplink,
    PublicSlot,
    PublicTask,
    RiskForecast,
)
from astramesh.communications.messages import Delivery, Message, MessageType

S = 10**9
H = 3600 * S
IDS = ("sc00", "sc01", "sc02")
SYNC = OwnershipSync(horizon_ns=3 * H, grace_status_intervals=2)


def _agent(me: str, owner: str, start_s: dict[str, int] | None = None,
           sync: OwnershipSync | None = SYNC) -> SpacecraftAgent:  # fmt: skip
    """B4 agent whose view gives T1 to ``owner``; slots start at 1 000 s unless given."""
    starts = {sc: 1000 for sc in IDS} | (start_s or {})
    slots = tuple(PublicSlot(sc, starts[sc] * S, (starts[sc] + 60) * S) for sc in IDS)
    a = SpacecraftAgent(me, tuple(p for p in IDS if p != me),
                        AgentSettings(status_interval_ns=30 * S, status_lifetime_ns=60 * S,
                                      ownership_sync=sync))  # fmt: skip
    mine = ((PlannedObservation("T1", starts[me] * S, (starts[me] + 60) * S),)
            if owner == me else ())  # fmt: skip
    a.observe(PlanUplink(0, "B4-rule-redistribution", 1, mine,
                         (PublicTask("T1", 3, owner, slots, 0.1),)))  # fmt: skip
    a.observe(Housekeeping(0, 80.0, 100.0, 0.0, 10.0, ()))
    return a


def _status(sender: str, seq: int, t_s: int, receiver: str, claims: tuple[str, ...] | None,
            mode: str = "NOMINAL") -> Delivery:  # fmt: skip
    payload: dict[str, object] = {"health": "nominal", "mode": mode}
    if claims is not None:
        payload["claims"] = claims
    t = t_s * S
    return Delivery(Message(sender, seq, t, t + 60 * S, MessageType.STATUS, 1, payload),
                    receiver, t)  # fmt: skip


def _owner(a: SpacecraftAgent) -> str | None:
    return a._public["T1"].owner


def _planned(a: SpacecraftAgent) -> list[str]:
    return [o.task_id for o in a.planned_observations()]


def test_status_carries_claims_only_when_on_and_tasking() -> None:
    on, off = _agent("sc00", "sc00"), _agent("sc00", "sc00", sync=None)
    for a in (on, off):
        a.payload_command(0, 10 * S, 0.1)
    st_on = next(m for m in on.step(0) if m.msg_type is MessageType.STATUS)
    st_off = next(m for m in off.step(0) if m.msg_type is MessageType.STATUS)
    assert tuple(st_on.payload["claims"]) == ("T1",)
    assert "claims" not in st_off.payload  # recorded B4 messages unchanged
    far = _agent("sc00", "sc00", {"sc00": 4 * 3600})  # beyond the 3 h horizon
    far.payload_command(0, 10 * S, 0.1)
    st = next(m for m in far.step(0) if m.msg_type is MessageType.STATUS)
    assert tuple(st.payload["claims"]) == ()
    prot = _agent("sc00", "sc00")
    prot.observe(RiskForecast(0, 5.0, 0.1, 0.1, issued_ns=0))  # protective
    prot.payload_command(0, 10 * S, 0.1)
    st = next(m for m in prot.step(0) if m.msg_type is MessageType.STATUS)
    assert prot.mode not in ("NOMINAL", "STORM_WATCH")
    assert tuple(st.payload["claims"]) == ()  # nothing claimed outside the tasking modes


def test_orphan_is_reassigned_by_b4_rule_after_the_grace_period() -> None:
    # split: sc00's view gives T1 to sc01, which does not claim it (its view: sc00)
    a = _agent("sc00", "sc01")
    a.receive_messages([_status("sc01", 0, 30, "sc00", ())])  # within 2 x 30 s grace
    assert _owner(a) == "sc01"
    assert _planned(a) == []
    a.receive_messages([_status("sc01", 1, 61, "sc00", ())])
    assert _owner(a) == "sc00"  # lowest eligible ID, the silent owner excluded
    assert _planned(a) == ["T1"]


def test_orphan_rule_ignores_slots_outside_the_horizon_or_already_started() -> None:
    late = _agent("sc00", "sc01", {"sc01": 4 * 3600})  # sender's slot beyond 3 h
    late.receive_messages([_status("sc01", 0, 100, "sc00", ())])
    assert _owner(late) == "sc01"
    begun = _agent("sc00", "sc01", {"sc01": 50})  # sender's slot already started
    begun.receive_messages([_status("sc01", 0, 100, "sc00", ())])
    assert _owner(begun) == "sc01"


def test_conflict_goes_to_the_lowest_id_and_the_loser_drops_its_task() -> None:
    b = _agent("sc01", "sc01")  # both sc00 and sc01 own T1 in their own views
    b.receive_messages([_status("sc00", 0, 10, "sc01", ("T1",))])
    assert _owner(b) == "sc00"
    assert _planned(b) == []
    a = _agent("sc00", "sc00")
    a.receive_messages([_status("sc01", 0, 10, "sc00", ("T1",))])
    assert _owner(a) == "sc00"
    assert _planned(a) == ["T1"]


def test_a_claimant_already_observing_wins_the_conflict() -> None:
    a = _agent("sc00", "sc00", {"sc01": 5})  # sc01's slot began at 5 s
    a.receive_messages([_status("sc01", 0, 10, "sc00", ("T1",))])
    assert _owner(a) == "sc01"
    assert _planned(a) == []


@pytest.mark.parametrize(("t_s", "winner"), [(50, "sc00"), (200, "sc01")])
def test_stale_claims_are_ignored(t_s: int, winner: str) -> None:
    c = _agent("sc02", "sc00")
    c.receive_messages([_status("sc00", 0, 0, "sc02", ("T1",))])  # sc00 claims at 0 s
    c.receive_messages([_status("sc01", 0, t_s, "sc02", ("T1",))])
    assert _owner(c) == winner  # sc00's claim counts only while younger than 60 s


def test_switched_off_agents_ignore_claims() -> None:
    a = _agent("sc00", "sc01", sync=None)
    a.receive_messages([_status("sc01", 0, 100, "sc00", ())])
    a.receive_messages([_status("sc02", 0, 100, "sc00", ("T1",))])
    assert _owner(a) == "sc01"
    assert _planned(a) == []


def test_settings_validation() -> None:
    with pytest.raises(ValueError, match="positive horizon"):
        OwnershipSync(horizon_ns=0, grace_status_intervals=2)
    with pytest.raises(ValueError, match="grace"):
        OwnershipSync(horizon_ns=H, grace_status_intervals=0)

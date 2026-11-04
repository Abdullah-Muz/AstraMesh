"""Gate P2: unhandled, malformed, expired, duplicate or stale messages cannot alter
an agent's plan or peer state (spec §5.3 duplicate/expiry/ordering rules)."""

from __future__ import annotations

import copy
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.agent import REJECT_REASONS, AgentSettings, SpacecraftAgent
from astramesh.agents.packets import NavigationFix
from astramesh.communications.messages import Delivery, Message, MessageType

S = AgentSettings(status_interval_ns=30, status_lifetime_ns=60)


def _agent() -> SpacecraftAgent:
    return SpacecraftAgent("sc00", ("sc01", "sc02"), S)


def _msg(sender: str = "sc01", seq: int = 0, created: int = 0, expires: int = 60,
         mtype: MessageType = MessageType.STATUS, r: Any = (1.0, 2.0, 3.0)) -> Message:  # fmt: skip
    return Message(sender, seq, created, expires, mtype, 0, {"r_m": list(r)})


def _deliver(m: Message, t: int = 1, to: str = "sc00") -> Delivery:
    return Delivery(m, to, t)


def test_accepts_valid_status_and_records_peer_state() -> None:
    a = _agent()
    a.receive_messages([_deliver(_msg(seq=3), t=5)])
    v = a.peer_view()["sc01"]
    assert v == {"newest_seq": 3, "last_heard_ns": 5, "reported_plan_version": 0}
    assert a.rejected_counts() == dict.fromkeys(REJECT_REASONS, 0)


def test_each_rejection_reason() -> None:
    a = _agent()
    a.receive_messages([_deliver(_msg(seq=5))])
    cases = [
        ("malformed", "not a delivery"),
        ("malformed", _deliver(_msg(seq=6), to="sc02")),
        ("from_self", _deliver(_msg(sender="sc00", seq=6))),
        ("unknown_sender", _deliver(_msg(sender="sc99", seq=6))),
        ("expired", _deliver(_msg(seq=6, expires=10), t=10)),
        ("duplicate", _deliver(_msg(seq=5))),
        ("unhandled_type", _deliver(_msg(seq=6, mtype=MessageType.TASK_BID))),
        ("stale", _deliver(_msg(seq=4))),
    ]
    for reason, d in cases:
        before = (copy.deepcopy(a.peer_view()), a.plan_version, a.n_accepted)
        a.receive_messages([d])  # type: ignore[list-item]
        assert (a.peer_view(), a.plan_version, a.n_accepted) == before, reason
        assert a.drain_log()[-1]["reason"] == reason
    counts = a.rejected_counts()
    assert counts["malformed"] == 2
    assert all(
        counts[r] == 1 for r in REJECT_REASONS if r not in ("malformed", "malformed_payload")
    )
    assert counts["malformed_payload"] == 0  # only agents running B2/B3 handle payload types


def test_out_of_order_older_status_does_not_overwrite_newer() -> None:
    a = _agent()
    a.receive_messages([_deliver(_msg(seq=2, r=(9.0, 9.0, 9.0)), t=40)])
    a.receive_messages([_deliver(_msg(seq=1, r=(1.0, 1.0, 1.0)), t=41)])
    assert a._peer_table["sc01"].reported_r_m == (9.0, 9.0, 9.0)
    assert a.rejected_counts()["stale"] == 1


def test_status_uses_only_past_navigation() -> None:
    a = _agent()
    (m0,) = a.step(0)
    assert m0.payload["r_m"] is None  # no fix yet: reports nothing rather than inventing
    a.observe(NavigationFix(10, (1.0, 2.0, 3.0), (0.0, 0.0, 0.0), 10.0, 0.1))
    a.observe(NavigationFix(5, (7.0, 7.0, 7.0), (0.0, 0.0, 0.0), 10.0, 0.1))  # older: ignored
    assert a.step(20) == []  # not due yet
    (m1,) = a.step(30)
    assert m1.payload["r_m"] == (1.0, 2.0, 3.0)
    assert m1.payload["nav_t_ns"] <= m1.created_ns
    assert (m1.seq, m1.expires_ns - m1.created_ns) == (1, 60)


junk_delivery = st.one_of(
    st.none(),
    st.integers(),
    st.text(max_size=5),
    st.builds(
        lambda s, q, c, life, t, mt, to: Delivery(
            Message(s, q, c, c + life, mt, 7, {"r_m": [0.0, 0.0, 0.0]}), to, c + t
        ),
        st.sampled_from(["sc00", "sc01", "sc02", "sc03", "x"]),
        st.integers(0, 50),
        st.integers(0, 1000),
        st.integers(1, 100),
        st.integers(0, 200),
        st.sampled_from(list(MessageType)),
        st.sampled_from(["sc00", "sc01"]),
    ),
)


@settings(max_examples=300)
@given(st.lists(junk_delivery, max_size=40))
def test_no_delivery_sequence_changes_the_plan_or_breaks_peer_invariants(
    batch: list[Any],
) -> None:
    a = _agent()
    a.receive_messages(batch)
    assert a.plan_version == 0  # no message type alters plans in this increment
    accepted = [
        d for d in batch
        if isinstance(d, Delivery) and d.receiver == "sc00" and d.message.sender in ("sc01", "sc02")
        and d.message.msg_type is MessageType.STATUS and d.delivered_ns < d.message.expires_ns
    ]  # fmt: skip
    for peer in ("sc01", "sc02"):
        seqs = [d.message.seq for d in accepted if d.message.sender == peer]
        newest = a.peer_view()[peer]["newest_seq"]
        assert newest == (max(seqs) if seqs else -1)  # never regresses, never invented
    assert a.n_accepted + sum(a.rejected_counts().values()) == len(batch)

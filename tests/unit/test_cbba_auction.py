"""B3 CBBA (P06) and B2 auction, at the algorithm level (no network)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.auction import AuctionState
from astramesh.agents.cbba import CbbaState, outbids
from astramesh.agents.packets import CatalogUplink, OwnTask

S = 10**9


def _catalog(algo: str, me_tasks: list[tuple[str, int, int]], order: list[str],
             storage: float = 100.0) -> CatalogUplink:  # fmt: skip
    own = tuple(OwnTask(t, p, start * S, (start + 60) * S, 0.075) for t, p, start in me_tasks)
    return CatalogUplink(0, algo, tuple(order), own, storage)


Winners = dict[str, set[str]]


def _run_cbba(spec: dict[str, list[tuple[str, int, int]]], order: list[str],
              storage: float = 100.0, max_rounds: int = 200) -> tuple[Winners, int]:  # fmt: skip
    """Synchronous rounds, lossless all-to-all messages, until nothing changes.

    Returns the winners and the index of the first round after which nothing changed."""
    agents = {a: CbbaState(a, _catalog("B3-cbba", t, order, storage)) for a, t in spec.items()}

    def snapshot() -> Any:
        return {a: (tuple(s.bundle), dict(s.y), dict(s.z)) for a, s in agents.items()}

    prev = None
    for r in range(max_rounds):
        now = r * 10 * S
        for s in agents.values():
            s.build_bundle(now)
        msgs = {a: s.message_payload() for a, s in agents.items()}
        for a, s in agents.items():
            for k in sorted(agents):
                if k != a:
                    s.receive(k, msgs[k], now + S)
        cur = snapshot()
        if cur == prev:
            return {a: {t.task_id for t in s.winning()} for a, s in agents.items()}, r - 1
        prev = cur
    raise AssertionError("CBBA did not converge")


def _sga(spec: dict[str, list[tuple[str, int, int]]], order: list[str],
         storage: float = 100.0) -> dict[str, set[str]]:  # fmt: skip
    """Sequential greedy algorithm (P06 Algorithm 4) with the same tie rules."""
    pos = {t: i for i, t in enumerate(order)}
    agents = sorted(spec)
    own = {a: {t: (p, st) for t, p, st in spec[a]} for a in agents}
    bundles: dict[str, list[str]] = {a: [] for a in agents}
    taken: set[str] = set()

    def score(a: str, t: str) -> int:
        if t in taken or t not in own[a]:
            return 0
        p, start = own[a][t]
        if start * S <= 0:
            return 0
        for b in bundles[a]:
            bs = own[a][b][1]
            if bs < start + 60 and start < bs + 60:
                return 0
        if 0.075 * (len(bundles[a]) + 1) > storage:
            return 0
        return p

    while True:
        best = max(((score(a, t), -agents.index(a), -pos[t], a, t) for a in agents for t in order),
                   default=None)  # fmt: skip
        if best is None or best[0] <= 0:
            return {a: set(b) for a, b in bundles.items()}
        _, _, _, a, t = best
        bundles[a].append(t)
        taken.add(t)


instance = st.integers(2, 4).flatmap(lambda n_agents: st.integers(1, 7).flatmap(
    lambda n_tasks: st.tuples(
        st.just(n_agents),
        st.lists(st.lists(st.integers(1, 5), min_size=n_tasks, max_size=n_tasks),
                 min_size=n_agents, max_size=n_agents),  # per-agent scores (still DMG)
        st.lists(st.lists(st.one_of(st.none(), st.integers(1, 30).map(lambda x: 100_000 + x * 20)),
                          min_size=n_tasks, max_size=n_tasks),
                 min_size=n_agents, max_size=n_agents),  # per agent: slot start or None
    )))  # fmt: skip


@settings(max_examples=150, deadline=None)
@given(instance, st.sampled_from([100.0, 0.15]))
def test_cbba_equals_sequential_greedy_without_loss(inst: Any, storage: float) -> None:
    """P06 Theorem 1 (DMG scores, synchronous, connected, lossless): CBBA = SGA.

    Slots start after 100 000 s, long after convergence, so scores do not change with
    time during the test (Theorem 1 assumes static scores; DL-045 makes a task score 0
    once its slot has started).
    """
    n_agents, prios, starts = inst
    order = [f"T{j}" for j in range(len(prios[0]))]
    spec = {
        f"sc{a:02d}": [(order[j], prios[a][j], s) for j, s in enumerate(starts[a]) if s is not None]
        for a in range(n_agents)
    }
    cbba, rounds = _run_cbba(spec, order, storage)
    assert cbba == _sga(spec, order, storage)
    # Theorem 1 bound: converged within N_min * D rounds (all-to-all, so D = 1).
    n_min = min(len(order), n_agents * len(order))
    assert rounds <= n_min
    claimed = [t for ts in cbba.values() for t in ts]
    assert len(claimed) == len(set(claimed))  # conflict-free


def test_outbids_ties_to_lower_id() -> None:
    assert outbids(5.0, "sc00", 5.0, "sc01")
    assert not outbids(5.0, "sc01", 5.0, "sc00")
    assert outbids(1.0, "sc03", 0.0, None)
    assert not outbids(0.0, None, 0.0, None)
    assert outbids(6.0, "sc03", 5.0, "sc00")


def test_release_resets_later_tasks_per_eq6() -> None:
    order = ["A", "B", "C"]
    s = CbbaState("sc01", _catalog("B3-cbba", [("A", 3, 100), ("B", 2, 300), ("C", 1, 500)], order))
    s.build_bundle(0)
    assert s.bundle == ["A", "B", "C"]
    s.receive("sc00", {"y": {"A": 3.0}, "z": {"A": "sc00"}, "s": {}}, S)  # sc00 wins A (tie)
    assert s.bundle == []
    assert (s.y["A"], s.z["A"]) == (3.0, "sc00")
    assert (s.y["B"], s.z["B"], s.y["C"], s.z["C"]) == (0.0, None, 0.0, None)
    assert s.s["sc00"] == S


def test_cbba_payload_validation() -> None:
    ok = {"y": {"A": 1.0}, "z": {"A": "sc00"}, "s": {"sc00": 5}}
    assert CbbaState.valid_payload(ok)
    bad_payloads: list[dict[str, Any]] = [
        {"y": {"A": 1.0}, "z": {}, "s": {}},
        {"y": {"A": -1.0}, "z": {"A": "x"}, "s": {}},
        {"y": {"A": True}, "z": {"A": "x"}, "s": {}},
        {"y": {}, "z": {}},
        {},
    ]
    for bad in bad_payloads:
        assert not CbbaState.valid_payload(bad)


def _auction(me: str, tasks: list[tuple[str, int, int]], order: list[str]) -> AuctionState:
    return AuctionState(me, _catalog("B2-auction", tasks, order), 5 * S)


def test_auction_all_bids_received_is_conflict_free() -> None:
    order = ["A", "B"]
    a = _auction("sc00", [("A", 3, 100)], order)
    b = _auction("sc01", [("A", 3, 100), ("B", 2, 300)], order)
    a.receive("sc01", {"bids": b.own_bids()}, S)
    b.receive("sc00", {"bids": a.own_bids()}, S)
    a.decide()
    b.decide()
    assert [t.task_id for t in a.won] == ["A"]  # tie on A -> lower ID
    assert [t.task_id for t in b.won] == ["B"]


def test_auction_lost_bid_creates_duplicate_claim() -> None:
    order = ["A"]
    a = _auction("sc00", [("A", 3, 100)], order)
    b = _auction("sc01", [("A", 3, 100)], order)
    a.receive("sc01", {"bids": b.own_bids()}, S)  # sc00's bid to sc01 is lost
    a.decide()
    b.decide()
    assert [t.task_id for t in a.won] == [t.task_id for t in b.won] == ["A"]
    late = _auction("sc02", [("A", 1, 100)], order)
    late.decide()
    late.receive("sc00", {"bids": {"A": 3.0}}, 10 * S)  # after the decision: ignored
    assert late.received == {}


# --- Table I, row by row (P06 p. 917; transcription verified against the rendered page) ---
AG_I, AG_K, AG_M, AG_N = "sc01", "sc02", "sc03", "sc04"
LOW, HIGH = 1.0, 2.0
Bid = tuple[float, str | None]
T_OLD, T_NEW = 5, 9


def _table_case(sender_z: str | None, recv_z: str | None, *, sender_beats: bool,
                sender_newer_m: bool, sender_newer_n: bool = False) -> Bid:  # fmt: skip
    """Receiver AG_I gets a message from AG_K about task A; return AG_I's (y, z) afterwards."""
    st = CbbaState(AG_I, _catalog("B3-cbba", [], ["A"]))
    y_recv, y_send = (LOW, HIGH) if sender_beats else (HIGH, LOW)
    st.y["A"], st.z["A"] = (y_recv if recv_z else 0.0), recv_z
    st.s = {AG_M: T_OLD if sender_newer_m else T_NEW, AG_N: T_OLD if sender_newer_n else T_NEW}
    s_k = {AG_M: T_NEW if sender_newer_m else T_OLD, AG_N: T_NEW if sender_newer_n else T_OLD}
    payload = {"y": {"A": y_send} if sender_z else {}, "z": {"A": sender_z} if sender_z else {},
               "s": s_k}  # fmt: skip
    st.receive(AG_K, payload, 100)
    return st.y["A"], st.z["A"]


UPD, RST = "update", "reset"


@pytest.mark.parametrize(
    ("row", "sender_z", "recv_z", "beats", "newer_m", "newer_n", "expected"),
    [
        (1, AG_K, AG_I, True, False, False, UPD), (1, AG_K, AG_I, False, False, False, "leave"),
        (2, AG_K, AG_K, False, False, False, UPD),
        (3, AG_K, AG_M, False, True, False, UPD), (3, AG_K, AG_M, True, False, False, UPD),
        (3, AG_K, AG_M, False, False, False, "leave"),
        (4, AG_K, None, False, False, False, UPD),
        (5, AG_I, AG_I, True, True, False, "leave"),
        (6, AG_I, AG_K, False, False, False, RST),
        (7, AG_I, AG_M, False, True, False, RST), (7, AG_I, AG_M, False, False, False, "leave"),
        (8, AG_I, None, True, True, False, "leave"),
        (9, AG_M, AG_I, True, True, False, UPD), (9, AG_M, AG_I, False, True, False, "leave"),
        (9, AG_M, AG_I, True, False, False, "leave"),
        (10, AG_M, AG_K, False, True, False, UPD), (10, AG_M, AG_K, False, False, False, RST),
        (11, AG_M, AG_M, False, True, False, UPD), (11, AG_M, AG_M, True, False, False, "leave"),
        (12, AG_M, AG_N, False, True, True, UPD), (12, AG_M, AG_N, True, True, False, UPD),
        (12, AG_M, AG_N, False, False, True, RST), (12, AG_M, AG_N, False, True, False, "leave"),
        (13, AG_M, None, False, True, False, UPD), (13, AG_M, None, False, False, False, "leave"),
        (14, None, AG_I, False, True, False, "leave"),
        (15, None, AG_K, False, False, False, UPD),
        (16, None, AG_M, False, True, False, UPD), (16, None, AG_M, False, False, False, "leave"),
        (17, None, None, False, True, False, "leave"),
    ],
)  # fmt: skip
def test_table_i_every_row(row: int, sender_z: str | None, recv_z: str | None, beats: bool,
                           newer_m: bool, newer_n: bool, expected: str) -> None:  # fmt: skip
    y_send = (HIGH if beats else LOW) if sender_z else 0.0
    y_recv0 = (LOW if beats else HIGH) if recv_z else 0.0
    got = _table_case(sender_z, recv_z, sender_beats=beats, sender_newer_m=newer_m,
                      sender_newer_n=newer_n)  # fmt: skip
    want = {UPD: (y_send, sender_z), RST: (0.0, None), "leave": (y_recv0, recv_z)}[expected]
    assert got == want, f"Table AG_I row {row}"

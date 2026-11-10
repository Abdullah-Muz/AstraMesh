"""B3: Consensus-Based Bundle Algorithm (Choi, Brunet & How 2009, P06), per agent.

Faithful to the paper's Phase 1 (bundle construction), Phase 2 (consensus with
the Table I action rules and the Eq. (5) timestamp update) and the Eq. (6)
release rule; choices the paper leaves open are fixed by DL-045:

* score c_ij = priority if the agent's own slot for task j has not started,
  does not overlap any bundle task's slot, and the bundle's data still fits;
  else 0 (diminishing marginal gain holds: adding tasks only removes options);
* ties go to the lower agent ID, both when choosing tasks (then catalogue
  order) and when comparing bids;
* Table I compares the timestamps held *before* the message; the timestamp
  vector is updated after the table, per Eq. (5);
* no bundle-length limit; no stop rule (rounds continue all run).

Only the standard library is used; nothing here can see truth or other agents'
private state. Messages carry (y, z, s) with entries only for claimed tasks;
a missing task means (y = 0, z = none).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from astramesh.agents.packets import CatalogUplink, OwnTask


def outbids(y1: float, z1: str | None, y2: float, z2: str | None) -> bool:
    """True if bid (y1 by z1) beats (y2 by z2): higher bid, ties to the lower agent ID."""
    if y1 != y2:
        return y1 > y2
    if z1 is None:
        return False
    if z2 is None:
        return True
    return z1 < z2


@dataclass(slots=True)
class CbbaState:
    me: str
    catalog: CatalogUplink
    bundle: list[str] = field(default_factory=list)
    y: dict[str, float] = field(default_factory=dict)
    z: dict[str, str | None] = field(default_factory=dict)
    s: dict[str, int] = field(default_factory=dict)
    _own: dict[str, OwnTask] = field(default_factory=dict)
    _order: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._own = {t.task_id: t for t in self.catalog.own}
        self._order = {tid: i for i, tid in enumerate(self.catalog.task_order)}
        for tid in self.catalog.task_order:
            self.y[tid] = 0.0
            self.z[tid] = None

    # -- Phase 1: bundle construction ------------------------------------------------
    def _score(self, tid: str, now_ns: int) -> float:
        t = self._own.get(tid)
        if t is None or t.start_ns <= now_ns or tid in self.bundle:
            return 0.0
        data = t.data_mb
        for b in self.bundle:
            o = self._own[b]
            if o.start_ns < t.stop_ns and t.start_ns < o.stop_ns:
                return 0.0
            data += o.data_mb
        if data > self.catalog.storage_capacity_mb:
            return 0.0
        return float(t.priority)

    def build_bundle(self, now_ns: int) -> bool:
        """Add tasks greedily while some task can be won; return True if the bundle grew."""
        grew = False
        while True:
            best: tuple[float, int, str] | None = None
            for tid in self.catalog.task_order:
                c = self._score(tid, now_ns)
                if c <= 0.0 or not outbids(c, self.me, self.y[tid], self.z[tid]):
                    continue
                key = (c, -self._order[tid], tid)
                if best is None or key[:2] > best[:2]:
                    best = key
            if best is None:
                return grew
            c, _, tid = best
            self.bundle.append(tid)
            self.y[tid] = c
            self.z[tid] = self.me
            grew = True

    # -- Phase 2: consensus ---------------------------------------------------------
    def message_payload(self) -> dict[str, Any]:
        claimed = [t for t in self.catalog.task_order if self.z[t] is not None]
        return {
            "y": {t: self.y[t] for t in claimed},
            "z": {t: self.z[t] for t in claimed},
            "s": dict(self.s),
        }

    @staticmethod
    def valid_payload(p: Mapping[str, Any]) -> bool:
        y, z, s = p.get("y"), p.get("z"), p.get("s")
        if not (isinstance(y, Mapping) and isinstance(z, Mapping) and isinstance(s, Mapping)):
            return False
        if set(y) != set(z):
            return False
        # The ``type(v) is`` tests are fast paths only; the isinstance tests decide.
        ok_y = all(v >= 0 if type(v) is float or type(v) is int
                   else isinstance(v, int | float) and not isinstance(v, bool) and v >= 0
                   for v in y.values())  # fmt: skip
        ok_z = all(type(v) is str or isinstance(v, str) for v in z.values())
        ok_s = all(type(v) is int or (isinstance(v, int) and not isinstance(v, bool))
                   for v in s.values())  # fmt: skip
        return ok_y and ok_z and ok_s

    def receive(self, k: str, p: Mapping[str, Any], now_ns: int) -> None:
        """Apply Table I for every task, then the Eq. (5) timestamps and Eq. (6) release."""
        yk: Mapping[str, float] = p["y"]
        zk: Mapping[str, str] = p["z"]
        sk: Mapping[str, int] = p["s"]
        i = self.me

        def s_k(m: str) -> int:
            return int(sk.get(m, -1))

        def s_i(m: str) -> int:
            return self.s.get(m, -1)

        for j in self.catalog.task_order:
            ykj = float(yk.get(j, 0.0))
            zkj = zk.get(j)
            yij, zij = self.y[j], self.z[j]
            beats = outbids(ykj, zkj, yij, zij)
            action = "leave"
            if zkj == k:
                if zij == i:
                    action = "update" if beats else "leave"
                elif zij == k or zij is None:
                    action = "update"
                else:  # zij = m
                    action = "update" if (s_k(zij) > s_i(zij) or beats) else "leave"
            elif zkj == i:
                if zij == k:
                    action = "reset"
                elif zij is not None and zij != i:  # m
                    action = "reset" if s_k(zij) > s_i(zij) else "leave"
            elif zkj is not None:  # sender thinks m (not i, not k)
                m = zkj
                if zij == i:
                    action = "update" if (s_k(m) > s_i(m) and beats) else "leave"
                elif zij == k:
                    action = "update" if s_k(m) > s_i(m) else "reset"
                elif zij == m or zij is None:
                    action = "update" if s_k(m) > s_i(m) else "leave"
                else:  # zij = n, not i, k, m
                    n = zij
                    if (s_k(m) > s_i(m) and s_k(n) > s_i(n)) or (s_k(m) > s_i(m) and beats):
                        action = "update"
                    elif s_k(n) > s_i(n) and s_i(m) > s_k(m):
                        action = "reset"
            else:  # sender thinks none
                if zij == k:
                    action = "update"
                elif zij is not None and zij != i:
                    action = "update" if s_k(zij) > s_i(zij) else "leave"
            if action == "update":
                self.y[j], self.z[j] = ykj, zkj
            elif action == "reset":
                self.y[j], self.z[j] = 0.0, None

        # Eq. (5): direct neighbour -> reception time; others -> newest known.
        for m, t in sk.items():
            if m not in (i, k):
                self.s[m] = max(self.s.get(m, -1), int(t))
        self.s[k] = now_ns

        # Eq. (6): release the first lost task and everything added after it.
        for n_bar, tid in enumerate(self.bundle):
            if self.z[tid] != i:
                for later in self.bundle[n_bar + 1 :]:
                    self.y[later], self.z[later] = 0.0, None
                del self.bundle[n_bar:]
                break

    def release_all(self) -> None:
        """Supervisor left NOMINAL (DL-054): give up every own claim; peers re-auction."""
        for tid in self.bundle:
            if self.z[tid] == self.me:
                self.y[tid], self.z[tid] = 0.0, None
        self.bundle.clear()

    def forget_peer(self, peer: str) -> None:
        """B3 + timeout (DL-052): drop every claim by a peer believed lost, so the tasks
        are re-auctioned. Not part of published CBBA."""
        for tid in self.catalog.task_order:
            if self.z[tid] == peer:
                self.y[tid], self.z[tid] = 0.0, None

    def winning(self) -> tuple[OwnTask, ...]:
        return tuple(self._own[t] for t in self.bundle if self.z[t] == self.me)

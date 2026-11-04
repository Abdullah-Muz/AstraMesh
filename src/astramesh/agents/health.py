"""Per-peer health beliefs (spec §5.4, DL-052): an agent's *belief*, never simulator truth.

Inputs are only what the agent itself receives: the time of each accepted message
from a peer, the peer's self-reported health in its status messages, and ground
notices (explicit failure confirmations). Rules:

* ``UNKNOWN`` until the first message from the peer (timers also run from t = 0,
  so a peer never heard from becomes SUSPECTED / LOST like any other);
* ``HEALTHY`` (or ``DEGRADED`` if the peer reports itself degraded) while the last
  message is at most ``suspect_ns`` old;
* ``SUSPECTED_UNAVAILABLE`` after ``suspect_ns`` of silence, ``COMMUNICATION_LOST``
  after ``lost_ns``;
* hearing a suspected or lost peer again gives ``RECOVERING``; after
  ``recover_messages`` further status messages it is HEALTHY / DEGRADED again;
* ``CONFIRMED_FAILED`` only from a ground notice; it is sticky. Silence alone can
  never produce it (Gate P3: a false outage is not a confirmed failure).

Standard library only (agent isolation rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field

HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
SUSPECTED = "SUSPECTED_UNAVAILABLE"
LOST = "COMMUNICATION_LOST"
CONFIRMED = "CONFIRMED_FAILED"
RECOVERING = "RECOVERING"
UNKNOWN = "UNKNOWN"
BELIEFS = (HEALTHY, DEGRADED, SUSPECTED, LOST, CONFIRMED, RECOVERING, UNKNOWN)
UNAVAILABLE_BELIEFS = frozenset({LOST, CONFIRMED})  # reassignment triggers (DL-052)
AVAILABLE_BELIEFS = frozenset({HEALTHY, DEGRADED, RECOVERING, UNKNOWN})


@dataclass(frozen=True, slots=True)
class HealthSettings:
    suspect_ns: int
    lost_ns: int
    recover_messages: int

    def __post_init__(self) -> None:
        if not 0 < self.suspect_ns < self.lost_ns or self.recover_messages < 1:
            raise ValueError("need 0 < suspect < lost and recover_messages >= 1")


@dataclass(slots=True)
class _Peer:
    belief: str = UNKNOWN
    last_heard_ns: int | None = None
    reported_degraded: bool = False
    recover_count: int = 0
    confirmed: bool = False


@dataclass(slots=True)
class HealthTracker:
    settings: HealthSettings
    peers: tuple[str, ...]
    _p: dict[str, _Peer] = field(default_factory=dict)
    history: list[tuple[int, str, str, str]] = field(default_factory=list)  # (t, peer, old, new)

    def __post_init__(self) -> None:
        self._p = {p: _Peer() for p in self.peers}

    def belief(self, peer: str) -> str:
        return self._p[peer].belief

    def beliefs(self) -> dict[str, str]:
        return {p: s.belief for p, s in sorted(self._p.items())}

    def _set(self, peer: str, new: str, now_ns: int) -> None:
        old = self._p[peer].belief
        if new != old:
            self._p[peer].belief = new
            self.history.append((now_ns, peer, old, new))

    def _settled(self, s: _Peer) -> str:
        return DEGRADED if s.reported_degraded else HEALTHY

    def heard(self, peer: str, now_ns: int, *, status: bool, degraded: bool | None) -> None:
        """An accepted message from ``peer`` arrived at ``now_ns``."""
        s = self._p[peer]
        s.last_heard_ns = now_ns
        if degraded is not None:
            s.reported_degraded = degraded
        if s.confirmed:
            return  # ground confirmation is authoritative and sticky
        if s.belief in (SUSPECTED, LOST):
            s.recover_count = 0
            self._set(peer, RECOVERING, now_ns)
        elif s.belief == RECOVERING:
            if status:
                s.recover_count += 1
                if s.recover_count >= self.settings.recover_messages:
                    self._set(peer, self._settled(s), now_ns)
        else:
            self._set(peer, self._settled(s), now_ns)

    def confirm_failed(self, peer: str, now_ns: int) -> None:
        self._p[peer].confirmed = True
        self._set(peer, CONFIRMED, now_ns)

    def tick(self, now_ns: int) -> list[str]:
        """Apply silence timers; return peers that just became unavailable (LOST)."""
        newly_lost = []
        for peer, s in sorted(self._p.items()):
            if s.confirmed:
                continue
            since = now_ns - (s.last_heard_ns if s.last_heard_ns is not None else 0)
            if since > self.settings.lost_ns:
                if s.belief != LOST:
                    self._set(peer, LOST, now_ns)
                    newly_lost.append(peer)
            elif since > self.settings.suspect_ns and s.belief not in (SUSPECTED, LOST):
                self._set(peer, SUSPECTED, now_ns)
        return newly_lost

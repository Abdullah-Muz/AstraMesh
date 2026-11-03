"""``SpacecraftAgent``: local state, message handling, outbound queue (spec §5.1-§5.3).

Phase 2 increment 1 implements the communication-facing parts of an agent:

* ``observe``: accept its own navigation fixes (sensor packets).
* ``receive_messages``: validate delivered messages and update the peer table.
* ``step``: emit due periodic messages (status) into the outbound queue, which
  the simulator collects; the agent never sends anything itself.

Message acceptance rules (applied in this order; the first that fails rejects
the message and increments a per-reason counter; nothing else changes):

1. ``malformed``      - not a :class:`Delivery` of a :class:`Message`, or addressed
                        to another receiver.
2. ``from_self``      - sender is this agent.
3. ``unknown_sender`` - sender is not a configured peer.
4. ``expired``        - delivery time is at or after ``expires_ns``.
5. ``duplicate``      - (sender, seq) already accepted.
6. ``unhandled_type`` - a message type this agent does not handle yet.
7. ``stale``          - seq lower than the newest accepted from that sender (an
                        older message must not overwrite newer peer state).

The plan (``plan_version``) is not modified by any message in this increment;
allocation logic comes later. Nothing in this module may import simulator,
dynamics-truth, scenario, or network modules (checked by tests).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from astramesh.agents.packets import NavigationFix
from astramesh.communications.messages import Delivery, Message, MessageType

REJECT_REASONS = (
    "malformed",
    "from_self",
    "unknown_sender",
    "expired",
    "duplicate",
    "unhandled_type",
    "stale",
)
HANDLED_TYPES = frozenset({MessageType.STATUS})


@dataclass(frozen=True, slots=True)
class AgentSettings:
    status_interval_ns: int
    status_lifetime_ns: int

    def __post_init__(self) -> None:
        if self.status_interval_ns <= 0 or self.status_lifetime_ns <= 0:
            raise ValueError("intervals must be positive")


@dataclass(slots=True)
class PeerRecord:
    """What this agent believes about a peer, from delivered messages only."""

    newest_seq: int = -1
    last_heard_ns: int | None = None
    last_status_created_ns: int | None = None
    reported_plan_version: int | None = None
    reported_r_m: tuple[float, ...] | None = None


@dataclass(slots=True)
class SpacecraftAgent:
    agent_id: str
    peers: tuple[str, ...]
    settings: AgentSettings
    plan_version: int = 0
    _seq: int = 0
    _nav: NavigationFix | None = None
    _next_status_ns: int = 0
    _peer_table: dict[str, PeerRecord] = field(default_factory=dict)
    _accepted: set[tuple[str, int]] = field(default_factory=set)
    _rejected: Counter[str] = field(default_factory=Counter)
    _outbox: list[Message] = field(default_factory=list)
    _log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.agent_id in self.peers:
            raise ValueError("an agent cannot be its own peer")
        self._peer_table = {p: PeerRecord() for p in self.peers}

    # -- inputs -----------------------------------------------------------------
    def observe(self, fix: NavigationFix) -> None:
        if not isinstance(fix, NavigationFix):
            raise TypeError(f"unsupported sensor packet {type(fix).__name__}")
        if self._nav is None or fix.t_ns >= self._nav.t_ns:
            self._nav = fix

    def receive_messages(self, deliveries: list[Delivery]) -> None:
        for d in deliveries:
            reason = self._check(d)
            if reason is not None:
                self._rejected[reason] += 1
                self._log.append({"kind": "message_rejected", "reason": reason,
                                  **self._describe(d)})  # fmt: skip
                continue
            self._accept(d)

    def _describe(self, d: Any) -> dict[str, Any]:
        m = getattr(d, "message", None)
        if isinstance(d, Delivery) and isinstance(m, Message):
            return {"sender": m.sender, "seq": m.seq, "type": str(m.msg_type),
                    "t_ns": d.delivered_ns}  # fmt: skip
        return {"object": type(d).__name__}

    def _check(self, d: Any) -> str | None:
        if not isinstance(d, Delivery) or not isinstance(d.message, Message):
            return "malformed"
        if d.receiver != self.agent_id:
            return "malformed"
        m = d.message
        if m.sender == self.agent_id:
            return "from_self"
        if m.sender not in self._peer_table:
            return "unknown_sender"
        if d.delivered_ns >= m.expires_ns:
            return "expired"
        if m.key in self._accepted:
            return "duplicate"
        if m.msg_type not in HANDLED_TYPES:
            return "unhandled_type"
        if m.seq < self._peer_table[m.sender].newest_seq:
            return "stale"
        return None

    def _accept(self, d: Delivery) -> None:
        m = d.message
        self._accepted.add(m.key)
        rec = self._peer_table[m.sender]
        rec.newest_seq = m.seq
        rec.last_heard_ns = d.delivered_ns
        if m.msg_type is MessageType.STATUS:
            rec.last_status_created_ns = m.created_ns
            rec.reported_plan_version = m.plan_version
            r = m.payload.get("r_m")
            rec.reported_r_m = tuple(float(x) for x in r) if isinstance(r, tuple) else None

    # -- outputs ----------------------------------------------------------------
    def step(self, now_ns: int) -> list[Message]:
        """Queue due periodic messages and hand over the outbound queue."""
        if now_ns >= self._next_status_ns:
            self._outbox.append(self._status(now_ns))
            self._next_status_ns = now_ns + self.settings.status_interval_ns
        out, self._outbox = self._outbox, []
        return out

    def _status(self, now_ns: int) -> Message:
        payload: dict[str, Any] = {"nav_t_ns": None, "r_m": None, "sigma_r_m": None}
        if self._nav is not None:
            payload = {
                "nav_t_ns": self._nav.t_ns,
                "r_m": list(self._nav.r_m),
                "sigma_r_m": self._nav.sigma_r_m,
            }
        msg = Message(
            sender=self.agent_id,
            seq=self._seq,
            created_ns=now_ns,
            expires_ns=now_ns + self.settings.status_lifetime_ns,
            msg_type=MessageType.STATUS,
            plan_version=self.plan_version,
            payload=payload,
        )
        self._seq += 1
        return msg

    # -- read-only views for logging/evaluation ------------------------------------
    def rejected_counts(self) -> dict[str, int]:
        return {r: self._rejected[r] for r in REJECT_REASONS}

    def peer_view(self) -> dict[str, dict[str, Any]]:
        return {
            p: {
                "newest_seq": r.newest_seq,
                "last_heard_ns": r.last_heard_ns,
                "reported_plan_version": r.reported_plan_version,
            }
            for p, r in sorted(self._peer_table.items())
        }

    def drain_log(self) -> list[dict[str, Any]]:
        out, self._log = self._log, []
        return out

    @property
    def n_accepted(self) -> int:
        return len(self._accepted)

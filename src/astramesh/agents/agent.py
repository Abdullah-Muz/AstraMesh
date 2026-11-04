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

from astramesh.agents.auction import AuctionState
from astramesh.agents.cbba import CbbaState
from astramesh.agents.packets import (
    CatalogUplink,
    Housekeeping,
    NavigationFix,
    PlannedObservation,
    PlanUplink,
)
from astramesh.communications.messages import Delivery, Message, MessageType

REJECT_REASONS = (
    "malformed",
    "from_self",
    "unknown_sender",
    "expired",
    "duplicate",
    "unhandled_type",
    "stale",
    "malformed_payload",
)
HANDLED_TYPES = frozenset({MessageType.STATUS})
ALLOCATION_TYPES = {"B2-auction": MessageType.TASK_BID, "B3-cbba": MessageType.PLAN_SYNC}


@dataclass(frozen=True, slots=True)
class AgentSettings:
    status_interval_ns: int
    status_lifetime_ns: int
    battery_reserve_fraction: float = 0.0  # do not start an observation below this charge
    allocation_lifetime_ns: int = 20_000_000_000  # task_bid / plan_sync expiry (DL-045)
    auction_deadline_ns: int = 5_000_000_000  # B2 decides at the first round at/after this

    def __post_init__(self) -> None:
        if self.status_interval_ns <= 0 or self.status_lifetime_ns <= 0:
            raise ValueError("intervals must be positive")
        if not 0.0 <= self.battery_reserve_fraction < 1.0:
            raise ValueError("battery_reserve_fraction must be in [0, 1)")


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
    _hk: Housekeeping | None = None
    _plan: tuple[PlannedObservation, ...] = ()
    _plan_algorithm: str | None = None
    _observing: PlannedObservation | None = None
    _alloc: CbbaState | AuctionState | None = None
    _last_plan_change_ns: int | None = None
    _finished: set[str] = field(default_factory=set)
    _declined: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.agent_id in self.peers:
            raise ValueError("an agent cannot be its own peer")
        self._peer_table = {p: PeerRecord() for p in self.peers}

    # -- inputs -----------------------------------------------------------------
    def observe(self, packet: NavigationFix | Housekeeping | PlanUplink | CatalogUplink) -> None:
        if isinstance(packet, NavigationFix):
            if self._nav is None or packet.t_ns >= self._nav.t_ns:
                self._nav = packet
        elif isinstance(packet, Housekeeping):
            if self._hk is None or packet.t_ns >= self._hk.t_ns:
                self._hk = packet
        elif isinstance(packet, CatalogUplink):
            if self._alloc is not None or packet.algorithm not in ALLOCATION_TYPES:
                self._log.append({"kind": "catalog_rejected", "algorithm": packet.algorithm})
                return
            if packet.algorithm == "B3-cbba":
                self._alloc = CbbaState(self.agent_id, packet)
            else:
                self._alloc = AuctionState(self.agent_id, packet, self.settings.auction_deadline_ns)
            self._plan_algorithm = packet.algorithm
            self._log.append(
                {
                    "kind": "catalog_accepted",
                    "algorithm": packet.algorithm,
                    "n_tasks": len(packet.task_order),
                    "n_own": len(packet.own),
                }
            )
        elif isinstance(packet, PlanUplink):
            if packet.version <= self.plan_version:
                self._log.append({"kind": "plan_rejected", "reason": "not_newer",
                                  "version": packet.version})  # fmt: skip
                return
            self._plan = tuple(sorted(packet.observations, key=lambda o: o.start_ns))
            self._plan_algorithm = packet.algorithm
            self.plan_version = packet.version
            self._log.append(
                {
                    "kind": "plan_accepted",
                    "algorithm": packet.algorithm,
                    "version": packet.version,
                    "n_observations": len(self._plan),
                }
            )
        else:
            raise TypeError(f"unsupported sensor packet {type(packet).__name__}")

    # -- plan execution (spec §5.2 validate_plan_against_resources) ---------------
    def payload_command(self, now_ns: int, step_ns: int, data_mb_per_step: float) -> str | None:
        """Task to observe during the step starting at ``now_ns``, or None (payload off).

        Before *starting* an observation the agent checks its own housekeeping:
        battery at or above the reserve and room for the remaining data. Once
        started it continues until the planned stop unless housekeeping shows an
        empty battery or full storage. It never acts on another agent's state.
        """
        if self._observing is not None and now_ns >= self._observing.stop_ns:
            self._finished.add(self._observing.task_id)
            self._observing = None
        if self._observing is not None:  # committed: finish it even if the plan changed
            current: PlannedObservation | None = self._observing
        else:
            current = next((o for o in self._plan if o.start_ns <= now_ns < o.stop_ns), None)
        if (
            current is None
            or current.task_id in self._finished
            or current.task_id in self._declined
        ):
            return None
        hk = self._hk
        if hk is None:
            return self._decline(current, "no_housekeeping")
        if self._observing is current:
            if hk.battery_wh <= 0.0 or hk.storage_used_mb >= hk.storage_capacity_mb:
                self._observing = None
                return self._decline(current, "resources_exhausted")
            return current.task_id
        remaining_steps = -(-(current.stop_ns - now_ns) // step_ns)
        if hk.battery_wh < self.settings.battery_reserve_fraction * hk.battery_capacity_wh:
            return self._decline(current, "battery_reserve")
        if hk.storage_used_mb + remaining_steps * data_mb_per_step > hk.storage_capacity_mb:
            return self._decline(current, "storage")
        self._observing = current
        return current.task_id

    def _decline(self, obs: PlannedObservation, reason: str) -> str | None:
        """Record that a planned observation will not be made; always returns None."""
        self._declined[obs.task_id] = reason
        self._log.append({"kind": "observation_declined", "task": obs.task_id, "reason": reason})
        return None

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
        if m.msg_type not in self._handled_types():
            return "unhandled_type"
        if m.seq < self._peer_table[m.sender].newest_seq:
            return "stale"
        if m.msg_type is not MessageType.STATUS and not self._alloc_valid(m):
            return "malformed_payload"
        return None

    def _handled_types(self) -> frozenset[MessageType]:
        if self._plan_algorithm in ALLOCATION_TYPES and self._alloc is not None:
            return HANDLED_TYPES | {ALLOCATION_TYPES[self._plan_algorithm]}
        return HANDLED_TYPES

    def _alloc_valid(self, m: Message) -> bool:
        return self._alloc is not None and self._alloc.valid_payload(m.payload)

    def _accept(self, d: Delivery) -> None:
        m = d.message
        self._accepted.add(m.key)
        rec = self._peer_table[m.sender]
        rec.newest_seq = m.seq
        rec.last_heard_ns = d.delivered_ns
        if m.msg_type is not MessageType.STATUS and self._alloc is not None:
            self._alloc.receive(m.sender, m.payload, d.delivered_ns)
            self._refresh_plan(d.delivered_ns)
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
        self._allocation_round(now_ns)
        out, self._outbox = self._outbox, []
        return out

    def _allocation_round(self, now_ns: int) -> None:
        alloc = self._alloc
        if isinstance(alloc, CbbaState):
            alloc.build_bundle(now_ns)
            self._refresh_plan(now_ns)
            self._outbox.append(self._message(now_ns, MessageType.PLAN_SYNC,
                                              alloc.message_payload()))  # fmt: skip
        elif isinstance(alloc, AuctionState):
            if not alloc.sent:
                self._outbox.append(self._message(now_ns, MessageType.TASK_BID,
                                                  {"bids": alloc.own_bids()}))  # fmt: skip
                alloc.sent = True
            if not alloc.decided and now_ns >= alloc.deadline_ns:
                alloc.decide()
                self._refresh_plan(now_ns)

    def _message(self, now_ns: int, mtype: MessageType, payload: dict[str, Any]) -> Message:
        msg = Message(self.agent_id, self._seq, now_ns,
                      now_ns + self.settings.allocation_lifetime_ns, mtype, self.plan_version,
                      payload)  # fmt: skip
        self._seq += 1
        return msg

    def _refresh_plan(self, now_ns: int) -> None:
        """Rebuild the executable plan from the allocation state (B2/B3)."""
        alloc = self._alloc
        tasks = alloc.winning() if isinstance(alloc, CbbaState) else (
            alloc.won if isinstance(alloc, AuctionState) else ())  # fmt: skip
        plan = tuple(PlannedObservation(t.task_id, t.start_ns, t.stop_ns)
                     for t in sorted(tasks, key=lambda t: t.start_ns))  # fmt: skip
        if plan != self._plan:
            self._plan = plan
            self.plan_version += 1
            self._last_plan_change_ns = now_ns
            self._log.append({"kind": "plan_changed", "version": self.plan_version,
                              "n_observations": len(plan)})  # fmt: skip

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

    def execution_view(self) -> dict[str, Any]:
        return {
            "plan_algorithm": self._plan_algorithm,
            "plan_version": self.plan_version,
            "planned": len(self._plan),
            "believed_finished": len(self._finished) + (1 if self._observing else 0),
            "declined": dict(sorted(self._declined.items())),
            "last_plan_change_ns": self._last_plan_change_ns,
        }

    def planned_observations(self) -> tuple[PlannedObservation, ...]:
        """Read-only copy of the current plan (for evaluation after a run)."""
        return self._plan

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
from astramesh.agents.health import (
    AVAILABLE_BELIEFS,
    UNAVAILABLE_BELIEFS,
    HealthSettings,
    HealthTracker,
)
from astramesh.agents.packets import (
    CatalogUplink,
    GroundNotice,
    Housekeeping,
    NavigationFix,
    PlannedObservation,
    PlanUplink,
    PublicTask,
    RiskForecast,
)
from astramesh.agents.supervisor import (
    NOMINAL,
    STORM_WATCH,
    TASKING_MODES,
    Supervisor,
    SupervisorSettings,
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
ALLOCATION_TYPES = {
    "B2-auction": MessageType.TASK_BID,
    "B3-cbba": MessageType.PLAN_SYNC,
    "B3-cbba+timeout": MessageType.PLAN_SYNC,
}
REDISTRIBUTING = {"B3-cbba+timeout", "B4-rule-redistribution"}  # react to lost peers (DL-052)
DEFAULT_SUPERVISOR = SupervisorSettings()
DEFAULT_HEALTH = HealthSettings(suspect_ns=90 * 10**9, lost_ns=300 * 10**9, recover_messages=2)


@dataclass(frozen=True, slots=True)
class AgentSettings:
    status_interval_ns: int
    status_lifetime_ns: int
    battery_reserve_fraction: float = 0.0  # do not start an observation below this charge
    allocation_lifetime_ns: int = 20_000_000_000  # task_bid / plan_sync expiry (DL-045)
    auction_deadline_ns: int = 5_000_000_000  # B2 decides at the first round at/after this
    health: HealthSettings = DEFAULT_HEALTH
    supervisor: SupervisorSettings = DEFAULT_SUPERVISOR
    watch_status_interval_ns: int = 10 * 10**9  # STORM_WATCH monitoring (DL-056)
    recovery_nav_max_age_ns: int = 60 * 10**9
    recovery_peer_heard_ns: int = 90 * 10**9

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
    reported_mode: str | None = None


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
    _health: HealthTracker | None = None
    _sup: Supervisor | None = None
    _sup_seen: int = 0
    _forecast: RiskForecast | None = None
    _history_seen: int = 0
    _public: dict[str, PublicTask] = field(default_factory=dict)
    _reassigned: set[str] = field(default_factory=set)
    _finished: set[str] = field(default_factory=set)
    _declined: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.agent_id in self.peers:
            raise ValueError("an agent cannot be its own peer")
        self._peer_table = {p: PeerRecord() for p in self.peers}
        self._health = HealthTracker(self.settings.health, self.peers)
        self._sup = Supervisor(self.settings.supervisor)

    # -- inputs -----------------------------------------------------------------
    def observe(
        self,
        packet: NavigationFix
        | Housekeeping
        | PlanUplink
        | CatalogUplink
        | GroundNotice
        | RiskForecast,
    ) -> None:
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
            if packet.algorithm.startswith("B3-cbba"):
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
            self._public = {t.task_id: t for t in packet.public_tasks}
            self._log.append(
                {
                    "kind": "plan_accepted",
                    "algorithm": packet.algorithm,
                    "version": packet.version,
                    "n_observations": len(self._plan),
                }
            )
        elif isinstance(packet, RiskForecast):
            if self._forecast is None or packet.t_ns >= self._forecast.t_ns:
                self._forecast = packet
        elif isinstance(packet, GroundNotice):
            assert self._health is not None
            for p in packet.confirmed_failed:
                if p in self._peer_table:
                    self._health.confirm_failed(p, packet.t_ns)
            self._after_health_change(packet.t_ns)
        else:
            raise TypeError(f"unsupported sensor packet {type(packet).__name__}")

    # -- plan execution (spec §5.2 validate_plan_against_resources) ---------------
    def payload_command(self, now_ns: int, step_ns: int, data_mb_per_step: float) -> str | None:
        """Task to observe during the step starting at ``now_ns``, or None (payload off).

        Before *starting* an observation the agent checks its own housekeeping:
        battery at or above the reserve and room for the remaining data. Once
        started it continues until the planned stop unless housekeeping shows an
        empty battery or full storage. It never acts on another agent's state.

        The protection supervisor is consulted first (DL-054/056): outside NOMINAL and
        STORM_WATCH the
        payload stays off and any running observation stops, whatever the plan says.
        """
        if not self._supervise(now_ns):  # protection first: the planner cannot override it
            if self._observing is not None:
                obs, self._observing = self._observing, None
                self._decline(obs, "protection_" + self.mode.lower())
            return None
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

    @property
    def mode(self) -> str:
        return self._sup.mode if self._sup is not None else NOMINAL

    def _supervise(self, now_ns: int) -> bool:
        """Update the supervisor from own housekeeping and forecast; True if science allowed."""
        sup = self._sup
        if sup is None:
            return True
        hk = self._hk
        frac = hk.battery_wh / hk.battery_capacity_wh if hk and hk.battery_capacity_wh else None
        sup.update(
            now_ns,
            battery_fraction=frac,
            critical_flags=hk.critical_flags if hk else (),
            risks=self._forecast.as_mapping() if self._forecast else {},
            forecast_enabled=self._forecast is not None,
            recovery_checks_ok=self._recovery_checks_ok(now_ns),
        )
        for t, old, new, why in sup.history[self._sup_seen :]:
            self._log.append({"kind": "mode_changed", "from": old, "to": new, "reason": why,
                              "t_ns": t})  # fmt: skip
            leaving = old in TASKING_MODES and new not in TASKING_MODES
            if leaving and isinstance(self._alloc, CbbaState):
                self._alloc.release_all()  # stop claiming; peers re-auction (DL-054)
                self._refresh_plan(now_ns)
        self._sup_seen = len(sup.history)
        for t, note in sup.notes:
            self._log.append({"kind": "supervisor_note", "note": note, "t_ns": t})
        sup.notes.clear()
        return sup.allows_payload()

    def _recovery_checks_ok(self, now_ns: int) -> bool:
        """RECOVERY -> NOMINAL checks from own state (DL-056): battery above the science
        reserve, a fresh navigation fix, and contact with a peer if any is believed up."""
        st = self.settings
        hk = self._hk
        if hk is None or hk.battery_wh < st.battery_reserve_fraction * hk.battery_capacity_wh:
            return False
        if self._nav is None or now_ns - self._nav.t_ns > st.recovery_nav_max_age_ns:
            return False
        if self._health is None:
            return True
        up = [p for p, b in self._health.beliefs().items()
              if b in ("HEALTHY", "DEGRADED", "RECOVERING")]  # fmt: skip
        if not up:
            return True
        return any(
            (h := self._peer_table[p].last_heard_ns) is not None
            and now_ns - h <= st.recovery_peer_heard_ns
            for p in up
        )

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
        if self._health is not None:
            is_status = m.msg_type is MessageType.STATUS
            h = m.payload.get("health") if is_status else None
            degraded = (h == "degraded") if isinstance(h, str) else None
            self._health.heard(m.sender, d.delivered_ns, status=is_status, degraded=degraded)
            self._after_health_change(d.delivered_ns)
        if m.msg_type is not MessageType.STATUS and self._alloc is not None:
            self._alloc.receive(m.sender, m.payload, d.delivered_ns)
            self._refresh_plan(d.delivered_ns)
        if m.msg_type is MessageType.STATUS:
            rec.last_status_created_ns = m.created_ns
            rec.reported_plan_version = m.plan_version
            r = m.payload.get("r_m")
            rec.reported_r_m = tuple(float(x) for x in r) if isinstance(r, tuple) else None
            mode = m.payload.get("mode")
            if isinstance(mode, str):
                was = rec.reported_mode
                rec.reported_mode = mode
                if (mode not in TASKING_MODES and was in (None, *TASKING_MODES)
                        and self._plan_algorithm == "B4-rule-redistribution"):  # fmt: skip
                    self._respond_to_loss(m.sender, d.delivered_ns)

    # -- outputs ----------------------------------------------------------------
    def step(self, now_ns: int) -> list[Message]:
        """Queue due periodic messages and hand over the outbound queue."""
        if self._health is not None:
            self._health.tick(now_ns)
            self._after_health_change(now_ns)
        if now_ns >= self._next_status_ns:
            self._outbox.append(self._status(now_ns))
            interval = (self.settings.watch_status_interval_ns if self.mode == STORM_WATCH
                        else self.settings.status_interval_ns)  # fmt: skip
            self._next_status_ns = now_ns + interval
        self._allocation_round(now_ns)
        out, self._outbox = self._outbox, []
        return out

    def _allocation_round(self, now_ns: int) -> None:
        alloc = self._alloc
        if isinstance(alloc, CbbaState):
            if self.mode in TASKING_MODES:  # protected, recovering or safe: no bids
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

    def _self_health(self) -> str:
        hk = self._hk
        if hk is not None and hk.battery_wh < self.settings.battery_reserve_fraction * (
            hk.battery_capacity_wh
        ):
            return "degraded"
        return "nominal"

    def _after_health_change(self, now_ns: int) -> None:
        """Log new belief changes and run the method's response to lost peers (DL-052)."""
        h = self._health
        if h is None:
            return
        new = h.history[self._history_seen :]
        self._history_seen = len(h.history)
        for t, peer, old, belief in new:
            self._log.append({"kind": "belief_changed", "peer": peer, "from": old, "to": belief,
                              "t_ns": t})  # fmt: skip
            if belief in UNAVAILABLE_BELIEFS and self._plan_algorithm in REDISTRIBUTING:
                self._respond_to_loss(peer, now_ns)

    def _respond_to_loss(self, peer: str, now_ns: int) -> None:
        if isinstance(self._alloc, CbbaState):  # B3 + timeout: re-auction the peer's claims
            self._alloc.forget_peer(peer)
            self._log.append({"kind": "claims_forgotten", "peer": peer})
            self._refresh_plan(now_ns)
            return
        assert self._health is not None
        beliefs = self._health.beliefs()  # B4: fixed rule, lowest available ID with a slot
        mine = {o.task_id for o in self._plan}
        taken: list[PlannedObservation] = []
        for tid, t in sorted(self._public.items()):
            if t.owner != peer or tid in self._reassigned:
                continue
            slots = {s.spacecraft: s for s in t.slots if s.start_ns > now_ns}
            ok = [sc for sc in sorted(slots) if self._can_take(sc, beliefs)]
            if not ok:
                continue
            self._reassigned.add(tid)
            winner = ok[0]
            self._public[tid] = PublicTask(t.task_id, t.priority, winner, t.slots, t.data_mb)
            if winner != self.agent_id or tid in mine:
                continue
            s = slots[winner]
            obs = PlannedObservation(tid, s.start_ns, s.stop_ns)
            plan = list(self._plan) + taken
            if any(o.start_ns < obs.stop_ns and obs.start_ns < o.stop_ns for o in plan):
                self._log.append({"kind": "takeover_skipped", "task": tid, "reason": "overlap"})
                continue
            taken.append(obs)
            self._log.append({"kind": "task_taken_over", "task": tid, "from": peer})
        if taken:
            self._plan = tuple(sorted(list(self._plan) + taken, key=lambda o: o.start_ns))
            self.plan_version += 1
            self._last_plan_change_ns = now_ns
            self._log.append({"kind": "plan_changed", "version": self.plan_version,
                              "n_observations": len(self._plan)})  # fmt: skip

    def _can_take(self, sc: str, beliefs: dict[str, str]) -> bool:
        """B4: believed available for new tasks (health and reported mode)."""
        if sc == self.agent_id:
            return self.mode in TASKING_MODES
        rec = self._peer_table.get(sc)
        mode_ok = rec is None or rec.reported_mode in (None, *TASKING_MODES)
        return beliefs.get(sc) in AVAILABLE_BELIEFS and mode_ok

    def mode_history(self) -> list[tuple[int, str, str, str]]:
        return list(self._sup.history) if self._sup is not None else []

    def health_beliefs(self) -> dict[str, str]:
        return self._health.beliefs() if self._health is not None else {}

    def belief_history(self) -> list[tuple[int, str, str, str]]:
        return list(self._health.history) if self._health is not None else []

    def _status(self, now_ns: int) -> Message:
        payload: dict[str, Any] = {"nav_t_ns": None, "r_m": None, "sigma_r_m": None}
        if self._nav is not None:
            payload = {
                "nav_t_ns": self._nav.t_ns,
                "r_m": list(self._nav.r_m),
                "sigma_r_m": self._nav.sigma_r_m,
            }
        payload["health"] = self._self_health()
        payload["mode"] = self.mode
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

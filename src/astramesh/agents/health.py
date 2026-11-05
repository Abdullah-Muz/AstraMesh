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

Two models decide SUSPECTED / LOST from silence (spec §7.2, DL-066):

* ``timeout`` (H-A): fixed silence timers ``suspect_ns`` and ``lost_ns``;
* ``bayes`` (H-B): the posterior probability that the peer became unavailable,
  given a silence of ``s`` (``p_unavailable``). SUSPECTED at ``suspect_p``, LOST at
  ``lost_p``. Everything else (RECOVERING, CONFIRMED_FAILED) is shared.

``PayloadBelief`` (H-C) is the agent's belief about its *own* payload, from the
calibrated probabilities of an onboard anomaly detector (DL-066).

Standard library only (agent isolation rule).
"""

from __future__ import annotations

import math
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
class BayesSettings:
    """H-B: silence model (DL-066). All values are fixed before any scenario is run.

    A peer that is up sends a status message every ``status_interval_ns``; each is
    lost independently with an unknown probability ``rho ~ Beta(loss_a, loss_b)``,
    updated from the gaps between status messages received while the peer is
    believed up. Unavailability starts at an exponential rate with mean
    ``mtbf_ns``. Messages of other types reset the silence but are not counted.
    """

    status_interval_ns: int
    mtbf_ns: int
    loss_a: float = 1.0
    loss_b: float = 30.0
    suspect_p: float = 0.5
    lost_p: float = 0.95

    def __post_init__(self) -> None:
        if self.status_interval_ns <= 0 or self.mtbf_ns <= 0:
            raise ValueError("status interval and MTBF must be positive")
        if self.loss_a <= 0 or self.loss_b <= 0:
            raise ValueError("Beta prior parameters must be positive")
        if not 0.0 < self.suspect_p < self.lost_p < 1.0:
            raise ValueError("need 0 < suspect_p < lost_p < 1")


def p_unavailable(silence_ns: int, loss_a: float, loss_b: float, s: BayesSettings) -> float:
    """P(peer unavailable | no message for ``silence_ns``).

    Prior: unavailability began within the silence, ``1 - exp(-silence / mtbf)``.
    Likelihood of the silence if the peer is up: all ``k`` expected status messages
    lost, ``E[rho^k]`` under the Beta posterior (beta-binomial). If it is down: 1.
    """
    if silence_ns <= 0:
        return 0.0
    prior = -math.expm1(-silence_ns / s.mtbf_ns)
    k = silence_ns // s.status_interval_ns
    log_surv = (math.lgamma(loss_a + k) - math.lgamma(loss_a)
                + math.lgamma(loss_a + loss_b) - math.lgamma(loss_a + loss_b + k))  # fmt: skip
    up = (1.0 - prior) * math.exp(log_surv)
    return prior / (prior + up)


@dataclass(frozen=True, slots=True)
class HealthSettings:
    suspect_ns: int
    lost_ns: int
    recover_messages: int
    bayes: BayesSettings | None = None  # None: timeout model (H-A); else H-B

    def __post_init__(self) -> None:
        if not 0 < self.suspect_ns < self.lost_ns or self.recover_messages < 1:
            raise ValueError("need 0 < suspect < lost and recover_messages >= 1")

    @property
    def model(self) -> str:
        return "timeout" if self.bayes is None else "bayes"


@dataclass(slots=True)
class _Peer:
    belief: str = UNKNOWN
    last_heard_ns: int | None = None
    reported_degraded: bool = False
    recover_count: int = 0
    confirmed: bool = False
    last_status_ns: int | None = None
    loss_a: float = 1.0
    loss_b: float = 30.0


@dataclass(slots=True)
class HealthTracker:
    settings: HealthSettings
    peers: tuple[str, ...]
    _p: dict[str, _Peer] = field(default_factory=dict)
    history: list[tuple[int, str, str, str]] = field(default_factory=list)  # (t, peer, old, new)

    def __post_init__(self) -> None:
        b = self.settings.bayes
        self._p = {p: _Peer() if b is None else _Peer(loss_a=b.loss_a, loss_b=b.loss_b)
                   for p in self.peers}  # fmt: skip

    def p_unavailable(self, peer: str, now_ns: int) -> float | None:
        """H-B posterior for ``peer`` (None under the timeout model)."""
        b = self.settings.bayes
        if b is None:
            return None
        s = self._p[peer]
        return p_unavailable(now_ns - (s.last_heard_ns or 0), s.loss_a, s.loss_b, b)

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
        b = self.settings.bayes
        if b is not None and status:
            if s.last_status_ns is not None and s.belief in (HEALTHY, DEGRADED):
                gap = now_ns - s.last_status_ns  # learn the loss rate only while believed up
                s.loss_a += max(0, round(gap / b.status_interval_ns) - 1)
                s.loss_b += 1
            s.last_status_ns = now_ns
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
        b = self.settings.bayes
        for peer, s in sorted(self._p.items()):
            if s.confirmed:
                continue
            since = now_ns - (s.last_heard_ns if s.last_heard_ns is not None else 0)
            if b is not None:
                p = p_unavailable(since, s.loss_a, s.loss_b, b)
                if p >= b.lost_p:
                    if s.belief != LOST:
                        self._set(peer, LOST, now_ns)
                        newly_lost.append(peer)
                elif p >= b.suspect_p and s.belief not in (SUSPECTED, LOST):
                    self._set(peer, SUSPECTED, now_ns)
                continue
            if since > self.settings.lost_ns:
                if s.belief != LOST:
                    self._set(peer, LOST, now_ns)
                    newly_lost.append(peer)
            elif since > self.settings.suspect_ns and s.belief not in (SUSPECTED, LOST):
                self._set(peer, SUSPECTED, now_ns)
        return newly_lost


@dataclass(frozen=True, slots=True)
class PayloadSettings:
    """H-C: own-payload belief from an onboard detector (DL-066).

    ``train_prior`` is the anomaly rate the detector's probabilities were calibrated
    to; dividing it out turns each probability into a likelihood ratio. Payload
    degradation starts at rate ``1 / mtbf_ns`` and ends at rate ``1 / repair_ns``.
    Probabilities are clipped to ``[clip, 1 - clip]`` so no single check is decisive.
    """

    interval_ns: int
    mtbf_ns: int
    repair_ns: int
    train_prior: float
    degraded_p: float = 0.9
    clear_p: float = 0.1
    clip: float = 0.01

    def __post_init__(self) -> None:
        if min(self.interval_ns, self.mtbf_ns, self.repair_ns) <= 0:
            raise ValueError("intervals must be positive")
        if not 0.0 < self.train_prior < 1.0 or not 0.0 < self.clip < 0.5:
            raise ValueError("train_prior must be in (0, 1) and clip in (0, 0.5)")
        if not 0.0 < self.clear_p < self.degraded_p < 1.0:
            raise ValueError("need 0 < clear_p < degraded_p < 1")


@dataclass(slots=True)
class PayloadBelief:
    """Two-state filter (payload ok / degraded) with hysteresis on the decision."""

    settings: PayloadSettings
    p: float = 0.0
    degraded: bool = False
    last_ns: int | None = None
    history: list[tuple[int, bool, float]] = field(default_factory=list)  # (t, degraded, p)

    def update(self, t_ns: int, prob: float) -> bool:
        """Fold in one detector probability; return True if the decision changed."""
        st = self.settings
        dt = st.interval_ns if self.last_ns is None else max(t_ns - self.last_ns, 0)
        self.last_ns = t_ns
        onset, repair = -math.expm1(-dt / st.mtbf_ns), -math.expm1(-dt / st.repair_ns)
        prior = self.p * (1.0 - repair) + (1.0 - self.p) * onset
        q = min(max(prob, st.clip), 1.0 - st.clip)
        lr = (q / (1.0 - q)) / (st.train_prior / (1.0 - st.train_prior))
        odds = prior / (1.0 - prior) * lr
        self.p = odds / (1.0 + odds)
        new = self.p >= st.degraded_p if not self.degraded else self.p > st.clear_p
        if new != self.degraded:
            self.degraded = new
            self.history.append((t_ns, new, self.p))
            return True
        return False

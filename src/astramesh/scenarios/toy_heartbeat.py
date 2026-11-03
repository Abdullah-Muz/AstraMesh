"""Toy heartbeat scenario — a Phase 0 reproducibility check, not a research model.

``n_nodes`` abstract nodes each broadcast a heartbeat every
``heartbeat_interval_s``; every (sender, receiver) delivery is independently
dropped with ``packet_loss_probability`` using the ``comms`` random stream.
There is no orbital geometry, link model, delay, or spacecraft state.

Its only purpose is to exercise the clock, random streams, event log,
configuration, and run manifest end-to-end so that same-seed replay can be
tested. Its outputs are not scientific results and must not be reported as
such.
"""

from __future__ import annotations

from dataclasses import dataclass

from astramesh.core.clock import SimulationClock, seconds_to_ns
from astramesh.core.config import ToyHeartbeatScenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams

ALGORITHM_NAME = "toy_heartbeat_v1"


@dataclass(frozen=True, slots=True)
class ToySummary:
    """Event counts from one toy run (bookkeeping only, not research metrics)."""

    rounds: int
    heartbeats_sent: int
    deliveries_attempted: int
    deliveries_lost: int

    def to_dict(self) -> dict[str, int]:
        return {
            "rounds": self.rounds,
            "heartbeats_sent": self.heartbeats_sent,
            "deliveries_attempted": self.deliveries_attempted,
            "deliveries_lost": self.deliveries_lost,
        }


def run_toy_heartbeat(
    config: ToyHeartbeatScenario, streams: RandomStreams, log: EventLog
) -> ToySummary:
    cfg = config.toy_heartbeat
    clock = SimulationClock(config.time.clock_spec())
    interval_ticks = seconds_to_ns(cfg.heartbeat_interval_s) // clock.spec.step_ns
    nodes = [f"node{i:02d}" for i in range(cfg.n_nodes)]
    comms = streams["comms"]

    rounds = sent = attempted = lost = 0
    log.record(
        tick=0,
        time_ns=0,
        source="sim",
        kind="scenario_start",
        data={"scenario_id": config.scenario_id, "nodes": nodes, "n_steps": clock.spec.n_steps},
    )
    for tick in clock.ticks():
        if tick % interval_ticks != 0:
            continue
        rounds += 1
        t_ns = clock.time_ns
        for sender in nodes:
            sent += 1
            log.record(tick=tick, time_ns=t_ns, source=sender, kind="heartbeat_sent")
            for receiver in nodes:
                if receiver == sender:
                    continue
                attempted += 1
                if comms.random() < cfg.packet_loss_probability:
                    lost += 1
                    kind = "heartbeat_lost"
                else:
                    kind = "heartbeat_delivered"
                log.record(tick=tick, time_ns=t_ns, source=sender, kind=kind, data={"to": receiver})

    summary = ToySummary(
        rounds=rounds, heartbeats_sent=sent, deliveries_attempted=attempted, deliveries_lost=lost
    )
    log.record(
        tick=clock.tick,
        time_ns=clock.time_ns,
        source="sim",
        kind="scenario_end",
        data=summary.to_dict(),
    )
    return summary

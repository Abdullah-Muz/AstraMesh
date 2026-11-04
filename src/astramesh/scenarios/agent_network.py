"""Phase 2 increment 1: isolated agents exchanging status over the crosslink network.

The simulator (this module) owns all truth: the formation trajectory, the
connectivity graph, and the random streams. Agents receive only

* navigation fixes of their own orbit (truth + Gaussian noise, ``sensors`` stream), and
* messages delivered to them by the network (``comms`` stream for loss/duplication),

and they hand outbound messages back from ``step``. Time runs in a SimPy
environment whose unit is the integer nanosecond, so event times are exact
and ties are processed in a fixed scheduling order (same seed => same run).

The per-tick order is fixed by :class:`~astramesh.scenarios.kernel.AgentKernel`:
navigation fixes, then agent steps in agent-ID order; deliveries run at their
own arrival times.

No allocation algorithm runs yet; plans stay at version 0. Outputs are
communication bookkeeping, not research results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from astramesh.agents.agent import AgentSettings, SpacecraftAgent
from astramesh.communications.network import LinkModel
from astramesh.core.clock import seconds_to_ns
from astramesh.core.config import AgentNetworkScenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.scenarios.formation_dynamics import (
    FormationRun,
    record_scenario_end,
    run_formation_dynamics,
    spacecraft_ids,
)
from astramesh.scenarios.kernel import AgentKernel

ALGORITHM_NAME = "none (status exchange only; no allocation)"
MESSAGES_FILE = "messages.jsonl"


@dataclass(frozen=True, slots=True)
class AgentNetworkRun:
    formation: FormationRun
    trace: list[dict[str, Any]]
    summary: dict[str, Any]
    agents: dict[str, SpacecraftAgent]


def make_links(config: AgentNetworkScenario | Any) -> LinkModel:
    net = config.network
    return LinkModel(
        range_m=net.crosslink_range_km * 1e3,
        min_ray_altitude_m=net.min_ray_altitude_km * 1e3,
        delay_ns=seconds_to_ns(net.delay_s),
        loss_probability=net.loss_probability,
        duplicate_probability=net.duplicate_probability,
    )


def make_kernel(
    config: AgentNetworkScenario | Any,
    formation: FormationRun,
    agents: dict[str, SpacecraftAgent],
    streams: RandomStreams,
    log: EventLog,
) -> AgentKernel:
    spec = config.time.clock_spec()
    ag = config.agents
    return AgentKernel(
        positions_m=formation.trajectory.y,
        ids=list(agents),
        agents=agents,
        links=make_links(config),
        sensors=streams["sensors"],
        comms=streams["comms"],
        log=log,
        step_ns=spec.step_ns,
        end_ns=spec.duration_ns,
        nav_interval_ns=seconds_to_ns(ag.nav_fix_interval_s),
        nav_sigma_r_m=ag.nav_position_sigma_m,
        nav_sigma_v_mps=ag.nav_velocity_sigma_mps,
    )


def run_agent_network(
    config: AgentNetworkScenario, streams: RandomStreams, log: EventLog
) -> AgentNetworkRun:
    formation = run_formation_dynamics(config, log, end_event=False)
    ids = spacecraft_ids(formation.trajectory.n_spacecraft)
    settings = AgentSettings(
        status_interval_ns=seconds_to_ns(config.agents.status_interval_s),
        status_lifetime_ns=seconds_to_ns(config.agents.status_lifetime_s),
    )
    agents = {a: SpacecraftAgent(a, tuple(p for p in ids if p != a), settings) for a in ids}
    kernel = make_kernel(config, formation, agents, streams, log)
    kernel.run()
    record_scenario_end(config, log)
    summary = dict(formation.summary)
    summary.update(
        {
            "network": kernel.network_summary(),
            **kernel.agents_summary(),
            "note": "communication bookkeeping only; no allocation or research metrics",
        }
    )
    return AgentNetworkRun(formation, kernel.trace, summary, agents)

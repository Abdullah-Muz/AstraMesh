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
from astramesh.agents.health import BayesSettings, HealthSettings
from astramesh.communications.network import LinkModel
from astramesh.core.clock import seconds_to_ns
from astramesh.core.config import AgentNetworkScenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.faults.schedule import FaultSchedule
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


def health_settings(config: AgentNetworkScenario | Any) -> HealthSettings:
    ag = config.agents
    h = ag.health
    bayes = None
    if h is not None and h.model == "bayes":
        bayes = BayesSettings(
            status_interval_ns=seconds_to_ns(ag.status_interval_s),
            mtbf_ns=seconds_to_ns(h.bayes.mtbf_s),
            loss_a=h.bayes.loss_prior_a,
            loss_b=h.bayes.loss_prior_b,
            suspect_p=h.bayes.suspect_probability,
            lost_p=h.bayes.lost_probability,
        )
    return HealthSettings(
        suspect_ns=seconds_to_ns(ag.health_suspect_s),
        lost_ns=seconds_to_ns(ag.health_lost_s),
        recover_messages=ag.health_recover_messages,
        bayes=bayes,
    )


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
    faults: FaultSchedule | None = None,
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
        faults=faults,
    )


def run_agent_network(
    config: AgentNetworkScenario, streams: RandomStreams, log: EventLog
) -> AgentNetworkRun:
    formation = run_formation_dynamics(config, log, end_event=False)
    ids = spacecraft_ids(formation.trajectory.n_spacecraft)
    settings = AgentSettings(
        status_interval_ns=seconds_to_ns(config.agents.status_interval_s),
        status_lifetime_ns=seconds_to_ns(config.agents.status_lifetime_s),
        health=health_settings(config),
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

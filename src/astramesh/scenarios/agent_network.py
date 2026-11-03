"""Phase 2 increment 1: isolated agents exchanging status over the crosslink network.

The simulator (this module) owns all truth: the formation trajectory, the
connectivity graph, and the random streams. Agents receive only

* navigation fixes of their own orbit (truth + Gaussian noise, ``sensors`` stream), and
* messages delivered to them by the network (``comms`` stream for loss/duplication),

and they hand outbound messages back from ``step``. Time runs in a SimPy
environment whose unit is the integer nanosecond, so event times are exact
and ties are processed in a fixed scheduling order (same seed => same run).

Process order at one instant: navigation fixes, then agent steps in agent-ID
order, then deliveries in the order they were scheduled.

No allocation algorithm runs yet; plans stay at version 0. Outputs are
communication bookkeeping, not research results.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

import networkx as nx
import simpy

from astramesh.agents.agent import REJECT_REASONS, AgentSettings, SpacecraftAgent
from astramesh.agents.packets import NavigationFix
from astramesh.communications.messages import Delivery, Message
from astramesh.communications.network import LinkModel, connectivity_graph, transmit
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

ALGORITHM_NAME = "none (status exchange only; no allocation)"
MESSAGES_FILE = "messages.jsonl"


@dataclass(frozen=True, slots=True)
class AgentNetworkRun:
    formation: FormationRun
    trace: list[dict[str, Any]]
    summary: dict[str, Any]
    agents: dict[str, SpacecraftAgent]


def run_agent_network(
    config: AgentNetworkScenario, streams: RandomStreams, log: EventLog
) -> AgentNetworkRun:
    formation = run_formation_dynamics(config, log, end_event=False)
    traj = formation.trajectory
    spec = config.time.clock_spec()
    step_ns, end_ns = spec.step_ns, spec.duration_ns
    ids = spacecraft_ids(traj.n_spacecraft)
    net, ag = config.network, config.agents
    links = LinkModel(
        range_m=net.crosslink_range_km * 1e3,
        min_ray_altitude_m=net.min_ray_altitude_km * 1e3,
        delay_ns=seconds_to_ns(net.delay_s),
        loss_probability=net.loss_probability,
        duplicate_probability=net.duplicate_probability,
    )
    settings = AgentSettings(
        status_interval_ns=seconds_to_ns(ag.status_interval_s),
        status_lifetime_ns=seconds_to_ns(ag.status_lifetime_s),
    )
    agents = {a: SpacecraftAgent(a, tuple(p for p in ids if p != a), settings) for a in ids}
    sensors, comms = streams["sensors"], streams["comms"]
    env = simpy.Environment(initial_time=0)
    trace: list[dict[str, Any]] = []
    counts = {"sent": 0, "linked": 0, "lost": 0, "unreachable": 0, "delivered": 0,
              "duplicates_injected": 0, "bytes_sent": 0, "in_flight_at_end": 0}  # fmt: skip
    graph_stats = {"epochs": 0, "fully_connected": 0, "min_edges": 10**9, "max_edges": 0}
    prev_edges: set[tuple[str, str]] | None = None

    def tick_of(t_ns: int) -> int:
        return t_ns // step_ns

    def record(t_ns: int, source: str, kind: str, data: dict[str, Any]) -> None:
        log.record(tick=tick_of(t_ns), time_ns=t_ns, source=source, kind=kind, data=data)

    def graph_at(t_ns: int) -> nx.DiGraph:
        nonlocal prev_edges
        g = connectivity_graph(ids, traj.y[tick_of(t_ns), :, :3], links)
        edges = set(g.edges())
        if prev_edges is not None:
            for e in sorted(edges - prev_edges):
                record(t_ns, "network", "link_up", {"from": e[0], "to": e[1]})
            for e in sorted(prev_edges - edges):
                record(t_ns, "network", "link_down", {"from": e[0], "to": e[1]})
        prev_edges = edges
        return g

    def nav_process() -> Generator[simpy.Event, None, None]:
        interval = seconds_to_ns(ag.nav_fix_interval_s)
        while env.now <= end_ns:
            k = tick_of(int(env.now))
            for j, a in enumerate(ids):
                dr = sensors.normal(0.0, 1.0, 3) * ag.nav_position_sigma_m
                dv = sensors.normal(0.0, 1.0, 3) * ag.nav_velocity_sigma_mps
                r = traj.y[k, j, :3] + dr
                v = traj.y[k, j, 3:] + dv
                agents[a].observe(NavigationFix(
                    t_ns=int(env.now),
                    r_m=(float(r[0]), float(r[1]), float(r[2])),
                    v_mps=(float(v[0]), float(v[1]), float(v[2])),
                    sigma_r_m=ag.nav_position_sigma_m,
                    sigma_v_mps=ag.nav_velocity_sigma_mps,
                ))  # fmt: skip
            yield env.timeout(interval)

    def deliver(d: Delivery) -> Generator[simpy.Event, None, None]:
        yield env.timeout(d.delivered_ns - int(env.now))
        agent = agents[d.receiver]
        agent.receive_messages([d])
        rejected = agent.drain_log()
        status = rejected[0]["reason"] if rejected else "accepted"
        counts["delivered"] += 1
        trace.append({"t_ns": d.delivered_ns, "event": "deliver", "sender": d.message.sender,
                      "seq": d.message.seq, "receiver": d.receiver, "result": status})  # fmt: skip
        if rejected:
            record(d.delivered_ns, d.receiver, "message_rejected", rejected[0])

    def send(msg: Message, now: int) -> None:
        g = graph_at(now)
        graph_stats["epochs"] += 1
        n_edges = g.number_of_edges()
        graph_stats["fully_connected"] += int(nx.is_strongly_connected(g))
        graph_stats["max_edges"] = max(graph_stats["max_edges"], n_edges)
        graph_stats["min_edges"] = min(graph_stats["min_edges"], n_edges)
        out = transmit(msg, now_ns=now, graph=g, peers=ids, links=links, rng=comms)
        counts["sent"] += 1
        counts["bytes_sent"] += msg.size_bytes
        counts["linked"] += len(out.deliveries) + len(out.lost_to)
        counts["lost"] += len(out.lost_to)
        counts["unreachable"] += len(out.out_of_range)
        seen: set[str] = set()
        for d in out.deliveries:
            if d.receiver in seen:
                counts["duplicates_injected"] += 1
                counts["linked"] -= 1  # a duplicate is not an extra link attempt
            seen.add(d.receiver)
            if d.delivered_ns > end_ns:
                counts["in_flight_at_end"] += 1
            env.process(deliver(d))
        trace.append(
            {
                "t_ns": now,
                "event": "send",
                "sender": msg.sender,
                "seq": msg.seq,
                "type": str(msg.msg_type),
                "bytes": msg.size_bytes,
                "lost_to": list(out.lost_to),
                "unreachable": list(out.out_of_range),
            }
        )

    def agent_process(a: str) -> Generator[simpy.Event, None, None]:
        interval = seconds_to_ns(ag.status_interval_s)
        while env.now <= end_ns:
            now = int(env.now)
            for msg in agents[a].step(now):
                send(msg, now)
            yield env.timeout(interval)

    env.process(nav_process())
    for a in ids:
        env.process(agent_process(a))
    env.run(until=end_ns + 1)
    record_scenario_end(config, log)

    rejected = {a: agents[a].rejected_counts() for a in ids}
    summary = dict(formation.summary)
    summary.update(
        {
            "network": {
                "model": "LOS + range, one hop, fixed delay, Bernoulli loss/duplication",
                **counts,
                "delivered_within_scenario": counts["delivered"],
                "status_epochs": graph_stats["epochs"],
                "fully_connected_epochs": graph_stats["fully_connected"],
                "min_directed_edges": graph_stats["min_edges"],
                "max_directed_edges": graph_stats["max_edges"],
            },
            "agents": {
                a: {
                    "accepted": agents[a].n_accepted,
                    "rejected": rejected[a],
                    "plan_version": agents[a].plan_version,
                    "peers": agents[a].peer_view(),
                }
                for a in ids
            },
            "rejected_total": {r: sum(rejected[a][r] for a in ids) for r in REJECT_REASONS},
            "max_status_gap_s": _max_gaps(trace, ids, end_ns),
            "note": "communication bookkeeping only; no allocation or research metrics",
        }
    )
    return AgentNetworkRun(formation, trace, summary, agents)


def _max_gaps(trace: list[dict[str, Any]], ids: list[str], end_ns: int) -> dict[str, float]:
    """Longest interval [s] between accepted status deliveries, per receiver<-sender pair."""
    last: dict[tuple[str, str], int] = {}
    gap: dict[tuple[str, str], int] = {}
    for e in trace:
        if e["event"] == "deliver" and e["result"] == "accepted" and e["t_ns"] <= end_ns:
            key = (e["receiver"], e["sender"])
            prev = last.get(key, 0)
            gap[key] = max(gap.get(key, 0), e["t_ns"] - prev)
            last[key] = e["t_ns"]
    out = {}
    for r in ids:
        for s in ids:
            if r == s:
                continue
            key = (r, s)
            g = max(gap.get(key, end_ns), end_ns - last.get(key, 0))
            out[f"{r}<-{s}"] = g / 1e9
    return out

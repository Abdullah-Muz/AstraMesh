"""Shared SimPy kernel for agent scenarios: sensors, agent steps, crosslink delivery.

One *driver* process runs every simulation tick and calls, in this fixed order:

1. navigation fixes (when due), from truth + ``sensors`` noise;
2. an optional scenario hook (e.g. housekeeping and plan execution);
3. ``agent.step(t)`` for every agent in ID order; outbound messages are offered
   to the network immediately.

Each delivery is its own SimPy process that wakes at its arrival time. Time is
integer nanoseconds; ties between a delivery and the driver at the same instant
are resolved by SimPy's scheduling order, which is deterministic.

Agents' log entries are recorded as events after every delivery and every
tick, with the agent as the source.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

import networkx as nx
import numpy as np
import simpy

from astramesh.agents.agent import REJECT_REASONS, SpacecraftAgent
from astramesh.agents.packets import NavigationFix
from astramesh.communications.messages import Delivery, Message
from astramesh.communications.network import LinkModel, connectivity_graph, transmit
from astramesh.core.events import EventLog


class AgentKernel:
    def __init__(
        self,
        *,
        positions_m: np.ndarray,  # (n_t, n_sc, 6) truth states on the tick grid
        ids: list[str],
        agents: dict[str, SpacecraftAgent],
        links: LinkModel,
        sensors: np.random.Generator,
        comms: np.random.Generator,
        log: EventLog,
        step_ns: int,
        end_ns: int,
        nav_interval_ns: int,
        nav_sigma_r_m: float,
        nav_sigma_v_mps: float,
    ) -> None:
        self.y = positions_m
        self.ids = ids
        self.agents = agents
        self.links = links
        self.sensors, self.comms = sensors, comms
        self.log = log
        self.step_ns, self.end_ns = step_ns, end_ns
        self.nav_interval_ns = nav_interval_ns
        self.nav_sigma_r_m, self.nav_sigma_v_mps = nav_sigma_r_m, nav_sigma_v_mps
        self.env = simpy.Environment(initial_time=0)
        self.trace: list[dict[str, Any]] = []
        self.counts = dict.fromkeys(
            ("sent", "linked", "lost", "unreachable", "delivered", "duplicates_injected",
             "bytes_sent", "in_flight_at_end"),
            0,
        )  # fmt: skip
        self.graph_stats = {"epochs": 0, "fully_connected": 0, "min_edges": 10**9, "max_edges": 0}
        self._prev_edges: set[tuple[str, str]] | None = None

    # -- events -------------------------------------------------------------------
    def record(self, t_ns: int, source: str, kind: str, data: dict[str, Any]) -> None:
        self.log.record(tick=t_ns // self.step_ns, time_ns=t_ns, source=source, kind=kind,
                        data=data)  # fmt: skip

    def flush_agent_log(self, a: str, t_ns: int) -> list[dict[str, Any]]:
        entries = self.agents[a].drain_log()
        for e in entries:
            data = {k: v for k, v in e.items() if k != "kind"}
            kind = e["kind"]
            if kind == "message_rejected":
                data = dict(e)  # keep the increment-1 event payload (includes "kind")
            self.record(t_ns, a, kind, data)
        return entries

    # -- network ------------------------------------------------------------------
    def _graph_at(self, t_ns: int) -> nx.DiGraph:
        g = connectivity_graph(self.ids, self.y[t_ns // self.step_ns, :, :3], self.links)
        edges = set(g.edges())
        if self._prev_edges is not None:
            for e in sorted(edges - self._prev_edges):
                self.record(t_ns, "network", "link_up", {"from": e[0], "to": e[1]})
            for e in sorted(self._prev_edges - edges):
                self.record(t_ns, "network", "link_down", {"from": e[0], "to": e[1]})
        self._prev_edges = edges
        return g

    def _deliver(self, d: Delivery) -> Generator[simpy.Event, None, None]:
        yield self.env.timeout(d.delivered_ns - int(self.env.now))
        self.agents[d.receiver].receive_messages([d])
        entries = self.flush_agent_log(d.receiver, d.delivered_ns)
        rejected = [e for e in entries if e["kind"] == "message_rejected"]
        self.counts["delivered"] += 1
        result = rejected[0]["reason"] if rejected else "accepted"
        self.trace.append({"t_ns": d.delivered_ns, "event": "deliver", "sender": d.message.sender,
                           "seq": d.message.seq, "receiver": d.receiver,
                           "result": result})  # fmt: skip

    def send(self, msg: Message, now: int) -> None:
        g = self._graph_at(now)
        gs, c = self.graph_stats, self.counts
        gs["epochs"] += 1
        n_edges = g.number_of_edges()
        gs["fully_connected"] += int(nx.is_strongly_connected(g))
        gs["max_edges"] = max(gs["max_edges"], n_edges)
        gs["min_edges"] = min(gs["min_edges"], n_edges)
        out = transmit(msg, now_ns=now, graph=g, peers=self.ids, links=self.links, rng=self.comms)
        c["sent"] += 1
        c["bytes_sent"] += msg.size_bytes
        c["linked"] += len(out.deliveries) + len(out.lost_to)
        c["lost"] += len(out.lost_to)
        c["unreachable"] += len(out.out_of_range)
        seen: set[str] = set()
        for d in out.deliveries:
            if d.receiver in seen:
                c["duplicates_injected"] += 1
                c["linked"] -= 1  # a duplicate is not an extra link attempt
            seen.add(d.receiver)
            if d.delivered_ns > self.end_ns:
                c["in_flight_at_end"] += 1
            self.env.process(self._deliver(d))
        self.trace.append({"t_ns": now, "event": "send", "sender": msg.sender, "seq": msg.seq,
                           "type": str(msg.msg_type), "bytes": msg.size_bytes,
                           "lost_to": list(out.lost_to),
                           "unreachable": list(out.out_of_range)})  # fmt: skip

    # -- driver ---------------------------------------------------------------------
    def _nav_fixes(self, k: int, t: int) -> None:
        for j, a in enumerate(self.ids):
            dr = self.sensors.normal(0.0, 1.0, 3) * self.nav_sigma_r_m
            dv = self.sensors.normal(0.0, 1.0, 3) * self.nav_sigma_v_mps
            r = self.y[k, j, :3] + dr
            v = self.y[k, j, 3:] + dv
            self.agents[a].observe(NavigationFix(
                t_ns=t,
                r_m=(float(r[0]), float(r[1]), float(r[2])),
                v_mps=(float(v[0]), float(v[1]), float(v[2])),
                sigma_r_m=self.nav_sigma_r_m,
                sigma_v_mps=self.nav_sigma_v_mps,
            ))  # fmt: skip

    def run(self, tick_hook: Callable[[int, int], None] | None = None) -> None:
        def driver() -> Generator[simpy.Event, None, None]:
            k = 0
            while k * self.step_ns <= self.end_ns:
                t = k * self.step_ns
                if t % self.nav_interval_ns == 0:
                    self._nav_fixes(k, t)
                if tick_hook is not None:
                    tick_hook(k, t)
                for a in self.ids:
                    for msg in self.agents[a].step(t):
                        self.send(msg, t)
                    self.flush_agent_log(a, t)
                k += 1
                yield self.env.timeout(self.step_ns)

        self.env.process(driver())
        self.env.run(until=self.end_ns + 1)

    # -- summaries --------------------------------------------------------------------
    def network_summary(self) -> dict[str, Any]:
        gs = self.graph_stats
        return {
            "model": "LOS + range, one hop, fixed delay, Bernoulli loss/duplication",
            **self.counts,
            "delivered_within_scenario": self.counts["delivered"],
            "status_epochs": gs["epochs"],
            "fully_connected_epochs": gs["fully_connected"],
            "min_directed_edges": gs["min_edges"],
            "max_directed_edges": gs["max_edges"],
        }

    def agents_summary(self) -> dict[str, Any]:
        rejected = {a: self.agents[a].rejected_counts() for a in self.ids}
        return {
            "agents": {
                a: {
                    "accepted": self.agents[a].n_accepted,
                    "rejected": rejected[a],
                    "plan_version": self.agents[a].plan_version,
                    "peers": self.agents[a].peer_view(),
                }
                for a in self.ids
            },
            "rejected_total": {r: sum(rejected[a][r] for a in self.ids) for r in REJECT_REASONS},
            "max_status_gap_s": max_status_gaps(self.trace, self.ids, self.end_ns),
        }


def max_status_gaps(trace: list[dict[str, Any]], ids: list[str], end_ns: int) -> dict[str, float]:
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

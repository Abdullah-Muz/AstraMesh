"""Time-varying crosslink network G(t) and message delivery (spec §5.3).

Connectivity
    A directed edge i -> j exists at a simulation tick when the spacecraft are
    within ``range_m`` (synthetic maximum, not a link budget) and the straight
    line between them stays at least ``min_ray_altitude_m`` above a spherical
    Earth of radius R_eq (line of sight). Links are symmetric under this model,
    but the graph is a NetworkX ``DiGraph`` so asymmetric faults can be added
    later. Positions are truth states at the tick at or before the send time.

Delivery
    A message sent at time t goes to every out-neighbour of the sender in G(t)
    (one hop; there is no routing or relay in the network layer). Each
    (message, receiver) delivery is independently lost with
    ``loss_probability`` and, if not lost, duplicated with
    ``duplicate_probability`` (both from the ``comms`` random stream). A
    delivered copy arrives after the fixed application-level ``delay_ns``
    (spec: 1 s; not propagation time). Whether a link still exists at arrival
    is not re-checked.

The network never inspects payloads and never delivers to the sender.
Determinism: one uniform draw per (message, receiver) for loss and, if
delivered, one for duplication, in receiver-ID order; no NumPy transcendental
functions or BLAS.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np
from numpy.typing import NDArray

from astramesh.communications.messages import Delivery, Message
from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.state import dot3


@dataclass(frozen=True, slots=True)
class LinkModel:
    range_m: float
    min_ray_altitude_m: float
    delay_ns: int
    loss_probability: float
    duplicate_probability: float

    def __post_init__(self) -> None:
        if not self.range_m > 0.0:
            raise ValueError("range_m must be positive")
        if self.min_ray_altitude_m < 0.0:
            raise ValueError("min_ray_altitude_m must be >= 0")
        if self.delay_ns < 0:
            raise ValueError("delay_ns must be >= 0")
        for name in ("loss_probability", "duplicate_probability"):
            p = getattr(self, name)
            if not 0.0 <= p <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


def line_of_sight(a: NDArray[np.float64], b: NDArray[np.float64], radius_m: float) -> bool:
    """True if the segment a-b stays strictly outside a sphere of ``radius_m`` at the origin."""
    d = b - a
    dd = float(dot3(d, d))
    if dd == 0.0:
        return bool(float(dot3(a, a)) > radius_m * radius_m)
    s = -float(dot3(a, d)) / dd  # parameter of the closest point to the origin
    s = min(1.0, max(0.0, s))
    c = a + s * d
    return bool(float(dot3(c, c)) > radius_m * radius_m)


def connectivity_graph(ids: list[str], r_m: NDArray[np.float64], links: LinkModel) -> nx.DiGraph:
    """G(t) for positions ``r_m`` (n_sc, 3) [m] in an inertial or Earth-fixed frame."""
    g = nx.DiGraph()
    g.add_nodes_from(ids)
    radius = R_EARTH_EQ_M + links.min_ray_altitude_m
    r2 = links.range_m * links.range_m
    for i, a in enumerate(ids):
        for j in range(i + 1, len(ids)):
            d = r_m[j] - r_m[i]
            if float(dot3(d, d)) <= r2 and line_of_sight(r_m[i], r_m[j], radius):
                g.add_edge(a, ids[j])
                g.add_edge(ids[j], a)
    return g


@dataclass(frozen=True, slots=True)
class SendOutcome:
    """Result of offering one message to the network."""

    message: Message
    deliveries: tuple[Delivery, ...]  # includes duplicates, in arrival order
    lost_to: tuple[str, ...]
    out_of_range: tuple[str, ...]  # peers not linked at send time


def transmit(
    message: Message,
    *,
    now_ns: int,
    graph: nx.DiGraph,
    peers: list[str],
    links: LinkModel,
    rng: np.random.Generator,
) -> SendOutcome:
    """Decide which peers receive ``message`` (see module docstring)."""
    if message.sender not in graph:
        raise ValueError(f"unknown sender {message.sender!r}")
    linked = set(graph.successors(message.sender))
    deliveries: list[Delivery] = []
    lost: list[str] = []
    unreachable: list[str] = []
    arrive = now_ns + links.delay_ns
    for peer in sorted(p for p in peers if p != message.sender):
        if peer not in linked:
            unreachable.append(peer)
            continue
        if float(rng.random()) < links.loss_probability:
            lost.append(peer)
            continue
        deliveries.append(Delivery(message, peer, arrive))
        if float(rng.random()) < links.duplicate_probability:
            deliveries.append(Delivery(message, peer, arrive))
    return SendOutcome(message, tuple(deliveries), tuple(lost), tuple(unreachable))

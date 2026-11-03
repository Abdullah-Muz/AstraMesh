"""Crosslink geometry and delivery decisions."""

from __future__ import annotations

import numpy as np
import pytest

from astramesh.communications.messages import Message, MessageType
from astramesh.communications.network import (
    LinkModel,
    connectivity_graph,
    line_of_sight,
    transmit,
)
from astramesh.dynamics.constants import R_EARTH_EQ_M

R = R_EARTH_EQ_M
LEO = R + 525e3


def _links(**kw: float) -> LinkModel:
    args = {"range_m": 100e3, "min_ray_altitude_m": 0.0, "delay_ns": 10**9,
            "loss_probability": 0.0, "duplicate_probability": 0.0}  # fmt: skip
    args.update(kw)
    return LinkModel(**args)  # type: ignore[arg-type]


def test_line_of_sight_blocked_by_earth_and_clear_otherwise() -> None:
    a = np.array([LEO, 0.0, 0.0])
    assert not line_of_sight(a, -a, R)  # through the centre
    assert line_of_sight(a, np.array([LEO, 50e3, 0.0]), R)
    # Chord between two points at angle 2*theta clears R iff LEO*cos(theta) > R.
    theta_max = np.arccos(R / LEO)
    for th, ok in ((theta_max * 0.99, True), (theta_max * 1.01, False)):
        p = np.array([LEO * np.cos(th), LEO * np.sin(th), 0.0])
        q = np.array([LEO * np.cos(th), -LEO * np.sin(th), 0.0])
        assert line_of_sight(p, q, R) is ok


def test_graph_uses_range_and_is_symmetric() -> None:
    r = np.array([[LEO, 0.0, 0.0], [LEO, 60e3, 0.0], [LEO, 120e3, 0.0]])
    g = connectivity_graph(["a", "b", "c"], r, _links())
    assert sorted(g.edges()) == [("a", "b"), ("b", "a"), ("b", "c"), ("c", "b")]


def _msg() -> Message:
    return Message("a", 0, 0, 10**10, MessageType.STATUS, 0, {})


def test_transmit_loss_duplication_and_unreachable() -> None:
    r = np.array([[LEO, 0.0, 0.0], [LEO, 60e3, 0.0], [LEO, 120e3, 0.0]])
    g = connectivity_graph(["a", "b", "c"], r, _links())
    rng = np.random.default_rng(0)
    out = transmit(_msg(), now_ns=5, graph=g, peers=["a", "b", "c"], links=_links(), rng=rng)
    assert [(d.receiver, d.delivered_ns) for d in out.deliveries] == [("b", 5 + 10**9)]
    assert out.out_of_range == ("c",)
    lost = transmit(_msg(), now_ns=5, graph=g, peers=["a", "b", "c"],
                    links=_links(loss_probability=1.0), rng=rng)  # fmt: skip
    assert lost.deliveries == ()
    assert lost.lost_to == ("b",)
    dup = transmit(_msg(), now_ns=5, graph=g, peers=["a", "b", "c"],
                   links=_links(duplicate_probability=1.0), rng=rng)  # fmt: skip
    assert [d.receiver for d in dup.deliveries] == ["b", "b"]


def test_loss_rate_is_statistically_consistent() -> None:
    r = np.array([[LEO, 0.0, 0.0], [LEO, 20e3, 0.0]])
    g = connectivity_graph(["a", "b"], r, _links())
    rng = np.random.default_rng(42)
    links = _links(loss_probability=0.1)
    n = 20_000
    lost = sum(len(transmit(_msg(), now_ns=0, graph=g, peers=["a", "b"], links=links,
                            rng=rng).lost_to) for _ in range(n))  # fmt: skip
    assert abs(lost / n - 0.1) < 5 * (0.1 * 0.9 / n) ** 0.5  # 5-sigma binomial bound


@pytest.mark.parametrize(
    "kw", [{"range_m": 0.0}, {"delay_ns": -1}, {"loss_probability": 1.5},
           {"duplicate_probability": -0.1}, {"min_ray_altitude_m": -1.0}],
)  # fmt: skip
def test_link_model_validation(kw: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must be"):
        _links(**kw)

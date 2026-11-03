"""Gate P2: agents act only on local state and delivered messages (spec §5.1, §14.1).

* Static: agent code imports nothing that can reach truth, the network, or the simulator.
* Dynamic: after a run, nothing reachable from an agent is a simulator object,
  a truth array, a random stream, or another agent.
* Messages are immutable, so a receiver cannot alter what a sender holds.
"""

from __future__ import annotations

import ast
import copy
import gc
from pathlib import Path
from types import MappingProxyType
from typing import Any

import networkx as nx
import numpy as np
import pytest
import simpy

from astramesh.agents.agent import SpacecraftAgent
from astramesh.communications.messages import Message, MessageError, MessageType
from astramesh.core.config import AgentNetworkScenario, parse_scenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.dynamics.twobody import Trajectory
from astramesh.scenarios.agent_network import run_agent_network

AGENTS_DIR = Path(__file__).resolve().parents[2] / "src" / "astramesh" / "agents"
ALLOWED_ASTRAMESH = ("astramesh.agents", "astramesh.communications.messages")
STDLIB_OK = {"__future__", "collections", "dataclasses", "typing", "math", "enum"}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def test_agent_code_imports_no_truth_network_or_simulator() -> None:
    files = sorted(AGENTS_DIR.glob("*.py"))
    assert files
    for f in files:
        for mod in _imports(f):
            if mod.startswith("astramesh"):
                assert mod.startswith(ALLOWED_ASTRAMESH), f"{f.name} imports {mod}"
            else:
                assert mod.split(".")[0] in STDLIB_OK, f"{f.name} imports {mod}"


@pytest.fixture(scope="module")
def short_run(request: pytest.FixtureRequest) -> Any:
    import yaml

    root = Path(__file__).resolve().parents[2]
    raw = yaml.safe_load((root / "configs/experiments/agent_network_24h.yaml").read_text())
    raw["time"]["duration_s"] = 1800
    raw["network"]["duplicate_probability"] = 0.05
    cfg = parse_scenario(raw)
    assert isinstance(cfg, AgentNetworkScenario)
    return run_agent_network(cfg, RandomStreams(cfg.random.seed), EventLog())


FORBIDDEN = (simpy.Environment, nx.Graph, Trajectory, RandomStreams, np.random.Generator,
             EventLog, np.ndarray)  # fmt: skip


def _reachable(root: object, limit: int = 200_000) -> list[object]:
    seen: dict[int, object] = {id(root): root}
    stack = [root]
    while stack and len(seen) < limit:
        obj = stack.pop()
        for ref in gc.get_referents(obj):
            if isinstance(ref, type) or id(ref) in seen:
                continue  # classes/modules are code, not state
            if type(ref).__name__ == "module":
                continue
            seen[id(ref)] = ref
            stack.append(ref)
    return list(seen.values())


def test_agents_hold_no_reference_to_simulator_truth_or_peers(short_run: Any) -> None:
    for agent in short_run.agents.values():
        for obj in _reachable(agent):
            assert not isinstance(obj, FORBIDDEN), f"{agent.agent_id} reaches {type(obj).__name__}"
            if isinstance(obj, SpacecraftAgent):
                assert obj is agent, f"{agent.agent_id} reaches agent {obj.agent_id}"


def test_message_payload_is_deeply_immutable() -> None:
    m = Message("sc00", 0, 0, 10, MessageType.STATUS, 0, {"a": [1.0, {"b": 2}]})
    assert isinstance(m.payload, MappingProxyType)
    with pytest.raises(TypeError):
        m.payload["a"] = 1  # type: ignore[index]
    inner = m.payload["a"]
    assert isinstance(inner, tuple)
    with pytest.raises(TypeError):
        inner[1]["b"] = 3
    with pytest.raises(AttributeError):
        m.seq = 5  # type: ignore[misc]
    src = {"x": [1.0, 2.0]}
    m2 = Message("sc00", 1, 0, 10, MessageType.STATUS, 0, src)
    src["x"].append(3.0)  # sender mutating its own data afterwards...
    assert m2.payload["x"] == (1.0, 2.0)  # ...does not change the message


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sender": ""},
        {"seq": -1},
        {"created_ns": 10, "expires_ns": 10},
        {"payload": {"x": float("nan")}},
        {"payload": {"x": object()}},
        {"payload": {1: 2}},
        {"plan_version": True},
    ],
)
def test_message_schema_violations_raise(kwargs: dict[str, Any]) -> None:
    base: dict[str, Any] = {"sender": "sc00", "seq": 0, "created_ns": 0, "expires_ns": 10,
            "msg_type": MessageType.STATUS, "plan_version": 0, "payload": {}}  # fmt: skip
    base.update(kwargs)
    with pytest.raises(MessageError):
        Message(**base)


def test_run_state_is_not_shared_between_agents(short_run: Any) -> None:
    agents = list(short_run.agents.values())
    for a in agents:
        for b in agents:
            if a is not b:
                assert a._peer_table is not b._peer_table
                assert a._accepted is not b._accepted
    snapshot = copy.deepcopy(agents[1].peer_view())
    agents[0]._peer_table["sc01"].newest_seq = 10**9  # tamper with one agent...
    assert agents[1].peer_view() == snapshot  # ...another is unaffected

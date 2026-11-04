# Autonomy Architecture

> **Owner:** Abdullah Muzher · **Status:** IN PROGRESS — Phase 2 increment 1 (agents, messages, network) implemented · **Spec:** §5, §14.1 · **Target phase:** 2 · **Last updated:** 2026-11-03

## Purpose

Specify the `SpacecraftAgent` components, interfaces, message schema, network model, and health-belief semantics in implementation detail.

## Requirements to satisfy (from spec)

- Each agent holds independent estimators, resource manager, task database, inbox/outbox, allocation logic, guidance interface, safety supervisor, and audit log (§5.1).
- Agents never share writable mission state or read hidden truth or undelivered messages (§5.1, §14.1 hard stop).
- Message fields: sender ID, sequence ID, creation time, expiry, type, plan version, payload; duplicate, expiry, ordering, and reconciliation rules (§5.3).
- Health beliefs (`HEALTHY` … `UNKNOWN`) are distinct from simulator ground truth; evidence rules for `CONFIRMED_FAILED` (§5.4).

## Content

### 1. Truth / agent boundary (increment 1)

The **simulator** (`scenarios/agent_network.py`) owns all truth: the trajectory, the connectivity graph, the random streams, and the clock. An **agent** (`agents/agent.py`) receives only two kinds of input:

| Input | Contents | Source |
|---|---|---|
| `NavigationFix` (`agents/packets.py`) | its **own** GCRS position/velocity + Gaussian noise (σ stated in the packet) | truth + `sensors` stream |
| `Delivery` | one `Message` delivered to it by the network | `comms` stream (loss, duplication) |

Agents return outbound messages from `step(now)`; they never call the network, the simulator, or another agent.

**Enforced by tests** (`tests/agent_isolation/`):
- **Static:** agent modules may import only the standard library, `astramesh.agents`, and `astramesh.communications.messages`.
- **Dynamic:** after a run, nothing reachable from an agent's object graph is a SimPy environment, a NetworkX graph, a trajectory, an `ndarray`, a random stream, the event log, or another agent. The test is shown to fail when such a reference is planted.
- **Messages:** payloads are deep-frozen, so a sender editing its own data later does not change a sent message.

### 2. Message schema (`communications/messages.py`)

| Field | Meaning |
|---|---|
| `sender`, `seq` | identity; `(sender, seq)` is unique and is the duplicate key |
| `created_ns`, `expires_ns` | integer ns since the epoch; `expires_ns > created_ns` |
| `msg_type` | `status` (handled); `task_bid`, `task_award`, `plan_sync` (reserved, rejected as unhandled until allocation exists) |
| `plan_version` | the sender's plan version |
| `payload` | read-only mapping of JSON scalars, tuples and mappings; non-finite floats rejected |

Size is the canonical-JSON length in bytes, used for byte accounting.

### 3. Acceptance rules (agent side; first failing rule wins, nothing else changes)

1. `malformed`: not a `Delivery` of a `Message`, or addressed to another agent.
2. `from_self`
3. `unknown_sender`
4. `expired`: delivered at or after `expires_ns`.
5. `duplicate`: `(sender, seq)` already accepted.
6. `unhandled_type`
7. `stale`: `seq` older than the newest accepted from that sender, so an out-of-order message cannot overwrite newer peer state.

Each rejection increments a per-reason counter and is logged as a `message_rejected` event. A property test (Hypothesis, 300 random batches of valid and invalid deliveries) checks three things: the plan version never changes; a peer's newest sequence number equals the maximum over valid deliveries; and every delivery is either accepted or counted as rejected.

### 4. Network (`communications/network.py`, DL-040)

- **Links:** G(t) is a NetworkX `DiGraph`. Edge i→j exists if the range is ≤ 100 km and the segment clears R_eq + `min_ray_altitude` (line of sight). Positions are truth at the tick at or before the send time.
- **Delivery:** one hop, to every linked peer. Each (message, receiver) is lost with probability p_loss, otherwise duplicated with probability p_dup; one uniform draw each from the `comms` stream, in receiver-ID order. Arrival is after a fixed 1 s application delay, and the link is not re-checked at arrival.
- **Not in increment 1:** routing or relay, link outages and partitions (injection mechanism, spec S05 — Phase 3), bandwidth limits.

### 5. Kernel (DL-039)

SimPy `Environment` with the **integer nanosecond** as its time unit, so every event time is exact. Processes:
- a navigation-fix process every `nav_fix_interval_s`;
- one process per agent, stepping every `status_interval_s`;
- one process per delivery.

Same-instant order is fixed by one per-tick driver (`scenarios/kernel.py`): navigation fixes, then any scenario hook (housekeeping and plan execution), then agent steps in ID order. Deliveries run at their own arrival times. (Increment 1 as first committed let SimPy's scheduling order put status steps before that instant's fix from t = 30 s onward, contradicting this text. The shared kernel fixed it, which changed only status message sizes: DL-043.) Same seed gives a byte-identical event log, message trace and summary (regression test, verified under two OpenBLAS/NumPy CPU code paths).

### 6. Plan execution (increment 2a, DL-041, DL-043)

New sensor packets (`agents/packets.py`):
- **`Housekeeping`**, every tick: the agent's **own** battery and storage. Values are exact in Phase 2; noise or faults come later.
- **`PlanUplink`**, at t = 0: only that agent's planned observations, with algorithm and version. Older or equal versions are rejected and logged. Messages cannot change the plan: a property test interleaves arbitrary deliveries with execution and checks that the commands are unchanged.

`payload_command(now)` returns the task to observe during the next step, or nothing:
- **Before starting:** battery ≥ reserve, and enough storage for the rest of the slot.
- **While observing:** stop if housekeeping shows an empty battery or full storage.

Each refusal is logged as `observation_declined` with a reason. The simulator applies the command to the **true** battery and storage, and scores the observations against truth (`scenarios/nominal_operations.py`).

B0 and B1 are both *external* planners: the plan is made outside the agents and uplinked. B1 additionally uses truth illumination and is flagged `privileged_information` in `plan.json`, the events and the summary. Agents execute either plan with the same resource checks.

### 7. Decentralized allocation (increment 3, DL-045, DL-046)

For B2 and B3 there is no external plan. Each agent gets a **`CatalogUplink`** at t = 0: the shared task order, plus its own predicted slots and data volumes. The allocation state lives inside the agent:

- **B3 CBBA** (`agents/cbba.py`, P06): every 10 s the agent builds its bundle and broadcasts `plan_sync` (y, z, s). On receipt it applies Table I, updates timestamps (Eq. 5) and releases tasks (Eq. 6).
- **B2 auction** (`agents/auction.py`): one `task_bid` broadcast at t = 0. Each agent decides winners alone from the bids it received.

An agent handles only its own algorithm's message type. Any other allocation type is `unhandled_type`, and a badly formed payload is `malformed_payload`; neither changes the plan. The executable plan is rebuilt from the allocation state after every round and receipt. Each change bumps `plan_version` and is logged as `plan_changed`. An observation is committed at slot start and finished even if the agent is outbid later.

### 8. Not yet implemented

Inter-agent re-planning after faults, health beliefs (§5.4), estimators beyond the latest fix, safety supervisor. Each will be added behind the same boundary.

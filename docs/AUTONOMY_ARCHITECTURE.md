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

Same-instant order is fixed: fixes, then agents in ID order, then deliveries in scheduling order. Same seed gives a byte-identical event log, message trace and summary (regression test, verified under two OpenBLAS/NumPy CPU code paths).

### 6. Not yet implemented

Allocation (B0–B3), task database and commitments, resource manager, health beliefs (§5.4), estimators beyond the latest fix, safety supervisor. Each will be added behind the same boundary.

"""PA-09: gravity-only propagation is bit-for-bit repeatable.

Initial states are written as literal floats (not computed with sin/cos) so the
golden digest does not depend on the platform's libm. The propagator itself
uses only IEEE-754 elementwise +, -, *, / and sqrt, which are correctly
rounded everywhere. If the digest changes, either the integrator changed
deliberately (update it and add a docs/DECISION_LOG.md entry) or replay broke.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from astramesh.dynamics.state import CartesianState, Frame
from astramesh.dynamics.twobody import Trajectory, propagate_two_body

EPOCH = datetime(2025, 6, 1, tzinfo=UTC)
# Four spacecraft on the 525 km / 97.5 deg reference orbit, 0.17 deg apart in
# argument of latitude (illustrative only; formation design is PA-06).
INITIAL = [
    ((6903137.0, 0.0, 0.0), (0.0, -991.8438626609845, 7533.802098988372)),
    (
        (6903106.614334251, 2673.436129881634, -20306.763478656427),
        (22.546092962779305, -991.8394968435184, 7533.768937312398),
    ),
    (
        (6903015.4576045, 5346.848724336796, -40613.34818800044),
        (45.09198744245022, -991.8263994295538, 7533.669452576411),
    ),
    (
        (6902863.530613244, 8020.214248146205, -60919.575360293384),
        (67.63748495765167, -991.8045705343934, 7533.503645656219),
    ),
]
GOLDEN_SHA256 = "fedd4c1eac82bed7485317da2fbac53bd820a2047d40831bf45f296eade09c64"


def _run() -> Trajectory:
    states = [CartesianState(Frame.GCRS, EPOCH, 0, r, v) for r, v in INITIAL]
    return propagate_two_body(states, step_ns=10 * 10**9, n_steps=8640)


def _digest(traj: Trajectory) -> str:
    h = hashlib.sha256()
    h.update(traj.t_ns.astype("<i8").tobytes())
    h.update(traj.y.astype("<f8").tobytes())
    return h.hexdigest()


def test_pa09_same_inputs_bitwise_identical() -> None:
    assert _digest(_run()) == _digest(_run())


def test_pa09_matches_golden_digest() -> None:
    assert _digest(_run()) == GOLDEN_SHA256

"""Clohessy-Wiltshire (Hill) closed-form relative motion: a *cross-check only*.

Valid only within its assumptions: circular chief orbit, two-body motion,
and separations small relative to the orbit radius over a short horizon.
Coordinates are the rectilinear RIC frame of :mod:`astramesh.dynamics.frames`
(x radial, y in-track, z cross-track; velocities in the rotating frame).

Equations of motion: ``x'' - 2n y' - 3n^2 x = 0``, ``y'' + 2n x' = 0``,
``z'' + n^2 z = 0``, with ``n`` the chief's mean motion.

Known limitation at AstraMesh's ~20 km in-train spacing: a neighbour on the
same circular orbit sits at rectilinear radial offset ``x0 = -a(1 - cos du)``
(~ -29 m at 20 km), which CW interprets as a lower orbit and drifts along
track at ``-6 n x0`` per unit time (~1.1 km per orbit). Truth has no such
drift. This is CW linearization (curvature) error, not a dynamics error;
see ``docs/NUMERICAL_MISSION_DESIGN.md`` §B.4.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

from astramesh.dynamics.state import NonPhysicalStateError


def cw_state_transition(n_radps: float, t_s: float) -> NDArray[np.float64]:
    """6x6 CW state-transition matrix for ``[x, y, z, vx, vy, vz]``."""
    if not (math.isfinite(n_radps) and n_radps > 0):
        raise NonPhysicalStateError(f"mean motion must be positive and finite, got {n_radps!r}")
    if not math.isfinite(t_s):
        raise NonPhysicalStateError(f"t_s must be finite, got {t_s!r}")
    n = n_radps
    nt = n * t_s
    c, s = math.cos(nt), math.sin(nt)
    return np.array(
        [
            [4 - 3 * c, 0, 0, s / n, 2 * (1 - c) / n, 0],
            [6 * (s - nt), 1, 0, -2 * (1 - c) / n, (4 * s - 3 * nt) / n, 0],
            [0, 0, c, 0, 0, s / n],
            [3 * n * s, 0, 0, c, 2 * s, 0],
            [-6 * n * (1 - c), 0, 0, -2 * s, 4 * c - 3, 0],
            [0, 0, -n * s, 0, 0, c],
        ],
        dtype=np.float64,
    )


def cw_propagate(
    rel_state: ArrayLike, n_radps: float, t_s: float | ArrayLike
) -> NDArray[np.float64]:
    """Propagate a RIC relative state ``[x, y, z, vx, vy, vz]`` (m, m/s).

    ``t_s`` may be a scalar (returns shape (6,)) or 1-D array (returns (len, 6)).
    """
    x0 = np.asarray(rel_state, dtype=np.float64)
    if x0.shape != (6,) or not np.all(np.isfinite(x0)):
        raise NonPhysicalStateError(f"rel_state must be a finite 6-vector, got {x0.shape}")
    times = np.atleast_1d(np.asarray(t_s, dtype=np.float64))
    out = np.stack([cw_state_transition(n_radps, float(t)) @ x0 for t in times])
    return out[0] if np.ndim(t_s) == 0 else out

"""Along-track ("string-of-pearls") formation initialization (spec §3.2).

All spacecraft share the reference orbit's semi-major axis, eccentricity,
inclination, RAAN, and argument of periapsis; they differ only in mean
anomaly. Spacecraft 0 is the leader at the reference anomaly; spacecraft k
trails it by ``k * spacing_m / a`` radians of mean anomaly. For a circular
orbit this is an along-track arc of exactly ``spacing_m`` between neighbours
(chord ``2 a sin(spacing_m / 2a)``).

Equal semi-major axes give equal periods, so under **two-body** dynamics there
is no secular along-track drift. **Do not use this with J2:** equal osculating
elements give unequal mean semi-major axes, and the formation drifts by up to
7.7 km/day (``NUMERICAL_MISSION_DESIGN.md`` §B.5.4). For J2 dynamics use
:func:`astramesh.dynamics.mean_elements.mean_matched_formation` (DL-027).
"""

from __future__ import annotations

import math

from astramesh.dynamics.elements import (
    KeplerElements,
    mean_to_true_anomaly,
    true_to_mean_anomaly,
)


def along_track_formation(
    reference: KeplerElements, *, n_spacecraft: int, spacing_m: float
) -> tuple[KeplerElements, ...]:
    """Elements of ``n_spacecraft`` spacecraft trailing ``reference`` in-train."""
    if isinstance(n_spacecraft, bool) or not isinstance(n_spacecraft, int):
        raise TypeError(f"n_spacecraft must be an int, got {type(n_spacecraft).__name__}")
    if n_spacecraft < 1:
        raise ValueError(f"n_spacecraft must be >= 1, got {n_spacecraft}")
    if not (math.isfinite(spacing_m) and spacing_m > 0):
        raise ValueError(f"spacing_m must be positive and finite, got {spacing_m!r}")
    d_mean = spacing_m / reference.a_m
    if (n_spacecraft - 1) * d_mean >= math.pi:
        raise ValueError(
            f"formation spans {(n_spacecraft - 1) * spacing_m / 1e3:.1f} km, more than half "
            "an orbit; along-track neighbours would no longer be well defined"
        )
    m0 = true_to_mean_anomaly(reference.nu_rad, reference.e)
    return tuple(
        KeplerElements(
            a_m=reference.a_m,
            e=reference.e,
            i_rad=reference.i_rad,
            raan_rad=reference.raan_rad,
            argp_rad=reference.argp_rad,
            nu_rad=mean_to_true_anomaly(m0 - k * d_mean, reference.e),
        )
        for k in range(n_spacecraft)
    )

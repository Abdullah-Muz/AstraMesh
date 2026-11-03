"""Sensor packets: the only way simulator truth reaches an agent (spec §5.2 ``observe``).

Packets are immutable and contain plain tuples/floats, never arrays or
objects shared with the simulator. Each packet is a *measurement* with stated
noise, not truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavigationFix:
    """Own-orbit GNSS-like fix: GCRS position/velocity with isotropic 1-sigma noise."""

    t_ns: int
    r_m: tuple[float, float, float]
    v_mps: tuple[float, float, float]
    sigma_r_m: float
    sigma_v_mps: float

    def __post_init__(self) -> None:
        if isinstance(self.t_ns, bool) or not isinstance(self.t_ns, int) or self.t_ns < 0:
            raise ValueError("t_ns must be a non-negative int")
        for name in ("r_m", "v_mps"):
            v = getattr(self, name)
            if len(v) != 3 or not all(isinstance(x, float) and math.isfinite(x) for x in v):
                raise ValueError(f"{name} must be three finite floats")
        if not (self.sigma_r_m >= 0.0 and self.sigma_v_mps >= 0.0):
            raise ValueError("sigmas must be >= 0")

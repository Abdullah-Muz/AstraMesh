"""Position-based access of solar protons to each spacecraft (DL-090, DL-091).

Simulator side (truth and the onboard risk input), NumPy only; labelled a model, not a
measurement. GOES >= 10 MeV flux (GEO, taken as the interplanetary flux) reaches a
spacecraft only where its invariant latitude is at or above the cutoff for 10 MeV
protons:

    Lambda_c = quiet - slope * max(-SYM-H, 0),  the shift capped at ``max_shift``,

with quiet = 65.2 deg (R08: Dst-corrected 8-15 MeV/n He cutoffs on a 25.85 deg circle,
~10 MeV protons about 1 deg poleward) and slope = 1 / 19.11 deg/nT (R08's first-order
Dst correction; SYM-H as the Dst proxy, R06). R08 observed down to Dst ~ -150 nT only;
the 15 deg cap is R08's own linear extrapolation to Dst ~ -300 nT. Access is a step
(R08 defines the cutoff at half the polar rate; the edge is sharp), so protons above
10 MeV just equatorward of the cutoff are ignored.

A missing SYM-H is treated conservatively: the cutoff moves by the whole cap (or to
the equator when uncapped), so missing data never shrinks the exposed region.

The onboard radiation input (DL-090 option A) is the forecast next-hour maximum times
the largest access along the spacecraft's own predicted track over the horizon; the
track is the precomputed trajectory (10 m navigation error is negligible here).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class CutoffModel:
    quiet_deg: float = 65.2
    slope_deg_per_nt: float = 1.0 / 19.11
    max_shift_deg: float | None = 15.0

    def cutoff_deg(self, sym_h_nt: float | None) -> float:
        """Invariant-latitude cutoff for >= 10 MeV protons [deg]."""
        if sym_h_nt is None or not np.isfinite(sym_h_nt):
            shift = self.max_shift_deg if self.max_shift_deg is not None else self.quiet_deg
        else:
            shift = self.slope_deg_per_nt * max(-float(sym_h_nt), 0.0)
            if self.max_shift_deg is not None:
                shift = min(shift, self.max_shift_deg)
        return max(self.quiet_deg - shift, 0.0)


def forward_window_max(x: FloatArray, window: int) -> FloatArray:
    """``out[k] = max(x[k : k + window])`` along axis 0 (truncated at the end)."""
    if window < 1:
        raise ValueError("window must be >= 1")
    x2 = x.reshape(len(x), -1)
    out = np.empty_like(x2)
    n = len(x2)
    for c in range(x2.shape[1]):
        col = x2[:, c]
        q: deque[int] = deque()  # indices with decreasing values
        for i in range(n - 1, -1, -1):
            while q and col[q[-1]] <= col[i]:
                q.pop()
            q.append(i)
            while q[0] >= i + window:
                q.popleft()
            out[i, c] = col[q[0]]
    return out.reshape(x.shape)

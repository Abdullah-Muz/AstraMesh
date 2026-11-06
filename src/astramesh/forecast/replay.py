"""S11 storm replay: the derived real-data series the simulation reads (DL-069).

Simulator-side, standard library and NumPy only. ``configs/data/s11_storm_series.json``
(made by ``scripts/data/make_storm_series.py``, sha256 pinned in each config) holds, on
the GOES 5-min grid for 8-15 May 2024:

* ``truth_flux_pfu``: the measured >= 10 MeV flux of each record (what the payload
  meets during that 5-min average);
* ``forecast_flux_pfu``: per forecast (``P-A``, ``P-B/q50``, ``P-C/q50``, ``P-B/q90``,
  ``P-C/q90``), the forecast of the next-hour maximum issued when that record arrives;
* ``sym_h_nt`` and ``ae_nt``: 5-min means.

Record ``i`` covers [start + i step, start + (i + 1) step) and becomes available
``latency`` after it starts. ``None`` in the file (no valid data) stays missing: the
supervisor never reads it as zero risk (DL-056).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[3]
FloatArray = npt.NDArray[np.float64]
FORECASTS = ("P-A", "P-B/q50", "P-C/q50", "P-B/q90", "P-C/q90")


def _arr(xs: list[float | None]) -> FloatArray:
    return np.array([math.nan if x is None else float(x) for x in xs], dtype=float)


@dataclass(frozen=True, slots=True)
class StormSeries:
    start_ns: int  # Unix ns of record 0
    step_ns: int
    latency_ns: int
    truth_pfu: FloatArray
    forecast_pfu: dict[str, FloatArray]
    sym_h_nt: FloatArray
    ae_nt: FloatArray

    @classmethod
    def load(cls, path: str, sha256: str) -> StormSeries:
        data = (ROOT / path).read_bytes()
        got = hashlib.sha256(data).hexdigest()
        if got != sha256:
            raise ValueError(f"{path}: sha256 {got} != pinned {sha256}")
        d = json.loads(data)
        start = int(np.datetime64(d["record_start_utc"].rstrip("Z"), "ns").astype(np.int64))
        fc = {k: _arr(v) for k, v in d["forecast_flux_pfu"].items()}
        if set(fc) != set(FORECASTS):
            raise ValueError(f"{path}: forecasts {sorted(fc)} != {sorted(FORECASTS)}")
        out = cls(start, int(d["step_s"]) * 10**9, int(d["latency_s"]) * 10**9,
                  _arr(d["truth_flux_pfu"]), fc, _arr(d["sym_h_nt"]), _arr(d["ae_nt"]))  # fmt: skip
        n = len(out.truth_pfu)
        if any(len(v) != n for v in (*fc.values(), out.sym_h_nt, out.ae_nt)):
            raise ValueError(f"{path}: series lengths differ")
        return out

    def _at(self, x: FloatArray, t_unix_ns: int, delay_ns: int) -> float | None:
        i = (t_unix_ns - self.start_ns - delay_ns) // self.step_ns
        if i < 0 or i >= len(x) or math.isnan(x[i]):
            return None
        return float(x[i])

    def truth(self, t_unix_ns: int) -> float | None:
        """Measured flux at ``t`` (pfu); evaluation only, never shown to agents."""
        return self._at(self.truth_pfu, t_unix_ns, 0)

    def forecast(self, name: str, t_unix_ns: int) -> float | None:
        """Latest forecast of the next-hour maximum available at ``t`` (pfu)."""
        return self._at(self.forecast_pfu[name], t_unix_ns, self.latency_ns)

    def indices(self, t_unix_ns: int) -> tuple[float | None, float | None]:
        """Latest available (SYM-H, AE) at ``t`` [nT]."""
        return (self._at(self.sym_h_nt, t_unix_ns, self.latency_ns),
                self._at(self.ae_nt, t_unix_ns, self.latency_ns))  # fmt: skip

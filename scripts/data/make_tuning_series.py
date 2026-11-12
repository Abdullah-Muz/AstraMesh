"""Build the handover tuning-storm series (DL-094): 8-16 February 2024, out of sample.

Run:  uv run python scripts/data/make_tuning_series.py

Same format as ``configs/data/s11_storm_series.json`` (``astramesh.forecast.replay``),
for the 2024 Q1 fold storm chosen by the owner (DL-094): P-B and P-C (1 h horizon,
quantiles 0.5 and 0.9) are fitted only on training rows whose whole target window ends
before 1 Jan 2024 (the forward-chaining rule of ``storm_forecast_benchmark.py``), then
forecast 8 Feb 2024 00:00 - 16 Feb 2024 00:00 UT. Writes
``configs/data/tuning_feb2024_series.json`` and prints its sha256. Deterministic.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from astramesh.datasets import goes, omni
from astramesh.datasets.goes import STEP_NS
from astramesh.forecast.features import LATENCY_NS, build_grid, features, target
from astramesh.forecast.models import PB, PC, PC_SETTINGS, pa_predict
from astramesh.forecast.replay import FORECASTS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "configs" / "data" / "tuning_feb2024_series.json"
HORIZON_S = 3600
FOLD_START = "2024-01-01"
WINDOW = ("2024-02-08", "2024-02-16")


def _ns(day: str) -> int:
    return int(np.datetime64(day, "ns").astype(np.int64))


def _round(x: Any, digits: int = 4) -> list[float | None]:
    out: list[float | None] = []
    for v in np.asarray(x, dtype=float):
        out.append(None if not math.isfinite(v) else float(f"{v:.{digits}g}"))
    return out


def main() -> int:
    g = build_grid(goes.load("DS-08"), omni.load("DS-09"))
    X, y = features(g), target(g, HORIZON_S)
    fit = g.t_ns + LATENCY_NS + HORIZON_S * 10**9 <= _ns(FOLD_START)
    win = (g.t_ns >= _ns(WINDOW[0])) & (g.t_ns < _ns(WINDOW[1]))
    idx = np.flatnonzero(win)
    if len(idx) == 0 or np.any(np.diff(g.t_ns[idx]) != STEP_NS):
        raise ValueError("tuning window is not a contiguous 5-min grid")
    logs = {"P-A": pa_predict(X[idx])}
    for q, tag in ((0.5, "q50"), (0.9, "q90")):
        logs[f"P-B/{tag}"] = PB(q).fit(X[fit], y[fit]).predict(X[idx])
        logs[f"P-C/{tag}"] = PC(q).fit(X[fit], y[fit]).predict(X[idx])
    assert set(logs) == set(FORECASTS)
    start = np.datetime_as_string(np.datetime64(int(g.t_ns[idx[0]]), "ns"), unit="s")
    doc = {
        "description": "Handover tuning storm (DL-094): GOES-18 >= 10 MeV flux (DL-068 "
        "method), 1 h forecasts of its maximum, OMNI SYM-H and AE, 8-16 Feb 2024; forecasts "
        "fitted only on rows whose target window ends before 2024-01-01 (2024 Q1 fold).",
        "generated_by": "scripts/data/make_tuning_series.py",
        "sources": ["DS-08", "DS-09"],
        "record_start_utc": start + "Z",
        "step_s": STEP_NS // 10**9,
        "latency_s": LATENCY_NS // 10**9,
        "horizon_s": HORIZON_S,
        "pc_settings": PC_SETTINGS,
        "truth_flux_pfu": _round(g.flux[idx]),
        "forecast_flux_pfu": {k: _round(10.0 ** logs[k]) for k in FORECASTS},
        "sym_h_nt": _round(g.omni["sym_h_nt"][idx]),
        "ae_nt": _round(g.omni["ae_nt"][idx]),
    }
    text = json.dumps(doc, indent=0, separators=(",", ":")) + "\n"
    OUT.write_text(text, encoding="ascii")
    print(OUT.relative_to(ROOT), len(text), "bytes, sha256",
          hashlib.sha256(text.encode("ascii")).hexdigest())  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

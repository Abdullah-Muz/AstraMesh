"""Build the S11 storm series read by the simulation (DL-069).

Run:  uv run python scripts/data/make_storm_series.py

Fits P-B and P-C (1 h horizon, quantiles 0.5 and 0.9) on all training data (DS-08,
DS-09: Jan 2023 - Apr 2024), forecasts the held-out storm week (DS-07, DS-06: 8-15 May
2024) and writes ``configs/data/s11_storm_series.json``: measured flux, the five
forecasts, SYM-H and AE on the GOES 5-min grid (``astramesh.forecast.replay``). Prints
the file's sha256 for the S11 configs. Deterministic (fixed seeds, single process).
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
OUT = ROOT / "configs" / "data" / "s11_storm_series.json"
HORIZON_S = 3600


def _round(x: Any, digits: int = 4) -> list[float | None]:
    out: list[float | None] = []
    for v in np.asarray(x, dtype=float):
        out.append(None if not math.isfinite(v) else float(f"{v:.{digits}g}"))
    return out


def main() -> int:
    train = build_grid(goes.load("DS-08"), omni.load("DS-09"))
    storm = build_grid(goes.load("DS-07"), omni.load("DS-06"))
    Xtr, ytr, Xst = features(train), target(train, HORIZON_S), features(storm)
    logs = {"P-A": pa_predict(Xst)}
    for q, tag in ((0.5, "q50"), (0.9, "q90")):
        logs[f"P-B/{tag}"] = PB(q).fit(Xtr, ytr).predict(Xst)
        logs[f"P-C/{tag}"] = PC(q).fit(Xtr, ytr).predict(Xst)
    assert set(logs) == set(FORECASTS)
    start = np.datetime_as_string(np.datetime64(int(storm.t_ns[0]), "ns"), unit="s")
    doc = {
        "description": "S11 storm replay series (DL-069): GOES-18 >= 10 MeV flux (DL-068 "
        "method), 1 h forecasts of its maximum, OMNI SYM-H and AE. Real data, 8-15 May "
        "2024; forecasts trained on Jan 2023 - Apr 2024 only.",
        "generated_by": "scripts/data/make_storm_series.py",
        "sources": ["DS-06", "DS-07", "DS-08", "DS-09"],
        "record_start_utc": start + "Z",
        "step_s": STEP_NS // 10**9,
        "latency_s": LATENCY_NS // 10**9,
        "horizon_s": HORIZON_S,
        "pc_settings": PC_SETTINGS,
        "truth_flux_pfu": _round(storm.flux),
        "forecast_flux_pfu": {k: _round(10.0 ** logs[k]) for k in FORECASTS},
        "sym_h_nt": _round(storm.omni["sym_h_nt"]),
        "ae_nt": _round(storm.omni["ae_nt"]),
    }
    text = json.dumps(doc, indent=0, separators=(",", ":")) + "\n"
    OUT.write_text(text, encoding="ascii")
    print(OUT.relative_to(ROOT), len(text), "bytes, sha256",
          hashlib.sha256(text.encode("ascii")).hexdigest())  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

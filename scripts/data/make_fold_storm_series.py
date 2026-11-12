"""Build the four out-of-sample evaluation storms (DL-098), one pinned series each.

Run:  uv run python scripts/data/make_fold_storm_series.py

Same format as ``configs/data/s11_storm_series.json`` (``astramesh.forecast.replay``).
The training period's episodes >= 100 pfu inside the out-of-sample fold blocks, except
the tuning storm (DL-094): 18 Jul 2023 and 29 Jul 2023 (2023 Q3 fold), 29 Jan 2024 and
23-24 Mar 2024 (2024 Q1 fold). Each window is 8 days, starting at 00:00 UT two days
before the episode's first record >= 100 pfu. P-B and P-C (1 h horizon, quantiles 0.5
and 0.9) are fitted only on rows whose whole target window ends before the fold start
(the rule of ``storm_forecast_benchmark.py``). Writes ``configs/data/fold_<name>_series.json``
and prints each sha256. Deterministic.
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
HORIZON_S = 3600
#: name -> (window start, fold start)
STORMS = {
    "jul18_2023": ("2023-07-16", "2023-07-01"),
    "jul29_2023": ("2023-07-27", "2023-07-01"),
    "jan29_2024": ("2024-01-27", "2024-01-01"),
    "mar23_2024": ("2024-03-21", "2024-01-01"),
}
WINDOW_DAYS = 8


def _ns(day: str) -> int:
    return int(np.datetime64(day, "ns").astype(np.int64))


def _round(x: Any, digits: int = 4) -> list[float | None]:
    out: list[float | None] = []
    for v in np.asarray(x, dtype=float):
        out.append(None if not math.isfinite(v) else float(f"{v:.{digits}g}"))
    return out


def out_path(name: str) -> Path:
    return ROOT / "configs" / "data" / f"fold_{name}_series.json"


def main() -> int:
    g = build_grid(goes.load("DS-08"), omni.load("DS-09"))
    X, y = features(g), target(g, HORIZON_S)
    issue_end = g.t_ns + LATENCY_NS + HORIZON_S * 10**9
    models: dict[str, dict[str, Any]] = {}
    for name, (start, fold) in STORMS.items():
        if fold not in models:
            fit = issue_end <= _ns(fold)
            models[fold] = {f"{m}/{tag}": cls(q).fit(X[fit], y[fit])
                            for q, tag in ((0.5, "q50"), (0.9, "q90"))
                            for m, cls in (("P-B", PB), ("P-C", PC))}  # fmt: skip
        lo = _ns(start)
        idx = np.flatnonzero((g.t_ns >= lo) & (g.t_ns < lo + WINDOW_DAYS * 86_400 * 10**9))
        if len(idx) != WINDOW_DAYS * 288 or np.any(np.diff(g.t_ns[idx]) != STEP_NS):
            raise ValueError(f"{name}: window is not a contiguous 8-day 5-min grid")
        logs = {"P-A": pa_predict(X[idx])}
        logs.update({k: m.predict(X[idx]) for k, m in models[fold].items()})
        assert set(logs) == set(FORECASTS)
        first = np.datetime_as_string(np.datetime64(int(g.t_ns[idx[0]]), "ns"), unit="s")
        doc = {
            "description": f"Evaluation storm {name} (DL-098): GOES-18 >= 10 MeV flux (DL-068 "
            f"method), 1 h forecasts of its maximum, OMNI SYM-H and AE, 8 days from {start}; "
            f"forecasts fitted only on rows whose target window ends before {fold}.",
            "generated_by": "scripts/data/make_fold_storm_series.py",
            "sources": ["DS-08", "DS-09"],
            "record_start_utc": first + "Z",
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
        out_path(name).write_text(text, encoding="ascii")
        print(out_path(name).relative_to(ROOT), len(text), "bytes, sha256",
              hashlib.sha256(text.encode("ascii")).hexdigest())  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Select the Phase 6 held-out storms and build their series (DL-113).

Run:  uv run python scripts/data/make_heldout_series.py

Period 1 Jun 2024 - 31 Oct 2026 (DS-11 GOES-18 SGPS, DS-12 OMNI 1-min). The rule, fixed
in DL-113 before any data were used:

* flux is the DL-068 >= 10 MeV integral (larger valid unit); NaN records count as below;
* an episode is the set of records >= 100 pfu in which crossings less than 48 h apart are
  merged;
* each episode's window is 8 days from 00:00 UT two days before its first record
  >= 100 pfu (DL-099); an episode whose first record falls inside an earlier qualifying
  window belongs to that window;
* a window qualifies if it lies inside the period (both sources give a contiguous grid
  over the whole period; the loaders check it);
* the qualifying windows, sorted by start, are permuted with ``default_rng(113)`` and the
  first floor(N / 3) are reserved: no series, no forecast, no statistic beyond the start
  date. The others are the test storms.

Forecasts P-A, P-B and P-C (q50, q90) are frozen exactly as for S11 (fitted on all of
DS-08 / DS-09, ``make_storm_series.py``) and never refitted. Writes one series per test
storm, ``configs/data/heldout_<yyyymmdd>_series.json`` (window start date), and
``configs/data/heldout_selection.json`` (rule, windows, reserve, test-storm facts and the
v3-0-3 consistency check). Prints each sha256. Deterministic.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from astramesh.datasets import goes, omni
from astramesh.datasets.goes import STEP_NS
from astramesh.datasets.sources import load_sources
from astramesh.forecast.features import LATENCY_NS, build_grid, features, target
from astramesh.forecast.models import PB, PC, PC_SETTINGS, pa_predict
from astramesh.forecast.replay import FORECASTS

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "configs" / "data"
HORIZON_S = 3600
DAY_NS = 86_400 * 10**9
PERIOD = ("2024-06-01", "2026-11-01")  # [start, end)
THRESHOLD_PFU = 100.0
MERGE_NS = 48 * 3600 * 10**9
LEAD_DAYS = 2
WINDOW_DAYS = 8
RESERVE_SEED = 113
VERSION_SPAN_DAYS = 90
QUIET_PFU = 10.0


def ns(day: str) -> int:
    return int(np.datetime64(day, "ns").astype(np.int64))


def utc(t_ns: int, unit: str = "s") -> str:
    """ISO time ("...Z") or, with unit "D", the date."""
    s = str(np.datetime_as_string(np.datetime64(int(t_ns), "ns"), unit=unit))
    return s if unit == "D" else s + "Z"


def episodes(t_ns: npt.NDArray[np.int64], flux: npt.NDArray[np.float64],
             threshold: float = THRESHOLD_PFU, merge_ns: int = MERGE_NS
             ) -> list[tuple[int, int]]:  # fmt: skip
    """(first, last) indices of records >= threshold, crossings < merge_ns apart merged."""
    idx = np.flatnonzero(np.nan_to_num(flux, nan=-np.inf) >= threshold)
    out: list[tuple[int, int]] = []
    for i in idx:
        if out and t_ns[i] - t_ns[out[-1][1]] < merge_ns:
            out[-1] = (out[-1][0], int(i))
        else:
            out.append((int(i), int(i)))
    return out


def windows(first_ns: list[int], lo_ns: int, hi_ns: int) -> list[dict[str, Any]]:
    """Window per episode (by its first record), in time order. An episode inside the
    latest qualifying window joins it; otherwise it opens a window, which qualifies if
    it lies inside [lo_ns, hi_ns)."""
    out: list[dict[str, Any]] = []
    last_ok: dict[str, Any] | None = None
    for t in sorted(first_ns):
        if last_ok is not None and t < last_ok["end_ns"]:
            last_ok["episodes"].append(t)
            continue
        start = (t // DAY_NS - LEAD_DAYS) * DAY_NS
        w = {"start_ns": start, "end_ns": start + WINDOW_DAYS * DAY_NS, "episodes": [t]}
        w["qualifies"] = lo_ns <= start and w["end_ns"] <= hi_ns
        if not w["qualifies"]:
            w["reason"] = "window extends outside the period"
        else:
            last_ok = w
        out.append(w)
    return out


def reserve(n: int, seed: int = RESERVE_SEED) -> set[int]:
    """Indices (into the start-sorted qualifying windows) held in reserve."""
    perm = np.random.default_rng(seed).permutation(n)
    return {int(i) for i in perm[: n // 3]}


def _round(x: Any, digits: int = 4) -> list[float | None]:
    out: list[float | None] = []
    for v in np.asarray(x, dtype=float):
        out.append(None if not math.isfinite(v) else float(f"{v:.{digits}g}"))
    return out


def version_check(t_ns: npt.NDArray[np.int64], flux: npt.NDArray[np.float64],
                  change_ns: int) -> dict[str, Any]:  # fmt: skip
    """Invalid-record fraction and the median flux on quiet days (no record >= 10 pfu),
    over VERSION_SPAN_DAYS before and after the processing-version change."""
    out: dict[str, Any] = {"change_utc": utc(change_ns, "D"), "span_days": VERSION_SPAN_DAYS}
    span = VERSION_SPAN_DAYS * DAY_NS
    for side, (a, b) in (("before", (change_ns - span, change_ns)),
                         ("after", (change_ns, change_ns + span))):  # fmt: skip
        m = (t_ns >= a) & (t_ns < b)
        f, days = flux[m], (t_ns[m] - a) // DAY_NS
        quiet = [d for d in np.unique(days)
                 if np.all(np.nan_to_num(f[days == d], nan=0.0) < QUIET_PFU)]  # fmt: skip
        qf = f[np.isin(days, quiet)]
        out[side] = {"invalid_fraction": round(float(np.isnan(f).mean()), 5),
                     "quiet_days": len(quiet),
                     "quiet_median_pfu": round(float(np.nanmedian(qf)), 4),
                     "quiet_p90_pfu": round(float(np.nanpercentile(qf, 90)), 4)}  # fmt: skip
    return out


def main() -> int:
    lo, hi = ns(PERIOD[0]), ns(PERIOD[1])
    g = build_grid(goes.load("DS-11"), omni.load("DS-12"))
    if g.t_ns[0] != lo or g.t_ns[-1] + STEP_NS != hi:
        raise ValueError("DS-11 does not cover exactly the period")
    flux = g.flux.copy()
    flux[np.isnan(g.log_flux)] = np.nan
    eps = episodes(g.t_ns, flux)
    ws = windows([int(g.t_ns[a]) for a, _ in eps], lo, hi)
    ok = [w for w in ws if w["qualifies"]]
    held = reserve(len(ok))
    names = {f.name for f in load_sources()["DS-11"].files}
    dates = [re.search(r"_d(\d{4})(\d{2})(\d{2})_v3-0-3", n) for n in names]
    change = min(ns("-".join(d.groups())) for d in dates if d)

    train = build_grid(goes.load("DS-08"), omni.load("DS-09"))
    Xtr, ytr, X = features(train), target(train, HORIZON_S), features(g)
    logs = {"P-A": pa_predict(X)}
    for q, tag in ((0.5, "q50"), (0.9, "q90")):
        logs[f"P-B/{tag}"] = PB(q).fit(Xtr, ytr).predict(X)
        logs[f"P-C/{tag}"] = PC(q).fit(Xtr, ytr).predict(X)
    assert set(logs) == set(FORECASTS)

    test, reserved = [], []
    for k, w in enumerate(ok):
        day = utc(w["start_ns"], "D")
        if k in held:
            reserved.append(day)
            continue
        idx = np.flatnonzero((g.t_ns >= w["start_ns"]) & (g.t_ns < w["end_ns"]))
        if len(idx) != WINDOW_DAYS * 288 or np.any(np.diff(g.t_ns[idx]) != STEP_NS):
            raise ValueError(f"{day}: window is not a contiguous 8-day 5-min grid")
        name = day.replace("-", "")[:8]
        f = flux[idx]
        doc = {
            "description": f"Held-out storm {name} (DL-113): GOES-18 >= 10 MeV flux (DL-068 "
            f"method), 1 h forecasts of its maximum, OMNI SYM-H and AE, 8 days from {day[:10]}; "
            "forecasts fitted on Jan 2023 - Apr 2024 only (as S11).",
            "generated_by": "scripts/data/make_heldout_series.py",
            "sources": ["DS-08", "DS-09", "DS-11", "DS-12"],
            "record_start_utc": utc(int(g.t_ns[idx[0]])),
            "step_s": STEP_NS // 10**9,
            "latency_s": LATENCY_NS // 10**9,
            "horizon_s": HORIZON_S,
            "pc_settings": PC_SETTINGS,
            "truth_flux_pfu": _round(f),
            "forecast_flux_pfu": {k2: _round(10.0 ** logs[k2][idx]) for k2 in FORECASTS},
            "sym_h_nt": _round(g.omni["sym_h_nt"][idx]),
            "ae_nt": _round(g.omni["ae_nt"][idx]),
        }
        text = json.dumps(doc, indent=0, separators=(",", ":")) + "\n"
        path = DATA / f"heldout_{name}_series.json"
        path.write_text(text, encoding="ascii")
        sha = hashlib.sha256(text.encode("ascii")).hexdigest()
        ge = np.nan_to_num(f, nan=-np.inf) >= THRESHOLD_PFU
        test.append({
            "name": name, "window_start_utc": day, "epoch_utc": utc(w["start_ns"] + 600 * 10**9),
            "series_file": str(path.relative_to(ROOT)), "series_sha256": sha,
            "first_ge100_utc": [utc(t) for t in w["episodes"]],
            "peak_pfu": round(float(np.nanmax(f)), 1),
            "hours_ge100": round(float(ge.sum()) * STEP_NS / 3.6e12, 2),
            "sym_h_min_nt": round(float(np.nanmin(g.omni["sym_h_nt"][idx])), 1),
            "processing": "v3-0-3" if w["start_ns"] >= change else (
                "v3-0-2" if w["end_ns"] <= change else "both"),
            "truth_invalid_fraction": round(float(np.isnan(f).mean()), 4),
            "ae_missing_fraction": round(float(np.isnan(g.omni["ae_nt"][idx]).mean()), 4),
        })  # fmt: skip
        print(path.relative_to(ROOT), len(text), "bytes, sha256", sha)
    selection = {
        "decision": "DL-113",
        "generated_by": "scripts/data/make_heldout_series.py",
        "period_utc": [PERIOD[0], PERIOD[1]],
        "rule": {"threshold_pfu": THRESHOLD_PFU, "merge_h": MERGE_NS / 3.6e12,
                 "lead_days": LEAD_DAYS, "window_days": WINDOW_DAYS,
                 "reserve": f"default_rng({RESERVE_SEED}).permutation, first floor(N/3)"},
        "n_episodes": len(eps), "n_windows": len(ws), "n_qualifying": len(ok),
        "not_qualifying": [{"window_start_utc": utc(w["start_ns"], "D"), "reason": w["reason"]}
                           for w in ws if not w["qualifies"]],
        "reserved_window_starts_utc": sorted(reserved),
        "test_storms": test,
        "version_check": version_check(g.t_ns, flux, change),
    }  # fmt: skip
    out = DATA / "heldout_selection.json"
    out.write_text(json.dumps(selection, indent=1) + "\n", encoding="ascii")
    print(out.relative_to(ROOT), "sha256", hashlib.sha256(out.read_bytes()).hexdigest())
    print(json.dumps({k: selection[k] for k in ("n_episodes", "n_windows", "n_qualifying")}),
          "reserved", len(reserved), "test", len(test))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

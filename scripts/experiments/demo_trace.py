"""Trace of one recorded storm run for the MP4 demonstration (DL-125 design, DL-126 code).

Re-runs the 23 Mar 2024 B4 baseline (Phase 5 setup, 20 km formation, seed 1), whose config
hash must equal the one recorded in ``docs/results/resync_meta.json``
(``phase5/mar23_2024/baseline/b4/seed1``) and whose utility must equal the recorded one.
It writes ``demo_trace.json`` with, for a 52 h window from 6 h before the storm onset (the
first measured record >= 100 pfu), one frame every 2 min of simulated time:

* per spacecraft: geocentric latitude and longitude, mode, whether it is in the access
  region (invariant latitude >= the truth cutoff) and in hazard (in access and the measured
  flux >= its tolerance), rebuilt as the run evaluates them and checked against the run's
  per-spacecraft hazard total;
* the measured flux and the access cutoff;
* a static invariant-latitude grid at the formation's altitude, so the renderer can draw
  the access region for each frame's cutoff;
* observation segments and task take-overs inside the window, and every mode transition.

Everything in the file is simulated except the flux and SYM-H (measured, DS-02/DL-098).
``scripts/figures/make_demo.py`` renders the MP4 from this file only.

    uv run python scripts/experiments/demo_trace.py --out /tmp/demo
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from negative_results import mode_at  # noqa: E402
from resync_comparison import config as resync_config  # noqa: E402

JOB = ("phase5", "mar23_2024", "baseline", "b4", 1)
RECORDED_KEY = "phase5/mar23_2024/baseline/b4/seed1"
RECORDED_META = ROOT / "docs/results/resync_meta.json"
RECORDED_PAIRS = ROOT / "docs/results/resync_pairs.csv"
FRAME_S = 120
BEFORE_ONSET_S = 6 * 3600
WINDOW_S = 52 * 3600  # long enough to include every spacecraft's return to tasking
ONSET_PFU = 100.0
GRID_DEG = 2.0
TRACE_FILE = "demo_trace.json"


def recorded() -> tuple[str, int]:
    """(config hash, B4 utility) recorded for the run in DL-124."""
    import csv

    meta = json.loads(RECORDED_META.read_text())
    with RECORDED_PAIRS.open() as f:
        row = next(r for r in csv.DictReader(f)
                   if (r["group"], r["storm"], r["arm"], r["seed"])
                   == ("phase5", "mar23_2024", "baseline", "1"))  # fmt: skip
    return meta["config_hashes"][RECORDED_KEY], int(row["b4_utility"])


def config() -> dict[str, Any]:
    raw: dict[str, Any] = resync_config(JOB)
    return raw


def window(t_s: npt.NDArray[np.float64], flux: npt.NDArray[np.float64]) -> tuple[float, float]:
    """[start, end) of the 52 h window: 6 h before the first flux >= 100 pfu, clipped."""
    above = np.flatnonzero(np.nan_to_num(flux, nan=-np.inf) >= ONSET_PFU)
    if above.size == 0:
        raise ValueError("no record reaches the onset threshold")
    start = max(float(t_s[0]), float(t_s[above[0]]) - BEFORE_ONSET_S)
    end = min(float(t_s[-1]), start + WINDOW_S)
    return start, end


def geocentric_lat_lon(r: npt.NDArray[np.float64]) -> tuple[npt.NDArray[np.float64],
                                                            npt.NDArray[np.float64]]:  # fmt: skip
    """Geocentric latitude and longitude [deg] of Earth-fixed positions ``(..., 3)``."""
    lat = np.degrees(np.arctan2(r[..., 2], np.hypot(r[..., 0], r[..., 1])))
    lon = np.degrees(np.arctan2(r[..., 1], r[..., 0]))
    return lat, lon


def invariant_grid(radius_m: float, axis: npt.NDArray[np.float64]) -> dict[str, Any]:
    """Invariant latitude on a geocentric lat/lon grid at ``radius_m`` (Earth-fixed)."""
    from astramesh.dynamics.geomagnetic import invariant_latitude_deg

    lat = np.arange(-90.0, 90.0 + GRID_DEG / 2, GRID_DEG)
    lon = np.arange(-180.0, 180.0 + GRID_DEG / 2, GRID_DEG)
    la, lo = np.meshgrid(np.radians(lat), np.radians(lon), indexing="ij")
    r = radius_m * np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)
    inv = invariant_latitude_deg(r, axis)
    return {"lat_deg": lat.tolist(), "lon_deg": lon.tolist(),
            "invariant_lat_deg": np.round(inv, 2).tolist()}  # fmt: skip


def run_trace() -> dict[str, Any]:
    from astramesh.agents.supervisor import MODES
    from astramesh.core.config import NominalOperationsScenario, parse_scenario
    from astramesh.core.events import EventLog
    from astramesh.core.rng import RandomStreams
    from astramesh.dynamics.constants import R_EARTH_EQ_M
    from astramesh.dynamics.geomagnetic import decimal_year, dipole_axis, invariant_latitude_deg
    from astramesh.evaluation.manifest import git_state
    from astramesh.forecast.access import CutoffModel
    from astramesh.forecast.replay import StormSeries
    from astramesh.scenarios import nominal_operations as nops

    cfg = parse_scenario(config())
    assert isinstance(cfg, NominalOperationsScenario)
    want_hash, want_utility = recorded()
    if cfg.config_hash() != want_hash:
        raise ValueError(f"config hash {cfg.config_hash()} != recorded {want_hash}")
    captured: dict[str, Any] = {}
    orig_geo = nops.geometry_products

    def geo_capture(*a: Any, **k: Any) -> Any:
        captured["geo"] = orig_geo(*a, **k)
        return captured["geo"]

    events = EventLog()
    nops.geometry_products = geo_capture
    try:
        t0 = time.perf_counter()
        run = nops.run_nominal_operations(cfg, RandomStreams(cfg.random.seed), events)
        wall = time.perf_counter() - t0
    finally:
        nops.geometry_products = orig_geo
    utility = run.summary["operations"]["utility"]
    if utility != want_utility:
        raise ValueError(f"utility {utility} != recorded {want_utility}")

    ids = sorted(run.agents)
    geo = captured["geo"]
    t_ns = np.asarray(run.formation.trajectory.t_ns, dtype=np.int64)
    t_s = t_ns / 1e9
    rp = cfg.environment.replay if cfg.environment is not None else None
    assert rp is not None
    series = StormSeries.load(rp.series_file, rp.series_sha256)
    epoch_ns = int(cfg.time.epoch_utc.timestamp()) * 10**9
    acc = rp.access
    cut = CutoffModel(acc.quiet_cutoff_deg, acc.storm_slope_deg_per_nt, acc.max_shift_deg)
    axis = dipole_axis(decimal_year(cfg.time.epoch_utc))
    lam = invariant_latitude_deg(geo.r_itrs, axis)
    cutoff = np.array([cut.cutoff_deg(series.sym_h_truth(epoch_ns + int(t))) for t in t_ns])
    flux = np.array([np.nan if (f := series.truth(epoch_ns + int(t))) is None else f
                     for t in t_ns])  # fmt: skip
    access = lam >= cutoff[:, None]
    tol = [rp.tolerance_pfu(j) for j in range(len(ids))]
    hazard = np.stack([np.nan_to_num(np.where(access[:, j], flux, 0.0), nan=-np.inf) >= tol[j]
                       for j in range(len(ids))], axis=1)  # fmt: skip
    hazard[-1] = False  # no step after the final tick, as the run evaluates it
    step = cfg.time.time_step_s
    for j, a in enumerate(ids):  # the rebuilt hazard must be the run's
        if float(hazard[:, j].sum()) * step != run.summary["storm"]["hazard_s"][a]:
            raise ValueError(f"{a}: rebuilt hazard does not match the run")

    start, end = window(t_s, flux)
    every = round(FRAME_S / step)
    k = np.flatnonzero((t_s >= start) & (t_s < end))[::every]
    lat, lon = geocentric_lat_lon(geo.r_itrs[k])
    tr = run.summary["protection"]["transitions"]
    frames = {
        "t_s": [float(x) for x in t_s[k]],
        "flux_pfu": [None if math.isnan(x) else round(float(x), 3) for x in flux[k]],
        "cutoff_deg": [round(float(x), 3) for x in cutoff[k]],
        "lat_deg": np.round(lat, 3).T.tolist(),  # [spacecraft][frame]
        "lon_deg": np.round(lon, 3).T.tolist(),
        "mode": [[mode_at(tr[a], float(t)) for t in t_s[k]] for a in ids],
        "in_access": access[k].T.tolist(),
        "in_hazard": hazard[k].T.tolist(),
    }
    segments = [{"spacecraft": g.spacecraft, "task": g.task_id,
                 "start_s": float(t_s[g.start_tick]),
                 "stop_s": float(t_s[min(g.stop_tick, len(t_s) - 1)]), "outcome": g.outcome}
                for g in run.segments
                if g.stop_tick > 0 and t_s[g.start_tick] < end
                and t_s[min(g.stop_tick, len(t_s) - 1)] > start]  # fmt: skip
    takeovers = [{"t_s": e.time_ns / 1e9, "agent": e.source, "task": e.data.get("task"),
                  "from": e.data.get("from")}
                 for e in events._events
                 if e.kind == "task_taken_over" and start <= e.time_ns / 1e9 < end]  # fmt: skip
    radius = R_EARTH_EQ_M + cfg.reference_orbit.mean_altitude_km * 1e3
    git = git_state(ROOT)
    return {
        "description": ("Simulated four-spacecraft formation (B4, baseline arm, 20 km, seed 1) "
                        "driven by the measured 23 Mar 2024 GOES >= 10 MeV flux and OMNI SYM-H "
                        "(DL-098 series). Everything except flux_pfu and the SYM-H behind "
                        "cutoff_deg is simulated."),
        "generated_by": "scripts/experiments/demo_trace.py",
        "git_commit": git["commit"], "git_dirty": git["dirty"],
        "config_hash": cfg.config_hash(), "recorded_key": RECORDED_KEY,
        "utility": utility, "wall_s": round(wall, 1),
        "epoch_utc": cfg.time.epoch_utc.isoformat(), "step_s": step, "frame_s": FRAME_S,
        "window_s": [start, end], "onset_pfu": ONSET_PFU,
        "spacecraft": ids, "tolerance_pfu": tol, "modes": list(MODES),
        "altitude_km": cfg.reference_orbit.mean_altitude_km,
        "frames": frames, "segments": segments, "takeovers": takeovers,
        "transitions": {a: tr[a] for a in ids},
        "invariant_grid": invariant_grid(radius, axis),
    }  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    trace = run_trace()
    (args.out / TRACE_FILE).write_text(json.dumps(trace, separators=(",", ":")) + "\n")
    n = len(trace["frames"]["t_s"])
    print(json.dumps({"frames": n, "utility": trace["utility"], "git_dirty": trace["git_dirty"],
                      "takeovers": len(trace["takeovers"])}))  # fmt: skip


if __name__ == "__main__":
    main()

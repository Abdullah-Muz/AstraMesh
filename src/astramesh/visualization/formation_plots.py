"""Basic diagnostic plots for a ``formation_dynamics`` run directory.

Reads ``trajectory.csv`` and ``config.resolved.json`` and writes PNG figures:

* ``adjacent_separation.png`` - distance between neighbouring spacecraft vs time
* ``radius_minus_req.png`` - |r| - R_eq per spacecraft vs time (not geodetic altitude)
* ``relative_ric.png`` - followers in the leader's RIC frame (radial vs in-track)
* ``ground_track_sc00.png`` - leader's geocentric latitude/longitude (ITRS)

Figures are for inspection only. They are not listed in the run manifest
(PNG encoding is not byte-reproducible), and they plot simulated truth, not
measurements.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.earth_frames import gcrs_to_itrs
from astramesh.dynamics.frames import eci_to_ric
from astramesh.dynamics.state import CartesianState, Frame
from astramesh.scenarios.formation_dynamics import TRAJECTORY_FILE

FIGURE_FILES = (
    "adjacent_separation.png",
    "radius_minus_req.png",
    "relative_ric.png",
    "ground_track_sc00.png",
)


def load_trajectory(run_dir: Path) -> tuple[np.ndarray, list[str], np.ndarray]:
    """Return ``t_ns`` (n_t,), spacecraft ids, and states (n_t, n_sc, 6)."""
    path = run_dir / TRAJECTORY_FILE
    with path.open(encoding="ascii") as fh:
        header = fh.readline().strip()
        if not header.startswith("t_ns,spacecraft,"):
            raise ValueError(f"{path} is not a trajectory file")
        rows = [line.rstrip("\n").split(",") for line in fh if line.strip()]
    ids = sorted({r[1] for r in rows})
    t_ns = np.array(sorted({int(r[0]) for r in rows}), dtype=np.int64)
    states = np.empty((len(t_ns), len(ids), 6))
    t_index = {int(t): k for k, t in enumerate(t_ns)}
    sc_index = {sc: j for j, sc in enumerate(ids)}
    for r in rows:
        states[t_index[int(r[0])], sc_index[r[1]]] = [float(x) for x in r[2:]]
    return t_ns, ids, states


def plot_run(run_dir: Path, out_dir: Path | None = None) -> list[Path]:
    """Write the diagnostic figures for ``run_dir``; return the files written."""
    out = out_dir or (run_dir / "figures")
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads((run_dir / "config.resolved.json").read_text(encoding="ascii"))
    epoch = datetime.fromisoformat(config["time"]["epoch_utc"].replace("Z", "+00:00"))
    t_ns, ids, y = load_trajectory(run_dir)
    hours = t_ns / 3.6e12
    title = config["scenario_id"]
    written: list[Path] = []

    def save(fig: Figure, name: str) -> None:
        fig.tight_layout()
        path = out / name
        fig.savefig(path, dpi=120)
        written.append(path)

    fig = Figure(figsize=(8, 4))
    ax = fig.add_subplot()
    for j in range(len(ids) - 1):
        sep = np.linalg.norm(y[:, j + 1, :3] - y[:, j, :3], axis=1) / 1e3
        ax.plot(hours, sep, label=f"{ids[j]}-{ids[j + 1]}")
    ax.set(xlabel="time since epoch [h]", ylabel="separation [km]", title=f"{title}: neighbours")
    if len(ids) > 1:
        ax.legend()
    ax.grid(alpha=0.3)
    save(fig, FIGURE_FILES[0])

    fig = Figure(figsize=(8, 4))
    ax = fig.add_subplot()
    for j, sc in enumerate(ids):
        ax.plot(hours, (np.linalg.norm(y[:, j, :3], axis=1) - R_EARTH_EQ_M) / 1e3, label=sc)
    ax.set(
        xlabel="time since epoch [h]",
        ylabel="|r| - R_eq [km] (not geodetic altitude)",
        title=f"{title}: orbit radius",
    )
    ax.legend()
    ax.grid(alpha=0.3)
    save(fig, FIGURE_FILES[1])

    fig = Figure(figsize=(8, 4))
    ax = fig.add_subplot()
    for j in range(1, len(ids)):
        rel = np.array(
            [
                eci_to_ric(
                    CartesianState(Frame.GCRS, epoch, int(t), y[k, 0, :3], y[k, 0, 3:]),
                    CartesianState(Frame.GCRS, epoch, int(t), y[k, j, :3], y[k, j, 3:]),
                ).r_m
                for k, t in enumerate(t_ns)
            ]
        )
        ax.plot(rel[:, 1] / 1e3, rel[:, 0], label=ids[j])
    ax.set(
        xlabel="in-track relative to sc00 [km]",
        ylabel="radial relative to sc00 [m]",
        title=f"{title}: followers in leader RIC (rectilinear)",
    )
    if len(ids) > 1:
        ax.legend()
    ax.grid(alpha=0.3)
    save(fig, FIGURE_FILES[2])

    r_itrs, _ = gcrs_to_itrs(epoch, t_ns, y[:, 0, :3], y[:, 0, 3:])
    lon = np.degrees(np.arctan2(r_itrs[:, 1], r_itrs[:, 0]))
    lat = np.degrees(np.arcsin(r_itrs[:, 2] / np.linalg.norm(r_itrs, axis=1)))
    jumps = np.abs(np.diff(lon)) > 180
    lon_plot = lon.copy()
    lon_plot[1:][jumps] = math.nan  # break the line at the antimeridian
    fig = Figure(figsize=(9, 4.5))
    ax = fig.add_subplot()
    ax.plot(lon_plot, lat, lw=0.8)
    ax.set(
        xlim=(-180, 180),
        ylim=(-90, 90),
        xlabel="longitude [deg] (ITRS)",
        ylabel="geocentric latitude [deg]",
        title=f"{title}: {ids[0]} ground track",
    )
    ax.grid(alpha=0.3)
    save(fig, FIGURE_FILES[3])
    return written

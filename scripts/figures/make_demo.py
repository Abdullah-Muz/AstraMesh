"""Render the MP4 demonstration from a recorded trace (DL-125 design, DL-126 code).

Reads ``docs/results/demo_trace.json`` (written by ``scripts/experiments/demo_trace.py``)
and nothing else, and draws one frame per trace frame:

* a map of the formation's ground track (geocentric latitude and longitude, no coastlines)
  with the access region for that frame's cutoff shaded; the four spacecraft are within
  60 km of each other, so one marker stands for the formation;
* the measured flux with each spacecraft's tolerance and a time cursor;
* one strip per spacecraft with its mode over the window, its hazard steps and its task
  take-overs.

The formation, modes and hazard are simulated; the flux and SYM-H are measured. The MP4
needs the optional ``viz`` group (imageio-ffmpeg supplies the ffmpeg executable); ``--still``
writes one frame as a PNG without ffmpeg. MP4 and PNG bytes are not reproducible across
encoder builds, so neither is hashed.

    uv run --group viz python scripts/figures/make_demo.py
    uv run python scripts/figures/make_demo.py --still docs/media/astramesh_demo_mar2024.png
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "docs/results/demo_trace.json"
MP4 = ROOT / "docs/media/astramesh_demo_mar2024.mp4"
FPS = 30
DPI = 100
SIZE_IN = (12.8, 7.2)  # 1280 x 720 at 100 dpi
TRAIL_FRAMES = 45  # 90 min of track at 2 min per frame
# Okabe-Ito colours (colour-blind safe)
MODE_COLOURS = {"NOMINAL": "#0072B2", "STORM_WATCH": "#E69F00", "PROTECTIVE": "#D55E00",
                "RECOVERY": "#CC79A7", "SAFE": "#000000"}  # fmt: skip
SC_COLOURS = ("#0072B2", "#009E73", "#E69F00", "#CC79A7")
TITLE = "AstraMesh: simulated four-spacecraft formation through the measured 23 Mar 2024 storm"


def load(path: Path = TRACE) -> dict[str, Any]:
    trace: dict[str, Any] = json.loads(path.read_text())
    return trace


def _utc(trace: dict[str, Any], t_s: float) -> dt.datetime:
    return dt.datetime.fromisoformat(trace["epoch_utc"]) + dt.timedelta(seconds=t_s)


def build(trace: dict[str, Any]) -> tuple[Figure, Callable[[int], None]]:
    """Figure with the static parts drawn, and ``update(i)`` that draws frame ``i``."""
    fr = trace["frames"]
    ids: list[str] = trace["spacecraft"]
    t_h = (np.asarray(fr["t_s"]) - fr["t_s"][0]) / 3600.0
    flux = np.array([np.nan if f is None else f for f in fr["flux_pfu"]], dtype=float)
    lat = np.asarray(fr["lat_deg"], dtype=float)[0]  # sc00 stands for the formation
    lon = np.asarray(fr["lon_deg"], dtype=float)[0]
    grid = trace["invariant_grid"]
    g_lat, g_lon = np.asarray(grid["lat_deg"]), np.asarray(grid["lon_deg"])
    inv = np.asarray(grid["invariant_lat_deg"])
    t0 = fr["t_s"][0]

    fig = Figure(figsize=SIZE_IN, dpi=DPI)
    gs = fig.add_gridspec(3, 2, height_ratios=(3.2, 1.6, 1.6), width_ratios=(2.6, 1.0),
                          left=0.06, right=0.98, top=0.89, bottom=0.07, hspace=0.45,
                          wspace=0.12)  # fmt: skip
    fig.suptitle(TITLE + "\n(B4 planner, baseline protection, 20 km formation, seed 1)",
                 fontsize=11)  # fmt: skip
    ax_map = fig.add_subplot(gs[0, 0])
    right = gs[0, 1].subgridspec(2, 1, height_ratios=(3.4, 0.8), hspace=0.0)
    ax_txt = fig.add_subplot(right[0])
    ax_leg = fig.add_subplot(right[1])
    ax_leg.axis("off")
    ax_flux = fig.add_subplot(gs[1, :])
    ax_mode = fig.add_subplot(gs[2, :], sharex=ax_flux)

    ax_map.set_xlim(-180, 180)
    ax_map.set_ylim(-90, 90)
    ax_map.set_xticks(range(-180, 181, 60))
    ax_map.set_yticks(range(-90, 91, 30))
    ax_map.grid(color="0.85", lw=0.5)
    ax_map.set_xlabel("Geocentric longitude (deg)")
    ax_map.set_ylabel("Geocentric latitude (deg)")
    ax_map.set_title("Ground track (simulated); shaded: access region for the current cutoff",
                     fontsize=9)  # fmt: skip
    (trail,) = ax_map.plot([], [], color="0.35", lw=1.2)
    dot = ax_map.scatter([lon[0]], [lat[0]], s=70, zorder=3, edgecolors="black")
    region: list[Any] = []

    ax_txt.axis("off")
    txt = ax_txt.text(0.0, 1.0, "", va="top", ha="left", family="monospace", fontsize=9,
                      transform=ax_txt.transAxes)  # fmt: skip

    ax_flux.semilogy(t_h, np.clip(flux, 0.1, None), color="black", lw=1.0)
    ax_flux.set_title("GOES >= 10 MeV proton flux (measured) and each spacecraft's tolerance",
                      fontsize=9)  # fmt: skip
    for tol in sorted(set(trace["tolerance_pfu"])):
        who = [s for s, x in zip(ids, trace["tolerance_pfu"], strict=True) if x == tol]
        ax_flux.axhline(tol, color="0.4", ls="--", lw=0.8)
        ax_flux.text(t_h[-1], tol, f" {tol:g} pfu: {', '.join(who)}", va="center", fontsize=7)
    ax_flux.set_ylabel("Flux (pfu)")
    ax_flux.set_xlim(t_h[0], t_h[-1] * 1.12)
    cur_f = ax_flux.axvline(0.0, color="#D55E00", lw=1.2)

    modes: list[str] = trace["modes"]
    for j, a in enumerate(ids):
        m = fr["mode"][j]
        start = 0
        for i in range(1, len(m) + 1):
            if i == len(m) or m[i] != m[start]:
                end = t_h[i] if i < len(m) else t_h[-1] + (t_h[1] - t_h[0])
                ax_mode.broken_barh([(t_h[start], end - t_h[start])], (j - 0.3, 0.4),
                                    color=MODE_COLOURS[m[start]])  # fmt: skip
                start = i
        hz = np.asarray(fr["in_hazard"][j], dtype=bool)
        ax_mode.scatter(t_h[hz], np.full(hz.sum(), j + 0.2), marker="|", s=10, color="black",
                        lw=0.8)  # fmt: skip
        tk = [(e["t_s"] - t0) / 3600.0 for e in trace["takeovers"] if e["agent"] == a]
        ax_mode.scatter(tk, np.full(len(tk), j - 0.42), marker="^", s=10,
                        color=SC_COLOURS[j % len(SC_COLOURS)])  # fmt: skip
    ax_mode.set_yticks(range(len(ids)), ids)
    ax_mode.set_ylim(len(ids) - 0.4, -0.7)
    ax_mode.set_xlabel(f"Hours from {_utc(trace, t0):%d %b %Y %H:%M} UTC")
    handles = [ax_leg.bar(0, 0, color=c, label=k.replace("_", " ").lower())
               for k, c in MODE_COLOURS.items() if k in modes]  # fmt: skip
    ax_leg.legend(handles=handles, loc="center left", ncol=2, fontsize=8, frameon=False,
                  title="mode (simulated)", title_fontsize=8)  # fmt: skip
    n_tk = len(trace["takeovers"])
    ax_mode.set_title("Mode per spacecraft; | hazard (in access and flux >= tolerance); "
                      f"^ tasks taken over ({n_tk} in all)", fontsize=9)  # fmt: skip
    cur_m = ax_mode.axvline(0.0, color="#D55E00", lw=1.2)
    n_done = np.array([sum(1 for s in trace["segments"]
                           if s["outcome"] == "completed" and s["stop_s"] <= t)
                       for t in fr["t_s"]])  # fmt: skip

    def update(i: int) -> None:
        for c in region:
            c.remove()
        region.clear()
        inside = (inv >= fr["cutoff_deg"][i]).astype(float)
        region.append(ax_map.contourf(g_lon, g_lat, inside, levels=[0.5, 1.5],
                                      colors=["#56B4E9"], alpha=0.35))  # fmt: skip
        k0 = max(0, i - TRAIL_FRAMES)
        lo, la = lon[k0 : i + 1].copy(), lat[k0 : i + 1].copy()
        jump = np.flatnonzero(np.abs(np.diff(lo)) > 180) + 1  # break the line at +-180 deg
        lo, la = np.insert(lo, jump, np.nan), np.insert(la, jump, np.nan)
        trail.set_data(lo, la)
        dot.set_offsets([[lon[i], lat[i]]])
        dot.set_facecolor(MODE_COLOURS[fr["mode"][0][i]])
        cur_f.set_xdata([t_h[i], t_h[i]])
        cur_m.set_xdata([t_h[i], t_h[i]])
        f = fr["flux_pfu"][i]
        lines = [f"{_utc(trace, fr['t_s'][i]):%Y-%m-%d %H:%M} UTC", "",
                 f"flux  {'n/a' if f is None else f'{f:8.1f}'} pfu (measured)",
                 f"access cutoff {fr['cutoff_deg'][i]:5.1f} deg inv. lat.", ""]  # fmt: skip
        for j, a in enumerate(ids):
            flag = " HAZARD" if fr["in_hazard"][j][i] else ""
            lines.append(f"{a} {fr['mode'][j][i]:<11}{flag}")
        lines += ["", f"observations completed: {n_done[i]}"]
        txt.set_text("\n".join(lines))

    update(0)
    return fig, update


def still(trace: dict[str, Any], out: Path, i: int | None = None) -> None:
    """One frame as a PNG (default: the frame with the highest flux)."""
    fig, update = build(trace)
    if i is None:
        f = [-1.0 if x is None else x for x in trace["frames"]["flux_pfu"]]
        i = int(np.argmax(f))
    update(i)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI)


def render(trace: dict[str, Any], out: Path, fps: int = FPS) -> None:
    import imageio_ffmpeg
    import matplotlib as mpl
    from matplotlib.animation import FFMpegWriter

    mpl.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    fig, update = build(trace)
    writer = FFMpegWriter(fps=fps, codec="libx264", extra_args=["-pix_fmt", "yuv420p"],
                          metadata={"title": TITLE})  # fmt: skip
    out.parent.mkdir(parents=True, exist_ok=True)
    with writer.saving(fig, str(out), dpi=DPI):
        for i in range(len(trace["frames"]["t_s"])):
            update(i)
            writer.grab_frame()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trace", type=Path, default=TRACE)
    ap.add_argument("--out", type=Path, default=MP4)
    ap.add_argument("--still", type=Path, default=None, help="write one PNG frame instead")
    args = ap.parse_args()
    trace = load(args.trace)
    if args.still is not None:
        still(trace, args.still)
    else:
        render(trace, args.out)


if __name__ == "__main__":
    main()

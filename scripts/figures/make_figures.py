"""Report figures F1 - F9 from committed results only (DL-125).

Every figure reads committed files under ``docs/results/`` and the pinned storm series in
``configs/data/``. Nothing is simulated or re-estimated here: each draw function reads,
selects and plots, and the only arithmetic is shown in the code (sums over a storm's arms
and spacecraft, absolute values, a change since day 0). Each caption says what is
*simulated* (formation, utility, hazard, protection) and what is *measured* (GOES flux,
OMNI SYM-H), as spec §19 requires. The PNGs are not byte-reproducible (as
``formation_plots.py`` notes), so they are not hashed; ``README.md`` in the output folder
lists each figure's source files.

    uv run python scripts/figures/make_figures.py [--out docs/figures]
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.dates as mdates
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[2]
WIDTH_IN = 7.0
DPI = 150

# Okabe-Ito colour-blind-safe palette
BLACK, ORANGE, SKY, GREEN = "#000000", "#E69F00", "#56B4E9", "#009E73"
YELLOW, BLUE, VERMILLION, PURPLE = "#F0E442", "#0072B2", "#D55E00", "#CC79A7"
PLANNERS = {"cbba_b3_timeout": ("B3 + timeout", BLUE, "o"), "rule_b4": ("B4", VERMILLION, "s")}
ARM_LABELS = {
    "handover": "forecast handover",
    "shorter": "shorter protection",
    "no_lookahead": "A1 no look-ahead",
    "no_forecast": "A2 no forecast",
    "no_hysteresis": "A3 no hysteresis",
    "no_reconciliation": "A4 no reconciliation",
}
STORM_LABELS = {
    "jul18_2023": "18 Jul 2023",
    "jul29_2023": "29 Jul 2023",
    "jan29_2024": "29 Jan 2024",
    "mar23_2024": "23 Mar 2024",
    "may2024": "May 2024",
    "20240606": "6 Jun 2024",
    "20241007": "7 Oct 2024",
    "20241025": "25 Oct 2024",
    "20250330": "30 Mar 2025",
    "20251109": "9 Nov 2025",
    "20260117": "17 Jan 2026",
    "2000km": "spread 2 000 km",
    "5000km": "spread 5 000 km",
}


@dataclass(frozen=True)
class FigureSpec:
    name: str
    title: str
    caption: str
    sources: tuple[str, ...]
    draw: Callable[[Path], Figure]


# -- readers -------------------------------------------------------------------------------
def read_csv(root: Path, rel: str) -> list[dict[str, str]]:
    with (root / rel).open(newline="") as f:
        return list(csv.DictReader(f))


def read_json(root: Path, rel: str) -> Any:
    return json.loads((root / rel).read_text())


def _new(height_in: float, ncols: int = 1, nrows: int = 1) -> tuple[Figure, list[Axes]]:
    fig = Figure(figsize=(WIDTH_IN, height_in), layout="constrained")
    axes = fig.subplots(nrows, ncols, squeeze=False)
    return fig, [ax for row in axes for ax in row]


def _f(x: str) -> float:
    return float(x) if x != "" else float("nan")


# -- F1 the 23 Mar 2024 storm -------------------------------------------------------------------
F1_SERIES = "configs/data/fold_mar23_2024_series.json"


def draw_f1(root: Path) -> Figure:
    d = read_json(root, F1_SERIES)
    start = np.datetime64(d["record_start_utc"].rstrip("Z"), "s")
    step = int(d["step_s"])
    lat = int(d["latency_s"])
    n = len(d["truth_flux_pfu"])
    t_rec = start + np.arange(n) * np.timedelta64(step, "s")  # record start
    t_issue = t_rec + np.timedelta64(lat, "s")  # issued when its record arrives

    def arr(xs: list[float | None]) -> np.ndarray[Any, np.dtype[np.float64]]:
        return np.array([np.nan if x is None else x for x in xs], dtype=float)

    fig, (ax, ax2) = _new(5.0, nrows=2)
    ax.plot(t_rec, arr(d["truth_flux_pfu"]), color=BLACK, lw=1.0, label="GOES ≥ 10 MeV (measured)")
    ax.plot(
        t_issue,
        arr(d["forecast_flux_pfu"]["P-B/q50"]),
        color=BLUE,
        lw=0.9,
        label="P-B median forecast",
    )
    ax.plot(
        t_issue,
        arr(d["forecast_flux_pfu"]["P-B/q90"]),
        color=ORANGE,
        lw=0.9,
        ls="--",
        label="P-B 0.9 quantile forecast",
    )
    for tol, txt in ((50, "50 pfu (sc02)"), (100, "100 pfu (sc00, sc01)"), (200, "200 pfu (sc03)")):
        ax.axhline(tol, color=GREEN, lw=0.8, ls=":")
        ax.text(t_rec[-1], tol, txt, color=GREEN, fontsize=7, ha="right", va="bottom")
    ax.set_yscale("log")
    ax.set_ylabel("flux [pfu]")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.3)
    ax2.plot(t_rec, arr(d["sym_h_nt"]), color=PURPLE, lw=0.8)
    ax2.set_ylabel("SYM-H [nT]")
    ax2.set_xlabel("UTC (2024)")
    ax2.grid(alpha=0.3)
    for a in (ax, ax2):
        a.xaxis.set_major_locator(mdates.DayLocator())  # type: ignore[no-untyped-call]
        a.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))  # type: ignore[no-untyped-call]
        a.set_xlim(t_rec[0], t_rec[-1])
    ax.tick_params(labelbottom=False)
    return fig


# -- F2 held-out storms ------------------------------------------------------------------------
F2_SRC = "docs/results/heldout_summary.csv"


def draw_f2(root: Path) -> Figure:
    rows = [r for r in read_csv(root, F2_SRC) if r["scope"] == "pooled: all test storms"]
    fig, (ax,) = _new(3.6)
    arms = list(ARM_LABELS)
    for k, (planner, (label, colour, marker)) in enumerate(PLANNERS.items()):
        by = {r["compared"]: r for r in rows if r["planner"] == planner}
        y = np.arange(len(arms)) + (0.15 if k == 0 else -0.15)
        m = np.array([_f(by[a]["mean"]) for a in arms])
        lo = np.array([_f(by[a]["ci_lo"]) for a in arms])
        hi = np.array([_f(by[a]["ci_hi"]) for a in arms])
        ax.errorbar(
            m, y, xerr=[m - lo, hi - m], fmt=marker, color=colour, ms=5, capsize=3, label=label
        )
    ax.axvline(0.0, color=BLACK, lw=0.8)
    ax.set_yticks(np.arange(len(arms)), [ARM_LABELS[a] for a in arms])
    ax.invert_yaxis()
    ax.set_xlabel("retention change against the baseline [fraction of QUIET utility]")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(axis="x", alpha=0.3)
    return fig


# -- F3 ablations ------------------------------------------------------------------------------
F3_DEV = "docs/results/ablation_summary.csv"
F3_HELD = "docs/results/heldout_summary.csv"
ABLATIONS = ("no_lookahead", "no_forecast", "no_hysteresis", "no_reconciliation")
F3_LABEL_OFFSETS: tuple[dict[str, tuple[int, int]], ...] = (  # label placement only
    {"no_lookahead": (-16, -12), "no_hysteresis": (8, 4)},
    {"no_forecast": (-18, 4), "no_lookahead": (8, 4)},
)


def draw_f3(root: Path) -> Figure:
    dev = [r for r in read_csv(root, F3_DEV) if r["scope"] == "pooled over storms"]
    held = [r for r in read_csv(root, F3_HELD) if r["scope"] == "pooled: all test storms"]
    fig, axes = _new(3.4, ncols=2)
    panels = (
        (axes[0], dev, "ablation", "Phase 5 storms (n = 5)"),
        (axes[1], held, "compared", "held-out storms (n = 6)"),
    )
    for i, (ax, rows, key, title) in enumerate(panels):
        sel = [r for r in rows if r[key] in ABLATIONS]
        dodge = 0.02 * max(_f(r["max_extra_unprotected_s"]) for r in sel)
        for planner, (_label, colour, marker) in PLANNERS.items():
            for r in sel:
                if r["planner"] != planner:
                    continue
                x, m = _f(r["max_extra_unprotected_s"]), _f(r["mean"])
                ax.errorbar(
                    x + (dodge if planner == "rule_b4" else 0.0),
                    m,
                    yerr=[[m - _f(r["ci_lo"])], [_f(r["ci_hi"]) - m]],
                    fmt=marker,
                    color=colour,
                    ms=5,
                    capsize=3,
                    mfc="none" if planner == "rule_b4" else colour,
                )
                if planner == "cbba_b3_timeout":
                    ax.annotate(
                        ARM_LABELS[r[key]].split()[0],
                        (x, m),
                        xytext=F3_LABEL_OFFSETS[i].get(r[key], (6, 2)),
                        textcoords="offset points",
                        fontsize=7,
                    )
        ax.axhline(0.0, color=BLACK, lw=0.8)
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("worst extra unprotected hazard [s]")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("pooled retention change [fraction of QUIET]")
    for planner, (label, colour, marker) in PLANNERS.items():
        axes[0].plot(
            [],
            [],
            marker,
            color=colour,
            mfc="none" if planner == "rule_b4" else colour,
            label=label,
        )
    axes[0].legend(fontsize=7, loc="lower right")
    return fig


# -- F4 protection tuning ----------------------------------------------------------------------
F4_SRC = "docs/results/protection_tuning_summary.csv"
CHOSEN = "pt:600:600:none"  # the DL-101 choice (PROTECTION_TUNING.md)
ELIGIBLE_LIMIT_S = 600.0  # DL-101 rule: at most 600 s more unprotected hazard than the baseline


def draw_f4(root: Path) -> Figure:
    rows = read_csv(root, F4_SRC)
    fig, (ax,) = _new(3.6)
    styles = {
        "none": (BLUE, "o", "no margin"),
        "ratio_0.9": (GREEN, "^", "margin: ratio 0.9"),
        "q90": (ORANGE, "D", "margin: P-B q0.9"),
    }
    seen: set[str] = set()
    groups: dict[float, list[tuple[int, int, float]]] = {}
    for r in rows:
        x, y = _f(r["max_extra_unprotected_s"]), _f(r["mean_retention"])
        if r["arm"] == "baseline":
            ax.plot(x, y, "*", color=BLACK, ms=11, label="baseline (H 3 600 s / D 1 800 s)")
            continue
        _, h, dw, margin = r["arm"].split(":")
        colour, marker, label = styles[margin]
        ax.plot(
            x, y, marker, color=colour, ms=6, alpha=0.8, label=None if margin in seen else label
        )
        seen.add(margin)
        if margin == "none":
            groups.setdefault(x, []).append((int(h), int(dw), y))
        if r["arm"] == CHOSEN:
            ax.plot(x, y, "o", ms=12, mfc="none", color=BLACK, label="chosen: H 600 s / D 600 s")
    for x, pts in groups.items():  # one label per group of coinciding no-margin arms
        hs = " / ".join(f"{v:,}".replace(",", " ") for v in sorted({p[0] for p in pts}))
        ds = " / ".join(str(v) for v in sorted({p[1] for p in pts}))
        ys = [p[2] for p in pts]
        span = f"{min(ys):.3f}" if min(ys) == max(ys) else f"{min(ys):.3f} - {max(ys):.3f}"
        ax.annotate(
            f"no margin\nH {hs} s, D {ds} s\nretention {span}",
            (x, min(ys)),
            xytext=(0, -12),
            textcoords="offset points",
            fontsize=7,
            ha="center",
            va="top",
        )
    ax.set_xlim(-40, 860)
    ax.axvline(ELIGIBLE_LIMIT_S, color=VERMILLION, ls="--", lw=0.9)
    ax.text(ELIGIBLE_LIMIT_S + 8, 0.53, "eligibility limit 600 s", color=VERMILLION, fontsize=7)
    ax.set_xlabel("worst extra unprotected hazard on any spacecraft and seed [s]")
    ax.set_ylabel("retention (mean of seeds 1 - 3)")
    ax.legend(fontsize=7, loc="center right")
    ax.grid(alpha=0.3)
    return fig


# -- F5 spread formation -----------------------------------------------------------------------
F5_SRC = "docs/results/spread_summary.csv"


def draw_f5(root: Path) -> Figure:
    rows = read_csv(root, F5_SRC)
    fig, (a1, a2) = _new(3.2, ncols=2)
    for arm, colour, marker, label in (
        ("baseline", BLUE, "o", "baseline protection"),
        ("shorter", ORANGE, "s", "shorter protection"),
    ):
        sel = sorted((r for r in rows if r["arm"] == arm), key=lambda r: float(r["spacing_km"]))
        x = [float(r["spacing_km"]) for r in sel]
        a1.plot(x, [float(r["retention"]) for r in sel], marker=marker, color=colour, label=label)
        a2.plot(x, [float(r["all_four_out_h"]) for r in sel], marker=marker, color=colour)
    for a in (a1, a2):
        a.set_xscale("log")
        a.set_xticks([20, 500, 2000, 5000], ["20", "500", "2 000", "5 000"])
        a.set_xlabel("along-track spacing [km]")
        a.grid(alpha=0.3)
    a1.set_ylabel("retention [fraction of QUIET]")
    a1.set_ylim(0.75, 0.9)
    a2.set_ylabel("all four out of tasking modes [h]")
    a2.set_ylim(0, 30)
    a1.legend(fontsize=7, loc="lower left")
    return fig


# -- F6 data latency ---------------------------------------------------------------------------
F6_SRC = "docs/results/negative_results.json"
LATENCIES_S = (0, 300, 600, 900, 1200)


def draw_f6(root: Path) -> Figure:
    n6 = read_json(root, F6_SRC)["N6"]
    fig, (ax,) = _new(3.4)
    colours = (BLUE, ORANGE, GREEN, PURPLE)
    markers = ("o", "s", "^", "D")
    for (storm, by_lat), colour, marker in zip(n6.items(), colours, markers, strict=True):
        y = [
            sum(sum(sc["unprotected_s"].values()) for sc in by_lat[f"{lat}s"].values())
            for lat in LATENCIES_S
        ]  # sum over the four spacecraft
        ax.plot(LATENCIES_S[1:], y[1:], marker=marker, color=colour, label=STORM_LABELS[storm])
        ax.plot(LATENCIES_S[:2], y[:2], ls=":", color=colour)
        ax.plot(0, y[0], marker=marker, color=colour, mfc="none")
    ax.axvline(600, color=BLACK, ls="--", lw=0.8)
    ax.text(610, ax.get_ylim()[1] * 0.95, "recorded setting", fontsize=7, va="top")
    ax.set_xticks(LATENCIES_S, ["0\n(non-causal)", "300", "600", "900", "1 200"])
    ax.set_xlabel("series data latency [s]")
    ax.set_ylabel("unprotected hazard, 4 spacecraft [s]")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.3)
    return fig


# -- F7 re-sync --------------------------------------------------------------------------------
F7_SRC = "docs/results/resync_pairs.csv"


def draw_f7(root: Path) -> Figure:
    rows = [r for r in read_csv(root, F7_SRC) if r["group"] != "test"]
    order = list(STORM_LABELS)  # Phase 5, held-out, then spread
    storms = sorted(dict.fromkeys(r["storm"] for r in rows), key=order.index)
    tot: dict[str, dict[str, int]] = {
        s: dict.fromkeys(("b4", "b4_split", "rs", "rs_split"), 0) for s in storms
    }
    for r in rows:  # sum over the storm's arms
        t = tot[r["storm"]]
        t["b4"] += int(r["b4_lost_available"])
        t["b4_split"] += int(r["b4_lost_available_split"])
        t["rs"] += int(r["resync_lost_available"])
        t["rs_split"] += int(r["resync_lost_available_split"])
    fig, (ax,) = _new(4.4)
    y = np.arange(len(storms))
    h = 0.38
    for off, key, colour, label in (
        (-h / 2, "b4", VERMILLION, "B4"),
        (h / 2, "rs", BLUE, "B4 + re-sync"),
    ):
        total = np.array([tot[s][key] for s in storms])
        split = np.array([tot[s][key + "_split"] for s in storms])
        ax.barh(y + off, split, h, color=colour, label=f"{label}: split")
        ax.barh(
            y + off,
            total - split,
            h,
            left=split,
            color=colour,
            alpha=0.35,
            label=f"{label}: not split",
        )
        for yy, v in zip(y + off, total, strict=True):
            ax.text(v + 1, yy, str(v), va="center", fontsize=7)
    ax.set_yticks(y, [STORM_LABELS.get(s, s) for s in storms])
    ax.invert_yaxis()
    ax.set_xlabel("tasks lost while a spacecraft was available, summed over arms [tasks]")
    ax.set_xlim(0, 1.1 * max(max(t["b4"], t["rs"]) for t in tot.values()))
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    return fig


# -- F8 Basilisk -------------------------------------------------------------------------------
F8_SRC = "docs/results/basilisk_daily.csv"


def draw_f8(root: Path) -> Figure:
    rows = [r for r in read_csv(root, F8_SRC) if int(r["day"]) > 0]  # day 0 is 0 by design
    day = [int(r["day"]) for r in rows]
    fig, (a1, a2) = _new(3.4, ncols=2)
    for col, colour, marker, label in (
        ("K1_dr_m", BLUE, "o", "K1 two-body"),
        ("K2_dr_m", ORANGE, "s", "K2 J2"),
        ("K3_dr_m", GREEN, "^", "K3 J2 + drag"),
    ):
        a1.plot(day, [float(r[col]) for r in rows], marker=marker, color=colour, label=label)
    a1.plot(
        day,
        [float(r["K3_drag_effect_m"]) for r in rows],
        ls="--",
        color=BLACK,
        label="K3: drag's own effect",
    )
    a1.set_ylabel("|AstraMesh - Basilisk| position [m]")
    s0 = float(read_csv(root, F8_SRC)[0]["K4_spacing_m"])
    a2.plot(
        day,
        [abs(float(r["K4_d_spacing_m"])) for r in rows],
        marker="o",
        color=PURPLE,
        label="|AstraMesh - Basilisk| spacing",
    )
    a2.plot(
        day,
        [abs(float(r["K4_spacing_m"]) - s0) for r in rows],
        ls="--",
        color=BLACK,
        label="spacing change since day 0",
    )
    a2.set_ylabel("K4 sc00 - sc01 spacing [m]")
    for a in (a1, a2):
        a.set_yscale("log")
        a.set_xlabel("day")
        a.grid(alpha=0.3)
    a1.legend(fontsize=7, loc="center left", bbox_to_anchor=(0.0, 0.55))
    a2.legend(fontsize=7, loc="center right")
    return fig


# -- F9 forecast skill -------------------------------------------------------------------------
F9_SRC = "docs/results/storm_forecast.csv"
MODELS = {
    "P-A": ("P-A persistence", BLACK, "o"),
    "P-B": ("P-B", BLUE, "s"),
    "P-C": ("P-C", ORANGE, "^"),
}


def draw_f9(root: Path) -> Figure:
    rows = [r for r in read_csv(root, F9_SRC) if r["split"] == "storm" and r["quantile"] == "0.5"]
    fig, (a1, a2) = _new(3.2, ncols=2)
    horizons = sorted({int(r["horizon_s"]) for r in rows})
    for k, (model, (label, colour, marker)) in enumerate(MODELS.items()):
        sel = {int(r["horizon_s"]): r for r in rows if r["model"] == model}
        x = np.arange(len(horizons)) + 0.08 * (k - 1)  # dodge the models apart
        for a, col in ((a1, "pinball"), (a2, "pod_100pfu")):
            m = np.array([_f(sel[h][col]) for h in horizons])
            lo = np.array([_f(sel[h][col + "_lo"]) for h in horizons])
            hi = np.array([_f(sel[h][col + "_hi"]) for h in horizons])
            a.errorbar(
                x,
                m,
                yerr=[m - lo, hi - m],
                marker=marker,
                color=colour,
                capsize=3,
                ms=5,
                label=label,
            )
    names = {1800: "30 min", 3600: "1 h", 10800: "3 h"}
    for a in (a1, a2):
        a.set_xticks(range(len(horizons)), [names[h] for h in horizons])
        a.set_xlabel("forecast horizon")
        a.grid(alpha=0.3)
    a1.set_ylabel("pinball loss, median [log10 pfu]")
    a2.set_ylabel("POD, 100 pfu (median forecast)")
    a2.set_ylim(0, 1.02)
    a1.legend(fontsize=7, loc="upper left")
    return fig


SIM = "Simulated"
FIGURES: tuple[FigureSpec, ...] = (
    FigureSpec(
        "f1_storm_mar2024.png",
        "F1. The March 2024 storm window (21 - 28 March)",
        "Measured GOES ≥ 10 MeV proton flux (5-min records) and the P-B forecasts of the next-hour "
        "maximum, plotted at their issue time (record start + 600 s latency), with the three "
        "modelled spacecraft tolerances; below, measured OMNI SYM-H. The forecasts are model "
        "outputs from the pinned series; the tolerances are synthetic limits, not properties "
        "of a real payload. The whole 8-day pinned window is shown (21 - 28 Mar 2024); the "
        "onset is on 23 Mar.",
        (F1_SERIES,),
        draw_f1,
    ),
    FigureSpec(
        "f2_heldout_retention.png",
        "F2. Held-out storms: retention change by arm",
        f"{SIM}: pooled retention change against the baseline protection over the six held-out "
        "storms (mean and 95 % t-interval, n = 6), for both planners, driven by measured storm "
        "data (HELDOUT.md, DL-115). The wide B4 interval under A1 measures B4's ownership-split "
        "defect, not the value of look-ahead.",
        (F2_SRC,),
        draw_f2,
    ),
    FigureSpec(
        "f3_ablations.png",
        "F3. Ablations: science against hazard",
        f"{SIM}: pooled retention change (mean and 95 % t-interval) against the worst extra "
        "unprotected hazard on any spacecraft and storm, for each ablation; left the five "
        "Phase 5 storms (ABLATIONS.md, DL-108), right the six held-out storms (HELDOUT.md, "
        "DL-115). Filled: B3 + timeout; open: B4 (same hazard, protection is "
        "planner-independent; B4 is drawn slightly to the right for legibility). By spec "
        "§10.2 a gain that adds unprotected hazard is not better.",
        (F3_DEV, F3_HELD),
        draw_f3,
    ),
    FigureSpec(
        "f4_protection_tuning.png",
        "F4. Protection tuning on the February 2024 storm",
        f"{SIM}: retention (mean of seeds 1 - 3) against the worst extra unprotected hazard "
        "for each look-ahead H / release dwell D (seconds) and margin, planner B4, on the "
        "tuning storm (PROTECTION_TUNING.md). Arms right of the 600 s limit were not "
        "eligible (DL-101). Several arms coincide: the margin variants share one hazard "
        "value each.",
        (F4_SRC,),
        draw_f4,
    ),
    FigureSpec(
        "f5_spread_formation.png",
        "F5. Spread formation on 23 - 24 March 2024",
        f"{SIM}: retention against QUIET at the same spacing, and hours with all four "
        "spacecraft out of the tasking modes at once, against along-track spacing (B4, "
        "seeds 1 - 3 identical; SPREAD_FORMATION.md). Duplicates are not charged here: at "
        "2 000 km shorter protection makes 108 duplicates and, charged, falls below the "
        "baseline.",
        (F5_SRC,),
        draw_f5,
    ),
    FigureSpec(
        "f6_latency.png",
        "F6. Data latency and onset hazard",
        f"{SIM}: baseline unprotected hazard (summed over the four spacecraft; all of it at "
        "onsets) against the latency of the measured-data series, on the four storms whose "
        "baseline has unprotected hazard (NEGATIVE_RESULTS.md N6). 0 s is non-causal (the "
        "5-min average is not yet complete) and is a bound only.",
        (F6_SRC,),
        draw_f6,
    ),
    FigureSpec(
        "f7_resync_lost.png",
        "F7. B4 ownership re-sync: tasks lost while available",
        f"{SIM}: tasks completed in the storm's B4 QUIET but lost while some spacecraft was in "
        "a tasking mode for a whole window, summed over the storm's arms, B4 against B4 + "
        "re-sync, on the development storms (five Phase 5 and six held-out storms) and the "
        "two spread runs (2 000 and 5 000 km) (seed 1; RESYNC_COMPARISON.md, DL-124). Dark: "
        "split tasks. These storms were used to develop the re-sync; on the two test storms "
        "nothing changed. Not shown: in the 2 000 km spread run the re-sync raised duplicates "
        "from 15 to 111.",
        (F7_SRC,),
        draw_f7,
    ),
    FigureSpec(
        "f8_basilisk.png",
        "F8. AstraMesh against Basilisk",
        f"{SIM}: daily differences between AstraMesh and Basilisk propagations of the same "
        "cases over 8 days (BASILISK_COMPARISON.md, DL-118). Left: position difference for "
        "K1 - K3, with drag's own effect under K3 for scale. Right: the K4 spacing difference "
        "against the spacing change it is compared with.",
        (F8_SRC,),
        draw_f8,
    ),
    FigureSpec(
        "f9_forecast_skill.png",
        "F9. Proton forecast skill against horizon",
        "Forecasts (P-B, P-C) and persistence (P-A) scored against measured GOES flux on the "
        "held-out storm week, 8 - 15 May 2024: pinball loss of the median (lower is better) and "
        "row-wise POD at 100 pfu, with 95 % day-bootstrap intervals (STORM_FORECAST.md, "
        "DL-073). One storm week; intervals are coarse.",
        (F9_SRC,),
        draw_f9,
    ),
)


def readme(figures: tuple[FigureSpec, ...]) -> str:
    out = [
        "# Report figures",
        "",
        "Drawn by `scripts/figures/make_figures.py` from committed files only "
        "(`docs/results/` and the pinned `configs/data/` series); the script computes no new "
        "result. The PNGs are not byte-reproducible, so they are not hashed. Regenerate with:",
        "",
        "    uv run python scripts/figures/make_figures.py",
        "",
        "Simulated: the formation, utility, hazard and protection. Measured: GOES proton flux and "
        "OMNI SYM-H. No figure shows a real mission.",
        "",
        "Data credits (GOES-18 SGPS: NOAA NCEI and GOES-R SEISS; OMNI: NASA/GSFC SPDF "
        "OMNIWeb, with the data citation) are in the project "
        "[README](../../README.md#external-data).",
        "",
    ]
    for f in figures:
        out += [
            f"## {f.title}",
            "",
            f"![{f.title}]({f.name})",
            "",
            f.caption,
            "",
            "Sources: " + ", ".join(f"`{s}`" for s in f.sources),
            "",
        ]
    return "\n".join(out)


def make(out: Path, root: Path = ROOT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for spec in FIGURES:
        fig = spec.draw(root)
        path = out / spec.name
        fig.savefig(path, dpi=DPI)
        written.append(path)
    (out / "README.md").write_text(readme(FIGURES))
    written.append(out / "README.md")
    return written


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "figures")
    args = ap.parse_args(argv)
    for p in make(args.out):
        print(p)


if __name__ == "__main__":
    main()

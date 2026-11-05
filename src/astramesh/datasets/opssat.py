"""OPS-SAT-AD (DS-02) loader and splits for the anomaly-detection benchmark (DL-064).

Simulator-side only: agents never import this module. Files are opened through
``require_pinned``, so a missing or changed file stops the benchmark.

Each segment carries the 18 handcrafted features published with the dataset
(``dataset.csv``, Ruszczak et al. 2025). The label is the ``anomaly`` column (the
``label`` column in ``segments.csv`` is constant; DL-063). Two splits are provided:

* ``official``: the dataset's ``train`` flag (stratified random, interleaved in time);
* ``time``: per channel, the earliest ``frac`` of segments by start time train and the
  rest test (spec §7.4). Segments do not overlap, so no gap is needed between the parts.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt

from astramesh.datasets.sources import RAW, load_sources, require_pinned

# Feature order as in the dataset authors' modelling notebook (kplabs-pl/OPS-SAT-AD).
FEATURES = (
    "mean", "var", "std", "len", "duration", "len_weighted", "gaps_squared", "n_peaks",
    "smooth10_n_peaks", "smooth20_n_peaks", "var_div_duration", "var_div_len",
    "diff_peaks", "diff2_peaks", "diff_var", "diff2_var", "kurtosis", "skew",
)  # fmt: skip

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class OpsSat:
    """One row per segment, ordered by segment id."""

    segment: npt.NDArray[np.int64]
    channel: npt.NDArray[np.str_]
    start: npt.NDArray[np.int64]  # first sample time, ns since the Unix epoch (UTC)
    X: FloatArray  # (n, 18) in FEATURES order
    y: npt.NDArray[np.int64]  # 1 = anomalous
    official_train: BoolArray

    def split(self, name: str) -> BoolArray:
        """Training mask for ``"official"`` or ``"time"``."""
        if name == "official":
            return self.official_train
        if name == "time":
            return time_split(self.channel, self.start)
        raise ValueError(f"unknown split {name!r}")


def _pinned(name: str, raw: Path) -> Path:
    (f,) = (f for f in load_sources()["DS-02"].files if f.name == name)
    return require_pinned(f, raw)


def _ns(ts: str) -> int:
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return int(t.timestamp()) * 1_000_000_000 + t.microsecond * 1000


def read_segments(raw: Path = RAW) -> dict[int, tuple[str, list[int], list[float]]]:
    """Raw telemetry per segment: channel, sample times (ns) and values."""
    out: dict[int, tuple[str, list[int], list[float]]] = {}
    with _pinned("segments.csv", raw).open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            seg = int(r["segment"])
            if seg not in out:
                out[seg] = (r["channel"], [], [])
            out[seg][1].append(_ns(r["timestamp"]))
            out[seg][2].append(float(r["value"]))
    return out


def load(raw: Path = RAW) -> OpsSat:
    with _pinned("dataset.csv", raw).open(newline="", encoding="utf-8") as fh:
        rows = sorted(csv.DictReader(fh), key=lambda r: int(r["segment"]))
    segs = read_segments(raw)
    for r in rows:
        if segs[int(r["segment"])][0] != r["channel"]:
            raise ValueError(f"segment {r['segment']}: channel differs between files")
    return OpsSat(
        segment=np.array([int(r["segment"]) for r in rows], dtype=np.int64),
        channel=np.array([r["channel"] for r in rows]),
        start=np.array([min(segs[int(r["segment"])][1]) for r in rows], dtype=np.int64),
        X=np.array([[float(r[k]) for k in FEATURES] for r in rows], dtype=np.float64),
        y=np.array([int(r["anomaly"]) for r in rows], dtype=np.int64),
        official_train=np.array([r["train"] == "1" for r in rows], dtype=np.bool_),
    )


def time_split(
    channel: npt.NDArray[np.str_], start: npt.NDArray[np.int64], frac: float = 0.75
) -> BoolArray:
    """Per channel, the earliest ``ceil(frac * n)`` segments by start time train."""
    train = np.zeros(len(channel), dtype=np.bool_)
    for ch in np.unique(channel):
        idx = np.flatnonzero(channel == ch)
        order = idx[np.argsort(start[idx], kind="stable")]
        train[order[: math.ceil(frac * len(order))]] = True
    return train


def time_folds(
    channel: npt.NDArray[np.str_], start: npt.NDArray[np.int64], k: int = 5
) -> npt.NDArray[np.int64]:
    """Fold id per row: within each channel, ``k`` contiguous blocks in time order."""
    fold = np.zeros(len(channel), dtype=np.int64)
    for ch in np.unique(channel):
        idx = np.flatnonzero(channel == ch)
        order = idx[np.argsort(start[idx], kind="stable")]
        fold[order] = (np.arange(len(order)) * k) // len(order)
    return fold

"""P-A / P-B / P-C forecasts of the next-hour maximum >= 10 MeV flux, and their scores
(spec §7.3, DL-069). All work in log10 pfu on the rows of ``features.features``.

* **P-A, reactive:** no forecast; the latest available flux (persistence).
* **P-B, probabilistic:** the empirical ``q``-quantile of (target - current level) in the
  training rows with the same current level (0.25 dex bins) and 1-h trend (falling,
  flat, rising at +/- 0.05 dex), added to the current level. Bins with fewer than
  ``MIN_BIN`` rows fall back to the level bin, then to all rows.
* **P-C, learned:** gradient-boosted quantile regression (scikit-learn
  ``HistGradientBoostingRegressor``, loss ``quantile``) on all ``FEATURES``. Settings are
  fixed in ``PC_SETTINGS`` before any evaluation and are not tuned.

A forecast is NaN when the current flux is invalid: the simulation passes that on as a
missing forecast, which the supervisor never treats as zero risk (DL-056).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from astramesh.forecast.features import FEATURES

FloatArray = npt.NDArray[np.float64]
LEVEL_EDGES = np.arange(-2.0, 4.01, 0.25)
TREND_EDGES = np.array([-0.05, 0.05])
MIN_BIN = 50
PC_SETTINGS: dict[str, Any] = {
    "max_iter": 300, "learning_rate": 0.05, "max_leaf_nodes": 31, "min_samples_leaf": 50,
    "l2_regularization": 1.0, "early_stopping": False, "random_state": 0,
}  # fmt: skip
I_LEVEL, I_D60 = FEATURES.index("log_flux"), FEATURES.index("d60")


def pa_predict(X: FloatArray) -> FloatArray:
    out: FloatArray = X[:, I_LEVEL].copy()
    return out


@dataclass
class PB:
    q: float
    table: dict[tuple[int, int], float] = field(default_factory=dict)
    level_table: dict[int, float] = field(default_factory=dict)
    overall: float = 0.0

    @staticmethod
    def _bins(X: FloatArray) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]:
        lv = np.digitize(X[:, I_LEVEL], LEVEL_EDGES)
        tr = np.digitize(np.nan_to_num(X[:, I_D60]), TREND_EDGES)
        return lv, tr

    def fit(self, X: FloatArray, y: FloatArray) -> PB:
        ok = np.isfinite(X[:, I_LEVEL]) & np.isfinite(y)
        rise = y[ok] - X[ok, I_LEVEL]
        lv, tr = self._bins(X[ok])
        self.overall = float(np.quantile(rise, self.q))
        self.level_table = {int(b): float(np.quantile(rise[lv == b], self.q))
                            for b in np.unique(lv) if np.sum(lv == b) >= MIN_BIN}  # fmt: skip
        self.table = {}
        for b in np.unique(lv):
            for t in np.unique(tr):
                sel = (lv == b) & (tr == t)
                if np.sum(sel) >= MIN_BIN:
                    self.table[(int(b), int(t))] = float(np.quantile(rise[sel], self.q))
        return self

    def predict(self, X: FloatArray) -> FloatArray:
        lv, tr = self._bins(X)
        fallback = [self.level_table.get(int(b), self.overall) for b in lv]
        rise = np.array([self.table.get((int(b), int(t)), f)
                         for b, t, f in zip(lv, tr, fallback, strict=True)])  # fmt: skip
        out: FloatArray = np.where(np.isfinite(X[:, I_LEVEL]), X[:, I_LEVEL] + rise, np.nan)
        return out


@dataclass
class PC:
    q: float
    model: Any = None

    def fit(self, X: FloatArray, y: FloatArray) -> PC:
        from sklearn.ensemble import HistGradientBoostingRegressor  # ml group only

        ok = np.isfinite(X[:, I_LEVEL]) & np.isfinite(y)
        self.model = HistGradientBoostingRegressor(loss="quantile", quantile=self.q,
                                                   **PC_SETTINGS)  # fmt: skip
        self.model.fit(X[ok], y[ok])
        return self

    def predict(self, X: FloatArray) -> FloatArray:
        pred = np.asarray(self.model.predict(X), dtype=float)
        out: FloatArray = np.where(np.isfinite(X[:, I_LEVEL]), pred, np.nan)
        return out


# -- scores ------------------------------------------------------------------------------
def pinball(y: FloatArray, pred: FloatArray, q: float) -> float:
    ok = np.isfinite(y) & np.isfinite(pred)
    d = y[ok] - pred[ok]
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


def coverage(y: FloatArray, pred: FloatArray) -> float:
    """Fraction of rows whose outcome is at or below the forecast (ideal: q)."""
    ok = np.isfinite(y) & np.isfinite(pred)
    return float(np.mean(y[ok] <= pred[ok]))


@dataclass(frozen=True, slots=True)
class Warnings:
    hits: int
    misses: int
    false_alarms: int
    correct_negatives: int
    onsets: int
    onsets_warned: int
    lead_s: tuple[float, ...]  # per warned onset: onset time - first warning issue time

    @property
    def pod(self) -> float:
        n = self.hits + self.misses
        return self.hits / n if n else float("nan")

    @property
    def far(self) -> float:
        """False-alarm ratio: false alarms / all warnings."""
        n = self.hits + self.false_alarms
        return self.false_alarms / n if n else float("nan")


def warnings(y: FloatArray, pred: FloatArray, log_level: FloatArray, threshold_log: float,
             step_s: float = 300.0, latency_steps: int = 2,
             lookback_steps: int = 36) -> Warnings:  # fmt: skip
    """Row-wise contingency table for "the next-horizon maximum reaches the threshold",
    plus event onsets: a record at or above the threshold after at least 1 h below it.
    An onset at record k is warned if some forecast issued in the 3 h before the record
    starts (rows k - latency - lookback .. k - latency) reaches the threshold; the lead
    time counts from the first such issue time to the start of record k."""
    ok = np.isfinite(y) & np.isfinite(pred)
    event, warn = y >= threshold_log, pred >= threshold_log
    hits = int(np.sum(ok & event & warn))
    misses = int(np.sum(ok & event & ~warn))
    fa = int(np.sum(ok & ~event & warn))
    cn = int(np.sum(ok & ~event & ~warn))
    above = np.nan_to_num(log_level, nan=-np.inf) >= threshold_log
    leads: list[float] = []
    onsets = 0
    for k in range(12, len(above)):
        if above[k] and not above[k - 12 : k].any():
            onsets += 1
            lo, hi = max(k - latency_steps - lookback_steps, 0), k - latency_steps
            w = np.flatnonzero(np.nan_to_num(pred[lo : hi + 1], nan=-np.inf) >= threshold_log)
            if len(w):
                leads.append((k - (lo + w[0]) - latency_steps) * step_s)
    return Warnings(hits, misses, fa, cn, onsets, len(leads), tuple(leads))

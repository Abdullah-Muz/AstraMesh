"""95 % intervals for the forecast scores of ``models`` (DL-072).

* **Row scores** (pinball loss, coverage, row-wise POD and false-alarm ratio): a
  percentile bootstrap over **UTC days**. Each resample draws whole days with replacement,
  so the strong autocorrelation within a day (a proton event lasts hours) stays inside a
  block. A forecast belongs to the UTC day of its record start (it is issued 10 min
  later), so every evaluation splits into whole calendar days of records; forecasts
  whose target window crosses midnight stay with that day. The dependence that
  remains between neighbouring days is ignored. The models are
  resampled **paired** (the same days for every model), which gives intervals for the
  differences between models too.
* **Onsets warned:** too few for a bootstrap (4 on the storm week), so the warned
  fraction gets an exact Clopper-Pearson interval, treating onsets as independent.

A ratio whose denominator is zero in a resample (no event or no warning on the drawn days)
is undefined there; its interval uses only the resamples where it is defined, and the
number of those is returned with it. With few days (8 on the storm week) these intervals
are coarse and somewhat too narrow; they are a guide to the sampling spread, not exact
coverage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy import stats

from astramesh.forecast.models import FloatArray

IntArray = npt.NDArray[np.int64]
DAY_NS = 86_400 * 10**9
N_BOOT = 2000
SEED = 20240510  # fixed: the bootstrap is deterministic
LEVEL = 0.95


@dataclass(frozen=True, slots=True)
class Interval:
    lo: float
    hi: float
    n_defined: int  # resamples in which the score is defined


def day_index(t_ns: IntArray) -> IntArray:
    """0-based UTC day of each time (the record starts), relative to the first day present."""
    d: IntArray = (t_ns // DAY_NS).astype(np.int64)
    return d - d.min()


def resample_days(n_days: int, n_boot: int = N_BOOT, seed: int = SEED) -> IntArray:
    """``n_boot`` x ``n_days`` matrix of day indices drawn with replacement. The same
    matrix is used for every model of one evaluation (paired)."""
    out: IntArray = np.random.default_rng(seed).integers(0, n_days, size=(n_boot, n_days))
    return out


def _per_day(values: FloatArray, day: IntArray, n_days: int) -> FloatArray:
    out: FloatArray = np.bincount(day, weights=values, minlength=n_days).astype(float)
    return out


def _percentile(samples: FloatArray) -> Interval:
    ok = np.isfinite(samples)
    if not ok.any():
        return Interval(float("nan"), float("nan"), 0)
    a = (1 - LEVEL) / 2
    lo, hi = np.quantile(samples[ok], [a, 1 - a])
    return Interval(float(lo), float(hi), int(ok.sum()))


@dataclass(frozen=True, slots=True)
class DayTotals:
    """Per-day sums from which every row score of one model can be recomputed."""

    n: FloatArray
    loss: FloatArray
    covered: FloatArray
    hits: dict[float, FloatArray]
    misses: dict[float, FloatArray]
    false_alarms: dict[float, FloatArray]

    @classmethod
    def build(cls, y: FloatArray, pred: FloatArray, q: float, day: IntArray, n_days: int,
              thresholds_log: tuple[float, ...]) -> DayTotals:  # fmt: skip
        ok = np.isfinite(y) & np.isfinite(pred)
        d = np.where(ok, y - pred, 0.0)
        loss = np.where(ok, np.maximum(q * d, (q - 1) * d), 0.0)
        hits, misses, fas = {}, {}, {}
        for thr in thresholds_log:
            event, warn = ok & (y >= thr), ok & (pred >= thr)
            hits[thr] = _per_day((event & warn).astype(float), day, n_days)
            misses[thr] = _per_day((event & ~warn).astype(float), day, n_days)
            fas[thr] = _per_day((~event & warn & ok).astype(float), day, n_days)
        return cls(_per_day(ok.astype(float), day, n_days), _per_day(loss, day, n_days),
                   _per_day((ok & (y <= pred)).astype(float), day, n_days),
                   hits, misses, fas)  # fmt: skip

    def scores(self, idx: IntArray) -> dict[str, FloatArray]:
        """Each score in every resample (rows of ``idx``); NaN where undefined."""

        def s(a: FloatArray) -> FloatArray:
            out: FloatArray = a[idx].sum(axis=1)
            return out

        def ratio(num: FloatArray, den: FloatArray) -> FloatArray:
            with np.errstate(invalid="ignore", divide="ignore"):
                out: FloatArray = np.where(den > 0, num / den, np.nan)
            return out

        n = s(self.n)
        out = {"pinball": ratio(s(self.loss), n), "coverage": ratio(s(self.covered), n)}
        for thr in self.hits:
            h, m, f = s(self.hits[thr]), s(self.misses[thr]), s(self.false_alarms[thr])
            out[f"pod@{thr}"] = ratio(h, h + m)
            out[f"far@{thr}"] = ratio(f, h + f)
        return out


def row_intervals(y: FloatArray, preds: dict[str, FloatArray], q: float, t_ns: IntArray,
                  thresholds_log: tuple[float, ...], n_boot: int = N_BOOT,
                  seed: int = SEED,
                  ) -> tuple[dict[str, dict[str, Interval]],
                             dict[tuple[str, str], dict[str, tuple[float, Interval]]]]:  # fmt: skip
    """Day-block bootstrap intervals for every row score of every model, and for the
    paired difference (second minus first) of every pair of models, in ``preds`` order.

    Score keys: ``pinball``, ``coverage``, ``pod@<thr>`` and ``far@<thr>`` with ``thr``
    the log10 threshold as given. Differences carry their point value (all rows)."""
    day = day_index(t_ns)
    n_days = int(day.max()) + 1
    idx = resample_days(n_days, n_boot, seed)
    everyday = np.arange(n_days, dtype=np.int64)[None, :]
    totals = {m: DayTotals.build(y, p, q, day, n_days, thresholds_log) for m, p in preds.items()}
    boot = {m: t.scores(idx) for m, t in totals.items()}
    point = {m: {k: float(v[0]) for k, v in t.scores(everyday).items()}
             for m, t in totals.items()}  # fmt: skip
    single = {m: {k: _percentile(v) for k, v in b.items()} for m, b in boot.items()}
    names = list(preds)
    pairs: dict[tuple[str, str], dict[str, tuple[float, Interval]]] = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pairs[(a, b)] = {k: (point[b][k] - point[a][k], _percentile(boot[b][k] - boot[a][k]))
                             for k in boot[a]}  # fmt: skip
    return single, pairs


def clopper_pearson(k: int, n: int, level: float = LEVEL) -> tuple[float, float]:
    """Exact binomial interval for ``k`` successes in ``n`` trials; NaN when ``n`` is 0."""
    if n == 0:
        return float("nan"), float("nan")
    ci = stats.binomtest(k, n).proportion_ci(confidence_level=level, method="exact")
    return float(ci.low), float(ci.high)

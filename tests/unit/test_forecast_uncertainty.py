"""Day-block bootstrap and Clopper-Pearson intervals for the forecast scores (DL-072)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

from astramesh.forecast.models import coverage, pinball, warnings
from astramesh.forecast.uncertainty import (
    DAY_NS,
    DayTotals,
    clopper_pearson,
    day_index,
    resample_days,
    row_intervals,
)

T0 = int(np.datetime64("2024-05-08T00:00", "ns").astype(np.int64))
STEP_NS = 300 * 10**9
THR = (math.log10(100.0),)


def _days(n_days: int, seed: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = 288 * n_days
    t = T0 + np.arange(n, dtype=np.int64) * STEP_NS
    rng = np.random.default_rng(seed)
    y = rng.normal(1.0, 0.6, n)
    return t, y, y + rng.normal(0.0, 0.3, n)


def test_days_are_utc_calendar_days() -> None:
    t = np.array([T0, T0 + DAY_NS - 1, T0 + DAY_NS, T0 + 3 * DAY_NS], dtype=np.int64)
    assert day_index(t).tolist() == [0, 0, 1, 3]


def test_resampling_is_deterministic_and_draws_whole_days() -> None:
    a, b = resample_days(8, n_boot=50), resample_days(8, n_boot=50)
    assert np.array_equal(a, b)
    assert a.shape == (50, 8)
    assert a.min() >= 0
    assert a.max() <= 7


def test_intervals_bracket_the_full_sample_scores() -> None:
    t, y, p = _days(30)
    single, _ = row_intervals(y, {"m": p}, 0.5, t, THR, n_boot=500)
    for score, value in (("pinball", pinball(y, p, 0.5)), ("coverage", coverage(y, p))):
        iv = single["m"][score]
        assert iv.lo < value < iv.hi
        assert iv.n_defined == 500


def test_paired_difference_of_identical_models_is_exactly_zero() -> None:
    t, y, p = _days(10)
    _, pairs = row_intervals(y, {"a": p, "b": p.copy()}, 0.9, t, THR, n_boot=200)
    for value, iv in pairs[("a", "b")].values():
        assert value == 0.0 or math.isnan(value)
        assert (iv.lo, iv.hi) == (0.0, 0.0) or iv.n_defined == 0


def test_a_better_model_has_a_negative_pinball_difference() -> None:
    t, y, p = _days(30)
    worse = p + np.random.default_rng(2).normal(0.0, 0.5, len(p))
    _, pairs = row_intervals(y, {"worse": worse, "better": p}, 0.5, t, THR, n_boot=500)
    diff, iv = pairs[("worse", "better")]["pinball"]
    assert iv.lo < diff < iv.hi < 0.0


def test_scores_undefined_in_a_resample_are_counted_out() -> None:
    t, _, _ = _days(8)
    y = np.zeros(len(t))
    y[:12] = 3.0  # events on day 0 only: POD is undefined when day 0 is not drawn
    single, _ = row_intervals(y, {"m": y.copy()}, 0.5, t, THR, n_boot=1000)
    pod = single["m"][f"pod@{THR[0]}"]
    assert 0 < pod.n_defined < 1000
    assert (pod.lo, pod.hi) == (1.0, 1.0)


def test_missing_forecasts_are_left_out_like_the_point_scores() -> None:
    t, y, p = _days(5)
    p[::7] = np.nan
    single, _ = row_intervals(y, {"m": p}, 0.5, t, THR, n_boot=300)
    iv = single["m"]["pinball"]
    assert iv.lo < pinball(y, p, 0.5) < iv.hi


def test_clopper_pearson() -> None:
    lo, hi = clopper_pearson(4, 4)
    assert lo == pytest.approx(0.3976, abs=1e-4)
    assert hi == 1.0
    lo, hi = clopper_pearson(0, 4)
    assert lo == 0.0
    assert hi == pytest.approx(0.6024, abs=1e-4)
    assert all(math.isnan(v) for v in clopper_pearson(0, 0))


def test_a_resample_scores_like_the_drawn_days_concatenated() -> None:
    """POD and FAR pool counts over the drawn days (a day drawn twice counts twice);
    they are not averages of daily ratios."""
    t, y, p = _days(6, seed=3)
    y[300:330] = 2.5  # events on day 1
    p[290:325] = 2.4
    day = day_index(t)
    totals = DayTotals.build(y, p, 0.5, day, 6, THR)
    draw = np.array([[1, 1, 4, 0, 1, 5]], dtype=np.int64)
    got = {k: float(v[0]) for k, v in totals.scores(draw).items()}
    rows = np.concatenate([np.flatnonzero(day == d) for d in draw[0]])
    ys, ps = y[rows], p[rows]
    w = warnings(ys, ps, ys, THR[0], horizon_steps=12)
    assert got["pinball"] == pytest.approx(pinball(ys, ps, 0.5))
    assert got["coverage"] == pytest.approx(coverage(ys, ps))
    assert got[f"pod@{THR[0]}"] == pytest.approx(w.pod)
    assert got[f"far@{THR[0]}"] == pytest.approx(w.far)


def test_missing_targets_and_forecasts_are_excluded_from_every_count() -> None:
    t, y, p = _days(5, seed=4)
    y[::5] = np.nan
    p[3::11] = np.nan
    ok = np.isfinite(y) & np.isfinite(p)
    single, _ = row_intervals(y, {"m": p}, 0.5, t, THR, n_boot=1)
    full, _ = row_intervals(y[ok], {"m": p[ok]}, 0.5, t[ok], THR, n_boot=1)
    assert single["m"]["pinball"] == full["m"]["pinball"]
    assert single["m"]["coverage"] == full["m"]["coverage"]


def test_intervals_do_not_depend_on_model_order_or_count() -> None:
    t, y, p = _days(10, seed=5)
    other = p + 0.2
    a, _ = row_intervals(y, {"m": p}, 0.5, t, THR, n_boot=300)
    b, pairs = row_intervals(y, {"o": other, "m": p}, 0.5, t, THR, n_boot=300)
    assert a["m"] == b["m"]
    _, swapped = row_intervals(y, {"m": p, "o": other}, 0.5, t, THR, n_boot=300)
    d1, iv1 = pairs[("o", "m")]["pinball"]
    d2, iv2 = swapped[("m", "o")]["pinball"]
    assert d1 == -d2
    assert (iv1.lo, iv1.hi) == pytest.approx((-iv2.hi, -iv2.lo))


@pytest.mark.parametrize(("k", "n"), [(1, 1), (2, 4), (3, 7), (9, 10), (0, 30)])
def test_clopper_pearson_matches_the_beta_quantiles(k: int, n: int) -> None:
    lo, hi = clopper_pearson(k, n)
    want_lo = 0.0 if k == 0 else stats.beta.ppf(0.025, k, n - k + 1)
    want_hi = 1.0 if k == n else stats.beta.ppf(0.975, k + 1, n - k)
    assert (lo, hi) == pytest.approx((want_lo, want_hi), abs=1e-9)

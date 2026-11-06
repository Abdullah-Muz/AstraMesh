"""Forecast grid, availability, targets, models and scores on synthetic data (DL-069)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from astramesh.datasets.goes import STEP_NS, ProtonSeries
from astramesh.datasets.omni import MINUTE_NS, OmniSeries
from astramesh.forecast.features import FEATURES, LAG_STEPS, build_grid, features, target
from astramesh.forecast.models import PB, PC, coverage, pa_predict, pinball, warnings

T0 = int(np.datetime64("2024-01-01T00:00", "ns").astype(np.int64))


def _grid(flux: np.ndarray, sym: float = -20.0):  # type: ignore[no-untyped-def]
    n = len(flux)
    t = T0 + np.arange(n, dtype=np.int64) * STEP_NS
    g = ProtonSeries(t, flux.astype(float), np.column_stack([flux, flux]).astype(float),
                     flux.astype(float) * 10)  # fmt: skip
    tm = T0 + np.arange(5 * n, dtype=np.int64) * MINUTE_NS
    vals = {"sym_h_nt": np.full(5 * n, sym), "ae_nt": np.arange(5 * n, dtype=float),
            "bz_gsm_nt": np.zeros(5 * n), "flow_speed_km_s": np.full(5 * n, np.nan)}  # fmt: skip
    return build_grid(g, OmniSeries(tm, vals))


def _event(n: int = 600, start: int = 300) -> np.ndarray:
    f = np.full(n, 0.5)
    f[start:] = 0.5 * 1.3 ** np.minimum(np.arange(n - start), 30)  # rises to ~1300 pfu
    return f


def test_omni_is_averaged_into_the_goes_bins() -> None:
    g = _grid(np.ones(10))
    assert g.omni["ae_nt"][0] == pytest.approx(2.0)  # minutes 0..4
    assert g.omni["ae_nt"][3] == pytest.approx(17.0)
    assert np.all(g.omni["sym_h_nt"] == -20.0)


def test_features_never_use_data_from_the_future() -> None:
    f = _event()
    base = features(_grid(f))
    for i in (10, 299, 300, 450):
        g2 = f.copy()
        g2[i + 1 :] *= 7.0  # change everything after record i
        changed = features(_grid(g2))
        np.testing.assert_array_equal(base[: i + 1], changed[: i + 1])


def test_target_is_the_max_over_the_window_after_issue() -> None:
    f = np.arange(1, 101, dtype=float)
    g = _grid(f)
    y = target(g, 3600)  # 12 records
    i = 10  # issued when record 10 arrives: window = records 12 .. 23
    assert y[i] == pytest.approx(math.log10(f[i + LAG_STEPS + 11]))
    last = 100 - LAG_STEPS - 12
    assert np.isfinite(y[last])
    assert np.isnan(y[last + 1])
    with pytest.raises(ValueError, match="multiple"):
        target(g, 100)


def test_invalid_current_flux_gives_no_forecast() -> None:
    f = _event()
    f[400] = np.nan
    X = features(_grid(f))
    y = target(_grid(f), 3600)
    pb = PB(0.5).fit(X, y)
    assert np.isnan(pa_predict(X)[400])
    assert np.isnan(pb.predict(X)[400])
    assert np.isfinite(pb.predict(X)[399])


def test_pb_quantiles_rise_with_q_and_fall_back_when_bins_are_sparse() -> None:
    f = np.concatenate([_event(), _event()])
    X, y = features(_grid(f)), target(_grid(f), 3600)
    lo, hi = PB(0.5).fit(X, y), PB(0.9).fit(X, y)
    assert np.all(hi.predict(X)[np.isfinite(X[:, 0])] >= lo.predict(X)[np.isfinite(X[:, 0])])
    probe = X[:1].copy()
    probe[0, 0] = 3.9  # a level never seen in training: overall quantile
    assert hi.predict(probe)[0] == pytest.approx(3.9 + hi.overall)


def test_pc_learns_a_rising_event_and_is_deterministic() -> None:
    f = np.concatenate([_event(), _event(), _event()])
    X, y = features(_grid(f)), target(_grid(f), 3600)
    a, b = PC(0.5).fit(X, y).predict(X), PC(0.5).fit(X, y).predict(X)
    np.testing.assert_array_equal(a, b)
    ok = np.isfinite(y) & np.isfinite(a)
    assert pinball(y[ok], a[ok], 0.5) < pinball(y[ok], pa_predict(X)[ok], 0.5)
    assert X.shape[1] == len(FEATURES)


def test_scores() -> None:
    y = np.array([0.0, 1.0, 2.0, 3.0])
    assert pinball(y, y, 0.9) == 0.0
    assert pinball(y, y - 1, 0.9) == pytest.approx(0.9)
    assert pinball(y, y + 1, 0.9) == pytest.approx(0.1)
    assert coverage(y, y + 0.5) == 1.0
    assert coverage(y, y - 0.5) == 0.0


def test_warnings_count_onsets_and_lead_time() -> None:
    n = 100
    level = np.full(n, 0.0)
    level[50:60] = 2.5  # one onset at record 50 (>= 100 pfu = 2.0 in log10)
    y = np.full(n, 0.0)
    y[40:58] = 2.5
    pred = np.full(n, 0.0)
    pred[42:60] = 2.5  # first warning issued with record 42 = 40 min before record 50 starts
    w = warnings(y, pred, level, 2.0, horizon_steps=12)
    assert (w.onsets, w.onsets_warned) == (1, 1)
    assert w.lead_s == ((50 - 42 - LAG_STEPS) * 300.0,)
    assert (w.hits, w.misses, w.false_alarms) == (16, 2, 2)
    assert w.pod == pytest.approx(16 / 18)
    late = warnings(y, np.where(np.arange(n) >= 49, 2.5, 0.0), level, 2.0, horizon_steps=12)
    assert late.onsets_warned == 0  # a warning issued after the record starts is no warning
    early = warnings(y, np.where(np.arange(n) >= 30, 2.5, 0.0), level, 2.0, horizon_steps=12)
    assert early.lead_s == (12 * 300.0,)  # credited only from one horizon before the onset


def test_an_earlier_episode_is_not_a_warning_of_the_next() -> None:
    level = np.zeros(100)
    level[20:30] = 2.5
    level[45:50] = 2.5  # second onset at 45 after 15 records below
    persistence = level.copy()  # P-A: forecast = latest measurement
    w = warnings(level, persistence, level, 2.0, horizon_steps=36)
    assert w.onsets == 2
    assert w.onsets_warned == 0  # persistence can never warn ahead of an onset

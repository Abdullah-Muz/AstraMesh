"""Anomaly benchmark pieces on synthetic data (DL-064); no external data needed."""

from __future__ import annotations

import numpy as np
import pytest

from astramesh.anomaly.benchmark import Calibrator, best_f1_threshold, run, stratified_folds
from astramesh.anomaly.detectors import METHODS, seed_everything
from astramesh.anomaly.metrics import brier, detection, ece, reliability
from astramesh.datasets.opssat import time_folds, time_split


def _data(n: int = 240, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < 0.2).astype(np.int64)
    X = rng.normal(size=(n, 18))
    X[y == 1] = 3.0 * X[y == 1] + 1.5  # anomalies: shifted and scattered (not a cluster)
    return X, y


def test_detection_metrics_on_a_known_case() -> None:
    y = np.array([0, 0, 0, 1, 1])
    pred = np.array([0, 1, 0, 1, 0])
    m = detection(y, pred, np.array([0.1, 0.6, 0.2, 0.9, 0.4]))
    assert (m["precision"], m["recall"], m["accuracy"]) == (0.5, 0.5, 0.6)
    assert m["aucroc"] == pytest.approx(5 / 6)
    assert m["false_alert_rate"] == pytest.approx(1 / 3)
    assert m["missed"] == 1.0


def test_calibration_metrics() -> None:
    y = np.array([0, 1] * 50)
    assert ece(y, np.full(100, 0.5)) == pytest.approx(0.0)
    assert brier(y, np.full(100, 0.5)) == pytest.approx(0.25)
    assert ece(y, y.astype(float)) == 0.0
    assert ece(np.zeros(4, np.int64), np.full(4, 0.9)) == pytest.approx(0.9)
    assert reliability(y, np.full(100, 0.5)) == [(5, 100, 0.5, 0.5)]


def test_best_f1_threshold_picks_the_separating_score() -> None:
    y = np.array([0, 0, 1, 0, 1, 1])
    s = np.array([0.1, 0.2, 0.7, 0.3, 0.8, 0.9])
    assert best_f1_threshold(y, s) == 0.7
    # tied scores are kept together (no threshold inside a tie)
    assert best_f1_threshold(np.array([1, 0, 1]), np.array([0.5, 0.5, 0.1])) in (0.5, 0.1)


def test_calibrator_choice() -> None:
    X, y = _data(600)
    assert Calibrator(y, X[:, 0]).kind == "isotonic"  # >= 100 anomalies
    small = Calibrator(y[:200], X[:200, 0])
    assert small.kind == "platt"
    p = small(np.linspace(-3, 6, 50))
    assert np.all((p >= 0) & (p <= 1))
    assert np.all(np.diff(p) >= 0)


def test_time_split_and_folds_follow_time_per_channel() -> None:
    ch = np.array(["a"] * 8 + ["b"] * 4)
    start = np.array([7, 6, 5, 4, 3, 2, 1, 0, 30, 10, 20, 40])
    train = time_split(ch, start)
    assert train.tolist() == [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0]
    folds = time_folds(ch, start, k=4)
    assert folds[:8].tolist() == [3, 3, 2, 2, 1, 1, 0, 0]  # contiguous blocks in time
    assert folds[8:].tolist() == [2, 0, 1, 3]


def test_stratified_folds_keep_anomalies_in_every_fold() -> None:
    _, y = _data()
    f = stratified_folds(y, 0)
    assert sorted(set(f.tolist())) == [0, 1, 2, 3, 4]
    assert all(y[f == k].sum() > 0 for k in range(5))


@pytest.mark.parametrize("name", list(METHODS))
def test_every_method_detects_and_repeats(name: str) -> None:
    X, y = _data()
    train = np.arange(len(y)) < 180
    folds = stratified_folds(y[train], 0)
    a = run(METHODS[name], X, y, train, folds, seed=3)
    b = run(METHODS[name], X, y, train, folds, seed=3)
    np.testing.assert_array_equal(a.test_score, b.test_score)  # seeded: exact repeat
    paper, calibrated = a.rows
    assert (paper["protocol"], calibrated["protocol"]) == ("paper", "calibrated")
    if name != "mo_gaal":  # a GAN learns little from 180 rows; its skill is measured on real data
        assert calibrated["aucroc"] > 0.8, calibrated
    assert 0 <= calibrated["ece"] <= 1
    assert paper["model_bytes"] > 0


def test_seed_everything_fixes_torch() -> None:
    import torch

    seed_everything(5)
    a = torch.rand(3)
    seed_everything(5)
    assert torch.equal(a, torch.rand(3))

"""One benchmark run: a method fitted on one split with one seed, under two protocols.

``paper``      the library's default decision (PyOD contamination 0.2 or ``predict``),
               comparable with Ruszczak et al. (2025).
``calibrated`` threshold and calibration chosen on out-of-fold training scores only
               (5 folds; stratified random for the official split, contiguous time blocks
               per channel for the time split). The threshold maximises out-of-fold F1.
               Scores become probabilities through isotonic regression (Platt scaling
               when the training set has fewer than ``ISOTONIC_MIN_POS`` anomalies). The
               test set is used once.

The final detector is refitted on all training rows, so both protocols share its test
scores and AUCs. Unsupervised fold models can score on slightly different scales from the
final model; this is a limit of reusing their out-of-fold scores.
"""

from __future__ import annotations

import pickle
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import torch
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from astramesh.anomaly.detectors import Method, seed_everything
from astramesh.anomaly.metrics import brier, detection, ece, reliability

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
ISOTONIC_MIN_POS = 100


def stratified_folds(y: IntArray, seed: int, k: int = 5) -> IntArray:
    fold = np.zeros(len(y), dtype=np.int64)
    for i, (_, te) in enumerate(StratifiedKFold(k, shuffle=True, random_state=seed).split(y, y)):
        fold[te] = i
    return fold


def best_f1_threshold(y: IntArray, score: FloatArray) -> float:
    """Score threshold (predict ``score >= t``) with the highest F1; ties -> higher t."""
    order = np.argsort(-score, kind="stable")
    s, yy = score[order], y[order]
    tp = np.cumsum(yy)
    fp = np.cumsum(1 - yy)
    last = np.r_[s[1:] != s[:-1], True]  # last index of each distinct score
    f1 = 2 * tp / (tp + fp + yy.sum())
    f1 = np.where(last, f1, -1.0)
    return float(s[int(np.argmax(f1))])


class Calibrator:
    def __init__(self, y: IntArray, score: FloatArray) -> None:
        if int(y.sum()) >= ISOTONIC_MIN_POS:
            self.kind = "isotonic"
            self.model: Any = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            self.model.fit(score, y)
        else:
            self.kind = "platt"
            self.model = LogisticRegression().fit(score.reshape(-1, 1), y)

    def __call__(self, score: FloatArray) -> FloatArray:
        if self.kind == "isotonic":
            return np.asarray(self.model.predict(score), dtype=np.float64)
        return np.asarray(self.model.predict_proba(score.reshape(-1, 1))[:, 1], dtype=np.float64)


def model_bytes(det: object) -> int:
    """Pickled size; for models holding PyTorch networks (MO-GAAL), their parameter bytes."""
    try:
        return len(pickle.dumps(det))
    except (pickle.PicklingError, TypeError, AttributeError):
        model = getattr(getattr(det, "inner", None), "model", None)
        nets = [v for v in vars(model).values() if isinstance(v, torch.nn.Module)]
        return sum(p.numel() * p.element_size() for n in nets for p in n.parameters())


@dataclass(frozen=True, slots=True)
class Outcome:
    rows: list[dict[str, Any]]  # one per protocol
    test_score: FloatArray
    test_prob: FloatArray
    bins: list[tuple[int, int, float, float]]


def run(
    method: Method,
    X: FloatArray,
    y: IntArray,
    train: npt.NDArray[np.bool_],
    folds: IntArray,
    seed: int,
) -> Outcome:
    """Fit ``method`` on ``train`` rows (``folds`` = fold id per training row)."""
    Xtr, ytr, Xte, yte = X[train], y[train], X[~train], y[~train]
    oof = np.empty(len(ytr))
    for k in np.unique(folds):
        seed_everything(seed)
        m = method.make(seed).fit(Xtr[folds != k], ytr[folds != k])
        oof[folds == k] = m.score(Xtr[folds == k])
    threshold = best_f1_threshold(ytr, oof)
    cal = Calibrator(ytr, oof)

    seed_everything(seed)
    det = method.make(seed)
    t0 = time.process_time()
    det.fit(Xtr, ytr)
    t1 = time.process_time()
    score = det.score(Xte)
    t2 = time.process_time()
    default = det.predict(Xte)
    size = model_bytes(det)
    prob = cal(score)
    common = {"method": method.name, "kind": method.kind, "seed": seed,
              "n_train": len(ytr), "n_test": len(yte), "test_anomalies": int(yte.sum()),
              "fit_cpu_s": t1 - t0, "score_cpu_ms_per_segment": 1000 * (t2 - t1) / len(yte),
              "model_bytes": size}  # fmt: skip
    paper = {**common, "protocol": "paper", **detection(yte, default, score),
             "threshold": float("nan"), "calibrator": "", "brier": float("nan"),
             "ece": float("nan")}  # fmt: skip
    pred = (score >= threshold).astype(np.int64)
    calibrated = {**common, "protocol": "calibrated", **detection(yte, pred, score),
                  "threshold": threshold, "calibrator": cal.kind, "brier": brier(yte, prob),
                  "ece": ece(yte, prob)}  # fmt: skip
    return Outcome([paper, calibrated], score, prob, reliability(yte, prob))

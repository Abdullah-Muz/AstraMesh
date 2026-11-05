"""Detection and calibration metrics (spec §7.4; paper metrics of Ruszczak et al. 2025).

Each segment is one event, so segment-level precision and recall are event-level.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]

PAPER_METRICS = ("aucpr", "aucroc", "accuracy", "f1", "precision", "recall", "mcc")


def detection(y: IntArray, pred: IntArray, score: FloatArray) -> dict[str, float]:
    """The paper's seven metrics: AUCs from ``score``, the rest from ``pred``."""
    return {
        "aucpr": float(average_precision_score(y, score)),
        "aucroc": float(roc_auc_score(y, score)),
        "accuracy": float(accuracy_score(y, pred)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "mcc": float(matthews_corrcoef(y, pred)),
        "false_alert_rate": float(np.mean(pred[y == 0])) if np.any(y == 0) else float("nan"),
        "missed": float(np.sum((pred == 0) & (y == 1))),
    }


def brier(y: IntArray, p: FloatArray) -> float:
    return float(np.mean((p - y) ** 2))


def ece(y: IntArray, p: FloatArray, bins: int = 10) -> float:
    """Expected calibration error with ``bins`` equal-width bins on [0, 1]."""
    idx = np.minimum((p * bins).astype(np.int64), bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.mean() * abs(float(p[m].mean()) - float(y[m].mean()))
    return total


def reliability(y: IntArray, p: FloatArray, bins: int = 10) -> list[tuple[int, int, float, float]]:
    """Per bin: (bin, count, mean predicted probability, observed anomaly fraction)."""
    idx = np.minimum((p * bins).astype(np.int64), bins - 1)
    return [(b, int(m.sum()), float(p[m].mean()), float(y[m].mean()))
            for b in range(bins) if (m := idx == b).any()]  # fmt: skip

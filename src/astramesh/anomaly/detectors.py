"""The benchmark's detectors behind one interface (DL-064).

Every detector is fitted on the training rows and returns a score (higher = more
anomalous) and the library's default decision, which is the paper's protocol: PyOD
defaults with contamination 0.2 for the unsupervised methods, ``predict`` for the
supervised ones. Features are standardised with a scaler fitted on the nominal training
rows only, as in the dataset authors' notebook; that is the only use of labels by the
classical and unsupervised detectors.

All randomness is seeded from ``seed``; PyTorch and XGBoost run single-threaded so the
results repeat exactly on one machine.
"""

from __future__ import annotations

import contextlib
import io
import random
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import torch
from pyod.models.iforest import IForest
from pyod.models.lof import LOF
from pyod.models.mo_gaal import MO_GAAL
from pyod.models.ocsvm import OCSVM
from pyod.models.xgbod import XGBOD
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
CONTAMINATION = 0.2  # the paper's setting: the anomaly fraction of the training set


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)  # noqa: NPY002  (PyOD and MO-GAAL draw from the global state)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


class RobustZ:
    """Classical baseline: the largest robust z-score over the features.

    Median and scale (1.4826 x MAD, else the standard deviation, else 1) come from all
    training rows; the default threshold is the training (1 - contamination) quantile.
    """

    def __init__(self, contamination: float = CONTAMINATION) -> None:
        self.contamination = contamination

    def fit(self, X: FloatArray, y: IntArray) -> RobustZ:
        self.med_ = np.median(X, axis=0)
        mad = 1.4826 * np.median(np.abs(X - self.med_), axis=0)
        sd = X.std(axis=0)
        self.scale_ = np.where(mad > 0, mad, np.where(sd > 0, sd, 1.0))
        self.threshold_ = float(np.quantile(self.score(X), 1 - self.contamination))
        return self

    def score(self, X: FloatArray) -> FloatArray:
        return np.asarray(np.max(np.abs(X - self.med_) / self.scale_, axis=1), dtype=np.float64)

    def predict(self, X: FloatArray) -> IntArray:
        return (self.score(X) > self.threshold_).astype(np.int64)


class PyodUnsupervised:
    """A PyOD detector fitted on all training rows without labels."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def fit(self, X: FloatArray, y: IntArray) -> PyodUnsupervised:
        with contextlib.redirect_stdout(io.StringIO()):  # MO-GAAL prints every epoch
            self.model.fit(X)
        return self

    def score(self, X: FloatArray) -> FloatArray:
        with contextlib.redirect_stdout(io.StringIO()):
            return np.asarray(self.model.decision_function(X), dtype=np.float64)

    def predict(self, X: FloatArray) -> IntArray:
        with contextlib.redirect_stdout(io.StringIO()):
            return np.asarray(self.model.predict(X), dtype=np.int64)


class Supervised:
    """A classifier using the labels; score = predicted anomaly probability."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def fit(self, X: FloatArray, y: IntArray) -> Supervised:
        with warnings.catch_warnings():
            # PyOD's XGBOD passes labels to its inner unsupervised detectors and a
            # ``silent`` option that XGBoost no longer reads; both are harmless.
            warnings.filterwarnings("ignore", "y should not be presented", UserWarning)
            warnings.filterwarnings("ignore", r"(?s).*\"silent\" \} are not used", UserWarning)
            self.model.fit(X, y)
        return self

    def score(self, X: FloatArray) -> FloatArray:
        if isinstance(self.model, XGBOD):  # its decision_function is the probability
            return np.asarray(self.model.decision_function(X), dtype=np.float64)
        return np.asarray(self.model.predict_proba(X)[:, 1], dtype=np.float64)

    def predict(self, X: FloatArray) -> IntArray:
        return np.asarray(self.model.predict(X), dtype=np.int64)


class Scaled:
    """Standardise with statistics of the nominal training rows, then run ``inner``."""

    def __init__(self, inner: RobustZ | PyodUnsupervised | Supervised) -> None:
        self.inner = inner

    def fit(self, X: FloatArray, y: IntArray) -> Scaled:
        self.scaler = StandardScaler().fit(X[y == 0])
        self.inner.fit(self.scaler.transform(X), y)
        return self

    def score(self, X: FloatArray) -> FloatArray:
        return self.inner.score(self.scaler.transform(X))

    def predict(self, X: FloatArray) -> IntArray:
        return self.inner.predict(self.scaler.transform(X))


@dataclass(frozen=True, slots=True)
class Method:
    name: str
    kind: str  # "classical", "unsupervised" or "supervised"
    make: Callable[[int], Scaled]  # seed -> unfitted detector; call seed_everything first


def _u(model: Any) -> Scaled:
    return Scaled(PyodUnsupervised(model))


def _s(model: Any) -> Scaled:
    return Scaled(Supervised(model))


C = CONTAMINATION
METHODS: dict[str, Method] = {m.name: m for m in (
    Method("robust_z", "classical", lambda s: Scaled(RobustZ())),
    Method("iforest", "unsupervised", lambda s: _u(IForest(contamination=C, random_state=s))),
    Method("lof", "unsupervised", lambda s: _u(LOF(contamination=C))),
    Method("ocsvm", "unsupervised", lambda s: _u(OCSVM(contamination=C))),
    Method("mo_gaal", "unsupervised", lambda s: _u(MO_GAAL(contamination=C))),
    Method("logreg", "supervised", lambda s: _s(LogisticRegression(max_iter=5000, random_state=s))),
    Method("random_forest", "supervised",
           lambda s: _s(RandomForestClassifier(random_state=s, n_jobs=1))),
    Method("hist_gbdt", "supervised", lambda s: _s(HistGradientBoostingClassifier(random_state=s))),
    Method("xgbod", "supervised", lambda s: _s(XGBOD(random_state=s, n_jobs=1))),
)}  # fmt: skip

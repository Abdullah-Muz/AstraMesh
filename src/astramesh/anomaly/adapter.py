"""Adapter from the real-data detector to simulated spacecraft (spec §7.2, DL-066).

Simulator-side. The OPS-SAT benchmark's calibrated detector probabilities for test
segments, grouped by true label, form an *empirical score sensor*: while a simulated
payload is healthy each check draws a probability from the nominal segments, while it
is degraded (a ``payload_degraded`` fault is active) from the anomalous segments. The
detector's real error rates and its drift between training and test periods carry over;
OPS-SAT telemetry is not claimed to belong to AstraMesh's spacecraft.

Assumptions (limits): checks are independent given the payload state (real anomalies
and false alerts cluster in time); a degraded AstraMesh payload looks like an OPS-SAT
anomaly to the detector. ``nominal_contamination`` stresses the first: a fraction of
healthy checks is drawn from the anomalous scores (domain shift).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class ScoreSensor:
    nominal: tuple[float, ...]
    anomalous: tuple[float, ...]
    train_prior: float
    nominal_contamination: float = 0.0

    @classmethod
    def load(cls, path: str, sha256: str, split: str, contamination: float = 0.0) -> ScoreSensor:
        f = ROOT / path
        data = f.read_bytes()
        got = hashlib.sha256(data).hexdigest()
        if got != sha256:
            raise ValueError(f"{path}: sha256 {got} != pinned {sha256}")
        s = json.loads(data)["splits"][split]
        return cls(tuple(s["nominal"]), tuple(s["anomalous"]), float(s["train_prior"]),
                   contamination)  # fmt: skip

    def draw(self, rng: np.random.Generator, degraded: bool) -> float:
        """One detector probability for a payload whose true state is ``degraded``."""
        if not degraded and self.nominal_contamination > 0.0:
            degraded = bool(rng.random() < self.nominal_contamination)
        pool = self.anomalous if degraded else self.nominal
        return float(pool[int(rng.integers(len(pool)))])

"""S11 storm replay through the real supervisor, around the 10 May 2024 peak (DL-069)."""

from __future__ import annotations

import copy
import hashlib
import itertools
from pathlib import Path
from typing import Any

import pytest
import yaml

from astramesh.core.config import NominalOperationsScenario, parse_scenario
from astramesh.core.events import EventLog
from astramesh.core.rng import RandomStreams
from astramesh.scenarios.nominal_operations import run_nominal_operations

ROOT = Path(__file__).resolve().parents[2]
SHA = hashlib.sha256((ROOT / "configs/data/s11_storm_series.json").read_bytes()).hexdigest()


def _run(forecast: str | None, tol: float = 100.0) -> dict[str, Any]:
    raw = yaml.safe_load((ROOT / "configs/experiments/nominal_ops_b0_24h.yaml").read_text())
    cfg = copy.deepcopy(raw)
    cfg["time"]["epoch_utc"] = "2024-05-10T12:00:00Z"  # flux rises through 100 pfu ~17 UT
    cfg["time"]["duration_s"] = 12 * 3600
    cfg["operations"]["algorithm"] = "rule_b4"
    if forecast is not None:
        cfg["environment"] = {"background_exposure_ratio": 0.0,
                              "replay": {"series_sha256": SHA, "forecast": forecast,
                                         "radiation_tolerance_pfu": tol}}  # fmt: skip
    parsed = parse_scenario(cfg)
    assert isinstance(parsed, NominalOperationsScenario)
    run = run_nominal_operations(parsed, RandomStreams(parsed.random.seed), EventLog())
    return run.summary


@pytest.fixture(scope="module")
def runs() -> dict[str, dict[str, Any]]:
    return {k: _run(None if k == "quiet" else k) for k in ("quiet", "P-A", "P-C/q50")}


def test_the_storm_protects_every_spacecraft_and_never_breaks_safety(runs: Any) -> None:
    assert "storm" not in runs["quiet"]
    for k in ("P-A", "P-C/q50"):
        s = runs[k]
        st = s["storm"]
        assert st["forecast"] == k
        assert all(v > 0 for v in st["hazard_s"].values())  # the same GEO proxy for all four
        assert all(any(x["to"] == "PROTECTIVE" for x in tr)
                   for tr in s["protection"]["transitions"].values())  # fmt: skip
        assert sum(s["protection"]["payload_steps_in_protected_modes"].values()) == 0
        assert s["operations"]["utility"] < runs["quiet"]["operations"]["utility"]


def test_unprotected_hazard_intervals_add_up(runs: Any) -> None:
    """DL-106: the intervals cover exactly the unprotected hazard and record what the
    spacecraft saw when each began."""
    for k in ("P-A", "P-C/q50"):
        st = runs[k]["storm"]
        for a, items in st["unprotected_hazard_intervals"].items():
            total = sum(x["end_s"] - x["start_s"] for x in items)
            assert total == pytest.approx(st["hazard_s"][a] - st["protected_in_hazard_s"][a])
            for x, y in itertools.pairwise(items):
                assert x["end_s"] < y["start_s"]  # merged and ordered
            for x in items:
                assert x["mode"] not in ("PROTECTIVE", "RECOVERY")
                assert x["flux_pfu"] >= 100.0


def test_a_forecast_protects_earlier_than_reacting(runs: Any) -> None:
    def first(k: str) -> float:
        return float(min(x["t_s"] for tr in runs[k]["protection"]["transitions"].values()
                         for x in tr if x["to"] == "PROTECTIVE"))  # fmt: skip

    assert first("P-C/q50") < first("P-A")
    exposed = {k: sum(runs[k]["storm"]["exposed_s"].values()) for k in ("P-A", "P-C/q50")}
    assert exposed["P-C/q50"] <= exposed["P-A"]

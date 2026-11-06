"""S11 storm series lookups, config and hash compatibility (DL-069)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from astramesh.core.config import parse_scenario
from astramesh.forecast import replay
from astramesh.forecast.replay import FORECASTS, StormSeries

ROOT = Path(__file__).resolve().parents[2]
SERIES = "configs/data/s11_storm_series.json"
SHA = hashlib.sha256((ROOT / SERIES).read_bytes()).hexdigest()
S = 10**9
T0 = 1715126400 * S  # 2024-05-08T00:00:00Z


def test_committed_series_shape_and_lookup_rules() -> None:
    s = StormSeries.load(SERIES, SHA)
    assert s.start_ns == T0
    assert (s.step_ns, s.latency_ns) == (300 * S, 600 * S)
    assert len(s.truth_pfu) == 8 * 288
    assert set(s.forecast_pfu) == set(FORECASTS)
    assert s.truth(T0) == s.truth_pfu[0]
    assert s.truth(T0 + 299 * S) == s.truth_pfu[0]
    assert s.truth(T0 + 300 * S) == s.truth_pfu[1]
    assert s.forecast("P-A", T0 + 599 * S) is None  # nothing has arrived yet
    assert s.forecast("P-A", T0 + 600 * S) == s.forecast_pfu["P-A"][0]
    assert s.forecast("P-A", T0 + 600 * S) == s.truth_pfu[0]  # P-A = latest measurement
    assert s.truth(T0 - S) is None
    assert s.truth(T0 + 8 * 86400 * S) is None
    peak = int(np.nanargmax(s.truth_pfu))
    assert s.truth_pfu[peak] == pytest.approx(221.4, abs=0.1)  # 10 May 17:45 UT (DL-068)
    assert s.forecast_pfu["P-B/q90"][peak] >= s.forecast_pfu["P-B/q50"][peak]


def test_series_pin_is_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="sha256"):
        StormSeries.load(SERIES, "0" * 64)
    doc = json.loads((ROOT / SERIES).read_text())
    del doc["forecast_flux_pfu"]["P-C/q90"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc))
    monkeypatch.setattr(replay, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="forecasts"):
        StormSeries.load("bad.json", hashlib.sha256(bad.read_bytes()).hexdigest())


def _cfg() -> dict[str, Any]:
    raw = yaml.safe_load((ROOT / "configs/experiments/nominal_ops_b0_24h.yaml").read_text())
    return copy.deepcopy(raw)


def test_absent_replay_keeps_the_config_hash_and_replay_excludes_scheduled_forecasts() -> None:
    raw = _cfg()
    raw["environment"] = {"background_exposure_ratio": 0.0}
    base = parse_scenario(raw)
    assert "replay" not in base.canonical_dict()["environment"]
    raw["environment"]["replay"] = {"series_sha256": SHA, "forecast": "P-C/q50"}
    with_replay = parse_scenario(raw)
    assert with_replay.config_hash() != base.config_hash()
    raw["environment"]["forecasts"] = [
        {"forecast_id": "F", "start_s": 0, "end_s": 600, "exposure_ratio": 1.2}
    ]
    with pytest.raises(ValueError, match="exclusive"):
        parse_scenario(raw)


def test_unknown_forecast_is_rejected() -> None:
    raw = _cfg()
    raw["environment"] = {"background_exposure_ratio": 0.0,
                          "replay": {"series_sha256": SHA, "forecast": "P-D"}}  # fmt: skip
    with pytest.raises(ValueError, match="forecast"):
        parse_scenario(raw)

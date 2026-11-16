"""MP4 demonstration (DL-125, DL-126): the traced run reuses the recorded configuration, the
window and coordinate helpers, and the renderer draws frames from a small synthetic trace
without ffmpeg. When the recorded trace is committed, it must carry the recorded hash."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from astramesh.core.config import parse_scenario

ROOT = Path(__file__).resolve().parents[2]


def _load(rel: str, name: str) -> ModuleType:
    path = ROOT / rel
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None
        assert spec.loader is not None
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        sys.path.remove(str(path.parent))
    return m


def _trace_mod() -> ModuleType:
    return _load("scripts/experiments/demo_trace.py", "demo_trace")


def _demo_mod() -> ModuleType:
    return _load("scripts/figures/make_demo.py", "make_demo")


def test_trace_reuses_the_recorded_configuration() -> None:
    m = _trace_mod()
    want_hash, want_utility = m.recorded()
    assert parse_scenario(m.config()).config_hash() == want_hash
    assert want_utility == 969  # DL-124: phase5 / mar23_2024 / baseline, B4, seed 1


def test_window_starts_before_the_onset_and_is_clipped() -> None:
    m = _trace_mod()
    t = np.arange(0.0, 100 * 3600.0, 600.0)
    flux = np.full(t.size, 5.0)
    flux[t >= 20 * 3600] = 150.0
    assert m.window(t, flux) == (14 * 3600.0, 14 * 3600.0 + m.WINDOW_S)
    flux_early = np.where(t >= 3600, 150.0, 5.0)
    assert m.window(t, flux_early)[0] == 0.0  # clipped at the run start
    with pytest.raises(ValueError, match="onset"):
        m.window(t, np.full(t.size, 5.0))


def test_geocentric_lat_lon() -> None:
    m = _trace_mod()
    r = np.array([[7.0e6, 0.0, 0.0], [0.0, 7.0e6, 0.0], [0.0, 0.0, 7.0e6], [-1.0, -1.0e-9, 0.0]])
    lat, lon = m.geocentric_lat_lon(r)
    np.testing.assert_allclose(lat, [0.0, 0.0, 90.0, 0.0], atol=1e-9)
    np.testing.assert_allclose(lon[:2], [0.0, 90.0], atol=1e-9)
    assert abs(abs(lon[3]) - 180.0) < 1e-6


def _synthetic(n: int = 6) -> dict[str, Any]:
    ids = ["sc00", "sc01", "sc02", "sc03"]
    t = [1000.0 + 120.0 * i for i in range(n)]
    modes = ["NOMINAL", "STORM_WATCH", "PROTECTIVE", "PROTECTIVE", "RECOVERY", "NOMINAL"][:n]
    return {
        "epoch_utc": "2024-03-21T00:00:00+00:00",
        "spacecraft": ids, "tolerance_pfu": [100.0, 100.0, 50.0, 200.0],
        "modes": ["NOMINAL", "STORM_WATCH", "PROTECTIVE", "RECOVERY", "SAFE"],
        "frames": {
            "t_s": t, "flux_pfu": [5.0, None, 300.0, 400.0, 80.0, 20.0][:n],
            "cutoff_deg": [62.0] * n,
            "lat_deg": [[-60.0 + 25.0 * i for i in range(n)]] * 4,
            "lon_deg": [[170.0 + 5.0 * i - (360.0 if 170.0 + 5.0 * i > 180 else 0.0)
                         for i in range(n)]] * 4,  # crosses +-180 deg
            "mode": [modes] * 4,
            "in_access": [[i % 2 == 0 for i in range(n)]] * 4,
            "in_hazard": [[i in (2, 3) for i in range(n)]] * 4,
        },
        "segments": [{"spacecraft": "sc00", "task": "T1", "start_s": 1000.0, "stop_s": 1100.0,
                      "outcome": "completed"}],
        "takeovers": [{"t_s": 1240.0, "agent": "sc01", "task": "T2", "from": "sc00"}],
        "invariant_grid": {"lat_deg": [-90.0, 0.0, 90.0], "lon_deg": [-180.0, 0.0, 180.0],
                           "invariant_lat_deg": [[90.0] * 3, [0.0] * 3, [90.0] * 3]},
    }  # fmt: skip


def test_renderer_draws_every_frame_and_a_still(tmp_path: Path) -> None:
    d = _demo_mod()
    trace = _synthetic()
    _fig, update = d.build(trace)
    for i in range(len(trace["frames"]["t_s"])):
        update(i)  # no ffmpeg needed to draw
    out = tmp_path / "still.png"
    d.still(trace, out)
    assert out.stat().st_size > 10_000


def test_committed_trace_matches_the_recorded_run() -> None:
    path = ROOT / "docs/results/demo_trace.json"
    if not path.exists():
        pytest.skip("trace not recorded yet (DL-126 order: code, then the recorded trace)")
    m = _trace_mod()
    trace = json.loads(path.read_text())
    want_hash, want_utility = m.recorded()
    assert trace["config_hash"] == want_hash
    assert trace["utility"] == want_utility
    assert trace["git_dirty"] is False
    keys = set(_synthetic()["frames"])
    assert set(trace["frames"]) == keys
    n = len(trace["frames"]["t_s"])
    assert all(len(trace["frames"][k]) in (n, len(trace["spacecraft"])) for k in keys)

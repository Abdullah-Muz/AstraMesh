"""Held-out storm selection rule (DL-113) on synthetic flux: episodes, windows, reserve."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
STEP = 300 * 10**9
H = 3600 * 10**9
DAY = 86_400 * 10**9


def _mod() -> ModuleType:
    path = ROOT / "scripts/data/make_heldout_series.py"
    spec = importlib.util.spec_from_file_location("make_heldout_series", path)
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _grid(days: int) -> tuple[np.ndarray, np.ndarray]:
    t = np.arange(0, days * DAY, STEP, dtype=np.int64)
    return t, np.full(len(t), 1.0)


def test_episodes_merge_crossings_less_than_48_h_apart() -> None:
    m = _mod()
    t, f = _grid(20)
    f[t == 1 * DAY] = 150.0
    f[t == 1 * DAY + 47 * H] = 120.0  # 47 h later: merged
    f[t == 6 * DAY] = 100.0  # exactly the threshold counts
    f[t == 6 * DAY + 48 * H] = 200.0  # 48 h later: a new episode
    f[t == 12 * DAY] = 99.9  # below
    f[t == 13 * DAY] = np.nan  # invalid records never count
    eps = m.episodes(t, f)
    starts = [int(t[a]) for a, _ in eps]
    assert starts == [1 * DAY, 6 * DAY, 6 * DAY + 48 * H]
    assert int(t[eps[0][1]]) == 1 * DAY + 47 * H


def test_windows_start_two_days_before_and_absorb_later_episodes() -> None:
    m = _mod()
    lo, hi = 0, 60 * DAY
    first = [10 * DAY + 5 * H, 15 * DAY, 30 * DAY + 23 * H]
    ws = m.windows(first, lo, hi)
    assert [w["start_ns"] for w in ws] == [8 * DAY, 28 * DAY]
    assert ws[0]["episodes"] == [10 * DAY + 5 * H, 15 * DAY]  # inside 8 - 16 d: joins
    assert all(w["qualifies"] for w in ws)
    assert all(w["end_ns"] - w["start_ns"] == 8 * DAY for w in ws)


def test_windows_outside_the_period_do_not_qualify_or_absorb() -> None:
    m = _mod()
    lo, hi = 5 * DAY, 30 * DAY
    ws = m.windows([6 * DAY, 9 * DAY, 25 * DAY], lo, hi)
    assert [(w["start_ns"] // DAY, w["qualifies"]) for w in ws] == [(4, False), (7, True),
                                                                   (23, False)]  # fmt: skip
    assert ws[0]["reason"] == ws[2]["reason"] == "window extends outside the period"


def test_reserve_is_one_third_and_deterministic() -> None:
    m = _mod()
    for n in range(0, 13):
        r = m.reserve(n)
        assert len(r) == n // 3
        assert r <= set(range(n))
        assert r == m.reserve(n)
    assert m.reserve(9) == {int(i) for i in np.random.default_rng(113).permutation(9)[:3]}
    assert m.reserve(12) != m.reserve(12, seed=114)


def test_version_check_reports_invalid_and_quiet_flux() -> None:
    m = _mod()
    t, f = _grid(200)
    change = 100 * DAY
    f[t >= change] = 2.0
    f[(t >= 50 * DAY) & (t < 51 * DAY)] = 20.0  # a non-quiet day before the change
    f[t == 120 * DAY] = np.nan
    out = m.version_check(t, f, change)
    assert out["before"]["quiet_median_pfu"] == 1.0
    assert out["after"]["quiet_median_pfu"] == 2.0
    assert out["before"]["quiet_days"] == 89
    assert out["after"]["quiet_days"] == 90
    assert out["before"]["invalid_fraction"] == 0.0
    assert out["after"]["invalid_fraction"] > 0.0

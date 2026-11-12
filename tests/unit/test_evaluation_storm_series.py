"""Pinned tuning and evaluation storm series (DL-094, DL-098): load, size, disjoint
windows, all before the held-out May 2024 week."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from astramesh.forecast.replay import StormSeries

PINNED = {
    "configs/data/tuning_feb2024_series.json":
        ("2854446b8c57e16b4d180646730c6c7e23309762d1b321dabcc1f01654fa982d", "2024-02-08"),
    "configs/data/fold_jul18_2023_series.json":
        ("f359a7da3e879df99bd9f87d5c2efeb91c1cc8601d2141b533e66503b6cd92bb", "2023-07-16"),
    "configs/data/fold_jul29_2023_series.json":
        ("bc7080ec122cff9fe11e84dd1dc3ff74f36adbebb3afc0ebb1c169ee3d5774a5", "2023-07-27"),
    "configs/data/fold_jan29_2024_series.json":
        ("f800a9865cbc7e917da6f329c84e8b0a5ddf0e534dbdbcf37e5e65eeb4a995ed", "2024-01-27"),
    "configs/data/fold_mar23_2024_series.json":
        ("0f63027f661df7e0c3ee3efb814c131b4d6f972dd963631183fc5f7c41a00acc", "2024-03-21"),
}  # fmt: skip
DAY_NS = 86_400 * 10**9
MAY_2024_NS = 1_715_126_400 * 10**9  # 2024-05-08T00:00:00Z, the held-out S11 week


@pytest.mark.parametrize("path", sorted(PINNED))
def test_series_load_with_pinned_hash(path: str) -> None:
    sha, day = PINNED[path]
    s = StormSeries.load(path, sha)
    assert len(s.truth_pfu) == 8 * 288
    assert s.step_ns == 300 * 10**9
    assert s.latency_ns == 600 * 10**9
    assert s.issued_ns(s.start_ns + s.latency_ns) == s.start_ns + s.latency_ns
    assert max(v for v in s.truth_pfu if v == v) >= 100.0  # each holds an episode >= 100 pfu
    assert int(np.datetime64(day, "ns").astype(np.int64)) == s.start_ns


def test_windows_are_disjoint_and_before_the_test_week() -> None:
    spans = sorted((StormSeries.load(p, sha).start_ns, p) for p, (sha, _) in PINNED.items())
    for (a, _), (b, _) in itertools.pairwise(spans):
        assert b - a >= 8 * DAY_NS
    assert spans[-1][0] + 8 * DAY_NS <= MAY_2024_NS

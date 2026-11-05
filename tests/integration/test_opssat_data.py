"""Checks on the real OPS-SAT-AD files (DL-064); skipped where data/ is empty (CI)."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from astramesh.datasets.opssat import FEATURES, OpsSat, load, read_segments
from astramesh.datasets.sources import RAW, load_sources


def _have_data() -> bool:
    return all(f.path(RAW).exists() for f in load_sources()["DS-02"].files)


pytestmark = pytest.mark.skipif(not _have_data(), reason="OPS-SAT-AD not downloaded")


@pytest.fixture(scope="module")
def data() -> OpsSat:
    return load()


def test_split_counts(data: OpsSat) -> None:
    assert len(data.y) == 2123
    assert int(data.y.sum()) == 434
    off, tim = data.split("official"), data.split("time")
    assert (int(off.sum()), int(data.y[off].sum())) == (1594, 321)  # paper Table 1 says 1494
    assert (int(tim.sum()), int(data.y[~tim].sum())) == (1596, 176)
    for ch in np.unique(data.channel):  # every test segment is later than its channel's train
        c = data.channel == ch
        assert data.start[c & tim].max() < data.start[c & ~tim].min()


def test_published_features_match_the_raw_telemetry(data: OpsSat) -> None:
    """Spot-check: recompute the basic statistics of every segment from segments.csv."""
    segs = read_segments()
    col = {k: i for i, k in enumerate(FEATURES)}
    for i, seg in enumerate(data.segment):
        _, t, v = segs[int(seg)]
        x = np.asarray(v)
        expect = {"len": len(x), "duration": (max(t) - min(t)) / 1e9, "mean": x.mean(),
                  "var": x.var(), "std": x.std()}  # fmt: skip
        if x.std() > 0:
            expect |= {"kurtosis": stats.kurtosis(x), "skew": stats.skew(x)}
        for k, e in expect.items():
            assert data.X[i, col[k]] == pytest.approx(e, rel=1e-6, abs=1e-12), (int(seg), k)

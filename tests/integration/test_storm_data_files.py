"""Checks on the real GOES-18 and OMNI files (DL-068); skipped where data/ is empty (CI)."""

from __future__ import annotations

import numpy as np
import pytest

from astramesh.datasets import goes, omni
from astramesh.datasets.sources import RAW, load_sources


def _have(*ids: str) -> bool:
    src = load_sources()
    return all(f.path(RAW).exists() for i in ids for f in src[i].files)


def _ns(iso: str) -> int:
    return int(np.datetime64(iso, "ns").astype(np.int64))


@pytest.mark.skipif(not _have("DS-07"), reason="GOES storm week not downloaded")
def test_storm_week_proton_flux() -> None:
    s = goes.load("DS-07")
    assert len(s.t_ns) == 8 * 288
    assert np.all(np.diff(s.t_ns) == goes.STEP_NS)
    assert s.t_ns[0] == _ns("2024-05-08T00:00")
    assert np.isnan(s.flux_ge10).sum() <= 2
    k = int(np.nanargmax(s.flux_ge10))
    assert s.t_ns[k] == _ns("2024-05-10T17:45")  # the 10 May proton event
    assert 150 < s.flux_ge10[k] < 400  # pfu; method-dependent (DL-068)
    quiet = s.t_ns < _ns("2024-05-10T00:00")
    assert np.nanmax(s.flux_ge10[quiet]) < 10  # below the NOAA S1 level before the event
    assert np.all(s.flux_ge10[~np.isnan(s.flux_ge10)] >= 0)


@pytest.mark.skipif(not _have("DS-06"), reason="OMNI May 2024 not downloaded")
def test_storm_week_geomagnetic_indices() -> None:
    o = omni.load("DS-06")
    assert len(o.t_ns) == 31 * 1440
    symh = o.values["sym_h_nt"]
    k = int(np.nanargmin(symh))
    assert (symh[k], o.t_ns[k]) == (-518, _ns("2024-05-11T02:14"))
    assert not np.isnan(symh).any()
    assert not np.isnan(o.values["ae_nt"]).any()


@pytest.mark.skipif(not _have("DS-08", "DS-09"), reason="forecast training data not downloaded")
def test_training_period_is_complete_and_precedes_the_storm() -> None:
    g, o = goes.load("DS-08"), omni.load("DS-09")
    assert g.t_ns[0] == _ns("2023-01-01T00:00") == o.t_ns[0]
    assert np.all(np.diff(g.t_ns) == goes.STEP_NS)
    assert len(g.t_ns) == 486 * 288
    assert g.t_ns[-1] < _ns("2024-05-01T00:00") <= o.t_ns[-1] + omni.MINUTE_NS
    assert np.isnan(g.flux_ge10).mean() < 0.01
    assert np.nanmax(g.flux_ge10) > 100  # the training period contains events above 100 pfu

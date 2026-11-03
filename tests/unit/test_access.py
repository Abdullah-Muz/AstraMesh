"""Access windows and opportunity merging on synthetic inputs."""

from __future__ import annotations

import math

import numpy as np
import pytest

from astramesh.dynamics.constants import R_EARTH_EQ_M, WGS84_E2
from astramesh.science.access import Site, access_windows, elevation_sine
from astramesh.science.opportunities import (
    OBSERVATION_TYPE,
    SOURCE_FLAG,
    Region,
    find_opportunities,
)

SIN20 = math.sin(math.radians(20.0))


def test_windows_are_runs_of_ticks_at_or_above_threshold() -> None:
    s = np.array([0.0, 0.5, 0.9, 0.5, 0.0, SIN20, 0.0, 0.5, 0.6])
    ws = access_windows(s, 20.0)
    assert [(w.first, w.last) for w in ws] == [(1, 3), (5, 5), (7, 8)]
    assert ws[0].peak == 2
    assert ws[0].peak_elevation_deg == pytest.approx(math.degrees(math.asin(0.9)), abs=1e-12)
    assert ws[1].n_ticks == 1  # exactly at the threshold counts as access
    assert not ws[0].truncated_start
    assert not ws[0].truncated_end
    assert ws[2].truncated_end
    assert not ws[2].truncated_start


def test_window_open_at_start_and_always_or_never_visible() -> None:
    ws = access_windows(np.array([0.9, 0.9, 0.0]), 20.0)
    assert [(w.first, w.last, w.truncated_start) for w in ws] == [(0, 1, True)]
    (w,) = access_windows(np.full(5, 0.99), 20.0)
    assert (w.first, w.last, w.truncated_start, w.truncated_end) == (0, 4, True, True)
    assert access_windows(np.zeros(5), 20.0) == []


def test_peak_elevation_clamped_at_zenith() -> None:
    (w,) = access_windows(np.array([1.0 + 1e-16]), 0.0)
    assert w.peak_elevation_deg == 90.0


@pytest.mark.parametrize("bad", [-1.0, 90.0, math.nan])
def test_invalid_threshold_raises(bad: float) -> None:
    with pytest.raises(ValueError, match="min_elevation_deg"):
        access_windows(np.zeros(3), bad)


def test_windows_need_one_dimensional_input() -> None:
    with pytest.raises(ValueError, match="1-D"):
        access_windows(np.zeros((3, 2)), 10.0)


def test_site_on_wgs84_ellipsoid() -> None:
    eq = Site.from_geodetic(0.0, 0.0)
    assert eq.itrs_m == pytest.approx((R_EARTH_EQ_M, 0.0, 0.0), abs=1e-9)
    pole = Site.from_geodetic(90.0, 0.0)
    b = R_EARTH_EQ_M * math.sqrt(1.0 - WGS84_E2)  # polar radius
    assert pole.itrs_m[2] == pytest.approx(b, abs=1e-6)
    assert pole.up == pytest.approx((0.0, 0.0, 1.0), abs=1e-15)
    for lat in (-60.0, 20.0, 45.0):
        s = Site.from_geodetic(lat, 30.0)
        x, y, z = s.itrs_m
        a2, b2 = R_EARTH_EQ_M**2, b * b
        assert (x * x + y * y) / a2 + z * z / b2 == pytest.approx(1.0, abs=1e-14)


@pytest.mark.parametrize(("lat", "lon"), [(91.0, 0.0), (0.0, 181.0), (math.nan, 0.0)])
def test_site_rejects_invalid_coordinates(lat: float, lon: float) -> None:
    with pytest.raises(ValueError, match="itude_deg"):
        Site.from_geodetic(lat, lon)


def test_elevation_sine_zenith_and_horizon() -> None:
    site = Site.from_geodetic(0.0, 0.0)
    over = np.array([R_EARTH_EQ_M + 5e5, 0.0, 0.0])
    side = np.array([R_EARTH_EQ_M, 1e6, 0.0])
    np.testing.assert_allclose(elevation_sine(np.stack([over, side]), site), [1.0, 0.0], atol=1e-15)


def _positions(visible: list[list[bool]]) -> np.ndarray:
    """Spacecraft straight over (0 N, 0 E) when visible, on the far side otherwise."""
    v = np.array(visible, dtype=bool)
    r = np.zeros((*v.shape, 3))
    r[..., 0] = np.where(v, R_EARTH_EQ_M + 5e5, -(R_EARTH_EQ_M + 5e5))
    return r


def test_overlapping_or_touching_windows_merge_into_one_opportunity() -> None:
    region = Region("R1", 3, Site.from_geodetic(0.0, 0.0))
    #            t: 0      1      2      3      4      5      6      7
    sc0 = [False, True, True, False, False, False, True, False]
    sc1 = [False, False, True, True, False, False, False, False]  # overlaps sc0 -> merged
    sc2 = [False, False, False, False, True, False, False, False]  # touches tick 3 -> merged
    r = _positions([list(x) for x in zip(sc0, sc1, sc2, strict=True)])
    sunlit = np.ones(r.shape[:2], dtype=bool)
    sunlit[2, 0] = False
    ops = find_opportunities([region], ["sc00", "sc01", "sc02"], r, sunlit, 20.0)
    assert [(o.first, o.last) for o in ops] == [(1, 4), (6, 6)]
    assert [e.spacecraft for e in ops[0].eligible] == ["sc00", "sc01", "sc02"]
    assert [e.sunlit_ticks for e in ops[0].eligible] == [1, 2, 1]
    assert [o.task_id for o in ops] == ["TEC_0001", "TEC_0002"]
    rec = ops[0].to_record(np.arange(8, dtype=np.int64) * 10**10, 10**10)
    assert rec["start_t_ns"] == 10**10
    assert rec["end_t_ns"] == 4 * 10**10
    assert rec["duration_s"] == 30.0
    assert rec["observation_type"] == OBSERVATION_TYPE
    assert rec["source_flag"] == SOURCE_FLAG
    assert rec["payload_energy_wh"] is None
    assert rec["storage_mb"] is None


def test_opportunities_ordered_by_time_then_region() -> None:
    a = Region("A", 1, Site.from_geodetic(0.0, 0.0))
    b = Region("B", 2, Site.from_geodetic(0.0, 0.0))
    r = _positions([[False], [True], [False]])
    ops = find_opportunities([b, a], ["sc00"], r, np.ones((3, 1), dtype=bool), 10.0)
    assert [(o.task_id, o.region.region_id) for o in ops] == [("TEC_0001", "A"), ("TEC_0002", "B")]


def test_inconsistent_shapes_raise() -> None:
    region = Region("R1", 3, Site.from_geodetic(0.0, 0.0))
    r = _positions([[True, False]])
    with pytest.raises(ValueError, match="inconsistent"):
        find_opportunities([region], ["sc00"], r, np.ones((1, 2), dtype=bool), 10.0)

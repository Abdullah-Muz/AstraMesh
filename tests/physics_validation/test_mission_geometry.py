"""Gate P1: science eligibility is explained by modeled geometry (increment 6a).

Independent references: Astropy's GCRS->ITRS transform, Astropy's apparent Sun,
the analytic eclipse fraction of a circular orbit, and Astropy's
EarthLocation + topocentric ITRS -> AltAz elevation (its documented recipe for
nearby objects). Tolerances come from ``scripts/studies/geometry_reference_errors.py``
(``docs/NUMERICAL_MISSION_DESIGN.md`` §B.7, rule DL-019).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import GCRS, ITRS, AltAz, CartesianRepresentation, EarthLocation, get_body

from astramesh.core.config import MissionGeometryScenario, load_scenario
from astramesh.core.events import EventLog
from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.earth_frames import gcrs_to_itrs, gcrs_to_itrs_matrices, rotate
from astramesh.dynamics.sun import in_shadow, sun_direction_gcrs
from astramesh.dynamics.timescales import scenario_time
from astramesh.scenarios.mission_geometry import MissionGeometryRun, run_mission_geometry

# §B.7 tolerances
ITRS_MATRIX_POS_M = 2e-8  # observed 3.8e-9 m (round-off, ~5x)
SUN_DIRECTION_RAD = 3e-4  # observed 1.01e-4 rad (aberration + light time not modelled)
SHADOW_FRACTION = 1e-5  # observed 4.9e-6 at 200 000 samples per orbit
ELEVATION_DEG = 2e-12  # observed 2.5e-13 deg (round-off, ~8x)

CONFIG = Path(__file__).resolve().parents[2] / "configs/experiments/mission_geometry_24h.yaml"
A = R_EARTH_EQ_M + 525e3


@pytest.fixture(scope="module")
def baseline() -> tuple[MissionGeometryScenario, MissionGeometryRun]:
    config = load_scenario(CONFIG)
    assert isinstance(config, MissionGeometryScenario)
    return config, run_mission_geometry(config, EventLog())


def astropy_elevation_deg(r_itrs_m: np.ndarray, lat: float, lon: float, tm: Any) -> np.ndarray:
    loc = EarthLocation.from_geodetic(lon, lat, 0.0)
    topo = CartesianRepresentation(r_itrs_m.T * u.m) - loc.get_itrs(tm).cartesian
    altaz = ITRS(topo, obstime=tm, location=loc).transform_to(
        AltAz(obstime=tm, location=loc, pressure=0.0)
    )
    return np.asarray(altaz.alt.to_value(u.deg), dtype=np.float64)


def test_erfa_itrs_matrices_match_astropy(
    baseline: tuple[MissionGeometryScenario, MissionGeometryRun],
) -> None:
    config, run = baseline
    traj = run.formation.trajectory
    k = slice(None, None, 30)
    r = np.ascontiguousarray(traj.y[k, 0, :3])
    t = traj.t_ns[k]
    ours = rotate(gcrs_to_itrs_matrices(config.time.epoch_utc, t), r)
    ref, _ = gcrs_to_itrs(config.time.epoch_utc, t, r, traj.y[k, 0, 3:])
    assert float(np.max(np.linalg.norm(ours - ref, axis=1))) <= ITRS_MATRIX_POS_M
    back = rotate(gcrs_to_itrs_matrices(config.time.epoch_utc, t), ours, transpose=True)
    assert float(np.max(np.linalg.norm(back - r, axis=1))) <= ITRS_MATRIX_POS_M


def test_sun_direction_matches_astropy() -> None:
    epoch = datetime(2025, 6, 1, tzinfo=UTC)
    t = np.arange(0, 366, 30, dtype=np.int64) * 86_400 * 10**9
    tm = scenario_time(epoch, t)
    ref = get_body("sun", tm).transform_to(GCRS(obstime=tm)).cartesian.xyz.to_value(u.m).T
    ref /= np.linalg.norm(ref, axis=1)[:, None]
    ours = sun_direction_gcrs(epoch, t)
    ang = np.arccos(np.clip(np.sum(ours * ref, axis=1), -1.0, 1.0))
    assert float(ang.max()) <= SUN_DIRECTION_RAD


@pytest.mark.parametrize("beta_deg", [0.0, 30.0, 60.0, 65.0, 70.0])
def test_cylindrical_shadow_matches_analytic_eclipse_fraction(beta_deg: float) -> None:
    beta = math.radians(beta_deg)
    n = 200_000
    h = np.array([math.sin(beta), 0.0, math.cos(beta)])
    p = np.array([math.cos(beta), 0.0, -math.sin(beta)])
    q = np.cross(h, p)
    th = np.arange(n) * (2 * math.pi / n)
    r = A * (np.cos(th)[:, None] * p + np.sin(th)[:, None] * q)
    sampled = float(np.mean(in_shadow(r, np.tile([1.0, 0.0, 0.0], (n, 1)))))
    s = math.sqrt(A * A - R_EARTH_EQ_M**2) / (A * math.cos(beta))
    analytic = 0.0 if s >= 1.0 else math.acos(s) / math.pi
    assert abs(sampled - analytic) <= SHADOW_FRACTION


def test_every_eligibility_is_explained_by_astropy_elevation(
    baseline: tuple[MissionGeometryScenario, MissionGeometryRun],
) -> None:
    """Inside every window the elevation meets the mask; just outside it does not."""
    config, run = baseline
    traj = run.formation.trajectory
    t, epoch, thr = traj.t_ns, config.time.epoch_utc, config.science.min_elevation_deg
    n_t = len(t)
    assert run.records, "baseline must have opportunities"
    for rec in run.records:
        for e in rec["eligible_spacecraft"]:
            j = int(e["spacecraft"][2:])
            first = int(np.searchsorted(t, e["start_t_ns"]))
            last = int(np.searchsorted(t, e["end_t_ns"]))
            peak = int(np.searchsorted(t, e["peak_t_ns"]))
            ticks = [k for k in (first - 1, first, peak, last, last + 1) if 0 <= k < n_t]
            r = np.ascontiguousarray(traj.y[ticks, j, :3])
            r_itrs, _ = gcrs_to_itrs(epoch, t[ticks], r, traj.y[ticks, j, 3:])
            el = dict(
                zip(
                    ticks,
                    astropy_elevation_deg(
                        r_itrs, rec["region_latitude_deg"], rec["region_longitude_deg"],
                        scenario_time(epoch, t[ticks]),
                    ),
                    strict=True,
                )
            )  # fmt: skip
            for k in (first, peak, last):
                assert el[k] >= thr - ELEVATION_DEG
            for k in (first - 1, last + 1):
                if k in el:
                    assert el[k] < thr + ELEVATION_DEG
            assert abs(el[peak] - e["peak_elevation_deg"]) <= ELEVATION_DEG
            assert e["n_ticks"] == last - first + 1
            assert rec["start_t_ns"] <= e["start_t_ns"] <= e["end_t_ns"] <= rec["end_t_ns"]


def test_no_access_is_missed(baseline: tuple[MissionGeometryScenario, MissionGeometryRun]) -> None:
    """At sampled ticks, every Astropy-visible (spacecraft, region) lies in a reported window."""
    config, run = baseline
    traj = run.formation.trajectory
    epoch, thr = config.time.epoch_utc, config.science.min_elevation_deg
    ticks = np.arange(0, len(traj.t_ns), 7)
    tm = scenario_time(epoch, traj.t_ns[ticks])
    covered: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for rec in run.records:
        for e in rec["eligible_spacecraft"]:
            key = (e["spacecraft"], rec["region_or_path_id"])
            covered.setdefault(key, []).append((e["start_t_ns"], e["end_t_ns"]))
    n_visible = 0
    for j in range(traj.n_spacecraft):
        r = np.ascontiguousarray(traj.y[ticks, j, :3])
        r_itrs, _ = gcrs_to_itrs(epoch, traj.t_ns[ticks], r, traj.y[ticks, j, 3:])
        for reg in config.science.regions:
            el = astropy_elevation_deg(r_itrs, reg.latitude_deg, reg.longitude_deg, tm)
            spans = covered.get((f"sc{j:02d}", reg.region_id), [])
            for k in np.flatnonzero(el >= thr + ELEVATION_DEG).tolist():
                n_visible += 1
                tk = int(traj.t_ns[ticks[k]])
                assert any(a <= tk <= b for a, b in spans), (j, reg.region_id, tk)
    assert n_visible > 0


def test_opportunity_records_are_ordered_and_consistent(
    baseline: tuple[MissionGeometryScenario, MissionGeometryRun],
) -> None:
    _, run = baseline
    recs = run.records
    assert [r["id"] for r in recs] == [f"TEC_{k + 1:04d}" for k in range(len(recs))]
    keys = [(r["start_t_ns"], r["region_or_path_id"]) for r in recs]
    assert keys == sorted(keys)
    for r in recs:
        assert r["start_t_ns"] == min(e["start_t_ns"] for e in r["eligible_spacecraft"])
        assert r["end_t_ns"] == max(e["end_t_ns"] for e in r["eligible_spacecraft"])
        assert all(0 <= e["sunlit_ticks"] <= e["n_ticks"] for e in r["eligible_spacecraft"])

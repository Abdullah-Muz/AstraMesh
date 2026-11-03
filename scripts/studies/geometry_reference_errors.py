"""Study for increment 6a: Earth rotation, Sun, shadow, access geometry, eclipse fractions.

Run:  uv run python scripts/studies/geometry_reference_errors.py [--out g.json]

Recorded in docs/NUMERICAL_MISSION_DESIGN.md §B.7; tolerances in
tests/physics_validation/test_mission_geometry.py derive from it (DL-019).

  G1  ERFA GCRS->ITRS matrices (no BLAS) vs Astropy's transform, on the 24 h
      baseline trajectory: max position difference.
  G2  ERFA epv00 Sun direction vs Astropy's apparent geocentric Sun, one year
      weekly: max angle (expected ~20 arcsec: aberration and light time).
  G3  Cylindrical shadow vs the analytic eclipse fraction of a circular orbit,
      f = arccos(sqrt(h^2 + 2 R h) / (r cos beta)) / pi, beta 0..65 deg,
      200 000 samples per orbit (fixed Sun).
  G4  Elevation from astramesh.science.access vs Astropy's ITRS->AltAz
      (pressure 0) for every tick, spacecraft, and region of the baseline above
      -5 deg: max difference; and agreement of the access decision at every
      tick. Astropy's satellite recipe is used: subtract the site's ITRS
      position and give Astropy a *topocentric* ITRS coordinate. (A geocentric
      ITRS coordinate is first re-centred through Astropy's astrometric frames,
      which shifts a 100 km-distant object by up to ~0.16 deg; that is not
      the geometry modelled here.)
  G5  Shadow-model error: cylinder vs conical umbra / penumbra (Sun radius
      695 700 km, IAU 2015 B3), for the baseline beta: per-eclipse duration
      difference, on a 0.1 s analytic circular orbit.
  G6  Eclipse fraction over a year for 525 km / 97.5 deg sun-synchronous orbits
      by local time of the ascending node (analytic formula, validated by G3).
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import astropy.units as u
import numpy as np
from astropy.coordinates import GCRS, ITRS, AltAz, CartesianRepresentation, EarthLocation, get_body

from astramesh.core.config import MissionGeometryScenario, load_scenario
from astramesh.core.events import EventLog
from astramesh.dynamics.constants import GM_EARTH_M3PS2, R_EARTH_EQ_M
from astramesh.dynamics.earth_frames import (
    earth_pole_gcrs,
    gcrs_to_itrs,
    gcrs_to_itrs_matrices,
    rotate,
)
from astramesh.dynamics.forces import equatorial_basis
from astramesh.dynamics.sun import in_shadow, sun_direction_gcrs, sun_position_gcrs
from astramesh.dynamics.timescales import scenario_time
from astramesh.scenarios.mission_geometry import run_mission_geometry
from astramesh.science.access import Site, elevation_sine

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "mission_geometry_24h.yaml"
R_SUN_M = 695_700e3
H = 525e3
A = R_EARTH_EQ_M + H


def analytic_eclipse_fraction(beta_rad: float, a_m: float = A) -> float:
    s = math.sqrt(a_m * a_m - R_EARTH_EQ_M**2) / (a_m * math.cos(beta_rad))
    return 0.0 if s >= 1.0 else math.acos(s) / math.pi


def circular_orbit(beta_rad: float, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Positions on a circular orbit whose normal makes angle beta with the Sun (+x)."""
    # Orbit normal h = (sin beta, 0, cos beta); in-plane axes p, q.
    h = np.array([math.sin(beta_rad), 0.0, math.cos(beta_rad)])
    p = np.array([math.cos(beta_rad), 0.0, -math.sin(beta_rad)])
    q = np.cross(h, p)
    th = np.arange(n) * (2 * math.pi / n)
    r = A * (np.cos(th)[:, None] * p + np.sin(th)[:, None] * q)
    return r, th


def g1(run: Any, epoch: datetime) -> dict[str, Any]:
    traj = run.formation.trajectory
    r = np.ascontiguousarray(traj.y[:, 0, :3])
    ours = rotate(gcrs_to_itrs_matrices(epoch, traj.t_ns), r)
    ref, _ = gcrs_to_itrs(epoch, traj.t_ns, r, traj.y[:, 0, 3:])
    return {"max_position_diff_m": float(np.max(np.linalg.norm(ours - ref, axis=1)))}


def g2(epoch: datetime) -> dict[str, Any]:
    t = np.arange(0, 366, 7, dtype=np.int64) * 86_400 * 10**9
    d = sun_direction_gcrs(epoch, t)
    tm = scenario_time(epoch, t)
    ref = get_body("sun", tm).transform_to(GCRS(obstime=tm)).cartesian.xyz.to_value(u.m).T
    ref /= np.linalg.norm(ref, axis=1)[:, None]
    ang = np.arccos(np.clip(np.sum(d * ref, axis=1), -1.0, 1.0))
    return {"max_angle_rad": float(ang.max()), "max_angle_arcsec": math.degrees(ang.max()) * 3600}


def g3() -> dict[str, Any]:
    out = {}
    worst = 0.0
    for beta_deg in range(0, 70, 5):
        r, _ = circular_orbit(math.radians(beta_deg), 200_000)
        sun = np.array([[1.0, 0.0, 0.0]])
        frac = float(np.mean(in_shadow(r[:, None, :] * 1.0, np.repeat(sun, len(r), 0))))
        exp = analytic_eclipse_fraction(math.radians(beta_deg))
        out[f"beta_{beta_deg}"] = {"sampled": frac, "analytic": exp}
        worst = max(worst, abs(frac - exp))
    return {"per_beta": out, "max_abs_diff": worst, "sample_resolution": 1 / 200_000}


def astropy_elevation_deg(
    r_itrs_m: np.ndarray, lat_deg: float, lon_deg: float, tm: Any
) -> np.ndarray:
    """Independent elevation: Astropy EarthLocation (WGS 84) + topocentric ITRS -> AltAz."""
    loc = EarthLocation.from_geodetic(lon_deg, lat_deg, 0.0)
    topo = CartesianRepresentation(r_itrs_m.T * u.m) - loc.get_itrs(tm).cartesian
    altaz = ITRS(topo, obstime=tm, location=loc).transform_to(
        AltAz(obstime=tm, location=loc, pressure=0.0)
    )
    return np.asarray(altaz.alt.to_value(u.deg), dtype=np.float64)


def g4(run: Any, config: MissionGeometryScenario, epoch: datetime) -> dict[str, Any]:
    traj = run.formation.trajectory
    t = traj.t_ns
    tm = scenario_time(epoch, t)
    thr = config.science.min_elevation_deg
    worst = 0.0
    boundary_margin = math.inf  # smallest |astropy elevation - threshold| at boundary ticks
    disagreements = 0
    peak_worst = 0.0
    for j in range(traj.n_spacecraft):
        r = np.ascontiguousarray(traj.y[:, j, :3])
        r_itrs = rotate(gcrs_to_itrs_matrices(epoch, t), r)
        r_ast, _ = gcrs_to_itrs(epoch, t, r, traj.y[:, j, 3:])
        for reg in config.science.regions:
            site = Site.from_geodetic(reg.latitude_deg, reg.longitude_deg)
            ours = np.degrees(np.arcsin(elevation_sine(r_itrs, site)))
            ref = astropy_elevation_deg(r_ast, reg.latitude_deg, reg.longitude_deg, tm)
            m = ref > -5.0
            worst = max(worst, float(np.max(np.abs(ours[m] - ref[m]))))
            vis = ref >= thr
            ours_vis = ours >= thr
            disagreements += int(np.count_nonzero(vis != ours_vis))
            edge = np.flatnonzero(np.diff(vis.astype(np.int8)))
            for k in np.concatenate([edge, edge + 1]):
                boundary_margin = min(boundary_margin, abs(float(ref[k]) - thr))
    for rec in run.records:
        for e in rec["eligible_spacecraft"]:
            j = int(e["spacecraft"][2:])
            k = int(np.searchsorted(t, e["peak_t_ns"]))
            r_ast, _ = gcrs_to_itrs(epoch, int(t[k]), traj.y[k, j, :3], traj.y[k, j, 3:])
            alt = astropy_elevation_deg(
                r_ast[None, :],
                rec["region_latitude_deg"],
                rec["region_longitude_deg"],
                tm[k : k + 1],
            )[0]
            peak_worst = max(peak_worst, abs(float(alt) - e["peak_elevation_deg"]))
    return {
        "max_elevation_diff_deg": worst,
        "max_peak_elevation_diff_deg": peak_worst,
        "access_decision_disagreements": disagreements,
        "min_boundary_margin_deg": boundary_margin,
    }


def conical_state(r: np.ndarray, sun_pos: np.ndarray) -> np.ndarray:
    """0 = sunlit, 1 = penumbra, 2 = umbra (spherical Earth R_eq)."""
    to_sun = sun_pos - r
    ds = np.linalg.norm(to_sun, axis=1)
    dr = np.linalg.norm(r, axis=1)
    th_s = np.arcsin(R_SUN_M / ds)
    th_e = np.arcsin(R_EARTH_EQ_M / dr)
    cos_sep = np.sum(to_sun * -r, axis=1) / (ds * dr)
    sep = np.arccos(np.clip(cos_sep, -1, 1))
    out = np.zeros(len(r), dtype=np.int8)
    out[sep < th_e + th_s] = 1
    out[(th_e > th_s) & (sep < th_e - th_s)] = 2
    return out


def g5(beta_deg: float) -> dict[str, Any]:
    period = 2 * math.pi * math.sqrt(A**3 / GM_EARTH_M3PS2)
    n = round(period / 0.1)
    r, _ = circular_orbit(math.radians(beta_deg), n)
    sun_pos = np.array([1.496e11, 0.0, 0.0])
    cyl = in_shadow(r, np.repeat([[1.0, 0.0, 0.0]], n, 0))
    con = conical_state(r, sun_pos)
    dt = period / n
    return {
        "beta_deg": beta_deg,
        "cylinder_s": float(np.count_nonzero(cyl) * dt),
        "umbra_s": float(np.count_nonzero(con == 2) * dt),
        "umbra_plus_penumbra_s": float(np.count_nonzero(con >= 1) * dt),
        "per_edge_cylinder_minus_umbra_s": float(
            (np.count_nonzero(cyl) - np.count_nonzero(con == 2)) * dt / 2
        ),
        "per_edge_penumbra_minus_cylinder_s": float(
            (np.count_nonzero(con >= 1) - np.count_nonzero(cyl)) * dt / 2
        ),
    }


def g6(epoch: datetime) -> dict[str, Any]:
    """Eclipse fraction by LTAN and month for a mean 525 km / 97.5 deg SSO."""
    pole = earth_pole_gcrs(epoch)
    rot = equatorial_basis(pole)
    inc = math.radians(97.5)
    out: dict[str, Any] = {}
    for ltan in (6.0, 7.41, 9.0, 10.5, 12.0, 13.5):
        row = {}
        for month in range(12):  # mid-month, 2025-06 .. 2026-05
            day = epoch + timedelta(days=30.4 * month + 14)
            t_ns = int((day - epoch).total_seconds()) * 10**9
            s = rot @ sun_direction_gcrs(epoch, [t_ns])[0]
            sun_ra = math.atan2(s[1], s[0])
            raan = sun_ra + math.radians(15.0 * (ltan - 12.0))
            h = np.array([math.sin(inc) * math.sin(raan), -math.sin(inc) * math.cos(raan),
                          math.cos(inc)])  # fmt: skip
            beta = math.asin(float(np.clip(h @ s, -1, 1)))
            row[day.strftime("%Y-%m")] = {
                "beta_deg": math.degrees(beta),
                "eclipse_fraction": analytic_eclipse_fraction(beta),
            }
        fr = [v["eclipse_fraction"] for v in row.values()]
        out[f"ltan_{ltan:g}h"] = {"monthly": row, "max": max(fr), "min": min(fr)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    config = load_scenario(CONFIG)
    assert isinstance(config, MissionGeometryScenario)
    epoch = config.time.epoch_utc
    run = run_mission_geometry(config, EventLog())
    beta = run.summary["orbit_orientation_at_epoch"]["beta_angle_deg"]
    sun0 = sun_position_gcrs(epoch, [0])[0]
    result = {
        "G1_itrs_matrices": g1(run, epoch),
        "G2_sun_direction": g2(epoch),
        "G3_shadow_vs_analytic": g3(),
        "G4_elevation_vs_astropy": g4(run, config, epoch),
        "G5_shadow_model": {"baseline": g5(abs(beta)), "beta_0": g5(0.0)},
        "G6_eclipse_fraction_sso": g6(epoch),
        "baseline": {
            "orbit_orientation_at_epoch": run.summary["orbit_orientation_at_epoch"],
            "eclipse_fraction": run.summary["illumination"]["eclipse_fraction"],
            "analytic_fraction_at_epoch_beta": analytic_eclipse_fraction(math.radians(beta)),
            "sun_distance_au": float(np.linalg.norm(sun0) / 149_597_870_700.0),
            "n_opportunities": run.summary["science"]["n_opportunities"],
        },
    }
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

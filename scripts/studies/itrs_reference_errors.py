"""Reference-error studies for PA-04 (ITRS part).

Run:  uv run python scripts/studies/itrs_reference_errors.py [--out study.json]

Results are recorded in docs/NUMERICAL_MISSION_DESIGN.md §B.3, and the
tolerances in tests/physics_validation/test_frames_itrs.py are derived from
them by the approved rule (DL-019).

Studies (epochs: the reference epoch 2025-06-01 and the candidate storm epoch
2024-05-10, each + up to 30 days):
  S1  GCRS -> ITRS -> GCRS round-trip error (position, velocity).
  S2  Earth rotation angle: ITRS longitude of the GCRS x-axis vs -ERA from the
      IERS 2010 formula (independent of Astropy except for UT1). The expected
      difference is second order in the pole offset plus polar motion.
  S3  Pole offset: angle between the GCRS z-axis and the ITRS z-axis vs the
      IAU 2006 precession polynomial for the CIP X, Y (nutation and polar
      motion excluded, so they bound the expected difference).
  S4  ITRS velocity vs a central finite difference of ITRS positions of the
      same orbit (states at t +/- h from the analytic Kepler reference).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from astramesh.dynamics.constants import R_EARTH_EQ_M
from astramesh.dynamics.earth_frames import gcrs_to_itrs, itrs_to_gcrs
from astramesh.dynamics.elements import KeplerElements
from astramesh.dynamics.kepler import kepler_propagate
from astramesh.dynamics.timescales import earth_orientation_data_version, scenario_time

EPOCHS = (datetime(2025, 6, 1, tzinfo=UTC), datetime(2024, 5, 10, tzinfo=UTC))
SPAN_NS = 30 * 86_400 * 10**9
NS = 10**9
EPS = float(np.finfo(np.float64).eps)
ARCSEC = math.pi / (180 * 3600)


def era_rad(jd_ut1: np.ndarray) -> np.ndarray:
    """Earth rotation angle, IERS Conventions (2010) eq. 5.15."""
    du = jd_ut1 - 2451545.0
    return 2 * math.pi * np.mod(0.7790572732640 + 1.00273781191135448 * du, 1.0)


def cip_xy_precession_arcsec(t_tt_centuries: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Polynomial part of the IAU 2006 CIP X, Y (IERS Conventions 2010 eq. 5.16)."""
    t = t_tt_centuries
    x = -0.016617 + 2004.191898 * t - 0.4297829 * t**2 - 0.19861834 * t**3
    y = -0.006951 - 0.025896 * t - 22.4072747 * t**2 + 0.00190059 * t**3
    return x, y


def _random_states(rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray]:
    r = np.empty((n, 3))
    v = np.empty((n, 3))
    for k in range(n):
        el = KeplerElements(
            a_m=float(rng.uniform(R_EARTH_EQ_M + 200e3, R_EARTH_EQ_M + 2000e3)),
            e=float(rng.uniform(0.0, 0.02)),
            i_rad=float(rng.uniform(0.0, math.pi)),
            raan_rad=float(rng.uniform(0.0, 2 * math.pi)),
            argp_rad=float(rng.uniform(0.0, 2 * math.pi)),
            nu_rad=float(rng.uniform(0.0, 2 * math.pi)),
        )
        r[k], v[k] = el.to_rv()
    return r, v


def study(epoch: datetime, rng: np.random.Generator, n: int = 2000) -> dict[str, Any]:
    t_ns = np.sort(rng.integers(0, SPAN_NS, n))
    r, v = _random_states(rng, n)

    # S1 round trip
    ri, vi = gcrs_to_itrs(epoch, t_ns, r, v)
    rb, vb = itrs_to_gcrs(epoch, t_ns, ri, vi)
    dr = np.linalg.norm(rb - r, axis=1)
    dv = np.linalg.norm(vb - v, axis=1)
    rn = np.linalg.norm(r, axis=1)

    # S2 rotation angle and S3 pole, from unit-axis probes
    t = scenario_time(epoch, t_ns)
    ex = np.tile([R_EARTH_EQ_M, 0.0, 0.0], (n, 1))
    ez = np.tile([0.0, 0.0, R_EARTH_EQ_M], (n, 1))
    zeros = np.zeros((n, 3))
    xi, _ = gcrs_to_itrs(epoch, t_ns, ex, zeros)
    zi, _ = gcrs_to_itrs(epoch, t_ns, ez, zeros)
    lon = np.arctan2(xi[:, 1], xi[:, 0])
    jd_ut1 = t.ut1.jd1 + t.ut1.jd2
    d_rot = np.angle(np.exp(1j * (lon + era_rad(jd_ut1))))  # wrapped difference
    pole_angle = np.arccos(np.clip(zi[:, 2] / np.linalg.norm(zi, axis=1), -1, 1))
    t_tt = (t.tt.jd1 - 2451545.0 + t.tt.jd2) / 36525.0
    x, y = cip_xy_precession_arcsec(t_tt)
    d_pole = pole_angle / ARCSEC - np.hypot(x, y)

    # S4 velocity vs finite difference, h = 0.1 s, on a subset
    h_ns = 100_000_000
    m = 200
    fd_err = np.empty(m)
    for k in range(m):
        rp, _ = kepler_propagate(r[k], v[k], h_ns / NS)
        rm, _ = kepler_propagate(r[k], v[k], -h_ns / NS)
        tk = int(t_ns[k])
        rip, _ = gcrs_to_itrs(epoch, tk + h_ns, rp, zeros[0])
        rim, _ = gcrs_to_itrs(epoch, tk - h_ns, rm, zeros[0])
        fd = (rip - rim) / (2 * h_ns / NS)
        fd_err[k] = float(np.linalg.norm(fd - vi[k]))

    return {
        "epoch": epoch.isoformat(),
        "samples": n,
        "roundtrip_max_pos_err_m": float(dr.max()),
        "roundtrip_max_pos_err_in_eps_r": float((dr / (EPS * rn)).max()),
        "roundtrip_max_vel_err_mps": float(dv.max()),
        "rotation_angle_max_abs_diff_rad": float(np.abs(d_rot).max()),
        "pole_angle_minus_precession_arcsec_min": float(d_pole.min()),
        "pole_angle_minus_precession_arcsec_max": float(d_pole.max()),
        "pole_angle_arcsec_range": [
            float(pole_angle.min() / ARCSEC),
            float(pole_angle.max() / ARCSEC),
        ],
        "fd_velocity_samples": m,
        "fd_velocity_max_err_mps": float(fd_err.max()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    rng = np.random.default_rng(20261103)
    result = {
        "python": sys.version.split()[0],
        "earth_orientation_data": earth_orientation_data_version(),
        "epochs": [study(e, rng) for e in EPOCHS],
    }
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

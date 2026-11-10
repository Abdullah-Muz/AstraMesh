"""Storm-time density D2 (NRLMSIS 2.0), MS-01 to MS-05 (DL-084).

MS-01 geodetic conversion against Astropy; the wrapper equals a direct pymsis call.
MS-02 drivers from the pinned OMNI2 files (skipped without data/, as in CI).
MS-03 quiet-time density at 525 km within a factor of 3 of USSA 1976 (sanity band).
MS-04 density rises with ap at fixed F10.7.
MS-05 a 24 h decay in the May 2024 storm exceeds a quiet day's, and RK4 still
      converges at fourth order with MSIS density (skipped without data/).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

pymsis = pytest.importorskip("pymsis")  # optional dependency group "atmosphere"

from astropy import units as u  # noqa: E402
from astropy.coordinates import EarthLocation  # noqa: E402

from astramesh.datasets.sources import RAW, load_sources  # noqa: E402
from astramesh.dynamics.constants import GM_EARTH_M3PS2, R_EARTH_EQ_M  # noqa: E402
from astramesh.dynamics.drag import DragModel, density  # noqa: E402
from astramesh.dynamics.earth_frames import earth_pole_gcrs, gcrs_to_itrs_matrices  # noqa: E402
from astramesh.dynamics.forces import ForceModel, specific_energy  # noqa: E402
from astramesh.dynamics.msis_density import (  # noqa: E402
    MSIS_VERSION,
    MsisDensity,
    MsisDrivers,
    itrs_to_geodetic,
)
from astramesh.dynamics.state import CartesianState, Frame  # noqa: E402
from astramesh.dynamics.twobody import propagate  # noqa: E402

MU = GM_EARTH_M3PS2
NS = 10**9
B = 0.0092


def _synthetic(f107: float, ap: float, days: int = 200) -> MsisDrivers:
    return MsisDrivers(
        datetime(2024, 1, 1, tzinfo=UTC), np.full(days * 24, ap), np.full(days, f107)
    )


def _have_ds10() -> bool:
    return all(f.path(RAW).exists() for f in load_sources()["DS-10"].files)


def _ds10() -> MsisDrivers:
    return MsisDrivers.from_omni2([f.path(RAW) for f in load_sources()["DS-10"].files])


def _msis(epoch: datetime, drivers: MsisDrivers, n_steps: int, step_s: int) -> MsisDensity:
    t_ns = np.arange(n_steps + 1, dtype=np.int64) * step_s * NS
    return MsisDensity(epoch, float(step_s), gcrs_to_itrs_matrices(epoch, t_ns), drivers)


def _circular(epoch: datetime, h_m: float, incl: float = 1.7) -> CartesianState:
    r = R_EARTH_EQ_M + h_m
    v = math.sqrt(MU / r)
    return CartesianState(Frame.GCRS, epoch, 0, np.array([r, 0.0, 0.0]),
                          np.array([0.0, v * math.cos(incl), v * math.sin(incl)]))  # fmt: skip


# -- MS-01 ---------------------------------------------------------------------------
def test_ms01_geodetic_and_wrapper() -> None:
    rng = np.random.default_rng(0)
    lat = rng.uniform(-89, 89, 50)
    lon = rng.uniform(-180, 180, 50)
    h = rng.uniform(400e3, 700e3, 50)
    loc = EarthLocation.from_geodetic(lon * u.deg, lat * u.deg, h * u.m)
    xyz = np.stack([loc.x.to_value(u.m), loc.y.to_value(u.m), loc.z.to_value(u.m)], axis=1)
    la, lo, hh = itrs_to_geodetic(xyz)
    np.testing.assert_allclose(la, lat, atol=1e-9)
    np.testing.assert_allclose(lo, lon, atol=1e-9)
    np.testing.assert_allclose(hh, h, atol=1e-4)

    epoch = datetime(2024, 5, 11, tzinfo=UTC)
    m = _msis(epoch, _synthetic(150.0, 15.0), 10, 10)
    r = np.array([[R_EARTH_EQ_M + 525e3, 0.0, 0.0], [0.0, R_EARTH_EQ_M + 525e3, 1e5]])
    got = m.density(r, 0.0)
    r_itrs = np.einsum("ij,nj->ni", m.matrices[0], r)
    la, lo, hh = itrs_to_geodetic(r_itrs)
    want = pymsis.calculate(np.full(2, np.datetime64("2024-05-11T00:00")), lo, la, hh / 1e3,
                            f107s=np.full(2, 150.0), f107as=np.full(2, 150.0),
                            aps=np.full((2, 7), 15.0), version=MSIS_VERSION)[:, 0]  # fmt: skip
    np.testing.assert_allclose(got, want, rtol=1e-12)


# -- MS-03 / MS-04 ---------------------------------------------------------------------
def _density_525(f107: float, ap: float) -> float:
    epoch = datetime(2024, 5, 11, tzinfo=UTC)
    m = _msis(epoch, _synthetic(f107, ap), 10, 10)
    return float(m.density(np.array([[R_EARTH_EQ_M + 525e3, 0.0, 0.0]]), 0.0)[0])


def test_ms03_quiet_density_is_near_ussa76() -> None:
    ussa = float(density(np.array([525e3]))[0])
    ratio = _density_525(150.0, 4.0) / ussa
    assert 1 / 3 < ratio < 3


def test_ms04_density_rises_with_ap() -> None:
    rho = [_density_525(150.0, ap) for ap in (4.0, 50.0, 200.0)]
    assert rho[0] < rho[1] < rho[2]


# -- MS-02 / MS-05 (real drivers) ------------------------------------------------------
@pytest.mark.skipif(not _have_ds10(), reason="DS-10 (OMNI2 hourly) not downloaded")
def test_ms02_drivers_from_omni2() -> None:
    d = _ds10()
    assert d.start == datetime(2023, 1, 1, tzinfo=UTC)
    assert d.f107_daily.size == 365 + 366
    t = datetime(2024, 5, 11, 2, tzinfo=UTC)
    f107, f107a, ap = d.inputs([t])
    day = (t - d.start).days
    h = (t - d.start) // timedelta(hours=1)
    assert f107[0] == d.f107_daily[day - 1]  # previous day
    assert f107a[0] == pytest.approx(np.mean(d.f107_daily[day - 40 : day + 41]))
    assert ap[0, 1] == d.ap_hourly[h]  # 3-hour ap now
    assert ap[0, 2] == d.ap_hourly[h - 3]
    assert ap[0, 0] > 100  # the 11 May 2024 storm day


def _run(epoch: datetime, drivers: MsisDrivers, step_s: int, drag: bool) -> np.ndarray:
    n = 86_400 // step_s
    pole = earth_pole_gcrs(epoch)
    d = DragModel((B,), density_fn=_msis(epoch, drivers, n, step_s).density) if drag else None
    fm = ForceModel(mu=MU, pole=pole, drag=d)
    y: np.ndarray = propagate([_circular(epoch, 525e3)], step_ns=step_s * NS, n_steps=n,
                              forces=fm).y[:, 0, :]  # fmt: skip
    return y


def _drag_decay_m(epoch: datetime, drivers: MsisDrivers) -> float:
    """24 h semi-major-axis decay from drag alone (drag-free run at the same step removed)."""
    a = [-MU / (2 * specific_energy(_run(epoch, drivers, 10, flag), ForceModel(mu=MU)))
         for flag in (True, False)]  # fmt: skip
    return float((a[0][0] - a[0][-1]) - (a[1][0] - a[1][-1]))


@pytest.mark.skipif(not _have_ds10(), reason="DS-10 (OMNI2 hourly) not downloaded")
def test_ms05_storm_decay_and_convergence() -> None:
    drivers = _ds10()
    storm = _drag_decay_m(datetime(2024, 5, 10, 12, tzinfo=UTC), drivers)
    quiet = _drag_decay_m(datetime(2024, 4, 20, tzinfo=UTC), drivers)
    assert quiet > 0
    assert storm > 1.5 * quiet

    epoch = datetime(2024, 5, 10, 12, tzinfo=UTC)
    end = {h: _run(epoch, drivers, h, True)[-1, :3] for h in (40, 20, 10)}
    order = math.log2(np.linalg.norm(end[40] - end[20]) / np.linalg.norm(end[20] - end[10]))
    assert 3.5 < order < 5.5

"""GOES-18 SEISS/SGPS L2 5-min proton averages (DS-07, DS-08): integral flux >= 10 MeV.

Simulator-side only: agents never import this module. Files are opened through
``require_pinned``; reading them needs the ``data`` dependency group (h5py).

The product has 13 differential proton channels (1-500 MeV, per keV) and one integral
channel above 500 MeV, for two sensor units looking west (-X) and east (+X). It has no
>= 10 MeV integral channel, so one is derived here (DL-068):

* where a channel's band lies wholly above 10 MeV, its measured band integral (average
  flux x band width) is used; where two bands overlap, the overlap is counted once;
* the rest of 10-500 MeV (the part of P4 above 10 MeV, the gaps between bands, and the
  top band to 500 MeV) uses a power law fitted so that its averages over the two
  neighbouring bands equal their measured fluxes (above the top band, the last two bands);
* if either neighbour's flux is not positive (common at quiet times: the channels are
  background-subtracted), that piece uses the mean of the two fluxes, negatives as 0;
* the > 500 MeV integral channel is added;
* a unit's average is valid only if every channel used is finite and at least half of its
  300 one-second samples were valid; the reported flux is the larger of the valid units
  (an upper-bound proxy, DL-068), NaN if neither unit is valid.

Units: protons / (cm^2 sr s), i.e. pfu. Times: start of each 5-min average, ns since the
Unix epoch (UTC).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from astramesh.datasets.sources import RAW, SourceFile, load_sources, require_pinned

FloatArray = npt.NDArray[np.float64]
LOW_KEV = 10_000.0  # 10 MeV
TOP_KEV = 500_000.0  # lower edge of the integral channel P11
MIN_VALID_FRACTION = 0.5
STEP_NS = 300 * 10**9


@dataclass(frozen=True, slots=True)
class ProtonSeries:
    t_ns: npt.NDArray[np.int64]
    flux_ge10: FloatArray  # pfu, NaN = no valid unit
    flux_by_unit: FloatArray  # (n, 2), NaN where that unit is invalid


def integral_above(lo: FloatArray, hi: FloatArray, j: FloatArray, low: float = LOW_KEV,
                   top: float = TOP_KEV) -> FloatArray:  # fmt: skip
    """Integral from ``low`` to ``top`` (keV) of the spectrum measured as band-average fluxes
    ``j`` (n records x m bands, per keV) over bands [``lo``, ``hi``] (m, keV, ordered by
    ``lo``); see the module docstring. Returns n values."""
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    f = np.atleast_2d(np.asarray(j, dtype=float))
    m = len(lo)
    if lo.shape != hi.shape or f.shape[1] != m or m < 2 or np.any(np.diff(lo) <= 0):
        raise ValueError("need >= 2 bands ordered by lower edge, matching the flux columns")
    total = np.zeros(f.shape[0])
    covered: list[tuple[float, float]] = []
    edge = low
    for i in range(m):  # measured band integrals
        a, b = max(lo[i], edge), min(hi[i], top)
        if lo[i] >= low and b > a:
            total += np.maximum(f[:, i], 0.0) * (b - a)
            covered.append((a, b))
            edge = b
    gaps, x = [], low
    for a, b in covered:
        if a > x:
            gaps.append((x, a))
        x = max(x, b)
    if x < top:
        gaps.append((x, top))
    for a, b in gaps:
        right = next((i for i in range(m) if lo[i] >= b), None)
        k0, k1 = (m - 2, m - 1) if right is None else (right - 1, right)
        total += _fitted_integral(lo[[k0, k1]], hi[[k0, k1]], f[:, k0], f[:, k1], a, b)
    return total


def _log_avg(g: FloatArray, lo: float, hi: float, ref: float) -> FloatArray:
    """log of the average over [lo, hi] of (E / ref) ** -g."""
    r, s = hi / lo, 1.0 - g
    near = np.abs(s) < 1e-9
    integral = np.where(
        near, np.log(r), (r ** np.where(near, 1.0, s) - 1.0) / np.where(near, 1.0, s)
    )
    out: FloatArray = -g * np.log(lo / ref) + np.log(integral) + np.log(lo / (hi - lo))
    return out


def _fitted_integral(lo: FloatArray, hi: FloatArray, j0: FloatArray, j1: FloatArray,
                     a: float, b: float) -> FloatArray:  # fmt: skip
    """Integral over [a, b] of the power law whose averages over the two bands are j0, j1;
    the mean of the two fluxes (negatives as 0) where either is not positive."""
    ok = (j0 > 0) & (j1 > 0)
    out = 0.5 * (np.maximum(j0, 0.0) + np.maximum(j1, 0.0)) * (b - a)
    if not np.any(ok):
        return out
    ref = lo[0]
    target = np.log(j1[ok] / j0[ok])
    g_lo, g_hi = np.full(target.shape, -20.0), np.full(target.shape, 40.0)
    for _ in range(80):  # bisection: the band-average ratio falls as g rises
        g = 0.5 * (g_lo + g_hi)
        above = _log_avg(g, lo[1], hi[1], ref) - _log_avg(g, lo[0], hi[0], ref) > target
        g_lo, g_hi = np.where(above, g, g_lo), np.where(above, g_hi, g)
    g = 0.5 * (g_lo + g_hi)
    scale = j0[ok] / np.exp(_log_avg(g, lo[0], hi[0], ref))  # flux at ref
    s, A, B = 1.0 - g, a / ref, b / ref
    near = np.abs(s) < 1e-9
    piece = np.where(near, np.log(B / A),
                     A ** np.where(near, 1.0, s) * ((B / A) ** np.where(near, 1.0, s) - 1.0)
                     / np.where(near, 1.0, s))  # fmt: skip
    out[ok] = scale * ref * piece
    return out


# v3-0-0 files omit "UTC"; the epoch is the same (checked: every stamp falls on the 5-min grid)
TIME_UNITS = ("seconds since 2000-01-01 12:00:00 UTC", "seconds since 2000-01-01 12:00:00")
TIME_EPOCH_NS = int(np.datetime64("2000-01-01T12:00:00", "ns").astype(np.int64))


def _var(h: Any, name: str) -> FloatArray:
    """A variable as float64 with its ``_FillValue`` replaced by NaN."""
    v = h[name]
    x = np.asarray(v[()], dtype=float)
    fill = v.attrs.get("_FillValue")
    if fill is not None:
        x[x == float(np.asarray(fill).ravel()[0])] = np.nan
    return x


@dataclass(frozen=True, slots=True)
class _Raw:
    t_ns: npt.NDArray[np.int64]
    diff: FloatArray  # (n, 2, 13) per keV, NaN = fill
    valid: FloatArray  # (n, 2, 13) valid 1-s samples
    n_avg: FloatArray  # (n,) 1-s records in the average
    integ: FloatArray  # (n, 2) > 500 MeV, pfu
    e_lo: FloatArray  # (2, 13) keV
    e_hi: FloatArray


def _read_raw(path: Path) -> _Raw:
    import h5py  # data group only; netCDF-4 files are HDF5

    with h5py.File(path, "r") as h:
        units = h["time"].attrs["units"]
        if (units.decode() if isinstance(units, bytes) else str(units)) not in TIME_UNITS:
            raise ValueError(f"{path.name}: unexpected time units {units!r}")
        sec = _var(h, "time")
        raw = (_var(h, "AvgDiffProtonFlux"), _var(h, "DiffValidL1bSamplesInAvg"),
               _var(h, "L1bRecordsInAvg"), _var(h, "AvgIntProtonFlux"),
               _var(h, "DiffProtonLowerEnergy"), _var(h, "DiffProtonUpperEnergy"))  # fmt: skip
    if np.isnan(sec).any() or np.any(sec != np.round(sec)):
        raise ValueError(f"{path.name}: missing or fractional time stamps")
    return _Raw(TIME_EPOCH_NS + sec.astype(np.int64) * 10**9, *raw)


def _flux(r: _Raw) -> ProtonSeries:
    by_unit = np.full((len(r.t_ns), 2), np.nan)
    need = MIN_VALID_FRACTION * np.maximum(np.nan_to_num(r.n_avg), 1.0)
    for u in range(2):
        idx = np.flatnonzero(r.e_hi[u] > LOW_KEV)  # bands reaching above 10 MeV (P4 straddles)
        j = r.diff[:, u, idx]
        enough = r.valid[:, u, idx] >= need[:, None]
        good = np.all(np.isfinite(j) & enough, axis=1) & np.isfinite(r.integ[:, u])
        flux = integral_above(r.e_lo[u, idx], r.e_hi[u, idx], np.where(good[:, None], j, 0.0))
        by_unit[:, u] = np.where(good, flux + np.maximum(r.integ[:, u], 0.0), np.nan)
    return ProtonSeries(r.t_ns, np.fmax(by_unit[:, 0], by_unit[:, 1]), by_unit)


def read_file(path: Path) -> ProtonSeries:
    return _flux(_read_raw(path))


def pinned_files(dataset: str) -> tuple[SourceFile, ...]:
    return load_sources()[dataset].files


def load(dataset: str, raw: Path = RAW) -> ProtonSeries:
    """All files of a GOES dataset (DS-07 or DS-08), in time order. Each run of files with
    the same channel band edges is integrated together (the edges changed with processing
    version v3-0-1 in March 2023)."""
    parts = sorted((_read_raw(require_pinned(f, raw)) for f in pinned_files(dataset)),
                   key=lambda r: int(r.t_ns[0]))  # fmt: skip
    t = np.concatenate([p.t_ns for p in parts])
    if np.any(np.diff(t) <= 0):
        raise ValueError(f"{dataset}: duplicate or unordered time stamps")
    groups: list[list[_Raw]] = []
    for p in parts:
        last = groups[-1][0] if groups else None
        if (
            last is not None
            and np.array_equal(p.e_lo, last.e_lo)
            and np.array_equal(p.e_hi, last.e_hi)
        ):
            groups[-1].append(p)
        else:
            groups.append([p])
    out = [_flux(_Raw(np.concatenate([p.t_ns for p in g]),
                      np.concatenate([p.diff for p in g]),
                      np.concatenate([p.valid for p in g]),
                      np.concatenate([p.n_avg for p in g]),
                      np.concatenate([p.integ for p in g]), g[0].e_lo, g[0].e_hi))
           for g in groups]  # fmt: skip
    return ProtonSeries(t, np.concatenate([o.flux_ge10 for o in out]),
                        np.concatenate([o.flux_by_unit for o in out]))  # fmt: skip

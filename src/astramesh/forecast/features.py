"""Time grid, availability, features and targets for the proton forecasts (DL-069).

Everything lives on the GOES 5-min grid. Record ``i`` (average over [s_i, s_i + 5 min))
becomes available at ``s_i + LATENCY``: the end of the average plus 5 min delivery. A
forecast issued at ``t`` may use only records with ``s_i + LATENCY <= t``, so row ``i``
of the feature matrix is the forecast issued at ``s_i + LATENCY`` from records ``<= i``.
OMNI 1-min values are averaged into the same 5-min bins and obey the same rule.

The target of row ``i`` for horizon ``H`` is log10 of the largest flux among the records
starting in [s_i + LATENCY, s_i + LATENCY + H): what the payload will actually meet
during the next ``H`` after the forecast is issued.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from astramesh.datasets.goes import STEP_NS, ProtonSeries
from astramesh.datasets.omni import OmniSeries

FloatArray = npt.NDArray[np.float64]
LATENCY_NS = 600 * 10**9
FLOOR_PFU = 0.01  # log10 floor; quiet >= 10 MeV flux is about 0.5 pfu
LAG_STEPS = LATENCY_NS // STEP_NS  # 2
FEATURES = (
    "log_flux", "d5", "d15", "d30", "d60", "d180", "max3h", "max24h", "hardness",
    "sym_h", "sym_h_min3h", "ae", "ae_max3h", "bz",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Grid:
    t_ns: npt.NDArray[np.int64]  # record starts, contiguous 5-min grid
    log_flux: FloatArray  # log10 of the >= 10 MeV flux, NaN = invalid
    log_p3: FloatArray
    omni: dict[str, FloatArray]  # 5-min means of sym_h_nt, ae_nt, bz_gsm_nt

    @property
    def flux(self) -> FloatArray:
        out: FloatArray = 10.0**self.log_flux
        return out


def _log(x: FloatArray) -> FloatArray:
    out: FloatArray = np.log10(np.maximum(x, FLOOR_PFU))
    return out


def build_grid(goes: ProtonSeries, omni: OmniSeries) -> Grid:
    t = goes.t_ns
    if np.any(np.diff(t) != STEP_NS):
        raise ValueError("GOES series must be on a contiguous 5-min grid")
    k = (omni.t_ns - t[0]) // STEP_NS
    inside = (k >= 0) & (k < len(t))
    bins: dict[str, FloatArray] = {}
    for name in ("sym_h_nt", "ae_nt", "bz_gsm_nt"):
        v = omni.values[name][inside]
        ok = ~np.isnan(v)
        s = np.bincount(k[inside][ok], weights=v[ok], minlength=len(t))
        c = np.bincount(k[inside][ok], minlength=len(t))
        with np.errstate(invalid="ignore", divide="ignore"):
            bins[name] = np.where(c > 0, s / np.maximum(c, 1), np.nan)
    lf = np.where(np.isnan(goes.flux_ge10), np.nan, _log(goes.flux_ge10))
    lp3 = np.where(np.isnan(goes.flux_p3), np.nan, _log(goes.flux_p3))
    return Grid(t, lf, lp3, bins)


def _shift(x: FloatArray, k: int) -> FloatArray:
    """x[i - k] at row i (NaN before the start)."""
    out = np.full_like(x, np.nan)
    out[k:] = x[:-k]
    return out


def _rolling(x: FloatArray, n: int, fn: str) -> FloatArray:
    """Running max or min over rows i-n+1 .. i, ignoring NaN (NaN if all missing)."""
    from numpy.lib.stride_tricks import sliding_window_view

    pad = np.concatenate([np.full(n - 1, np.nan), x])
    win = sliding_window_view(pad, n)
    fill = -np.inf if fn == "max" else np.inf
    w = np.where(np.isnan(win), fill, win)
    r = w.max(axis=1) if fn == "max" else w.min(axis=1)
    out: FloatArray = np.where(np.isinf(r), np.nan, r)
    return out


def features(g: Grid) -> FloatArray:
    """(n, len(FEATURES)); row i = the forecast issued at t_ns[i] + LATENCY_NS."""
    lf = g.log_flux
    sym, ae, bz = g.omni["sym_h_nt"], g.omni["ae_nt"], g.omni["bz_gsm_nt"]
    cols = [
        lf,
        lf - _shift(lf, 1), lf - _shift(lf, 3), lf - _shift(lf, 6),
        lf - _shift(lf, 12), lf - _shift(lf, 36),
        _rolling(lf, 36, "max"), _rolling(lf, 288, "max"),
        lf - g.log_p3,
        sym, _rolling(sym, 36, "min"), ae, _rolling(ae, 36, "max"), bz,
    ]  # fmt: skip
    return np.column_stack(cols)


def target(g: Grid, horizon_s: int) -> FloatArray:
    """log10 of the largest flux in [issue, issue + horizon); NaN where the window runs
    past the data or holds no valid record."""
    h = horizon_s * 10**9 // STEP_NS
    if h * STEP_NS != horizon_s * 10**9 or h < 1:
        raise ValueError("horizon must be a positive multiple of 5 min")
    lf = g.log_flux
    n = len(lf)
    future = _rolling(lf, h, "max")  # max over i-h+1 .. i
    out = np.full(n, np.nan)
    last = n - LAG_STEPS - h + 1  # rows whose window ends inside the data
    if last > 0:
        out[:last] = future[LAG_STEPS + h - 1 : LAG_STEPS + h - 1 + last]
    return out

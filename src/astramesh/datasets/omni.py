"""NASA OMNI high-resolution 1-min data (DS-06, DS-09): geomagnetic indices and IMF Bz.

Simulator-side only: agents never import this module. Files are opened through
``require_pinned``.

Column layout of the 1-min ASCII files (46 fields; omniweb.gsfc.nasa.gov/html/
HROdocum.html): 1 year, 2 day of year, 3 hour, 4 minute (start of the average, UT),
19 Bz GSM [nT] (fill 9999.99), 22 flow speed [km/s] (fill 99999.9), 38 AE [nT] (fill
99999), 42 SYM/H [nT] (fill 99999). Fill values become NaN. AE and SYM/H come from the
WDC for Geomagnetism, Kyoto; the IMF and plasma values are time-shifted to the bow-shock
nose and have long gaps in this storm (39 % of May 2024 flow speeds are missing).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from astramesh.datasets.sources import RAW, load_sources, require_pinned

FloatArray = npt.NDArray[np.float64]
N_FIELDS = 46
# name: (0-based column, fill value)
COLUMNS = {"bz_gsm_nt": (18, 9999.99), "flow_speed_km_s": (21, 99999.9),
           "ae_nt": (37, 99999.0), "sym_h_nt": (41, 99999.0)}  # fmt: skip
MINUTE_NS = 60 * 10**9


@dataclass(frozen=True, slots=True)
class OmniSeries:
    t_ns: npt.NDArray[np.int64]  # start of each 1-min average, ns since the Unix epoch
    values: dict[str, FloatArray]  # COLUMNS keys; NaN = fill


def read_file(path: Path) -> OmniSeries:
    text = path.read_text(encoding="ascii")
    n_rows = text.count("\n")
    a = np.array(text.split(), dtype=float)
    if n_rows == 0 or a.size != n_rows * N_FIELDS:
        raise ValueError(f"{path.name}: expected {N_FIELDS} fields on each of {n_rows} rows")
    a = a.reshape(n_rows, N_FIELDS)
    year, doy, hour, minute = (a[:, i].astype(np.int64) for i in range(4))
    days = (year - 1970).astype("datetime64[Y]").astype("datetime64[D]") + (doy - 1)
    t = days.astype("datetime64[ns]").astype(np.int64) + (hour * 60 + minute) * MINUTE_NS
    if np.any(np.diff(t) != MINUTE_NS):
        raise ValueError(f"{path.name}: rows are not consecutive minutes")
    vals = {}
    for name, (col, fill) in COLUMNS.items():
        x = a[:, col].copy()
        x[np.isclose(x, fill)] = np.nan
        vals[name] = x
    return OmniSeries(t, vals)


def load(dataset: str, raw: Path = RAW) -> OmniSeries:
    """All files of an OMNI dataset (DS-06 or DS-09), concatenated in time order."""
    parts = sorted((read_file(require_pinned(f, raw)) for f in load_sources()[dataset].files),
                   key=lambda p: int(p.t_ns[0]))  # fmt: skip
    t = np.concatenate([p.t_ns for p in parts])
    if np.any(np.diff(t) != MINUTE_NS):
        raise ValueError(f"{dataset}: files are not contiguous")
    return OmniSeries(t, {k: np.concatenate([p.values[k] for p in parts]) for k in COLUMNS})

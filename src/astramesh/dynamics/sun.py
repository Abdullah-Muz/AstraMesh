"""Sun direction and Earth's shadow (cylindrical model).

Sun position
    Geocentric Sun = minus ERFA ``epv00``'s heliocentric Earth position (VSOP87
    based, IAU SOFA), in the BCRS/ICRS axes, which coincide with GCRS axes to
    milliarcseconds. Light time (~8.3 min, ~20 arcsec of apparent motion) and
    annual aberration (~20 arcsec) are not applied: for eclipse geometry and
    illumination a ~1e-4 rad direction error is far below the model error of
    the shadow itself (``NUMERICAL_MISSION_DESIGN.md`` §B.7). The computation
    is ERFA C code plus elementwise arithmetic (no BLAS, DL-031).

Shadow
    Cylindrical shadow of a spherical Earth with the WGS 84 equatorial radius:
    a spacecraft is in shadow when it is behind the Earth (r . s < 0) and within
    R_eq of the Earth-Sun line. Penumbra, Earth's flattening, and atmospheric
    refraction are ignored. Their effect on eclipse entry and exit times is
    measured in §B.7 rather than assumed.
"""

from __future__ import annotations

from datetime import datetime

import erfa
import numpy as np
from astropy.coordinates.builtin_frames.utils import get_jd12
from numpy.typing import ArrayLike, NDArray

from astramesh.dynamics.constants import AU_M, R_EARTH_EQ_M
from astramesh.dynamics.state import dot3, norm3
from astramesh.dynamics.timescales import scenario_time

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


def sun_position_gcrs(epoch_utc: datetime, t_ns: ArrayLike) -> FloatArray:
    """Geocentric Sun position [m], shape (n, 3), for integer times ``t_ns``."""
    t = np.atleast_1d(np.asarray(t_ns))
    if t.ndim != 1:
        raise ValueError(f"t_ns must be a scalar or a 1-D array, got shape {t.shape}")
    tt1, tt2 = get_jd12(scenario_time(epoch_utc, t), "tt")
    pvh, _ = erfa.epv00(tt1, tt2)
    earth_helio_au = np.asarray(pvh["p"], dtype=np.float64).reshape(t.shape[0], 3)
    out: FloatArray = -earth_helio_au * AU_M
    return out


def sun_direction_gcrs(epoch_utc: datetime, t_ns: ArrayLike) -> FloatArray:
    """Unit vector from Earth's centre to the Sun, shape (n, 3)."""
    s = sun_position_gcrs(epoch_utc, t_ns)
    out: FloatArray = s / norm3(s)[:, None]
    return out


def in_shadow(r_m: FloatArray, sun_dir: FloatArray, radius_m: float = R_EARTH_EQ_M) -> BoolArray:
    """Cylindrical-shadow test.

    ``r_m`` has shape (n, ..., 3) (e.g. time x spacecraft x 3) and ``sun_dir``
    shape (n, 3) with unit vectors. Returns a boolean array of shape (n, ...).
    """
    s = sun_dir.reshape(sun_dir.shape[0], *([1] * (r_m.ndim - 2)), 3)
    along = dot3(r_m, s)
    perp = r_m - along[..., None] * s
    out: BoolArray = (along < 0.0) & (dot3(perp, perp) < radius_m * radius_m)
    return out

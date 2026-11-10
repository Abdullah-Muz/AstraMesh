"""Physical constants used by the dynamics layer (SI units).

GM and the equatorial radius come from WGS 84 (NGA.STND.0036_1.0.0_WGS84, 2014,
Table 3.1); J2 comes from EGM2008 C-bar(2,0). Mixing WGS 84 GM/a with the
EGM2008 coefficient changes the J2 acceleration by ~2e-7 relative (negligible
here). Values are entered once and imported everywhere else;
``docs/DECISION_LOG.md`` (DL-018, DL-024) records sources and verification status.
"""

from __future__ import annotations

from typing import Final

#: Earth's gravitational parameter GM (including the atmosphere) [m^3 s^-2].
GM_EARTH_M3PS2: Final[float] = 3.986004418e14

#: Earth's equatorial radius (WGS 84 semi-major axis) [m].
R_EARTH_EQ_M: Final[float] = 6_378_137.0

#: WGS 84 inverse flattening 1/f (defining parameter) [dimensionless].
WGS84_INV_FLATTENING: Final[float] = 298.257223563

#: WGS 84 flattening f.
WGS84_FLATTENING: Final[float] = 1.0 / WGS84_INV_FLATTENING

#: WGS 84 first eccentricity squared e^2 = f (2 - f).
WGS84_E2: Final[float] = WGS84_FLATTENING * (2.0 - WGS84_FLATTENING)

#: Earth's nominal mean angular velocity (WGS 84 defining parameter) [rad/s].
#: Used for the co-rotating atmosphere in the drag model (DL-080); verification
#: against NGA.STND.0036 is pending with the other constants (DL-018).
OMEGA_EARTH_RADPS: Final[float] = 7.292115e-5

#: Astronomical unit (IAU 2012 Resolution B2, exact) [m].
AU_M: Final[float] = 149_597_870_700.0

#: Earth's normalized degree-2 zonal coefficient C-bar(2,0), EGM2008 (tide-free).
#: Source: Pavlis et al., EGM2008 coefficient file (NGA). Entered from the
#: published value; verification against the source file is pending (DL-024).
C20_NORMALIZED_EGM2008: Final[float] = -4.84165143790815e-4

#: Unnormalized J2 = -sqrt(5) * C-bar(2,0) [dimensionless] (~1.0826262e-3).
J2_EARTH: Final[float] = -(5.0**0.5) * C20_NORMALIZED_EGM2008

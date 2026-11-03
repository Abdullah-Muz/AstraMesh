"""Physical constants used by the dynamics layer (SI units).

Source: World Geodetic System 1984 defining parameters, NGA.STND.0036_1.0.0_WGS84
(2014), Table 3.1. Values are entered here once and imported everywhere else;
``docs/NUMERICAL_MISSION_DESIGN.md`` records the source and its verification status.
"""

from __future__ import annotations

from typing import Final

#: Earth's gravitational parameter GM (including the atmosphere) [m^3 s^-2].
GM_EARTH_M3PS2: Final[float] = 3.986004418e14

#: Earth's equatorial radius (WGS 84 semi-major axis) [m].
R_EARTH_EQ_M: Final[float] = 6_378_137.0

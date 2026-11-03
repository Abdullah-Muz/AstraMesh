"""Science opportunities (spec §3.4 task records) from region access windows.

One opportunity is one pass of the formation over one region: the access
windows of all spacecraft for that region that overlap or touch in time are
merged. The opportunity lists every eligible spacecraft with its own window,
so the eligibility of each spacecraft can be traced to its geometry.

Fields the spec leaves to later phases stay ``None``: ``payload_energy_wh``
and ``storage_mb`` (resource model, increment 6b), ``quality_threshold`` and
``cooperative_requirement`` (Phase 2 planning). ``source_flag`` marks the
records as synthetic and geometry-only (no external data yet).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from astramesh.science.access import Site, Window, access_windows, elevation_sine

OBSERVATION_TYPE = "slant_tec_proxy"
REQUIRED_CAPABILITY = "GNSS_TEC"
SOURCE_FLAG = "synthetic_geometry_only"


@dataclass(frozen=True, slots=True)
class Region:
    region_id: str
    priority: int
    site: Site


@dataclass(frozen=True, slots=True)
class Eligibility:
    spacecraft: str
    window: Window
    sunlit_ticks: int


@dataclass(frozen=True, slots=True)
class Opportunity:
    task_id: str
    region: Region
    first: int
    last: int
    eligible: tuple[Eligibility, ...]

    def to_record(self, t_ns: NDArray[np.int64], step_ns: int) -> dict[str, Any]:
        """JSON-ready task record (times as integer ns since the scenario epoch)."""
        return {
            "id": self.task_id,
            "observation_type": OBSERVATION_TYPE,
            "region_or_path_id": self.region.region_id,
            "priority": self.region.priority,
            "required_capability": REQUIRED_CAPABILITY,
            "start_t_ns": int(t_ns[self.first]),
            "end_t_ns": int(t_ns[self.last]),
            "duration_s": (self.last - self.first) * step_ns / 1e9,
            "region_latitude_deg": self.region.site.latitude_deg,
            "region_longitude_deg": self.region.site.longitude_deg,
            "eligible_spacecraft": [
                {
                    "spacecraft": e.spacecraft,
                    "start_t_ns": int(t_ns[e.window.first]),
                    "end_t_ns": int(t_ns[e.window.last]),
                    "peak_t_ns": int(t_ns[e.window.peak]),
                    "peak_elevation_deg": e.window.peak_elevation_deg,
                    "n_ticks": e.window.n_ticks,
                    "sunlit_ticks": e.sunlit_ticks,
                    "truncated_start": e.window.truncated_start,
                    "truncated_end": e.window.truncated_end,
                }
                for e in self.eligible
            ],
            "payload_energy_wh": None,
            "storage_mb": None,
            "quality_threshold": None,
            "cooperative_requirement": None,
            "source_flag": SOURCE_FLAG,
        }


def find_opportunities(
    regions: list[Region],
    spacecraft: list[str],
    r_itrs_m: NDArray[np.float64],
    sunlit: NDArray[np.bool_],
    min_elevation_deg: float,
) -> list[Opportunity]:
    """Opportunities from ITRS positions ``r_itrs_m`` (n_t, n_sc, 3) on the tick grid.

    ``sunlit`` (n_t, n_sc) is recorded per eligible spacecraft for later power
    accounting; it does not affect eligibility (a GNSS TEC receiver does not
    need sunlight).
    """
    n_t, n_sc, _ = r_itrs_m.shape
    if len(spacecraft) != n_sc or sunlit.shape != (n_t, n_sc):
        raise ValueError("spacecraft, positions and sunlit shapes are inconsistent")
    passes: list[tuple[int, int, Region, list[Eligibility]]] = []
    for region in regions:
        sin_el = elevation_sine(r_itrs_m, region.site)  # (n_t, n_sc)
        found: list[Eligibility] = []
        for j, sc in enumerate(spacecraft):
            for w in access_windows(sin_el[:, j], min_elevation_deg):
                lit = int(np.count_nonzero(sunlit[w.first : w.last + 1, j]))
                found.append(Eligibility(sc, w, lit))
        found.sort(key=lambda e: (e.window.first, e.spacecraft))
        for e in found:
            if passes and passes[-1][2] is region and e.window.first <= passes[-1][1] + 1:
                first, last, _, group = passes[-1]
                group.append(e)
                passes[-1] = (first, max(last, e.window.last), region, group)
            else:
                passes.append((e.window.first, e.window.last, region, [e]))
    passes.sort(key=lambda p: (p[0], p[2].region_id))
    return [
        Opportunity(
            task_id=f"TEC_{k + 1:04d}",
            region=region,
            first=first,
            last=last,
            eligible=tuple(sorted(group, key=lambda e: e.spacecraft)),
        )
        for k, (first, last, region, group) in enumerate(passes)
    ]

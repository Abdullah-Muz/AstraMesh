"""AstraMesh: research platform for fault-tolerant decentralized spacecraft autonomy.

Phase 0 provides reproducibility infrastructure (clock, random streams, event
log, configuration schema, run manifests). Phase 1 adds validated truth
dynamics in ``astramesh.dynamics`` (currently D0 two-body only). No autonomy
or science models are implemented yet.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("astramesh")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled tree
    __version__ = "0+unknown"

__all__ = ["__version__"]

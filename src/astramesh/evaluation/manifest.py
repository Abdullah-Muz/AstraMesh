"""Provenance manifest written alongside every run (specification §10.4).

The manifest records everything needed to trace a result back to a commit,
configuration, seed, data version, and software environment. It is the one
run artifact that is *expected* to differ between replays, because it contains
the wall-clock run timestamp; determinism is checked on the other artifacts,
whose hashes the manifest lists.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
_TRACKED_PACKAGES = (
    "astramesh",
    "numpy",
    "pydantic",
    "pyyaml",
    "astropy",
    "astropy-iers-data",
    "pyerfa",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def find_project_root(start: Path) -> Path | None:
    """Nearest ancestor of ``start`` (inclusive) that contains ``pyproject.toml``."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def git_state(root: Path | None) -> dict[str, Any]:
    """Current commit and whether the working tree differs from it.

    Untracked (non-ignored) files count as dirty: new, uncommitted source code
    means the run cannot be reproduced from ``commit`` alone.
    """
    if root is None:
        return {"commit": None, "dirty": None}
    commit = _git(root, "rev-parse", "HEAD")
    status = _git(root, "status", "--porcelain", "--untracked-files=normal")
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def software_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for pkg in _TRACKED_PACKAGES:
        try:
            versions[pkg] = version(pkg)
        except PackageNotFoundError:
            versions[pkg] = None
    return versions


def build_manifest(
    *,
    experiment_id: str,
    scenario_id: str,
    config_hash: str,
    seed: int,
    effective_stream_seeds: dict[str, int],
    algorithm: str,
    artifacts: dict[str, str],
    project_root: Path | None,
    dynamics_model: str = "none",
    science_data_version: str = "none",
    telemetry_data_version: str = "none",
) -> dict[str, Any]:
    lockfile = project_root / "uv.lock" if project_root else None
    git = git_state(project_root)
    return {
        "manifest_version": MANIFEST_VERSION,
        "experiment_id": experiment_id,
        "scenario_id": scenario_id,
        "run_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "config_hash": config_hash,
        "seed": seed,
        "stream_seeds": dict(sorted(effective_stream_seeds.items())),
        "dynamics_model": dynamics_model,
        "science_data_version": science_data_version,
        "telemetry_data_version": telemetry_data_version,
        "algorithm": algorithm,
        "software_lockfile_hash": (
            sha256_file(lockfile) if lockfile is not None and lockfile.is_file() else None
        ),
        "software": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "packages": software_versions(),
        },
        "artifacts": [{"path": p, "sha256": h} for p, h in sorted(artifacts.items())],
    }

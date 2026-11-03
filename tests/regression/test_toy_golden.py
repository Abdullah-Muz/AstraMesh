"""Golden-hash regression for the toy scenario.

The expected digest was produced by the reference implementation and must be
identical on every platform (Windows, WSL2/Linux, CI). If it changes, the
event stream changed: either a deliberate, documented change (update the
digest and add a docs/DECISION_LOG.md entry) or a reproducibility regression.
"""

from __future__ import annotations

from pathlib import Path

from astramesh.evaluation.runner import run_scenario

GOLDEN_EVENTS_SHA256 = "06e3d5ea00c621e7ea6eb8b0ae5e10c1b8a468b819a80b007e1cf02c3e1826bd"
GOLDEN_N_EVENTS = 338


def test_toy_heartbeat_matches_golden_digest(toy_config_path: Path, tmp_path: Path) -> None:
    result = run_scenario(toy_config_path, tmp_path / "run")
    assert result.n_events == GOLDEN_N_EVENTS
    assert result.events_sha256 == GOLDEN_EVENTS_SHA256


GOLDEN_TOY_CONFIG_HASH = "bfe1fa070c21097231ec399a45aa0f9d2fa8529983b237ab3e3759a0584604a3"


def test_toy_config_hash_is_stable(toy_config_path: Path) -> None:
    """Schema refactors must not change the hash of an existing config."""
    from astramesh.core.config import load_scenario

    assert load_scenario(toy_config_path).config_hash() == GOLDEN_TOY_CONFIG_HASH

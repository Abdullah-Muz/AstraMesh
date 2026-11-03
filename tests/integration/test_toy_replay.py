"""End-to-end determinism: config -> run -> artifacts (Phase 0 definition of done)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from astramesh.cli import EXIT_INVALID_CONFIG, EXIT_OK, main
from astramesh.core.config import load_scenario
from astramesh.evaluation.manifest import sha256_file
from astramesh.evaluation.runner import (
    EVENTS_FILE,
    MANIFEST_FILE,
    RESOLVED_CONFIG_FILE,
    SUMMARY_FILE,
    run_config,
    run_scenario,
)

DETERMINISTIC_FILES = (EVENTS_FILE, SUMMARY_FILE, RESOLVED_CONFIG_FILE)
REQUIRED_MANIFEST_KEYS = {
    "experiment_id",
    "run_timestamp_utc",
    "git_commit",
    "config_hash",
    "seed",
    "dynamics_model",
    "science_data_version",
    "telemetry_data_version",
    "algorithm",
    "software_lockfile_hash",
    "artifacts",
}


def test_same_seed_replays_byte_identically(toy_config_path: Path, tmp_path: Path) -> None:
    a = run_scenario(toy_config_path, tmp_path / "a")
    b = run_scenario(toy_config_path, tmp_path / "b")
    assert a.events_sha256 == b.events_sha256
    for name in DETERMINISTIC_FILES:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_different_seed_changes_events(toy_config_path: Path, tmp_path: Path) -> None:
    config = load_scenario(toy_config_path)
    other = config.model_copy(update={"random": config.random.model_copy(update={"seed": 2})})
    a = run_config(config, tmp_path / "a")
    b = run_config(other, tmp_path / "b")
    assert a.events_sha256 != b.events_sha256


def test_manifest_is_complete_and_consistent(toy_config_path: Path, tmp_path: Path) -> None:
    result = run_scenario(toy_config_path, tmp_path / "run")
    manifest = json.loads((tmp_path / "run" / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest.keys() >= REQUIRED_MANIFEST_KEYS
    assert manifest == result.manifest
    assert manifest["config_hash"] == load_scenario(toy_config_path).config_hash()
    assert manifest["software_lockfile_hash"] is not None  # uv.lock found at repo root
    listed = {a["path"]: a["sha256"] for a in manifest["artifacts"]}
    assert set(listed) == set(DETERMINISTIC_FILES)
    for name, digest in listed.items():
        assert sha256_file(tmp_path / "run" / name) == digest


def test_event_stream_is_well_formed(toy_config_path: Path, tmp_path: Path) -> None:
    run_scenario(toy_config_path, tmp_path / "run")
    lines = (tmp_path / "run" / EVENTS_FILE).read_text(encoding="ascii").splitlines()
    events = [json.loads(line) for line in lines]
    assert events[0]["kind"] == "scenario_start"
    assert events[-1]["kind"] == "scenario_end"
    assert [e["seq"] for e in events] == list(range(len(events)))
    times = [e["t_ns"] for e in events]
    assert times == sorted(times)
    summary = json.loads((tmp_path / "run" / SUMMARY_FILE).read_text(encoding="ascii"))
    lost = sum(e["kind"] == "heartbeat_lost" for e in events)
    delivered = sum(e["kind"] == "heartbeat_delivered" for e in events)
    assert summary["deliveries_lost"] == lost
    assert summary["deliveries_attempted"] == lost + delivered


def test_refuses_to_overwrite_existing_run(toy_config_path: Path, tmp_path: Path) -> None:
    run_scenario(toy_config_path, tmp_path / "run")
    with pytest.raises(FileExistsError):
        run_scenario(toy_config_path, tmp_path / "run")
    run_scenario(toy_config_path, tmp_path / "run", overwrite=True)


def test_cli_run_and_validate(toy_config_path: Path, tmp_path: Path) -> None:
    assert main(["validate", str(toy_config_path)]) == EXIT_OK
    assert main(["run", str(toy_config_path), "--out", str(tmp_path / "cli")]) == EXIT_OK
    assert (tmp_path / "cli" / MANIFEST_FILE).is_file()


def test_cli_reports_invalid_config(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("schema_version: 1\n", encoding="utf-8")
    assert main(["validate", str(bad)]) == EXIT_INVALID_CONFIG

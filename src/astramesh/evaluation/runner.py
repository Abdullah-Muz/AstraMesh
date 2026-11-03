"""Config-driven run harness: config -> simulation -> artifacts + manifest.

Each run directory contains:

* ``events.jsonl`` - canonical event log (deterministic)
* ``summary.json`` - scenario bookkeeping counts (deterministic)
* ``config.resolved.json`` - the validated configuration (deterministic)
* ``manifest.json`` - provenance; lists the SHA-256 of the files above
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astramesh.core.config import ScenarioConfig, load_scenario
from astramesh.core.events import EventLog, canonical_json
from astramesh.core.rng import RandomStreams
from astramesh.evaluation.manifest import build_manifest, find_project_root, sha256_file
from astramesh.scenarios import toy_heartbeat

EVENTS_FILE = "events.jsonl"
SUMMARY_FILE = "summary.json"
RESOLVED_CONFIG_FILE = "config.resolved.json"
MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True, slots=True)
class RunResult:
    output_dir: Path
    events_sha256: str
    n_events: int
    manifest: dict[str, Any]


def _write_canonical(path: Path, obj: Any) -> str:
    with path.open("w", encoding="ascii", newline="\n") as fh:
        fh.write(canonical_json(obj) + "\n")
    return sha256_file(path)


def default_experiment_id(config: ScenarioConfig) -> str:
    return f"{config.scenario_id}_seed{config.random.seed:03d}"


def run_scenario(
    config_path: Path,
    output_dir: Path,
    *,
    experiment_id: str | None = None,
    overwrite: bool = False,
) -> RunResult:
    """Load ``config_path``, run it, and write artifacts into ``output_dir``."""
    config = load_scenario(config_path)
    return run_config(
        config,
        output_dir,
        experiment_id=experiment_id,
        overwrite=overwrite,
        project_root=find_project_root(config_path.parent) or find_project_root(Path.cwd()),
    )


def run_config(
    config: ScenarioConfig,
    output_dir: Path,
    *,
    experiment_id: str | None = None,
    overwrite: bool = False,
    project_root: Path | None = None,
) -> RunResult:
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"output directory {output_dir} is not empty (use overwrite)")
    output_dir.mkdir(parents=True, exist_ok=True)

    streams = RandomStreams(config.random.seed, config.random.stream_seeds)
    log = EventLog()
    if config.scenario_type == "toy_heartbeat":
        summary = toy_heartbeat.run_toy_heartbeat(config, streams, log).to_dict()
        algorithm = toy_heartbeat.ALGORITHM_NAME
    else:  # pragma: no cover - guarded by the schema's Literal type
        raise ValueError(f"unsupported scenario_type {config.scenario_type!r}")

    artifacts = {
        EVENTS_FILE: log.write_jsonl(output_dir / EVENTS_FILE),
        SUMMARY_FILE: _write_canonical(output_dir / SUMMARY_FILE, summary),
        RESOLVED_CONFIG_FILE: _write_canonical(
            output_dir / RESOLVED_CONFIG_FILE, config.canonical_dict()
        ),
    }
    manifest = build_manifest(
        experiment_id=experiment_id or default_experiment_id(config),
        scenario_id=config.scenario_id,
        config_hash=config.config_hash(),
        seed=config.random.seed,
        effective_stream_seeds=streams.effective_seeds,
        algorithm=algorithm,
        artifacts=artifacts,
        project_root=project_root,
    )
    with (output_dir / MANIFEST_FILE).open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return RunResult(
        output_dir=output_dir,
        events_sha256=artifacts[EVENTS_FILE],
        n_events=len(log),
        manifest=manifest,
    )

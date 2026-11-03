"""Config-driven run harness: config -> simulation -> artifacts + manifest.

Each run directory contains:

* ``events.jsonl`` - canonical event log (deterministic)
* ``summary.json`` - scenario bookkeeping counts (deterministic)
* ``config.resolved.json`` - the validated configuration (deterministic)
* ``trajectory.csv`` - sampled truth states (formation scenarios; deterministic)
* ``opportunities.json`` - science task records (mission_geometry only; deterministic)
* ``manifest.json`` - provenance; lists the SHA-256 of the files above
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astramesh.core.config import (
    AnyScenarioConfig,
    FormationDynamicsScenario,
    MissionGeometryScenario,
    ToyHeartbeatScenario,
    load_scenario,
)
from astramesh.core.events import EventLog, canonical_json
from astramesh.core.rng import RandomStreams
from astramesh.evaluation.manifest import build_manifest, find_project_root, sha256_file
from astramesh.scenarios import formation_dynamics, mission_geometry, toy_heartbeat

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


AnyScenario = AnyScenarioConfig


def default_experiment_id(config: AnyScenario) -> str:
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
    config: AnyScenario,
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
    extra_artifacts: dict[str, str] = {}
    dynamics_model = "none"
    if isinstance(config, ToyHeartbeatScenario):
        summary = toy_heartbeat.run_toy_heartbeat(config, streams, log).to_dict()
        algorithm = toy_heartbeat.ALGORITHM_NAME
    elif isinstance(config, FormationDynamicsScenario):
        run = formation_dynamics.run_formation_dynamics(config, log)
        summary = run.summary
        algorithm = formation_dynamics.ALGORITHM_NAME
        dynamics_model = run.trajectory.model_id
        traj_path = output_dir / formation_dynamics.TRAJECTORY_FILE
        formation_dynamics.write_trajectory_csv(run, traj_path)
        extra_artifacts[formation_dynamics.TRAJECTORY_FILE] = sha256_file(traj_path)
    elif isinstance(config, MissionGeometryScenario):
        mg = mission_geometry.run_mission_geometry(config, log)
        summary = mg.summary
        algorithm = mission_geometry.ALGORITHM_NAME
        dynamics_model = mg.formation.trajectory.model_id
        traj_path = output_dir / formation_dynamics.TRAJECTORY_FILE
        formation_dynamics.write_trajectory_csv(mg.formation, traj_path)
        extra_artifacts[formation_dynamics.TRAJECTORY_FILE] = sha256_file(traj_path)
        extra_artifacts[mission_geometry.OPPORTUNITIES_FILE] = _write_canonical(
            output_dir / mission_geometry.OPPORTUNITIES_FILE, mg.records
        )
    else:  # pragma: no cover - guarded by the schema's discriminated union
        raise ValueError(f"unsupported scenario_type {config.scenario_type!r}")

    artifacts = {
        **extra_artifacts,
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
        dynamics_model=dynamics_model,
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

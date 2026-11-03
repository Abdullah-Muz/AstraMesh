"""Scenario configuration schema and loader.

Configurations are YAML files validated against the models below. Unknown keys
are rejected, so a typo cannot silently fall back to a default. Field names
carry their unit as a suffix (``_s``, ``_m``, ``_deg``, ...) per
``docs/CONVENTIONS.md``.

The ``config_hash`` is the SHA-256 of the *validated* configuration in
canonical JSON form, so it is unaffected by YAML comments, key order, or
formatting, but changes whenever any effective value changes.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from astramesh.core.clock import ClockSpec, require_utc, seconds_to_ns
from astramesh.core.events import canonical_json
from astramesh.core.rng import StreamName

SCHEMA_VERSION = 1

Seed = Annotated[StrictInt, Field(ge=0, le=2**63 - 1)]
PositiveSeconds = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TimeConfig(_Model):
    """Simulation time grid. See ``docs/CONVENTIONS.md`` §Time."""

    epoch_utc: datetime = Field(
        description="Scenario epoch, ISO 8601 UTC, e.g. 2025-06-01T00:00:00Z"
    )
    duration_s: PositiveSeconds = Field(description="Scenario duration [s]")
    time_step_s: PositiveSeconds = Field(description="Fixed simulation time step [s]")

    @field_validator("epoch_utc")
    @classmethod
    def _epoch_is_utc(cls, v: datetime) -> datetime:
        return require_utc(v, name="epoch_utc")

    @model_validator(mode="after")
    def _grid_is_consistent(self) -> TimeConfig:
        self.clock_spec()  # raises ValueError with a precise message if inconsistent
        return self

    def clock_spec(self) -> ClockSpec:
        return ClockSpec.from_seconds(self.epoch_utc, self.time_step_s, self.duration_s)


class RandomConfig(_Model):
    """Random-stream seeds. See ``astramesh.core.rng``."""

    seed: Seed = Field(description="Root seed for every stream")
    stream_seeds: dict[StreamName, Seed] = Field(
        default_factory=dict, description="Optional per-stream seed overrides"
    )


class ToyHeartbeatConfig(_Model):
    """Phase 0 infrastructure check: NOT a communications or mission model."""

    n_nodes: int = Field(ge=2, le=64)
    heartbeat_interval_s: PositiveSeconds
    packet_loss_probability: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class ScenarioConfig(_Model):
    """Top-level scenario configuration."""

    schema_version: Literal[1]
    scenario_id: Identifier
    description: str = Field(min_length=1)
    scenario_type: Literal["toy_heartbeat"]
    time: TimeConfig
    random: RandomConfig
    toy_heartbeat: ToyHeartbeatConfig

    @model_validator(mode="after")
    def _heartbeat_on_grid(self) -> ScenarioConfig:
        step_ns = self.time.clock_spec().step_ns
        interval_ns = seconds_to_ns(
            self.toy_heartbeat.heartbeat_interval_s, name="heartbeat_interval_s"
        )
        if interval_ns % step_ns != 0:
            raise ValueError(
                "toy_heartbeat.heartbeat_interval_s must be an integer multiple of time.time_step_s"
            )
        return self

    def canonical_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def config_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.canonical_dict()).encode("ascii")).hexdigest()


class ConfigError(ValueError):
    """Raised when a configuration file cannot be read or fails validation."""


def load_scenario(path: Path) -> ScenarioConfig:
    """Load and validate a scenario configuration file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"config {path} must contain a YAML mapping at the top level")
    return parse_scenario(raw, source=str(path))


def parse_scenario(raw: dict[str, Any], *, source: str = "<dict>") -> ScenarioConfig:
    from pydantic import ValidationError

    try:
        return ScenarioConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid scenario config {source}:\n{exc}") from exc


def scenario_json_schema() -> dict[str, Any]:
    """JSON Schema for :class:`ScenarioConfig` (for editors and documentation)."""
    return ScenarioConfig.model_json_schema()

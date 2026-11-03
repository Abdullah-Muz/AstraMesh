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
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

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


class _ScenarioBase(_Model):
    """Fields shared by every scenario type."""

    schema_version: Literal[1]
    scenario_id: Identifier
    description: str = Field(min_length=1)
    time: TimeConfig
    random: RandomConfig

    def canonical_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def config_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.canonical_dict()).encode("ascii")).hexdigest()

    def _require_on_grid(self, value_s: float, name: str) -> None:
        step_ns = self.time.clock_spec().step_ns
        if seconds_to_ns(value_s, name=name) % step_ns != 0:
            raise ValueError(f"{name} must be an integer multiple of time.time_step_s")


class ToyHeartbeatScenario(_ScenarioBase):
    """Phase 0 infrastructure scenario."""

    scenario_type: Literal["toy_heartbeat"]
    toy_heartbeat: ToyHeartbeatConfig

    @model_validator(mode="after")
    def _heartbeat_on_grid(self) -> ToyHeartbeatScenario:
        self._require_on_grid(
            self.toy_heartbeat.heartbeat_interval_s, "toy_heartbeat.heartbeat_interval_s"
        )
        return self


Degrees360 = Annotated[float, Field(ge=0.0, lt=360.0, allow_inf_nan=False)]


class DynamicsConfig(_Model):
    """Truth gravity model (constants come from ``astramesh.dynamics.constants``)."""

    model: Literal["two_body", "j2"] = Field(
        description="two_body = D0 point mass; j2 = D1 point mass + J2 about the epoch pole"
    )


class ReferenceOrbitConfig(_Model):
    """Leader's orbit as MEAN elements in Earth's equatorial frame (DL-026)."""

    mean_altitude_km: float = Field(
        gt=150.0, le=2000.0, allow_inf_nan=False,
        description="Mean semi-major axis minus the WGS 84 equatorial radius [km]",
    )  # fmt: skip
    mean_inclination_deg: float = Field(ge=0.0, le=180.0, allow_inf_nan=False)
    raan_deg: Degrees360 = Field(
        description="Node in the equatorial frame; origin = GCRS x projected on the equator"
    )
    start_argument_of_latitude_deg: Degrees360


class FormationConfig(_Model):
    """Along-track formation; spacecraft 0 leads, the others trail."""

    n_spacecraft: int = Field(ge=1, le=16)
    along_track_spacing_km: float = Field(gt=0.0, le=500.0, allow_inf_nan=False)


class OutputConfig(_Model):
    trajectory_sample_interval_s: PositiveSeconds = Field(
        description="Interval between recorded states (multiple of time.time_step_s)"
    )


class FormationDynamicsScenario(_ScenarioBase):
    """Phase 1 truth-dynamics scenario: formation initialization and propagation."""

    scenario_type: Literal["formation_dynamics"]
    dynamics: DynamicsConfig
    reference_orbit: ReferenceOrbitConfig
    formation: FormationConfig
    output: OutputConfig

    @model_validator(mode="after")
    def _sampling_on_grid(self) -> FormationDynamicsScenario:
        self._require_on_grid(
            self.output.trajectory_sample_interval_s, "output.trajectory_sample_interval_s"
        )
        sample_ns = seconds_to_ns(self.output.trajectory_sample_interval_s)
        if self.time.clock_spec().duration_ns % sample_ns != 0:
            raise ValueError(
                "time.duration_s must be an integer multiple of "
                "output.trajectory_sample_interval_s (so the final state is recorded)"
            )
        return self


ScenarioConfig = Annotated[
    ToyHeartbeatScenario | FormationDynamicsScenario, Field(discriminator="scenario_type")
]
_ADAPTER: TypeAdapter[ToyHeartbeatScenario | FormationDynamicsScenario] = TypeAdapter(
    ScenarioConfig
)


class ConfigError(ValueError):
    """Raised when a configuration file cannot be read or fails validation."""


def load_scenario(path: Path) -> ToyHeartbeatScenario | FormationDynamicsScenario:
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


def parse_scenario(
    raw: dict[str, Any], *, source: str = "<dict>"
) -> ToyHeartbeatScenario | FormationDynamicsScenario:
    try:
        return _ADAPTER.validate_python(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid scenario config {source}:\n{exc}") from exc


def scenario_json_schema() -> dict[str, Any]:
    """JSON Schema for all scenario types (for editors and documentation)."""
    schema = _ADAPTER.json_schema()
    schema["title"] = "ScenarioConfig"
    return schema

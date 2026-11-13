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
        d = self.model_dump(mode="json")
        # Optional blocks added after configs were pinned are omitted when absent, so
        # their introduction does not change existing configuration hashes (DL-066).
        ag = d.get("agents")
        if isinstance(ag, dict) and ag.get("health") is None:
            ag.pop("health", None)
        if isinstance(ag, dict) and ag.get("handover", 0) is None:
            ag.pop("handover")  # DL-094
        env = d.get("environment")
        if isinstance(env, dict) and env.get("replay") is None:
            env.pop("replay", None)  # DL-069
        dyn = d.get("dynamics")
        if isinstance(dyn, dict) and dyn.get("drag") is None:
            dyn.pop("drag", None)  # DL-081
        if d.get("control", 0) is None:
            d.pop("control")  # DL-087
        for f in d.get("faults") or ():  # DL-090: forecast_delay only
            if isinstance(f, dict) and f.get("delay_s", 0) is None:
                f.pop("delay_s")
        rp = env.get("replay") if isinstance(env, dict) else None
        if isinstance(rp, dict):  # DL-090 blocks omitted when absent
            for key in ("access", "forecast_max_age_s"):
                if rp.get(key, 0) is None:
                    rp.pop(key)
        drag = dyn.get("drag") if isinstance(dyn, dict) else None
        if isinstance(drag, dict):  # DL-084 fields omitted at their defaults
            if drag.get("density") == "ussa76":
                drag.pop("density", None)
            if drag.get("density_scale_ratio") == 1.0:
                drag.pop("density_scale_ratio", None)
        return d

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


class DragConfig(_Model):
    """Nominal drag (D1, DL-080): USSA 1976 density, co-rotating atmosphere."""

    ballistic_m2pkg: list[Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]] = Field(
        min_length=1,
        description="B = C_D A / m [m^2/kg]: one value for all spacecraft, or one per spacecraft",
    )
    density: Literal["ussa76", "msis2"] = Field(
        default="ussa76",
        description="ussa76 = D1 mid-activity table; msis2 = D2 NRLMSIS 2.0 with DS-10 drivers "
        "(needs the atmosphere dependency group; academic, non-commercial licence, DL-084)",
    )
    density_scale_ratio: float = Field(
        default=1.0, gt=0.0, le=10.0, allow_inf_nan=False,
        description="multiplies the msis2 density (uncertainty sensitivity, DL-084)",
    )  # fmt: skip

    @model_validator(mode="after")
    def _scale_only_for_msis(self) -> DragConfig:
        if self.density == "ussa76" and self.density_scale_ratio != 1.0:
            raise ValueError("dynamics.drag.density_scale_ratio applies to density: msis2 only")
        return self


#: Largest step for runs with drag: RK4's own semi-major-axis drift is 0.003 m/day at
#: 10 s but 23 m/day at 60 s, against ~15 m/day from drag (NUMERICAL_MISSION_DESIGN §B.9).
MAX_DRAG_STEP_S = 10.0


class DynamicsConfig(_Model):
    """Truth force model (constants come from ``astramesh.dynamics.constants``)."""

    model: Literal["two_body", "j2"] = Field(
        description="two_body = D0 point mass; j2 = D1 point mass + J2 about the epoch pole"
    )
    drag: DragConfig | None = Field(default=None, description="optional nominal drag (DL-080)")


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
    along_track_spacing_km: float = Field(
        gt=0.0, le=6000.0, allow_inf_nan=False,
        description="Along-track spacing [km]; the formation must span under half an orbit "
        "(checked at initialization). Cap 6000 km (DL-106; was 500 km)",
    )  # fmt: skip


class OutputConfig(_Model):
    trajectory_sample_interval_s: PositiveSeconds = Field(
        description="Interval between recorded states (multiple of time.time_step_s)"
    )


class FormationScenarioBase(_ScenarioBase):
    """Fields shared by the formation scenario types."""

    dynamics: DynamicsConfig
    reference_orbit: ReferenceOrbitConfig
    formation: FormationConfig
    output: OutputConfig

    @model_validator(mode="after")
    def _drag_settings(self) -> FormationScenarioBase:
        drag = self.dynamics.drag
        if drag is None:
            return self
        n_b, n_sc = len(drag.ballistic_m2pkg), self.formation.n_spacecraft
        if n_b not in (1, n_sc):
            raise ValueError(f"dynamics.drag needs 1 or {n_sc} ballistic coefficients, got {n_b}")
        if self.time.time_step_s > MAX_DRAG_STEP_S:
            raise ValueError(
                f"runs with drag need time.time_step_s <= {MAX_DRAG_STEP_S:g} s (§B.9)"
            )
        return self

    @model_validator(mode="after")
    def _sampling_on_grid(self) -> FormationScenarioBase:
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


class FormationDynamicsScenario(FormationScenarioBase):
    """Phase 1 truth-dynamics scenario: formation initialization and propagation."""

    scenario_type: Literal["formation_dynamics"]


class RegionConfig(_Model):
    """A synthetic science region, represented by its centre on the WGS 84 ellipsoid."""

    region_id: Identifier
    latitude_deg: float = Field(ge=-90.0, le=90.0, allow_inf_nan=False, description="Geodetic")
    longitude_deg: float = Field(ge=-180.0, le=180.0, allow_inf_nan=False)
    priority: int = Field(ge=1, le=5, description="Fixed task value w_j (spec §3.4)")


class ScienceConfig(_Model):
    """Geometry-only science opportunities (spec §3.4; a scheduling abstraction)."""

    min_elevation_deg: float = Field(
        ge=0.0, lt=90.0, allow_inf_nan=False,
        description="Minimum spacecraft elevation above the region centre's horizon [deg]",
    )  # fmt: skip
    regions: list[RegionConfig] = Field(min_length=1, max_length=256)

    @field_validator("regions")
    @classmethod
    def _unique_ids(cls, v: list[RegionConfig]) -> list[RegionConfig]:
        ids = [r.region_id for r in v]
        if len(set(ids)) != len(ids):
            raise ValueError("region_id values must be unique")
        return v


Fraction = Annotated[float, Field(gt=0.0, le=1.0, allow_inf_nan=False)]
PositiveFloat = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


class SpacecraftConfig(_Model):
    """Resource model of every spacecraft (spec §3.3; values PROVISIONAL, DL-035/036)."""

    mass_kg: PositiveFloat = Field(description="Initial (wet) mass [kg]")
    solar_generation_w: NonNegativeFloat = Field(description="Generation while sunlit [W]")
    bus_power_w: NonNegativeFloat = Field(description="Continuous essential load [W]")
    battery_capacity_wh: PositiveFloat = Field(description="Usable battery energy [Wh]")
    battery_initial_fraction: Fraction = Field(description="Initial state of charge")
    charge_efficiency_fraction: Fraction = Field(description="Stored / delivered when charging")
    payload_power_w: NonNegativeFloat = Field(description="Science payload load while on [W]")
    payload_data_rate_kbps: NonNegativeFloat = Field(description="Science data rate [kbit/s]")
    storage_capacity_mb: PositiveFloat = Field(description="Data storage [MB = 1e6 bytes]")
    thrust_mn: PositiveFloat = Field(description="Maximum thrust [mN]")
    thruster_power_w: NonNegativeFloat = Field(description="Load while thrusting [W]")
    specific_impulse_s: PositiveFloat = Field(description="Propulsion specific impulse [s]")
    delta_v_budget_mps: NonNegativeFloat = Field(description="Total delta-v budget [m/s]")


class FormationKeepingConfig(_Model):
    """Along-track formation keeping against differential drag (DL-087).

    Leader-follower chain: spacecraft k keeps ``formation.along_track_spacing_km`` behind
    spacecraft k-1 with tangential burns of the ``spacecraft`` thruster, decided once per
    nominal orbit. Thrust, specific impulse, mass and budget come from ``spacecraft``.
    """

    deadband_km: PositiveFloat = Field(default=0.5, description="No burn while |error| <= this")
    time_constant_s: PositiveFloat = Field(
        default=86_400.0, description="Target drift rate = -error / time constant [s]"
    )
    max_drift_rate_mps: PositiveFloat = Field(
        default=0.02, description="Limit on the target along-track drift rate [m/s]"
    )
    navigation_sigma_m: NonNegativeFloat = Field(
        default=10.0, description="GNSS position error per axis, per spacecraft (modelled) [m]"
    )
    estimator_jerk_psd_m2ps5: PositiveFloat = Field(
        default=1e-18,
        description="Spacing filter process noise: white jerk spectral density [m^2/s^5]",
    )


class ControlConfig(_Model):
    """Onboard control running inside the truth propagation (DL-087 option A)."""

    formation_keeping: FormationKeepingConfig


class MissionScenarioBase(FormationScenarioBase):
    """Formation + science regions + spacecraft resources (shared by mission scenarios)."""

    science: ScienceConfig
    spacecraft: SpacecraftConfig
    control: ControlConfig | None = Field(
        default=None, description="optional formation keeping (DL-087); omitted when absent"
    )

    @model_validator(mode="after")
    def _control_needs_followers(self) -> MissionScenarioBase:
        if self.control is not None and self.formation.n_spacecraft < 2:
            raise ValueError("control.formation_keeping needs at least two spacecraft")
        return self


class MissionGeometryScenario(MissionScenarioBase):
    """Phase 1 mission geometry: formation dynamics + illumination + science opportunities
    + finite resource accounting."""

    scenario_type: Literal["mission_geometry"]


class NetworkConfig(_Model):
    """Crosslink model (spec §5.3; values PROVISIONAL)."""

    crosslink_range_km: PositiveFloat = Field(description="Synthetic maximum link range [km]")
    min_ray_altitude_km: NonNegativeFloat = Field(
        description="Line of sight must clear R_eq + this altitude [km]"
    )
    delay_s: NonNegativeFloat = Field(description="Application-level delivery delay [s]")
    loss_probability: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    duplicate_probability: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


Probability = Annotated[float, Field(gt=0.0, lt=1.0, allow_inf_nan=False)]
PositiveFloat_ = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]


class BayesHealthConfig(_Model):
    """H-B silence model (DL-066); fixed before any scenario is run."""

    mtbf_s: PositiveSeconds = Field(
        default=30 * 86400.0, description="Prior mean time to unavailability [s]"
    )
    loss_prior_a: PositiveFloat_ = Field(default=1.0, description="Beta prior on message loss")
    loss_prior_b: PositiveFloat_ = Field(default=30.0, description="Beta prior on message loss")
    suspect_probability: Probability = 0.5
    lost_probability: Probability = 0.95

    @model_validator(mode="after")
    def _order(self) -> BayesHealthConfig:
        if not self.suspect_probability < self.lost_probability:
            raise ValueError("bayes.suspect_probability must be < bayes.lost_probability")
        return self


class PayloadCheckConfig(_Model):
    """H-C onboard payload detector, adapted from the OPS-SAT benchmark (DL-066)."""

    interval_s: PositiveSeconds = Field(default=300.0, description="Detector check period [s]")
    sensor_file: str = Field(
        default="configs/data/opssat_score_sensor.json",
        description="Empirical score distributions (repo-relative)",
    )
    sensor_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sensor_split: Literal["time", "official"] = "time"
    mtbf_s: PositiveSeconds = Field(
        default=30 * 86400.0, description="Prior mean time to payload degradation [s]"
    )
    repair_s: PositiveSeconds = Field(
        default=86400.0, description="Prior mean degradation duration [s]"
    )
    degraded_probability: Probability = 0.9
    clear_probability: Probability = 0.1
    clip_probability: Annotated[float, Field(gt=0.0, lt=0.5)] = 0.01
    nominal_contamination_fraction: Annotated[float, Field(ge=0.0, lt=1.0)] = Field(
        default=0.0,
        description="Domain-shift stress: fraction of healthy checks drawn from anomalous scores",
    )

    @model_validator(mode="after")
    def _order(self) -> PayloadCheckConfig:
        if not self.clear_probability < self.degraded_probability:
            raise ValueError(
                "payload_check.clear_probability must be < payload_check.degraded_probability"
            )
        return self


class HealthModelConfig(_Model):
    """Health estimation model (spec §7.2): H-A timeout, H-B bayes, H-C bayes + detector."""

    model: Literal["timeout", "bayes"]
    bayes: BayesHealthConfig = BayesHealthConfig()
    payload_check: PayloadCheckConfig | None = None


class HandoverConfig(_Model):
    """Forecast-handover candidate (DL-078, DL-094): announce [now, now + lead] while the
    own radiation ratio >= ``window_threshold_ratio`` or while protected, and release own
    tasks starting inside it. Absent = the reactive baseline."""

    window_threshold_ratio: PositiveFloat = Field(description="Own radiation ratio (option A)")
    lead_s: PositiveSeconds = Field(description="Window length [s]")
    share_window: bool = Field(
        default=True, description="Announce the window in status (false: no-sharing ablation)"
    )


class AgentsConfig(_Model):
    """Agent message timing and sensor noise (values PROVISIONAL)."""

    status_interval_s: PositiveSeconds = Field(description="Status report period (spec: 30 s)")
    status_lifetime_s: PositiveSeconds = Field(description="Status message expiry after creation")
    nav_fix_interval_s: PositiveSeconds = Field(description="Own navigation-fix period")
    nav_position_sigma_m: NonNegativeFloat = Field(description="1-sigma per axis [m]")
    nav_velocity_sigma_mps: NonNegativeFloat = Field(description="1-sigma per axis [m/s]")
    health_suspect_s: PositiveSeconds = Field(
        default=90.0, description="Silence before SUSPECTED_UNAVAILABLE [s] (DL-052)"
    )
    health_lost_s: PositiveSeconds = Field(
        default=300.0, description="Silence before COMMUNICATION_LOST [s] (DL-052)"
    )
    health_recover_messages: int = Field(
        default=2, ge=1, le=100, description="Status messages after RECOVERING before HEALTHY"
    )
    health: HealthModelConfig | None = Field(
        default=None, description="Absent: H-A timeout model (DL-052); see DL-066"
    )
    handover: HandoverConfig | None = Field(
        default=None, description="Forecast-handover candidate (DL-094); absent = baseline"
    )

    @model_validator(mode="after")
    def _health_order(self) -> AgentsConfig:
        if not self.health_suspect_s < self.health_lost_s:
            raise ValueError("agents.health_suspect_s must be < agents.health_lost_s")
        return self


class AgentNetworkScenario(FormationScenarioBase):
    """Phase 2 increment 1: isolated agents exchanging status over the crosslink network."""

    scenario_type: Literal["agent_network"]
    network: NetworkConfig
    agents: AgentsConfig

    @model_validator(mode="after")
    def _agent_timing_on_grid(self) -> AgentNetworkScenario:
        self._require_on_grid(self.agents.nav_fix_interval_s, "agents.nav_fix_interval_s")
        self._require_on_grid(self.agents.status_interval_s, "agents.status_interval_s")
        h = self.agents.health
        if h is not None and h.payload_check is not None:
            self._require_on_grid(h.payload_check.interval_s, "payload_check.interval_s")
        seconds_to_ns(self.network.delay_s, name="network.delay_s")
        seconds_to_ns(self.agents.status_lifetime_s, name="agents.status_lifetime_s")
        return self


class OperationsConfig(_Model):
    """Nominal science operations (Phase 2 increment 2; DL-041, DL-043)."""

    algorithm: Literal[
        "static_b0", "centralized_b1", "auction_b2", "cbba_b3", "rule_b4", "cbba_b3_timeout"
    ] = Field(
        description=(
            "static_b0 = B0 static greedy; centralized_b1 = B1 MILP reference (privileged); "
            "auction_b2 = B2 one-shot auction; cbba_b3 = B3 CBBA (decentralized); "
            "rule_b4 = B4 rule-based redistribution; cbba_b3_timeout = B3 + timeout handling"
        )
    )
    min_observation_s: PositiveSeconds = Field(
        description="Continuous observation needed to complete a task [s] (DL-041: 60 s)"
    )
    battery_reserve_fraction: float = Field(
        ge=0.0, lt=1.0, allow_inf_nan=False,
        description="Agents do not start an observation below this state of charge",
    )  # fmt: skip


class FaultConfig(_Model):
    """One injected fault (spec §5.4, DL-050). Ground truth; agents never see it."""

    fault_id: Identifier
    type: Literal[
        "unavailable",
        "comms_outage",
        "partition",
        "payload_degraded",
        "power_degraded",
        "critical_fault",
        "forecast_outage",
        "forecast_delay",
    ]
    spacecraft: list[Identifier] = Field(
        default_factory=list, description="Affected spacecraft (not used for partition)"
    )
    groups: list[list[Identifier]] = Field(
        default_factory=list, description="Partition groups; unlisted spacecraft form one more"
    )
    start_s: NonNegativeFloat = Field(description="Fault start [s since epoch]")
    end_s: PositiveFloat | None = Field(default=None, description="Fault end [s]; null = permanent")
    severity_fraction: float = Field(
        default=1.0, ge=0.0, le=1.0, allow_inf_nan=False,
        description="power_degraded: remaining generation fraction (0 = none)",
    )  # fmt: skip
    cause: str = Field(min_length=1, description="Cause / model (free text)")
    observability: Literal["effects_only", "self_reported", "ground_confirmed"] = Field(
        description="How agents can learn of it (DL-050); effects_only in increment 1"
    )
    consequences: str = Field(min_length=1, description="Expected consequences (free text)")
    ground_confirmation_s: NonNegativeFloat | None = Field(
        default=None, description="Ground confirms the failure to all agents at this time [s]"
    )
    delay_s: PositiveFloat | None = Field(
        default=None, description="forecast_delay: extra delivery latency [s] (DL-090)"
    )

    @model_validator(mode="after")
    def _consistent(self) -> FaultConfig:
        if self.end_s is not None and self.end_s <= self.start_s:
            raise ValueError(f"{self.fault_id}: end_s must be after start_s")
        if self.type == "partition":
            members = [m for g in self.groups for m in g]
            if len(self.groups) < 1 or len(members) != len(set(members)):
                raise ValueError(f"{self.fault_id}: partition needs disjoint groups")
            if self.spacecraft:
                raise ValueError(f"{self.fault_id}: use groups, not spacecraft, for partition")
        else:
            if not self.spacecraft or self.groups:
                raise ValueError(f"{self.fault_id}: needs spacecraft and no groups")
        confirmed = self.observability == "ground_confirmed"
        if confirmed != (self.ground_confirmation_s is not None):
            raise ValueError(
                f"{self.fault_id}: ground_confirmation_s is required for, and only for, "
                "observability ground_confirmed"
            )
        if self.ground_confirmation_s is not None and self.ground_confirmation_s < self.start_s:
            raise ValueError(f"{self.fault_id}: ground_confirmation_s before start_s")
        if self.type != "power_degraded" and self.severity_fraction != 1.0:
            raise ValueError(f"{self.fault_id}: severity_fraction applies to power_degraded only")
        if (self.type == "forecast_delay") != (self.delay_s is not None):
            raise ValueError(f"{self.fault_id}: delay_s is required for, and only for, "
                             "forecast_delay")  # fmt: skip
        return self

    @property
    def recoverable(self) -> bool:
        return self.end_s is not None


class ForecastConfig(_Model):
    """A scheduled interval of predicted exposure (synthetic, Phase 3; DL-054)."""

    forecast_id: Identifier
    dimension: Literal["radiation", "navcomms", "orbital"] = Field(
        default="radiation", description="Risk dimension (spec §6.3); never averaged"
    )
    spacecraft: list[Identifier] = Field(default_factory=list, description="Empty = all")
    start_s: NonNegativeFloat
    end_s: PositiveFloat
    exposure_ratio: float | None = Field(
        ge=0.0, allow_inf_nan=False,
        description="Predicted risk / modelled tolerance of that subsystem; null = invalid",
    )  # fmt: skip

    @model_validator(mode="after")
    def _ordered(self) -> ForecastConfig:
        if self.end_s <= self.start_s:
            raise ValueError(f"{self.forecast_id}: end_s must be after start_s")
        return self


class PositionAccessConfig(_Model):
    """Position-based proton access (DL-090 option A, values DL-091): flux reaches a
    spacecraft only at or above the invariant-latitude cutoff for 10 MeV protons,
    quiet - slope * max(-SYM-H, 0), the shift capped at ``max_shift_deg``. A model."""

    quiet_cutoff_deg: float = Field(
        default=65.2, gt=0.0, le=90.0, allow_inf_nan=False,
        description="Cutoff invariant latitude at SYM-H >= 0 (R08)",
    )  # fmt: skip
    storm_slope_deg_per_nt: float = Field(
        default=1.0 / 19.11, ge=0.0, allow_inf_nan=False,
        description="Equatorward shift per nT of negative SYM-H (R08: Dst / 19.11)",
    )  # fmt: skip
    max_shift_deg: float | None = Field(
        default=15.0, ge=0.0, allow_inf_nan=False,
        description="Cap on the shift (R08's extrapolation to Dst ~ -300 nT); null = none",
    )  # fmt: skip
    horizon_s: PositiveSeconds = Field(
        default=3600.0, description="Look-ahead along the own track for the risk input"
    )


class StormReplayConfig(_Model):
    """Real-data storm replay (S11, DL-069): every spacecraft's radiation, orbital and
    nav/comms inputs come from the pinned May 2024 series instead of scheduled intervals.
    The tolerances are synthetic modelled limits (ratio 1.0 = at the limit)."""

    series_file: str = Field(
        default="configs/data/s11_storm_series.json", description="Repo-relative series file"
    )
    series_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    forecast: Literal["P-A", "P-B/q50", "P-C/q50", "P-B/q90", "P-C/q90"] = Field(
        description="Radiation input: P-A latest measurement, P-B/P-C 1 h forecasts"
    )
    radiation_tolerance_pfu: (
        Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
        | list[Annotated[float, Field(gt=0.0, allow_inf_nan=False)]]
    ) = Field(
        default=100.0,
        description="GOES >= 10 MeV flux at the payload's modelled tolerance (GEO upper "
        "bound); one value, or one per spacecraft (DL-090)",
    )
    orbital_tolerance_nt: float = Field(
        default=250.0, gt=0.0, allow_inf_nan=False,
        description="-SYM-H at which the orbital-disturbance ratio is 1.0",
    )  # fmt: skip
    navcomms_tolerance_nt: float = Field(
        default=2000.0, gt=0.0, allow_inf_nan=False,
        description="AE at which the nav/comms ratio is 1.0",
    )  # fmt: skip
    access: PositionAccessConfig | None = Field(
        default=None, description="Position-based access (DL-090); absent = GEO proxy for all"
    )
    forecast_max_age_s: PositiveSeconds | None = Field(
        default=None,
        description="Agents treat inputs issued longer ago than this as invalid (DL-090)",
    )

    def tolerance_pfu(self, index: int) -> float:
        tol = self.radiation_tolerance_pfu
        return tol[index] if isinstance(tol, list) else tol


class EnvironmentConfig(_Model):
    """Environmental hazard inputs: synthetic scheduled forecasts, or a real-data replay."""

    background_exposure_ratio: float = Field(
        ge=0.0, allow_inf_nan=False, description="Exposure ratio outside scheduled intervals"
    )
    forecasts: list[ForecastConfig] = Field(default_factory=list)
    replay: StormReplayConfig | None = Field(
        default=None, description="Real-data storm replay (S11); excludes scheduled forecasts"
    )

    @model_validator(mode="after")
    def _one_source(self) -> EnvironmentConfig:
        if self.replay is not None and self.forecasts:
            raise ValueError("environment.replay and environment.forecasts are exclusive")
        return self


class SupervisorConfig(_Model):
    """Protection supervisor guards (DL-054; PROVISIONAL)."""

    safe_battery_fraction: float = Field(default=0.10, ge=0.0, lt=1.0, allow_inf_nan=False)
    safe_exit_battery_fraction: float = Field(default=0.50, gt=0.0, le=1.0, allow_inf_nan=False)
    safe_exit_dwell_s: NonNegativeFloat = 600.0
    protect_exposure_ratio: PositiveFloat = 1.0
    release_exposure_ratio: PositiveFloat = 0.8
    release_dwell_s: NonNegativeFloat = 1800.0
    watch_enter_ratio: PositiveFloat = 0.6
    watch_release_ratio: PositiveFloat = 0.5
    watch_release_dwell_s: NonNegativeFloat = 1800.0
    invalid_to_watch_s: NonNegativeFloat = 600.0
    recovery_min_dwell_s: NonNegativeFloat = 300.0
    recovery_nav_max_age_s: PositiveSeconds = 60.0
    recovery_peer_heard_s: PositiveSeconds = 90.0
    watch_status_interval_s: PositiveSeconds = Field(
        default=10.0, description="Status period in STORM_WATCH (on the step grid; DL-056)"
    )

    @model_validator(mode="after")
    def _ordered(self) -> SupervisorConfig:
        if not self.safe_battery_fraction < self.safe_exit_battery_fraction:
            raise ValueError("safe_battery_fraction must be < safe_exit_battery_fraction")
        if not self.release_exposure_ratio < self.protect_exposure_ratio:
            raise ValueError("release_exposure_ratio must be < protect_exposure_ratio")
        if not self.watch_release_ratio < self.watch_enter_ratio <= self.protect_exposure_ratio:
            raise ValueError("need watch_release_ratio < watch_enter_ratio <= protect")
        return self


class NominalOperationsScenario(MissionScenarioBase):
    """Phase 2 S00: isolated agents execute a science plan over the crosslink network."""

    scenario_type: Literal["nominal_operations"]
    network: NetworkConfig
    agents: AgentsConfig
    operations: OperationsConfig
    faults: list[FaultConfig] = Field(default_factory=list, description="Injected faults (S01+)")
    environment: EnvironmentConfig | None = Field(
        default=None, description="Synthetic hazard forecasts; absent = no hazard model"
    )
    supervisor: SupervisorConfig = Field(default_factory=SupervisorConfig)

    @model_validator(mode="after")
    def _ops_timing_on_grid(self) -> NominalOperationsScenario:
        ids = {f"sc{k:02d}" for k in range(self.formation.n_spacecraft)}
        seen: set[str] = set()
        for f in self.faults:
            if f.fault_id in seen:
                raise ValueError(f"duplicate fault_id {f.fault_id!r}")
            seen.add(f.fault_id)
            named = set(f.spacecraft) | {m for g in f.groups for m in g}
            if named - ids:
                raise ValueError(f"{f.fault_id}: unknown spacecraft {sorted(named - ids)}")
            self._require_on_grid(f.start_s, f"faults[{f.fault_id}].start_s")
            if f.end_s is not None:
                self._require_on_grid(f.end_s, f"faults[{f.fault_id}].end_s")
            if f.ground_confirmation_s is not None:
                self._require_on_grid(
                    f.ground_confirmation_s, f"faults[{f.fault_id}].ground_confirmation_s"
                )
        self._require_on_grid(
            self.supervisor.watch_status_interval_s, "supervisor.watch_status_interval_s"
        )
        rp = self.environment.replay if self.environment is not None else None
        tol = rp.radiation_tolerance_pfu if rp is not None else None
        if isinstance(tol, list) and len(tol) != self.formation.n_spacecraft:
            raise ValueError("radiation_tolerance_pfu needs one value per spacecraft")
        for f in self.faults:  # only replay inputs carry issue times (age rule, DL-090)
            if f.type in ("forecast_outage", "forecast_delay") and rp is None:
                raise ValueError(f"{f.fault_id}: {f.type} needs environment.replay")
        if self.environment is not None:
            for fc in self.environment.forecasts:
                if set(fc.spacecraft) - ids:
                    raise ValueError(f"{fc.forecast_id}: unknown spacecraft")
                self._require_on_grid(fc.start_s, f"forecasts[{fc.forecast_id}].start_s")
                self._require_on_grid(fc.end_s, f"forecasts[{fc.forecast_id}].end_s")
        self._require_on_grid(self.agents.nav_fix_interval_s, "agents.nav_fix_interval_s")
        self._require_on_grid(self.agents.status_interval_s, "agents.status_interval_s")
        self._require_on_grid(self.operations.min_observation_s, "operations.min_observation_s")
        h = self.agents.health
        if h is not None and h.payload_check is not None:
            self._require_on_grid(h.payload_check.interval_s, "payload_check.interval_s")
        seconds_to_ns(self.network.delay_s, name="network.delay_s")
        seconds_to_ns(self.agents.status_lifetime_s, name="agents.status_lifetime_s")
        return self


AnyScenarioConfig = (
    ToyHeartbeatScenario
    | FormationDynamicsScenario
    | MissionGeometryScenario
    | AgentNetworkScenario
    | NominalOperationsScenario
)


ScenarioConfig = Annotated[AnyScenarioConfig, Field(discriminator="scenario_type")]
_ADAPTER: TypeAdapter[AnyScenarioConfig] = TypeAdapter(ScenarioConfig)


class ConfigError(ValueError):
    """Raised when a configuration file cannot be read or fails validation."""


def load_scenario(path: Path) -> AnyScenarioConfig:
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


def parse_scenario(raw: dict[str, Any], *, source: str = "<dict>") -> AnyScenarioConfig:
    try:
        return _ADAPTER.validate_python(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid scenario config {source}:\n{exc}") from exc


def scenario_json_schema() -> dict[str, Any]:
    """JSON Schema for all scenario types (for editors and documentation)."""
    schema = _ADAPTER.json_schema()
    schema["title"] = "ScenarioConfig"
    return schema

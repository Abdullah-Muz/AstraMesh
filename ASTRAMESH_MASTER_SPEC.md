# AstraMesh
## Master Research & Engineering Specification — v1.0

> **Fault-Tolerant Decentralized Spacecraft Autonomy**  
> **Reference mission:** Adaptive Ionospheric Observation and Space-Weather-Aware Protection  
> **Baseline date:** 2026-11-03  
> **Design status:** Approved research baseline; physical parameters, algorithms, and scientific results remain subject to verification  
> **Implementation status:** Not started  
> **Project type:** Independent, public-methods computational research; no real spacecraft control

---

## How to use this document

This file is the **authoritative design baseline** for AstraMesh. It describes what we intend to build, the reasons behind the choices, the evidence required before moving forward, and the limits of what we can claim. Supporting files may elaborate on individual areas, but they should not silently supersede this master specification.

**Status legend**

- **APPROVED** — agreed project direction or architectural requirement.
- **PROVISIONAL** — proposed numerical value or implementation choice that must be validated.
- **PLANNED** — future feature; not required for the first development gate.
- **OPTIONAL** — include only if experiments justify it.
- **UNVERIFIED** — literature metadata, scientific assumption, or novelty claim awaiting investigation.

**Design baseline ≠ research validation.** Version 1.0 freezes the starting design, not the correctness of numerical models, dataset interpretations, or the originality of future research contributions.

---

# 1. Executive Summary

AstraMesh is a Python-first, CPU-feasible research platform for a **four-spacecraft, decentralized low-Earth-orbit mission**. Its spacecraft cooperatively schedule simulated ionospheric observations, exchange information over constrained inter-satellite links, assess individual health and environmental risk, select protective operating modes, and attempt to preserve scientific value when spacecraft become unavailable or space-weather conditions worsen.

The core problem is **decision-making under incomplete information**. A satellite that stops transmitting might be failed, healthy but disconnected, or in a protective mode. Individual agents must act using their own estimates and received messages, not the simulator's global truth. Their plans must respect finite power, memory, communication, propulsion, and safety constraints.

AstraMesh combines these research tracks:

1. **Validated astrodynamics:** relative orbits, orbital propagation, resource-constrained maneuver modeling, and eventually realistic perturbations.
2. **Decentralized autonomy:** science-task allocation, network partitions, message delays, task reconciliation, and graceful degradation.
3. **Intelligent state assessment:** probabilistic spacecraft-health inference, telemetry anomaly detection, and optional lightweight ML models.
4. **Space-weather-aware protection:** five operating modes and a local safety supervisor that cannot be overridden by mission planning.
5. **Reproducible experiments:** strong classical baselines, external space-data sources, Monte Carlo evaluations, and honest reporting of failures and limitations.

**AstraMesh is not required to use reinforcement learning.** Learning is introduced only where it has a defined role and a meaningful baseline. The project's objective is not merely to simulate satellites, but to assess whether information-aware, safe, decentralized autonomy makes a measurable difference.

### 1.1 Non-goals for the first prototype

- Flight-qualified guidance, navigation, control, software, or radiation protection.
- Real spacecraft commanding or antenna/radio deployment.
- A physical movable radiation shield or speculative magnetic shielding system.
- High-fidelity GNSS receiver electronics, ray tracing, or full ionospheric tomography.
- Detailed battery chemistry, reaction-wheel dynamics, thermal finite elements, or component radiation transport.
- Full-size ESA telemetry training pipelines, distributed cloud services, or mandatory GPUs.
- A claimed novel algorithm before detailed related-work comparison.

---

# 2. Scientific and Research Objectives

## 2.1 Primary research question — APPROVED

**Can a decentralized spacecraft constellation preserve useful scientific operations during uncertain spacecraft-health events, communication disruption, and hazardous space-weather conditions while keeping local protection and maneuver constraints satisfied?**

## 2.2 Testable hypotheses

| ID | Hypothesis | What would count as evidence? |
|---|---|---|
| H1 | Fault-aware task planning retains more mission utility than static scheduling when spacecraft capacity is lost. | Paired fault-injection trials with fixed tasks and resources. |
| H2 | Explicit health uncertainty reduces premature failure declarations and conflicting reallocations relative to timeout-only monitoring. | Same planner, different health estimators; assess false alarms and mission cost. |
| H3 | Space-weather-aware protective logic can improve the tradeoff between hazard exposure and science downtime compared with naïve fixed thresholds. | Historical environmental replays + independently defined synthetic spacecraft-response models. |
| H4 | A local safety supervisor reduces invalid or unsafe maneuver proposals executed during mission recovery. | Comparison of plan execution with/without proposed safety gate under matched scenarios; no universal safety claim. |
| H5 | Forecast-informed protection may improve mission continuity at a given safety-risk budget. | Calibrated forecast vs. probabilistic and reactive baselines on held-out events. |

H1–H5 are hypotheses, not promised outcomes. We may narrow the final research contribution to **one** of them after the literature review and baseline results.

## 2.3 Scientific integrity requirements

- Differentiate **established literature**, **our independent implementation**, and **a genuine methodological contribution**.
- Keep training, validation, and held-out test data separate; avoid future-information leakage in forecasting.
- Never treat an anomalous telemetry point as proof of irreversible spacecraft failure.
- Never treat geomagnetic Kp alone as a component-specific radiation dose or threshold.
- Report unsafe outcomes, false alarms, lost science, timing, and numerical failures instead of hiding them within a single score.
- Keep NASA Starling's existing distributed ionospheric-science autonomy demonstration visible in the related-work analysis.

---

# 3. Reference Mission: Adaptive Ionospheric Observation

## 3.1 Mission concept — APPROVED

Four 6U-class simulated spacecraft fly in near-circular LEO in a **nominal along-track arrangement**. Each has a simplified dual-frequency GNSS/TEC-capable science payload, autonomous planning software, limited energy and data capacity, crosslinks, a local health and protection supervisor, and a constrained maneuver budget.

The spacecraft select available science opportunities, allocate observation responsibilities, and share only permitted status/task messages. Real observations and model products from UCAR COSMIC-2 and NOAA GloTEC inform the scientific scenario. Early experiments use simplified observation geometry; later experiments may integrate GNSS transmitter/receiver line-of-sight constraints.

**Critical science caveat:** Slant total electron content (TEC) is a path-integrated observation, not a measurement of a single grid-cell value. The initial region-based priority model is an expressly labeled scheduling abstraction. It must not be described as physically complete radio-occultation retrieval or ionospheric tomography.

## 3.2 Orbital design — approved starting values, provisional physics

| Parameter | Initial value | Status and rationale |
|---|---:|---|
| Number of spacecraft | 4 | **APPROVED** — enough for multi-hop coordination and partitions; CPU-feasible. |
| Class | 6U CubeSat-style abstraction | **APPROVED** reference category, not a detailed flight design. |
| Reference altitude | 525 km | **APPROVED PROVISIONAL** — LEO where atmospheric drag matters. |
| Inclination | 97.5° | **PROVISIONAL** high-inclination/near-sun-synchronous candidate; verify under J2. |
| Eccentricity | 0 (reference) | **PROVISIONAL** initially near-circular for simpler validation. |
| Nominal layout | Along-track/string-of-pearls | **APPROVED** simple topology and understandable fault experiments. |
| Adjacent separation | ~20 km | **PROVISIONAL** initial spacing; verify geometry and drift. |
| Nominal scenario duration | 24 h | **PROVISIONAL** several orbital revolutions and science windows. |
| Integration step | 10 s candidate | **PROVISIONAL** acceptance through convergence tests only. |
| Mission planning interval | 60 s candidate | **PROVISIONAL** event-driven replanning may occur sooner. |
| Spacecraft state propagation | 2-body first | **APPROVED** first physics gate, followed by higher fidelity. |

**Frame/physics requirements:** Use explicit ECI frame definitions (including epoch), an Earth-fixed frame where needed for observation geometry, and a specified local orbital frame (e.g., RIC/LVLH with declared axis convention). Set four initial conditions from **consistent orbital elements**, not four frozen cartoon offsets. Verify that a stated inclination actually gives the intended nodal precession when J2 is included. A two-body model by itself **does not establish sun-synchronous behavior**.

**Separate truth models:** The simulation's numerical state and individual agents' estimated states are distinct. No agent may read exact future events or hidden truth.

## 3.3 Spacecraft abstraction — recommended provisional values

| Subsystem | Candidate value/model | Reason for inclusion |
|---|---|---|
| Simulated spacecraft mass | 12 kg | Plausible order-of-magnitude 6U research assumption; verify. |
| Electrical generation | 25 W *during specified generating conditions* | Finite energy budget; not a constant eclipse-time supply. |
| Battery | 100 Wh usable model candidate | Power-aware payload/protection decisions; validate depth-of-discharge assumptions. |
| Science payload | Simplified dual-frequency GNSS TEC receiver | Relevant to ionospheric science and Starling precedent. |
| Science load | 5 W candidate | Explicit opportunity cost; subject to payload reference check. |
| Propulsion | 0.5 mN maximum low-thrust | Permits maneuver tradeoffs without impulsive, unconstrained control. |
| Delta-v budget | 5 m/s total | Forces finite maneuver-resource accounting. |
| Attitude determination/control | Abstract pointing and health state in V1 | Needed for science/SAFE rules; detailed wheel dynamics later. |
| Data storage | 1 GB working model | Makes observations compete for finite resources. |
| ISL nominal range | 100 km *synthetic maximum* | Convenient linked 20 km arrangement; not an RF link budget. |

At 12 kg, a 0.5 mN thrust corresponds to about `4.17e-5 m/s²`. Delivering 5 m/s at constant mass and full thrust takes roughly **33.3 hours of accumulated thrust time**: therefore do **not** assume fast, arbitrary orbital reconfiguration. Check power, duty cycle, and propellant feasibility before using this propulsion model for ambitious trajectories.

Eclipse intervals, array orientation, essential avionics consumption, power margin, and battery charging must be modeled before asserting an energy budget is feasible. A SAFE or PROTECTIVE mode is not simply "all systems off."

## 3.4 Science task model

A task record should have at minimum:

```yaml
id: TEC_0042
start_utc: "<scenario UTC>"
end_utc: "<scenario UTC>"
observation_type: "slant_tec_proxy"
region_or_path_id: "REGION_12"
priority: 3
required_capability: "GNSS_TEC"
payload_energy_wh: null  # derived from payload power × time
storage_mb: null        # derived from observation definition
quality_threshold: null
cooperative_requirement: null
source_flag: "synthetic_from_data_informed_scenario"
```

Initial mission: target **40–60 candidate observation opportunities per 24-hour simulation**, only as an experiment-size suggestion. If a geometry-based model yields a different number, use the modeled number and report it. Do not force synthetic observations to match a preferred count.

### Mission utility

A candidate transparent utility definition is:

\[
U_{\mathrm{sci}} = \sum_{j=1}^{M} w_j\,q_j\,c_j,
\]

where `w_j` is a fixed task value, `q_j ∈ [0,1]` is observation quality under a specified model, and `c_j ∈ {0,1}` indicates valid completion in its time window. Define whether repeat/overlapping observations earn additional value; default is **no duplicate credit** unless the science objective calls for repeat sampling.

Report two different normalizations separately:

1. **Healthy-reference retention** `U_fault / U_healthy_reference` — how much original scientific opportunity survived the disruption.
2. **Post-fault efficiency** `U_fault / U_post_fault_oracle` — how effectively a strategy used the feasible surviving resources (when the oracle can be computed).

Do not present the second as the same thing as the first, or assume an oracle is always computationally practical. Report total unnormalized utility and the feasible mission constraints as well.

---

# 4. Physics, Environmental Models, and Validation

## 4.1 Dynamics levels

**D0 — First gate:** Independent, nonlinear two-body Kepler propagation for each spacecraft and an analytical/cross-checked reference; compare a restricted Clohessy–Wiltshire/Hill model only within its circular-reference, small-separation assumptions.

**D1 — Follow-up:** J2 oblateness and nominal atmospheric drag; assess secular drift and near-sun-synchronous precession. Keep inertial and Earth-fixed conversions explicit.

**D2 — Storm replay:** Atmospheric-density changes driven by defensible space-weather proxies/inputs and an atmospheric model (such as an NRLMSISE family implementation) with explicit uncertainty; do not turn Kp directly into a fictitious force.

**D3 — Higher-fidelity comparison:** Basilisk scenarios for selected propagation and control cases; document mismatches and assumptions.

**D4 — Optional:** Detailed GNSS geometry, attitude dynamics, thrust pointing, power/thermal subsystems, and covariance-aware navigation.

Simplified drag acceleration:

\[
\mathbf{a}_{\mathrm{drag}}=-\frac{1}{2}\rho\,C_D\frac{A}{m}\|\mathbf v_{\mathrm{rel}}\|\mathbf v_{\mathrm{rel}}.
\]

Density `ρ`, drag coefficient `C_D`, projected area `A`, spacecraft mass `m`, and velocity relative to the atmosphere `v_rel` must be sourced or marked modeled. In V1, **attitude-based differential-drag control is out of scope**; drag is a disturbance to estimate and report, not a substitute for approved maneuver authority.

## 4.2 Space-weather effects must remain distinct

| Environmental phenomenon | What can be modeled | Response in initial AstraMesh scope |
|---|---|---|
| Geomagnetic activity / upper-atmosphere heating | Atmospheric density and drag changes in LEO | Predict orbital drift; adjust future schedule or stationkeeping plan if feasible. |
| Solar energetic particles / radiation | A defined component-risk model, **not** inferred from Kp alone | Suspend vulnerable science functions; preserve essential functions. |
| Ionospheric irregularities / GNSS degradation | Reduced measurement quality, uncertain navigation or communication status | Raise estimator uncertainty; reassess observation feasibility and assignments. |
| Network/ground link disruption | Link outages, delays, stale messages | Replan using locally available information; reconcile when links return. |

An environmental **risk proxy** and a spacecraft's **true damage/health state** are different variables. We will use controlled synthetic health-response models for experiments and label them as such.

## 4.3 Historical storm replay

The **May 10–13, 2024 geomagnetic storm** is a candidate historical disturbance scenario. Historical NASA OMNI and NOAA geomagnetic products can be used for 2024 inputs, subject to cadence/availability review.

**Do not use GloTEC as historical May 2024 truth:** NOAA's operational global GloTEC product begins in 2025. For 2024, select period-appropriate NOAA/NASA/COSMIC-2 products and clearly separate observation data from assimilated model outputs. A later 2025/2026 storm can be chosen for scenarios explicitly requiring GloTEC.

## 4.4 Phase 1 physics acceptance tests

- Two-body propagation agrees with an independent analytic/high-accuracy reference over the defined horizon.
- Energy and angular momentum remain consistent in the no-perturbation model within measured integration error.
- Halving the time step gives convergent state estimates.
- ECI ↔ Earth-fixed ↔ local-frame transformations pass round-trip tests; units are explicit.
- Initial orbital elements produce the intended along-track geometry and dynamically reasonable relative drift.
- J2 validation occurs before claiming sun-synchronous precession.
- Gravity-only and zero-thrust tests are deterministic.
- Failure or invalid numerical input produces a visible error, not fabricated dynamics.
- Physics accuracy thresholds are **set using independent reference error studies**, not invented in this document.

---

# 5. Autonomous Spacecraft Agent Architecture

## 5.1 Local agent components — APPROVED

Every `SpacecraftAgent` has independent:

- Navigation/relative-state estimator and covariance.
- Health-state estimator with uncertainty.
- Environmental-risk assessor and forecast interface.
- Resource manager (battery, power, storage, delta-v).
- Local science-task database, bids, commitments, and plan version.
- Received message inbox and outbound queue.
- Decentralized task allocation/reconciliation logic.
- Guidance and control interface.
- **Independent safety/protection supervisor**.
- Audit/event log.

The simulator may centrally schedule events for deterministic execution, but **agents must not share writable mission state or consume inaccessible global information**.

## 5.2 Conceptual interfaces

```python
agent.observe(sensor_packets)
agent.update_estimates(now)
agent.receive_messages(delivered_packets)
agent.assess_health_and_risk(now)
agent.propose_task_plan(now)
agent.validate_plan_against_resources(now)
agent.compute_control_request(now)
agent.supervisor.filter_or_reject(request, now)
agent.log_decision(now)
```

These are design-level names, not finalized API commitments.

## 5.3 Network model

Use a time-varying directed connectivity graph `G(t) = (V, E(t))`. Initial normal connectivity is connected; partitions and failures are explicit test conditions. Do not let normal communication become an always-available broadcast oracle.

| Parameter | Starting assumption | Status |
|---|---|---|
| Crosslink availability | Line-of-sight plus synthetic 100 km range | PROVISIONAL; geometry-first, link budget later. |
| Application-level delay | 1 s | PROVISIONAL, **not** propagation time. |
| Normal packet loss | 1% | PROVISIONAL stress setting. |
| Degraded loss | 10–30% | PROVISIONAL stress scenarios. |
| Status reporting | Every 30 s | PROVISIONAL. |
| High-level scheduling | Every 60 s, plus events | PROVISIONAL. |
| Partition/reconnect | Deterministic replayable injected events | REQUIRED. |

A message must carry sender ID, sequence ID, creation timestamp, expiry, message type, mission/plan version, and the applicable payload (state estimate/covariance, health belief, task claims, resources, etc.). Include duplicate handling, expiry, message ordering rules, and reconciliation semantics. No static assumption that partitions magically reach global consensus.

## 5.4 Fault and health assessment

Local beliefs may use the values:

`HEALTHY`, `DEGRADED`, `SUSPECTED_UNAVAILABLE`, `COMMUNICATION_LOST`, `CONFIRMED_FAILED`, `RECOVERING`, `UNKNOWN`.

These labels describe **an agent's belief**; injected ground-truth fault status remains a separate field held by the simulator. Define which evidence can warrant `CONFIRMED_FAILED`; missed heartbeats alone generally cannot prove physical failure.

Failure types: complete unavailability, partial propulsion loss, sensor degradation, temporary communications outage, longer partition, conflicting reports, false failure suspicion, multiple simultaneous degradations, and protected-payload suspension. A failed spacecraft remains a physical object and potential collision hazard.

Each fault injection must specify type, cause/model, start/end times, severity, observability, recoverability, and consequences.

---

# 6. Five-Mode Protection Supervisor — APPROVED

## 6.1 Philosophy

**Local spacecraft survival takes precedence over constellation-level science allocation.** Protection and control validation belong to a local supervisor, not to a planner that may maximize scientific score. This is a simulation architecture, not flight software certification.

Modes:

| Mode | Purpose | Science operations | Essential operations |
|---|---|---|---|
| `NOMINAL` | Normal science and coordination | On where feasible | Navigation, power, health monitoring and communications. |
| `STORM_WATCH` | Increased exposure/risk/uncertainty | On or constrained | Increased monitoring, contingency planning, forecast validation. |
| `PROTECTIVE` | Proactive protection against defined environmental hazard | Vulnerable functions suspended | Maintain allowable survival/nav/comms functions. |
| `RECOVERY` | Controlled return from protection | Phased reactivation | Validate subsystem health and reconcile mission plan. |
| `SAFE` | Critical local fault response | Off unless survival-critical | Minimum feasible survival functions, safe attitude/power state. |

**PROTECTIVE is an environmental precaution; SAFE is a critical local-fault response.** A spacecraft need not be physically failed to be PROTECTIVE. SAFE may be entered from any mode based on an independently defined critical condition.

## 6.2 Guarded mode transitions

| From → To | Guard | Side effects |
|---|---|---|
| NOMINAL → STORM_WATCH | Sustained elevated environmental exposure risk, or high uncertainty under a documented policy | Increase sampling/forecast checks; prepare alternative schedules. |
| STORM_WATCH → PROTECTIVE | Predicted subsystem exposure exceeds a specific modeled limit, with evidence-quality checks | Suspend declared vulnerable functions; publish availability change. |
| STORM_WATCH → NOMINAL | Risk remains below watch-release guard with valid telemetry | Resume ordinary monitoring. |
| PROTECTIVE → RECOVERY | Sustained risk below lower release threshold **and** no critical local fault | Run component self-checks; gradually restore functions. |
| RECOVERY → NOMINAL | Power, attitude, nav, required sensors and applicable comm checks pass; tasks reconciled | Rejoin normal scheduling. |
| RECOVERY → PROTECTIVE | Hazard reappears or restoration checks do not justify nominal operation | Return to limited-operation protection. |
| Any → SAFE | Critical local fault / survival constraint violation | Preempt mission planner and science execution. |
| SAFE → recovery path | Explicit fault-resolution, telemetry, and supervisor-approved conditions | Never auto-clear merely because risk forecast improved. |

Use hysteresis, minimum dwell times, confidence checks, and explicit policies for stale/missing inputs. Invalid forecast values must not silently become zero risk. Set per-risk thresholds based on the **modeled subsystem's** tolerances, not arbitrary NOAA storm labels.

### Illustrative normalized-risk values — NOT validated thresholds

`watch = 0.35`, `protect = 0.70`, `release = 0.25` were used in a conceptual discussion to illustrate hysteresis. They are *not* flight requirements, component limits, or calibrated space-weather thresholds. Treat them as optional example values in a toy test configuration only, and never encode them as immutable defaults for scientific results.

## 6.3 Three independent environmental risk dimensions

1. **Radiation/electronics risk** — needs suitable particle/flux/dose proxies and component-specific models; do not equate Kp with radiation dose.
2. **Navigation/communications risk** — GNSS quality, stale/missing observations, network telemetry, space-weather context.
3. **Orbital-disturbance risk** — density estimates, drag-driven drift, trajectory and separation uncertainty.

A local power/thermal/attitude fault remains a **separate critical safety input**. Do not average severe risk away by combining categories into one generic score.

## 6.4 Validation requirements

- Critical local fault forces SAFE regardless of current mode or mission utility.
- Brief noisy spikes do not cause rapid oscillatory transitions.
- Protection requires a valid modeled hazard policy and sufficient evidence; missing values follow the documented conservative rule.
- Different spacecraft may rationally occupy different modes under different local information.
- Protection messages reach distributed planning only through delivered network messages.
- Task reallocation cannot force a PROTECTIVE spacecraft to reactivate its science payload.
- RECOVERY requires health checks, resource readiness, and plan reconciliation.
- All state changes, guard inputs, and overrides are timestamped and replayable.

---

# 7. Machine Learning and Probabilistic Estimation

## 7.1 Role of ML — APPROVED

ML is a tool for **prediction and inference**, not an unbounded agent permitted to command thrusters or bypass protection. Initial candidates:

- Real telemetry anomaly detection.
- Fault/health-belief estimation and calibration.
- Space-weather or observation-priority forecasting.
- Optional learned task-value/feasibility surrogate, only if comparisons justify it.

**Reinforcement learning is OPTIONAL.** The first research result should stand on credible model-based, probabilistic, and optimization baselines.

## 7.2 Three-way health estimation comparison

| ID | Method | Purpose |
|---|---|---|
| H-A | Heartbeat/timeout-only classifier | Simple operational baseline. |
| H-B | Bayesian/HMM or explicit probabilistic health model | Classical uncertainty-aware comparison. |
| H-C | Lightweight learned anomaly detector + calibrated health inference | ML candidate; assess incremental value. |

**Hold downstream mission planning identical** while comparing H-A, H-B, and H-C. Otherwise detector and planner improvements are confounded.

Telemetry anomaly detection must be evaluated on real labeled telemetry **independently** from simulated multi-spacecraft mission recovery. Bridging the two requires a documented adapter from anomaly score → uncertain health belief, and stress tests for cross-mission domain shift. There is no claim that OPS-SAT, SMAP, or ESA-ADB data belong to AstraMesh's four fictional spacecraft.

## 7.3 Three-way protection comparison

| ID | Method | Purpose |
|---|---|---|
| P-A | Fixed rule/threshold policy | Reactive baseline. |
| P-B | Probabilistic risk + hysteresis | Uncertainty-aware classical baseline. |
| P-C | ML-aided forecast feeding the **same** local supervisor | Forecast-assisted candidate. |

Forecast evaluation uses chronological splits and forecast lead times. Simulated spacecraft hazard outcomes cannot be described as observed hardware damage.

## 7.4 ML metrics and safeguards

Measure event-based precision/recall, false-alert rate, missed detections, detection latency, calibration (e.g., reliability/ECE/Brier where applicable), drift, data gaps, CPU latency, and memory footprint. For protection decisions report false protective activation, missed defined hazard, science downtime, and resource costs.

Use time-based / mission-based separation, never shuffled samples that leak temporal structure across training and test. Avoid mixing the same telemetry event or overlapping window into both partitions. Compare ML with reasonable classical baselines, not just a no-op.

---

# 8. External Datasets and Provenance Registry

## 8.1 Initial approved data program

| Data source | Source URL | What it supports | Scope / caution |
|---|---|---|---|
| **ESA Anomaly Dataset / ESA-ADB** | https://github.com/esa/anomaly-dataset ; https://zenodo.org/records/12528696 | Annotated spacecraft telemetry for anomaly research. | Large (~tens of GB); initial **sampled subset only** on 32 GB-RAM CPU laptop. Benchmark pipeline's full requirements may exceed local resources. |
| **ESA OPS-SAT-AD** | https://zenodo.org/records/15108715 | Small-spacecraft, labeled anomaly benchmark; feasible initial local experiments. | Segments and splits are benchmark-specific; do not call anomaly a confirmed fatal failure. |
| **NOAA GloTEC** | https://www.ncei.noaa.gov/products/space-weather/ionospheric-program/total-electron-content | Global assimilated TEC/electron-density context and spatial priorities. | Operational global product **from 2025**; model product, not ground truth. Inspect quality flags. |
| **CelesTrak GP / OMM** | https://celestrak.org/NORAD/elements/ | Public orbital-element reference scenarios and parsing workflows. | General-perturbations elements are **not** exact inertial truth; prefer OMM-compatible formats over a TLE-only pipeline. |
| **UCAR COSMIC-2** | https://www.cosmic.ucar.edu/what-we-do/cosmic-2/data | Real GNSS radio-occultation, TEC and orbit products, science geometry references. | Multiple processing levels/cadences; check access, provenance, and dependency with assimilated GloTEC. |
| **NASA OMNI / SPDF** | https://omniweb.gsfc.nasa.gov/ ; https://spdf.gsfc.nasa.gov/ | Historical solar-wind/geomagnetic environmental replay. | Historical observation inputs must not leak future conditions into forecast. |
| **NOAA SWPC / NCEI** | https://www.spaceweather.gov/ ; https://www.ncei.noaa.gov/satellite/space-weather-data | Geomagnetic and radiation-relevant environmental context. | Different products represent different phenomena and temporal cadences. |

### Optional later sources

- **NASA SMAP / Mars Science Laboratory Telemanom:** https://github.com/khundman/telemanom — historical anomaly baseline; older benchmark with known limitations.
- **NASA GOLD:** https://gold.cs.ucf.edu/data/search/ — ionospheric/thermospheric science, subject to mission compatibility.
- **SatNOGS:** https://network.satnogs.org/ — ground-station observation records; **not** direct inter-satellite radio-link truth.
- **Copernicus Data Space:** https://dataspace.copernicus.eu/ — only if evaluating alternate Earth-observation missions.

## 8.2 Data-handling requirements

Create `docs/DATASET_REGISTRY.md`, one record per dataset with owner, URL/DOI, precise version/date, retrieved file/hash, license/terms, sampling interval, units, geospatial/time conventions, missingness/quality flags, event labels, expected RAM/storage footprint, intended experiment, leakage risks, and domain-transfer caveats.

**Never claim:** ESA/NASA telemetry from separate missions constitutes a synchronized four-member AstraMesh swarm; TEC model values are independent truth for COSMIC-2 inputs that were assimilated into them; or telemetry anomaly labels prove spacecraft loss.

**Resource policy:** Begin with one or two OPS-SAT-AD channels and a bounded temporal/environmental slice. Do not attempt the complete ESA-ADB benchmark (its recommended compute and storage may exceed this laptop) before measured resource sizing. Pin source versions and file hashes; keep large raw datasets out of Git.

---

# 9. Algorithmic Baselines and Research-Gap Matrix

## 9.1 Baselines

| ID | Algorithm | Comparison role |
|---|---|---|
| B0 | Static/no-replanning scheduler | How much does coordination help after disruption? |
| B1 | Centralized information-rich optimizer | Reference bound / comparative oracle; disclose privileged information. |
| B2 | Basic distributed auction | Simple decentralized allocation. |
| B3 | Conventional CBBA / published satellite-adapted variant | Strong, literature-grounded decentralized baseline. |
| B4 | Fault-aware rule-based task redistribution | Strong non-ML recovery comparator. |
| R1 | AstraMesh research method, **TBD** | Define only after full-text related-work and failure analysis. |

For space-weather protection compare P-A/P-B/P-C; for health estimates compare H-A/H-B/H-C. Change one major component at a time. Reproduce an established algorithm's assumptions faithfully or label a simplified implementation as **CBBA-inspired**, not exact CBBA.

## 9.2 Preliminary research-gap matrix — UNVERIFIED as a novelty claim

| Prior work | Established area | Overlap / investigation needed |
|---|---|---|
| NASA Starling / DSA | Flight-demonstrated four-CubeSat distributed ionospheric observations and reactive task coordination. | Cannot claim the first such mission; compare information assumptions and fault response. |
| Choi, Brunet & How (2009) CBBA | Consensus-based auction/bundle task allocation. | Baseline for allocation; verify delay/partition assumptions. |
| Song et al. (2023) ICBBA | Onboard decentralized LEO observation planning with coupled constraints. | Compare observation feasibility and scheduling constraints. |
| Reid et al. (2026) | Resource-constrained task redistribution following agent loss. | Strong competitor for post-fault mission value; inspect communication assumptions. |
| Ye & Dong (2026) | Decentralized proof-of-benefit mission negotiation. | Strong competitor for utility-based negotiation; inspect fault semantics. |
| Azadmanesh et al. (2026) | Decoupling global and local swarm fault indicators. | Strong competitor for distributed fault attribution; avoid broad novelty claims. |
| Distributed spacecraft MPC papers | Formation reconfiguration, communication tradeoffs, collision avoidance. | Respect physical safety and computational limitations. |
| ESA / OPS-SAT telemetry benchmark research | Real satellite anomaly detection. | Use explicit calibration and domain-transfer analysis, not blanket novelty claims. |

### Candidate narrow contributions (select **one** after review)

- **G1:** Health-belief-aware decentralized task reassignment that distinguishes confirmed loss from communication outage.
- **G2:** Recovery-plan reconciliation across temporary partitions with bounded communication and physically constrained science operations.
- **G3:** Decentralized protection-mode coordination during space-weather episodes: mission-value tradeoff under false alarms, heterogeneous risk, and incomplete knowledge.
- **G4:** Integrating calibrated predictive health/environment estimates into safety-constrained scheduling; quantify when forecasts help versus hurt.

**Novelty gate:** Read closest literature in full; reproduce meaningful conventional baselines; identify a demonstrable shortcoming; formalize one algorithmic change and falsifiable hypothesis; run held-out ablations; then write a cautiously bounded novelty claim, if warranted.

---

# 10. Experimental Program

## 10.1 Required test scenarios

| ID | Scenario | Primary measured behavior |
|---|---|---|
| S00 | Nominal four-satellite mission | Observation scheduling, resource accounting, geometry. |
| S01 | One permanently unavailable satellite | Reassignment and retained utility. |
| S02 | Two failures at separated times | Graceful degradation. |
| S03 | Partial propulsion or sensor degradation | Feasible plans under changed capabilities. |
| S04 | Temporary loss of one satellite's messages | Avoid premature declaration and unnecessary task duplication. |
| S05 | Split network (e.g., 2 + 2 nodes), then reconnect | Independent local decisions and plan reconciliation. |
| S06 | Stale/conflicting health reports | Robust beliefs and assignment conflict rates. |
| S07 | Prolonged elevated environmental risk | Protective selection and scientific opportunity cost. |
| S08 | Brief false environmental alert | Chatter avoidance and unnecessary science loss. |
| S09 | Environmental episode plus network partition | Combined risk and decentralized protection. |
| S10 | Hazard episode plus true critical local fault | SAFE override, no planner bypass. |
| S11 | Historic May 2024 storm context | Environmentally grounded replay using **2024-available** source products, synthetic component response. |

## 10.2 Metrics

**Primary:** raw science utility and healthy-reference retention, with safety status reported in parallel.

**Additional:** post-fault oracle efficiency where available; valid task completions; duplicate/conflicting allocations; time to consistent/feasible recovery; packet counts/bytes; resource consumption (Wh, storage, delta-v); estimator false alarms/misses; belief calibration; protection dwell time, false protection, missed modeled hazard; navigation uncertainty; nearest approach; collision/separation constraint violations; algorithm CPU time and peak memory.

Avoid treating a higher utility as better if it violates the prespecified safety constraints. Record infeasible plans and solver timeouts explicitly.

## 10.3 Statistical design

- Freeze fixed reference scenarios and final test conditions before the proposed method is tuned.
- Pair algorithm runs with common starting states, task lists, fault events, and random streams where applicable.
- Define separate seeds for task-generation, communication, sensor noise, fault injection, and algorithm stochasticity.
- Run multiple trials, report confidence intervals, and state sample counts.
- Record negative results, calibration problems, and computational failures.
- Include ablations: without health uncertainty, without forecasting, without protective hysteresis, without plan reconciliation, without maneuver feasibility, etc., **when those components exist**.
- Compare at fleet sizes 4 first; scaling to 6–8 or more is later, not an opening requirement.

## 10.4 Provenance artifact per run

```yaml
experiment_id: "S05_B3_seed001"
run_timestamp_utc: "<filled automatically>"
git_commit: "<git sha>"
config_hash: "<sha256>"
seed: 1
dynamics_model: "D0_two_body"
science_data_version: "<recorded source + hash>"
telemetry_data_version: "<recorded source + hash or none>"
algorithm: "CBBA_baseline"
software_lockfile_hash: "<sha256>"
artifacts:
  - events.jsonl
  - metrics.json
  - trajectory.parquet
  - task_decisions.parquet
```

---

# 11. Technology Stack and Adoption Plan

| Area | Core / near-term | Later or optional |
|---|---|---|
| Language/runtime | Python; Ubuntu 24.04 WSL2; Git | Performance-optimized compiled extension only if profiling supports it. |
| Dependency management | `uv`, `pyproject.toml`, `uv.lock` | Containers only if portability requires them. |
| Physics | NumPy, SciPy | Basilisk reference/validation; J2 and atmospheric models. |
| Astrodynamics data | Astropy (time/frames/units), OMM reader | Skyfield/`sgp4` for CelesTrak GP data when needed. |
| Optimization | SciPy solvers for simple problems | CVXPY + OSQP for convex constrained models; choose solver by formulation. |
| Communications | NetworkX + SimPy | RF link budget / advanced network simulator if justified. |
| Estimation | NumPy, SciPy | FilterPy or focused custom Kalman/Bayesian filters. |
| ML | scikit-learn | PyOD, PyTorch if justified; no mandatory MARL. |
| Scientific data | pandas, PyArrow, Xarray | NetCDF4/cdflib, DVC selectively. |
| Visualization | Matplotlib, Plotly | Basilisk Vizard if installation/performance permits. |
| Testing | pytest, Hypothesis | GitHub Actions lightweight CI; coverage and benchmark tooling. |
| Experiment configs | YAML with schema validation | MLflow only if experiment volume requires it. |

**Installation sequence:**

1. Phase 0: `uv`, NumPy, SciPy, pytest, Hypothesis, PyYAML, Matplotlib, pandas.
2. Phase 1: Astropy and validated dynamics/geometry utilities as needed.
3. Phase 2: NetworkX, SimPy, chosen optimization tools.
4. Phase 3: Data readers + scikit-learn and probabilistic-estimation tools.
5. Phase 4–5: Basilisk, atmospheric models, advanced visualization and optional PyTorch after compatibility tests.

Avoid installing everything at once. Record OS/Python/package compatibility and add dependencies only to support a tested requirement. With the available Ryzen/32 GB/CPU-only machine, small multi-agent numerical simulations and classical ML are preferred over full high-compute benchmark reproductions.

---

# 12. Software Layout and Interfaces

Proposed repository (final package name `astramesh`):

```text
AstraMesh/
├── README.md
├── ASTRAMESH_MASTER_SPEC.md
├── pyproject.toml
├── uv.lock
├── LICENSE
├── CITATION.cff
├── references.bib                 # verified bibliographic metadata only
├── configs/
│   ├── mission/
│   ├── dynamics/
│   ├── spacecraft/
│   ├── networks/
│   ├── protection/
│   └── experiments/
├── src/astramesh/
│   ├── core/                      # clocks, units, configs, events
│   ├── dynamics/                  # truth propagation / frames
│   ├── science/                   # TEC tasks / opportunities
│   ├── agents/                    # isolated per-satellite state
│   ├── communications/            # routed messages and faults
│   ├── estimation/                # navigation / health beliefs
│   ├── planning/                  # static, auctions, CBBA, etc.
│   ├── protection/                # five-mode local safety FSM
│   ├── control/                   # feasible maneuvers
│   ├── weather/                   # risks and historical replay
│   ├── datasets/                  # import and validation adapters
│   ├── ml/                        # anomaly models / calibration
│   ├── faults/                    # simulation fault injection
│   ├── evaluation/                # metrics / replay / reports
│   └── visualization/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── physics_validation/
│   ├── agent_isolation/
│   └── regression/
├── experiments/                   # config + scripts; not large raw files
├── data/                          # local ignored data, no secrets
├── docs/
│   ├── NUMERICAL_MISSION_DESIGN.md
│   ├── RESEARCH_MATRIX.md
│   ├── LITERATURE_REVIEW.md
│   ├── DATASET_REGISTRY.md
│   ├── AUTONOMY_ARCHITECTURE.md
│   ├── PROTECTION_MODES.md
│   ├── EXPERIMENT_PROTOCOL.md
│   ├── ROADMAP.md
│   └── DECISION_LOG.md
└── scripts/
```

**Authoritative-document rule:** This master file captures project-level decisions. Supporting files add quantitative evidence, mathematical derivations, test results, and integration detail. Updates that alter mission scope, safety semantics, research hypotheses, or acceptance criteria must update the master file and decision log.

---

# 13. Development Roadmap and Exit Gates

## Phase 0 — Research and reproducibility foundation

**Build:** repo, environment, dependency lock, lint/test conventions, config schemas, reference registry, literature matrix, minimal event log. Establish source versions and safe dataset access methods.

**Gate P0:** Clean environment setup; unit-test runner and CI; repeatable toy experiment; first priority references reviewed; exact simulation epoch/frames/units specified; physics acceptance plan signed off.

## Phase 1 — Validated four-spacecraft dynamics and mission geometry

**Build:** two-body propagator, orbital initial-element generation, along-track formation, clocks/frames, basic plots, synthetic science opportunities, finite resource accounting.

**Gate P1:** Independent propagation and convergence checks pass; four initial orbits are consistent; 24 h baseline completes; science eligibility can be explained by modeled geometry; fixed seeds replay identically.

## Phase 2 — Decentralized nominal science operations

**Build:** independent agents, inboxes/outboxes, NetworkX/SimPy crosslinks, static baseline, centralized reference, auction/CBBA implementation, nominal task scheduling.

**Gate P2:** Each agent acts only on local state/delivered messages; no privileged leakage; baseline comparisons operate on identical tasks/resources; unhandled network messages cannot alter plans.

## Phase 3 — Deterministic faults and protection supervisor

**Build:** full fault/event schema; health timeout baseline; `NOMINAL`, `PROTECTIVE`, `SAFE` first; complete five-mode state machine thereafter; safety overrides and messages to planner; scenario replay.

**Gate P3:** SAFE always overrides; invalid forecast behavior defined; no mode chatter under brief noise; false outage does not count as confirmed fatal failure; distributed task replanning cannot defeat protection.

## Phase 4 — External data and probabilistic/ML experiments

**Build:** bounded OPS-SAT and ESA telemetry samples, GloTEC/COSMIC-2 science context, historical environment streams, baseline anomaly detector, calibrated probabilistic health model and optional light learned model.

**Gate P4:** Data licenses/provenance and train/test partitions documented; anomaly results independently benchmarked; synthetic-vs-real interface explicit; preliminary health/forecast comparisons complete with uncertainty.

## Phase 5 — Storm-aware distributed recovery

**Build:** atmospheric drag disturbance extension, event/forecast risk policies, multi-spacecraft protection decisions, network partitions, independent task recovery, optional feasible low-thrust maneuver optimization.

**Gate P5:** Combined failure/science/protection scenarios reproducible; no claims of radiation or flight safety beyond simulation assumptions; baseline and candidate methods compared fairly.

## Phase 6 — Research conclusion and public demonstration

**Build:** held-out Monte Carlo, selected Basilisk comparisons, ablations, negative-result analysis, technical report, project README, actual-result plots and demo video.

**Gate P6:** Every reported result traces to a commit/config/data version; limitations disclosed; novelty only claimed if supported by full-text prior-work comparison and experimental evidence.

### Timing (planning only)

- **3–5 weeks at ~15–20 hours/week:** an *early* working orbital/communication/basic-recovery demonstration if dependencies and physics validation progress smoothly; not the full research objective.
- **~11–18 weeks at ~15–20 hours/week:** a research-oriented integrated prototype in an optimistic-to-moderate scenario; literature review, robust ML evaluation, and physically credible validation can take longer.
- Avoid treating these estimates as deadlines or compromising validation to achieve them.

---

# 14. Engineering Acceptance Tests and Hard Stops

## 14.1 Hard-stop defects

A new feature should not proceed past its gate if it introduces:

- Nonphysical orbital propagation, coordinate-frame/unit errors, or unexamined numerical divergence.
- An autonomy agent reading hidden ground truth or unseen future events.
- A distributed planner able to override `SAFE`/`PROTECTIVE` requirements.
- Mislabeling telemetry anomalies as confirmed failure or synthetic data as real constellation measurements.
- Dataset leakage or results that cannot be traced to a known source/configuration.
- Unsafe maneuver requests silently executed without modeled checks.

## 14.2 Noncritical backlog

Animation polish, full-flight hardware detail, expensive pipeline replications, exotic ML models, overengineered infrastructure, and low-severity cosmetic issues are deferred unless required by a validation gate or research result.

## 14.3 Initial ten validation checks

- [ ] Two-body propagation matches a high-accuracy reference within documented tolerances.
- [ ] Numerical step refinement converges on a fixed scenario.
- [ ] Reference frames and physical units pass round-trip checks.
- [ ] Four spacecraft retain dynamically consistent initial formation parameters.
- [ ] No agent accesses another agent's private state or undelivered packets.
- [ ] Science opportunity feasibility is determined from modeled geometry and resources.
- [ ] Energy, storage, and delta-v accounting is conserved and bounded.
- [ ] Repeated runs using identical seeds/configs produce identical outcomes.
- [ ] Protection override tests pass and invalid forecasts are explicitly handled.
- [ ] Complete nominal 24 h scenario runs without unhandled exceptions or silent physics failures.

---

# 15. Literature Review and Reference Library

**Reading-list policy:** The 23 legacy research entries below were compiled during project planning. Some bibliographic identifiers have been checked against original publishers/institutions; others **still require metadata verification** before entering a formal `references.bib`. A DOI being present here is not proof that we have read the full paper or assessed its methodological limitations.

**Review each reference for:** exact bibliographic metadata; problem and assumptions; local vs privileged information; state/physics fidelity; networking model; failure semantics; safety constraints; baselines; metrics and sample sizes; limitations; candidate replication; possible overlap with AstraMesh.

## 15.1 Existing core research reading list (P01–P23)

### Distributed spacecraft autonomy and mission planning

| ID | Publication / resource | Year | Source | Review status |
|---|---|---:|---|---|
| P01 | *Advancing Autonomy in Distributed Space Systems: Insights From On-Orbit Testing with the Starling 1.0 Mission* | 2024 | https://ntrs.nasa.gov/citations/20240004120 | NASA record to be read in full; metadata check. |
| P02 | *Decentralized, Decomposition-Based Observation Scheduling for a Large-Scale Satellite Constellation* (ICAPS version) | 2024 | https://doi.org/10.1609/icaps.v34i1.31535 | Full-text review pending. |
| P03 | *On-Board Decentralized Observation Planning for LEO Satellite Constellations* | 2023 | https://doi.org/10.3390/a16020114 | Publisher record confirmed; review pending. |
| P04 | *Satellite Scheduling Problems: A Survey of Applications in Earth and Outer Space Observation* | 2025 | https://doi.org/10.1016/j.cor.2024.106875 | Publisher record confirmed; review pending. |
| P05 | *Decentralized Satellite Constellation Replanning for Event Observation* | 2025 | https://doi.org/10.2514/1.A36143 | Publisher record confirmed; review pending. |

### Distributed coordination and task allocation

| ID | Publication | Year | Source | Review status |
|---|---|---:|---|---|
| P06 | Choi, Brunet & How — *Consensus-Based Decentralized Auctions for Robust Task Allocation* | 2009 | https://doi.org/10.1109/TRO.2009.2022423 | Foundational baseline; full method review required. |
| P07 | *Decentralized Task Allocation for Heterogeneous Teams with Cooperation Constraints* | 2010 | https://dspace.mit.edu/entities/publication/997f9e55-8346-49e4-ae66-8b7c36d419da | Metadata/full-text check pending. |
| P08 | *Consensus and Cooperation in Networked Multi-Agent Systems* | 2007 | https://doi.org/10.1109/JPROC.2006.887293 | Foundational consensus review pending. |
| P09 | Reid et al. — *A Decentralized Framework for Resource-Constrained Task Redistribution* | 2026 | https://doi.org/10.1609/aaaiss.v8i1.42523 | Publisher metadata checked; **priority novelty competitor**. |
| P10 | *Distributed Observation Scheduling and Sensor Fusion for Large Agile Constellations* | 2026 | https://www.max-robotics.com/en/research/publications/cmv83qk8c00dnoo4ckgdth9md | Metadata/full text unverified. |

### Orbital dynamics, formation control, and safety

| ID | Publication | Year | Source | Review status |
|---|---|---:|---|---|
| P11 | Clohessy & Wiltshire — *Terminal Guidance System for Satellite Rendezvous* | 1960 | https://doi.org/10.2514/8.8704 | Dynamics derivation and applicability review pending. |
| P12 | *Modeling and Control of Satellite Formations: A Survey* | 2022 | https://www.mdpi.com/2673-4052/3/3/26 | Exact title/metadata check pending. |
| P13 | *Distributed Event-Triggered Model Predictive Control for Spacecraft Swarm* | 2024 | https://doi.org/10.1109/TAES.2024.3485601 | Exact metadata and assumptions check pending. |
| P14 | Chen, Wu & Sun — *Computationally Efficient Distributed Model Predictive Control of Satellite Swarms* | 2026 | https://doi.org/10.1016/j.asr.2025.11.014 | Publisher record confirmed; full method review pending. |
| P15 | *Event-Triggered Distributed Model Predictive Control for Spacecraft Formation with Collision Avoidance* | 2025 | https://doi.org/10.1016/j.ifacol.2025.11.268 | Exact metadata and assumptions check pending. |

### State estimation, fault tolerance, and simulation

| ID | Publication | Year | Source | Review status |
|---|---|---:|---|---|
| P16 | Sinopoli et al. — *Kalman Filtering with Intermittent Observations* | 2004 | https://doi.org/10.1109/TAC.2004.834121 | Filtering assumptions review pending. |
| P17 | *Adaptive Fault-Tolerant Control with Communication Delays and Its Application in Spacecraft Formation* | 2024 | https://doi.org/10.11835/j.issn.1000.582X.2024.04.009 | Metadata/full-text check pending. |
| P18 | *Basilisk: A Flexible, Scalable and Modular Astrodynamics Simulation Framework* | 2020 | https://doi.org/10.2514/1.I010762 | Framework reference; metadata/validation review pending. |

### Closest recent novelty competitors

| ID | Publication | Year | Source | Review status |
|---|---|---:|---|---|
| P19 | *Decentralized, Decomposition-Based Observation Scheduling for a Large-Scale Satellite Constellation* (journal version related to P02) | 2025 | https://doi.org/10.1613/jair.1.16997 | **Do not count as independent method without comparison to P02.** |
| P20 | Guo et al. — *An Improvement of Contract Net Protocol for Distributed Satellite Collaborative Task Planning* | 2026 | https://doi.org/10.1155/ijae/5536856 | Publisher record confirmed; review pending. |
| P21 | Ye & Dong — *Decentralized Proof-of-Benefit Mission Negotiation Method for Satellite Clusters* | 2026 | https://doi.org/10.1016/j.asr.2026.05.020 | Publisher record confirmed; **priority novelty competitor**. |
| P22 | Azadmanesh et al. — *Decoupling Global and Local Faults in Satellite Swarms Using Smart-Freeze Adaptation and Isolation-Priority Logic* | 2026 | https://doi.org/10.3390/aerospace13020176 | Publisher record confirmed; **priority fault-attribution competitor**. |
| P23 | *Scalable Architecture for Rapid Setup and Execution of Multi-Satellite Simulations* | 2024 | https://doi.org/10.1016/j.asr.2023.11.026 | Metadata and applicability check pending. |

## 15.2 Additional ML, dataset, and mission references (D01–D09)

| ID | Reference | Source | Relevance |
|---|---|---|---|
| D01 | NASA — *What is Starling?* | https://www.nasa.gov/smallspacecraft/what-is-starling/ | Flight demonstration scope, four 6U spacecraft, in-train and passive safety orbital layouts. |
| D02 | NASA — *What Is NASA's Distributed Spacecraft Autonomy?* | https://www.nasa.gov/centers-and-facilities/ames/what-is-nasas-distributed-spacecraft-autonomy/ | Ionospheric science and autonomous task selection flight context. |
| D03 | Hundman et al. — *Detecting Spacecraft Anomalies Using LSTMs and Nonparametric Dynamic Thresholding* (2018) | https://doi.org/10.1145/3219819.3219845 | NASA SMAP/MSL anomaly detection historical benchmark. |
| D04 | Kotowski et al. — *European Space Agency Benchmark for Anomaly Detection in Satellite Telemetry* (2024) | https://arxiv.org/abs/2406.17826 | ESA telemetry anomaly benchmark and limitations. |
| D05 | Ruszczak et al. — *The OPS-SAT benchmark for detecting anomalies in satellite telemetry* | https://doi.org/10.1038/s41597-025-05035-3 | CubeSat anomaly detection and official splits. |
| D06 | UCAR COSMIC Program — *COSMIC-2 Data Products* | https://doi.org/10.5065/t353-c093 | GNSS science and precise orbit product provenance. |
| D07 | NOAA NCEI — *Total Electron Content (US-TEC and GloTEC)* | https://www.ncei.noaa.gov/products/space-weather/ionospheric-program/total-electron-content | GloTEC assimilated TEC and 2025+ coverage. |
| D08 | CelesTrak — *A New Way to Obtain GP Data* | https://celestrak.org/NORAD/documentation/gp-data-formats.php | OMM/GP formats and TLE constraints. |
| D09 | Basilisk — Official documentation | https://avslab.github.io/basilisk/ | Simulation and validation platform capabilities. |

## 15.3 Recommended reading order

**Priority A — Before algorithm design:** P01, D01, D02, P06, P03, P09, P19, P21, P22, P08.

**Priority B — Before control, science, and safe-mode claims:** P11, P12, P13, P14, P15, P16, P17, P18, D06, D07.

**Priority C — Before ML claims:** D03, D04, D05 and their benchmark repositories/splits; investigate domain shift and label ambiguity.

**Priority D — Extended work:** P02, P04, P05, P07, P10, P20, P23.

Literature matrix columns: `reference_id`, `verified_title`, `authors`, `year`, `doi/url`, `problem`, `agent_info`, `networking_assumptions`, `physics`, `fault_model`, `safety_model`, `method`, `baselines`, `metrics`, `scale`, `key_limitations`, `AstraMesh_overlap`, `replication_priority`.

---

# 16. Decision Register — v1.0

| Decision | Status | Notes |
|---|---|---|
| Project name **AstraMesh** | APPROVED | Public repository/package proposed; confirm availability when created. |
| Independent simulation/research rather than deployed system | APPROVED | No proprietary employer information or flight control. |
| Four 6U-class satellites performing ionospheric observations | APPROVED | Science model initially simplified. |
| 525 km reference LEO | APPROVED PROVISIONAL | Numerical validation required. |
| 97.5° reference inclination | PROVISIONAL | Verify J2 and intended nodal precession. |
| Initial along-track arrangement, ~20 km spacing | APPROVED direction / PROVISIONAL spacing | Dynamic orbital initial conditions required. |
| 12 kg, 25 W, 100 Wh, 5 W payload, 0.5 mN, 5 m/s, 1 GB | PROVISIONAL | Resource and hardware feasibility study required. |
| GNSS/TEC science model with COSMIC-2/GloTEC context | APPROVED | No false claims of full retrieval fidelity. |
| ESA-ADB, OPS-SAT-AD, GloTEC, CelesTrak | APPROVED data program | Stage datasets; full processing depends on resources. |
| Add COSMIC-2 and NASA/NOAA storm-history sources | APPROVED direction | Validate source cadence and availability. |
| Decentralized agents with isolated local state | APPROVED | Core integrity requirement. |
| CBBA and strong conventional planning baselines | APPROVED direction | Exact implementations chosen after literature review. |
| ML without mandatory RL | APPROVED | Classical/probabilistic baselines first. |
| Five protection modes, critical SAFE override | APPROVED | Local autonomy supervisor. |
| Separate radiation/comms/drag risk channels | APPROVED | Avoid invalid composite weather inference. |
| Historical storm replay | APPROVED | May 2024 candidate; GloTEC not usable for 2024. |
| Physical deployable shielding | OUT OF INITIAL SCOPE | Could be future hardware feasibility research. |
| Attitude-based drag control | OUT OF INITIAL SCOPE | Added only after relevant dynamics/control validation. |
| Research algorithm novelty | UNVERIFIED | Must clear related-work gate. |

---

# 17. First Engineering Execution Brief

The first implementation task is **Phase 0: repository setup and verifiable research infrastructure**, not building an elaborate orbital animation or training an ML policy.

### Initial deliverables

1. Create the `AstraMesh` repository and `astramesh` Python package.
2. Set up `uv`, a pinned supported Python version, pytest, Hypothesis, and a minimal CPU-compatible dependency set.
3. Add this master file and create empty linked docs with explicit owners/requirements.
4. Define a validated scenario-configuration schema and common units/time/frame conventions.
5. Implement deterministic simulation clocks, random seeds, event logging, and result manifests.
6. Add one tiny deterministic scenario to prove same-seed replay and create basic CI.
7. Record the first literature matrix entries and initial physics-test design.
8. Document license/terms for external data; **do not download large ESA-ADB assets yet**.

### Definition of done

- Fresh environment can install/run the baseline project.
- `pytest` and a minimal GitHub CI job pass.
- A config-driven toy run emits a complete provenance manifest and reproducible event log.
- No fake flight, science, fault, or ML performance metrics appear in documentation.
- Phase 1 is ready to start with explicit reference orbit, numerical test procedures, and data/physics constraints.

---

# 18. Open Validation Questions

These do **not** block repo setup, but must be answered at the relevant gates:

1. Does 525 km / 97.5° satisfy the desired near-sun-synchronous behavior once J2 is modeled?
2. What initial orbital elements realize ~20 km in-train spacing without unintended secular relative drift?
3. What is the science-quality and observation-access model for a simplified GNSS TEC instrument?
4. What are the correct eclipse-aware spacecraft power loads and essential operations by mode?
5. Does the 0.5 mN / 5 m/s propulsion candidate permit any meaningful recovery maneuvers on the chosen timescale?
6. What local observations support a health belief, and what evidence—if any—justifies confirmed failure?
7. Which threat-specific physical/radiation risk proxies are supported by available historical data and model assumptions?
8. What performance and data-quality limitations make a full ESA-ADB reproduction impractical on the local machine?
9. What is the closest prior work to the precise proposed uncertainty-aware recovery algorithm?
10. Which held-out experiments can genuinely distinguish a useful research contribution from feature integration?

---

# 19. Publication and Communication Standards

AstraMesh may be described as an **independent spacecraft-autonomy research project** combining orbital simulation, distributed task allocation, probabilistic estimation, real spacecraft telemetry benchmarks, and space-weather-aware protection.

Do not describe it as a real satellite constellation, flight-validated system, NASA collaboration, demonstrated new algorithm, or autonomous radiation-shield actuation. Use the terms **simulated**, **model-based**, **data-informed**, **proposed**, **measured**, and **validated** precisely.

Final deliverables should include reproducible software, configuration files, exact data provenance, baseline comparisons, diagrams and videos generated from actual experiments, a limitations section, and a publication-style technical report. A negative result is a valid research outcome if the experiment is careful and reproducible.

---

## Version History

| Version | Meaning |
|---|---|
| v0.1 | Initial decentralized spacecraft recovery concept. |
| v0.2 | Initial 23-paper reading backlog. |
| v0.3 | Agent knowledge, risk, experiment, and research-gap specification. |
| v0.4 | Renamed from SwarmMind to **AstraMesh**. |
| v0.5 (design decisions) | Hybrid ML/autonomy, external data, five-mode protection, space-weather awareness. |
| **v1.0 — 2026-11-03** | **Consolidated approved research/design baseline, numerical candidates, gate criteria, provenance rules, and bibliography.** |

**Next work item:** Phase 0 repository setup and research infrastructure.  
**Final research claim:** To be determined by evidence, not by the existence of this design specification.

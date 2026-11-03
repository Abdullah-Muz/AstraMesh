# AstraMesh

**Research platform for fault-tolerant decentralized spacecraft autonomy, intelligent mission planning, and space-weather resilience.**

AstraMesh is an independent, public-methods computational research project. It is a Python-first, CPU-feasible simulation platform for a **simulated four-spacecraft, decentralized low-Earth-orbit mission** that cooperatively schedules ionospheric observations, coordinates over constrained inter-satellite links, assesses its own health and environmental risk, and tries to preserve scientific value when spacecraft become unavailable or space-weather conditions worsen.

> **Project status: Phase 1 complete; Phase 2 (decentralized nominal science operations) in progress.**
> The repository contains reproducibility infrastructure, validated truth dynamics (two-body and J2) for a four-spacecraft formation, mission geometry (illumination, geometry-only science opportunities), and resource accounting, each with its physics acceptance tests. Phase 2 has started with isolated spacecraft agents exchanging messages over a modelled crosslink network. It contains **no** task-allocation, planning, or science-retrieval model yet, and no research results. Nothing here should be read as a validated or published finding.

The authoritative design document is **[`ASTRAMESH_MASTER_SPEC.md`](ASTRAMESH_MASTER_SPEC.md)** (v1.0). Where this README and the specification differ, the specification governs.

---

## The problem

The core challenge is **decision-making under incomplete information**. A satellite that stops transmitting might be failed, healthy but disconnected, or deliberately in a protective mode. Each simulated spacecraft agent must act on its own estimates and the messages it actually receives — never on the simulator's global truth — while respecting finite power, storage, communication, propulsion, and safety constraints.

## Primary research question

> Can a decentralized spacecraft constellation preserve useful scientific operations during uncertain spacecraft-health events, communication disruption, and hazardous space-weather conditions while keeping local protection and maneuver constraints satisfied?

The specification defines five testable hypotheses (H1–H5) covering fault-aware task planning, explicit health uncertainty, space-weather-aware protection, a local safety supervisor, and forecast-informed protection. **These are hypotheses, not promised outcomes**; the final contribution may be narrowed to one of them after literature review and baseline experiments.

## Research tracks

1. **Validated astrodynamics** — relative orbits, propagation (two-body first, then J2/drag), and resource-constrained maneuver modeling.
2. **Decentralized autonomy** — science-task allocation, network partitions, message delays, plan reconciliation, and graceful degradation.
3. **Intelligent state assessment** — probabilistic spacecraft-health inference, telemetry anomaly detection, and optional lightweight ML.
4. **Space-weather-aware protection** — a five-mode local supervisor (`NOMINAL`, `STORM_WATCH`, `PROTECTIVE`, `RECOVERY`, `SAFE`) that mission planning cannot override.
5. **Reproducible experiments** — strong classical baselines, external space-data sources, Monte Carlo evaluation, and honest reporting of failures and limitations.

Reinforcement learning is **optional**, not a requirement. ML is used for prediction and inference only, never as an unbounded controller.

## Reference mission (provisional values)

| Parameter | Starting value | Status |
|---|---|---|
| Spacecraft | 4 × 6U CubeSat-class abstractions | Approved |
| Orbit | ~525 km near-circular LEO, 97.5° inclination | Provisional — requires J2 validation |
| Formation | Along-track ("string-of-pearls"), ~20 km spacing | Provisional |
| Science | Simplified dual-frequency GNSS/TEC observation scheduling | Approved — a scheduling abstraction, not RO retrieval or tomography |

All physical and numerical parameters are starting points that must be validated; see §3 of the specification.

## Planned technology stack

| Area | Core / near-term |
|---|---|
| Language & environment | Python on Ubuntu 24.04 (WSL2), Git |
| Dependency management | `uv`, `pyproject.toml`, `uv.lock` |
| Configuration | YAML validated with pydantic (unknown keys rejected) |
| Numerics & physics | NumPy, SciPy; Astropy for time, frames, and units |
| Networking & discrete events | NetworkX, SimPy |
| Data | pandas, PyArrow, Xarray |
| Machine learning | scikit-learn (others only if justified) |
| Visualization | Matplotlib, Plotly |
| Testing | pytest, Hypothesis |
| Later / optional | Basilisk (validation), CVXPY + OSQP, atmospheric models, PyTorch |

Dependencies will be added incrementally, phase by phase, only when a tested requirement needs them (specification §11).

## Planned external data sources

ESA Anomaly Dataset (ESA-ADB), ESA OPS-SAT-AD, NOAA GloTEC, CelesTrak GP/OMM, UCAR COSMIC-2, NASA OMNI/SPDF, and NOAA SWPC/NCEI. **No datasets are included in this repository**; large raw data is kept out of Git, and every source will be recorded with version, hash, license, and caveats in a dataset registry (specification §8).

## Getting started

Requires [uv](https://docs.astral.sh/uv/). uv installs the pinned Python version (3.12) automatically.

```bash
git clone https://github.com/Abdullah-Muz/AstraMesh.git
cd AstraMesh
uv sync --locked                     # create the environment from uv.lock

uv run pytest                        # tests
uv run ruff check . && uv run mypy   # lint and type checks

# Phase 0 toy scenario: proves same-seed replay (not a mission model)
uv run astramesh validate configs/experiments/toy_heartbeat.yaml
uv run astramesh run configs/experiments/toy_heartbeat.yaml --out results/toy

# Phase 1 dynamics baseline: 4 spacecraft, 20 km in-train, 24 h, point mass + J2
uv run astramesh run configs/experiments/formation_24h_j2.yaml --out results/formation
uv run astramesh plot results/formation          # diagnostic figures in results/formation/figures

# Phase 1 mission geometry: the same formation + illumination + science opportunities
uv run astramesh run configs/experiments/mission_geometry_24h.yaml --out results/mission
uv run astramesh plot results/mission

# Phase 2 increment 1: isolated agents exchanging status over the crosslink network
uv run astramesh run configs/experiments/agent_network_24h.yaml --out results/network
```

A run writes `events.jsonl`, `summary.json`, `config.resolved.json`, and a provenance `manifest.json` (git commit, config hash, seeds, lockfile hash, artifact hashes). The formation scenarios also write `trajectory.csv` (sampled truth states), and the mission-geometry scenario writes `opportunities.json` (geometry-only science task records with energy and data costs) and a resource summary (battery, storage, Δv) in `summary.json`. See [`docs/EXPERIMENT_PROTOCOL.md`](docs/EXPERIMENT_PROTOCOL.md).

## Roadmap

| Phase | Focus | Status |
|---|---|---|
| 0 | Research and reproducibility foundation | Complete except the Priority A full-text literature review (in parallel; see [`docs/ROADMAP.md`](docs/ROADMAP.md)) |
| 1 | Validated four-spacecraft dynamics and mission geometry | Complete (Gate P1 signed off 2026-11-03) |
| 2 | Decentralized nominal science operations | In progress (agents and crosslink network; allocation after the literature review) |
| 3 | Deterministic faults and protection supervisor | Not started |
| 4 | External data and probabilistic/ML experiments | Not started |
| 5 | Storm-aware distributed recovery | Not started |
| 6 | Research conclusion and public demonstration | Not started |

Each phase has explicit exit gates defined in specification §13.

## Scope and integrity

AstraMesh is a **simulation and research project**. It is **not** a real satellite constellation, flight software, a flight-validated system, or a NASA/ESA collaboration, and it makes no claim of a novel algorithm before a full related-work comparison. Results will be reported as **simulated**, **model-based**, or **data-informed** as appropriate, and negative results will be reported as valid outcomes.

## Repository contents

| Path | Purpose |
|---|---|
| [`ASTRAMESH_MASTER_SPEC.md`](ASTRAMESH_MASTER_SPEC.md) | Authoritative research and engineering specification (v1.0) |
| [`docs/`](docs/) | Supporting documents: conventions, physics test plan, literature matrix, dataset registry, decision log, roadmap |
| [`src/astramesh/`](src/astramesh/) | Python package (`core/` clock, RNG, events, config; `dynamics/` validated truth dynamics, frames, time scales; `evaluation/` runner and manifests; `science/` region access and science opportunities; `resources/` energy, storage and Δv ledgers; `agents/` isolated spacecraft agents; `communications/` messages and crosslink network; `scenarios/` runnable scenarios; `visualization/` diagnostic plots) |
| [`scripts/studies/`](scripts/studies/) | Reference-error studies behind every physics test tolerance |
| [`configs/`](configs/) | Scenario configuration files (YAML) |
| [`tests/`](tests/) | Unit, integration, and regression tests |
| `data/` | Local, Git-ignored dataset area (no data committed) |
| `pyproject.toml`, `uv.lock`, `.python-version` | Project metadata and locked dependencies |
| `.github/workflows/ci.yml` | Continuous integration: lint, type check, tests, baseline smoke runs |
| [`LICENSE`](LICENSE) | MIT License — applies to source code |
| [`LICENSE-DOCS`](LICENSE-DOCS) | Creative Commons Attribution 4.0 International — applies to documentation |

## License

AstraMesh uses two licenses:

- **Code — [MIT License](LICENSE).** Applies to all source code, tests, scripts, configuration files, and other software in this repository unless a file states otherwise.
- **Documentation — [CC BY 4.0](LICENSE-DOCS).** Applies to [`ASTRAMESH_MASTER_SPEC.md`](ASTRAMESH_MASTER_SPEC.md), this README, the contents of `docs/`, and written reports, diagrams, and figures, unless a file states otherwise.

Copyright © 2026 Abdullah Muzher.

**Attributing the documentation:** when reusing or adapting documentation, credit it as, for example:

> *AstraMesh Master Research & Engineering Specification* by Abdullah Muzher, https://github.com/Abdullah-Muz/AstraMesh, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Indicate if changes were made.

**Not covered:** external datasets, third-party publications, and other third-party material referenced by this project remain under their owners' terms and are not relicensed here.

# Roadmap and Gate Tracking

> **Owner:** Abdullah Muzher · **Status:** ACTIVE · **Spec:** §13, §14, §17 · **Last updated:** 2026-11-05

Phase definitions and exit gates are defined in spec §13; this file tracks status only.

| Phase | Focus | Status |
|---|---|---|
| 0 | Research and reproducibility foundation | **Complete except** Priority A full-text review (8 of 10 items drafted from full text, owner verification pending; P01 unavailable, P21 paywalled; see `LITERATURE_REVIEW.md`) |
| 1 | Validated four-spacecraft dynamics and mission geometry | **Complete**: Gate P1 signed off 2026-11-03 (DL-037); open follow-ups listed there |
| 2 | Decentralized nominal science operations | **Complete**: Gate P2 signed off 2026-11-03 (DL-049); open follow-ups listed there |
| 3 | Deterministic faults and protection supervisor | **Complete**: Gate P3 signed off 2026-11-04 (DL-061); open follow-ups listed there |
| 4 | External data and probabilistic/ML experiments | **In progress** (DL-062) |
| 5 | Storm-aware distributed recovery | Not started |
| 6 | Research conclusion and public demonstration | Not started |

## Phase 0 deliverables (spec §17)

| # | Deliverable | Status |
|---|---|---|
| 1 | Repository and `astramesh` package | Done |
| 2 | `uv`, pinned Python, pytest, Hypothesis, minimal CPU dependency set | Done |
| 3 | Master spec + linked docs with owners/requirements | Done (this `docs/` set) |
| 4 | Validated scenario-config schema; units/time/frame conventions | Done — conventions approved 2026-11-03 |
| 5 | Deterministic clocks, random seeds, event logging, result manifests | Done |
| 6 | Tiny deterministic scenario proving same-seed replay; basic CI | Done — replay verified on Windows, WSL2, and GitHub Actions |
| 7 | First literature-matrix entries; initial physics-test design | Priority A metadata entered; physics test plan approved 2026-11-03 |
| 8 | License/terms documentation for external data; no large downloads | Registry started; 2 of 7 licenses checked; nothing downloaded |

## Phase 1 increments

| # | Increment | Status |
|---|---|---|
| 1 | D0 core: frame-tagged states, WGS 84 constants, Kepler elements, universal-variable analytic reference, fixed-step RK4 multi-spacecraft propagator, RIC frame; reference-error studies; PA-01/02/03, PA-04 (RIC), PA-05 (constructors), PA-09 (gravity-only), PA-10 | **Done** — commit `4dd6010`, CI green; tolerances approved 2026-11-03 |
| 2 | Astropy time scales (UTC→TT/UT1) and GCRS↔ITRS with IERS version in manifest; PA-04 (ITRS) | **Done**: commit `934b8e5`, CI passing; ITRS tolerances approved 2026-11-03 |
| 3 | Formation initialization from consistent elements (~20 km along-track); PA-06; CW cross-check PA-07 | **Done**: commit `abc50c2`, CI passing; tolerances approved 2026-11-03 |
| 4 | J2 (D1) and secular nodal-precession check PA-08; Part A SSO question | **Done**: commit `7cad3da`, CI passing; tolerances approved |
| 4b | Mean-element initialization (DL-026/027): reference orbit as mean elements; mean-matched formation | **Done**: commit `7c8f7dd`, CI passing; tolerances approved 2026-11-03 |
| 5 | Dynamics scenario config (unit-suffixed schema), 24 h baseline run with manifest `dynamics_model`, basic plots | **Done**: commits `a700f54` and `428fb65` (DL-031 CPU-independence fix), CI passing |
| 6a | Mission geometry: per-tick ERFA Earth rotation, Sun and cylindrical shadow, WGS 84 region access, geometry-only opportunities (spec §3.4), `mission_geometry` scenario, plots; Part A Q4 eclipse fraction | **Done**: commit `298dc87`, CI passing; §B.7 tolerances, DL-032 and DL-033 approved 2026-11-03 |
| 6b | Finite resource accounting (energy with eclipse, storage, Δv); Part A Q4 power balance and Q5 propulsion feasibility | **Done**: commit `5493310`, CI passing; values (DL-035, DL-036) and §B.8 approved 2026-11-03 |

## Phase 2 increments

| # | Increment | Status |
|---|---|---|
| 1 | Isolated `SpacecraftAgent`s, message schema, NetworkX G(t) crosslinks, SimPy kernel, acceptance rules, isolation tests (`agent_network` scenario) | **Done**: commit `414bf2d`, CI passing; values and acceptance rules (DL-040) approved 2026-11-03 |
| 2a | Task catalogue and utility (DL-041), live battery/storage truth, agent plan execution with resource checks, truth scoring, B0 static scheduler, S00 scenario (`nominal_operations`) | **Done**: commit `a48de98`, CI passing; DL-043 approved 2026-11-03 |
| 2b | B1 centralized reference (SciPy `milp`, DL-042, DL-044) | **Done**: commit `5fa618c`, CI passing |
| 3 | B2 one-shot auction, B3 CBBA (DL-045, DL-046) | **Done**: commit `eb9ee25`, CI passing |
| 4 | S00 comparison of B0–B3 under message loss (DL-047, DL-048) | **Done**: results commit `60fbadf` (script `dafa540`); reviewed and approved 2026-11-03 |

## Phase 3 increments

| # | Increment | Status |
|---|---|---|
| 1 | Fault schema and deterministic injection: unavailable, comms outage, partition, payload and power degradation; scenarios S01–S05 + power fault | **Done**: commit `9bcd8ee`, CI passing |
| 2 | Health beliefs (§5.4), timeout baseline, B4 fault-aware redistribution, B3 + timeout | **Done**: commit `362d648`, CI passing |
| 3 | Supervisor NOMINAL/PROTECTIVE/SAFE, command filtering, planner cannot override | **Done**: commit `85b8cff`, CI passing |
| 4 | Full five-mode machine: STORM_WATCH, RECOVERY, three risk dimensions, hysteresis, dwell, invalid-input policy | **Done**: commit `e3c675f`, CI passing |
| 5 | Fault-scenario comparison (S01–S10; S06 deferred) | **Done**: script `bb2ea8e`, B4 fix `311477a` (DL-059), 600-run results in [`docs/results/FAULT_COMPARISON.md`](results/FAULT_COMPARISON.md) (DL-060); reviewed and approved 2026-11-04 |

## Phase 4 increments

| # | Increment | Status |
|---|---|---|
| 1 | Data registry and pinned fetch: OPS-SAT-AD, OMNI 1-min and GOES-18 SGPS for May 2024; ESA-ADB sized only | Implemented (DL-063) |
| 2 | Anomaly-detection benchmark on OPS-SAT-AD, independent of the simulation; official and time-ordered splits | **Done**: code `c557c6b` (DL-064), results `f0760f8` in [`docs/results/OPSSAT_BENCHMARK.md`](results/OPSSAT_BENCHMARK.md) (DL-065); approved 2026-11-05 |
| 3 | Calibrated probabilistic health model; adapter from detector scores to simulated beliefs; comparison with the timeout on S01/S03/S04 | Code `42c24a9` (DL-066); 440-run results in [`docs/results/HEALTH_COMPARISON.md`](results/HEALTH_COMPARISON.md) (DL-067), awaiting review |
| 4 | May 2024 storm replay (OMNI, GOES protons) as S11, no future-data leakage; bounded COSMIC-2/GloTEC context | Not started |
| 5 | Gate P4 comparison write-up | Not started |

## Gate P4 checklist (spec §13)

- [ ] Data licences/provenance and train/test partitions documented (increment 1: licences, hashes and measured facts in `DATASET_REGISTRY.md`; increment 2: OPS-SAT-AD official and time splits, per-channel counts and CV folds in the DS-02 record; storm-data partitions in increment 4)
- [ ] Anomaly results independently benchmarked (increment 2: real OPS-SAT telemetry, independent of the simulation, reproduces the published results; official and time splits; DL-065)
- [ ] Synthetic-vs-real interface explicit (increment 3: the pinned score-sensor file is the only link from OPS-SAT data to the simulation; real and synthetic parts and the untested assumptions are listed in `HEALTH_COMPARISON.md`; the storm-data interface comes in increment 4)
- [ ] Preliminary health/forecast comparisons complete with uncertainty (increment 3: H-A/H-B/H-C health comparison with 95 % t-intervals, n = 10, DL-067; the forecast comparison comes in increment 4)

## Gate P3 checklist (spec §13)

- [x] SAFE always overrides (increment 3: SAFE checked first; property test + override tests from every mode)
- [x] Invalid forecast behaviour defined (DL-056: never releases a protected mode, never triggers PROTECTIVE alone, NOMINAL → STORM_WATCH after 10 min; tested)
- [x] No mode chatter under brief noise (five-mode machine: hysteresis on both watch and protect, 30 min release dwells, 5 min minimum recovery; 3 h jitter test gives one entry and no release)
- [x] False outage does not count as confirmed fatal failure (increment 2: CONFIRMED_FAILED only from ground notices; property test and 0 confirmations while available in all 600 fault-comparison runs, including the S04 false outage and the S05/S09 partitions)
- [x] Distributed task replanning cannot defeat protection (increment 3: supervisor gates every payload command; property test with arbitrary messages and plan uplinks; payload steps in protected modes = 0 in all 600 fault-comparison runs, including S07–S10 with CBBA, B4 and B3 + timeout reallocating; S10 shows SAFE overriding PROTECTIVE)

## Gate P2 checklist (spec §13)

- [x] Each agent acts only on local state/delivered messages (static import rule and object-graph checks, shown to catch planted leaks, for status, B0/B1 execution and B3 CBBA agents)
- [x] No privileged leakage (agents receive only own sensor packets, own plan or catalogue, and delivered messages; B1's truth use is confined to the external reference planner and flagged `privileged_information`)
- [x] Baseline comparisons operate on identical tasks/resources (one base configuration; catalogue checked identical across B0–B3 for every seed in the 120-run comparison)
- [x] Unhandled network messages cannot alter plans (acceptance rules incl. `malformed_payload`; property tests interleave arbitrary messages with plan execution; B3 accepts only well-formed `plan_sync`)

## Gate P1 checklist (spec §13)

- [x] Independent propagation and convergence checks pass (PA-01–PA-04, PA-08; `NUMERICAL_MISSION_DESIGN.md` §B.2–§B.5)
- [x] Four initial orbits are consistent (PA-06; mean-element initialization §B.6)
- [x] 24 h baseline completes (`formation_24h_j2.yaml`; regression test and CI smoke run)
- [x] Science eligibility can be explained by modeled geometry (6a; independently checked against Astropy AltAz, `tests/physics_validation/test_mission_geometry.py`; §B.7 approved 2026-11-03)
- [x] Fixed seeds replay identically (scenario replay test, pinned digests; scope DL-029)

## Gate P0 checklist (spec §13)

- [x] Clean environment setup (`uv sync --locked`)
- [x] Unit-test runner and CI passing (first CI run on commit `0522165`: success)
- [x] Repeatable toy experiment (byte-identical replay, golden hash)
- [ ] First priority references **reviewed** — metadata only so far; full-text review not started
- [x] Exact simulation epoch/frames/units specified — `CONVENTIONS.md`, approved 2026-11-03
- [x] Physics acceptance plan signed off — `NUMERICAL_MISSION_DESIGN.md` Part B, approved 2026-11-03

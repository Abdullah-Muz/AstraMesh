# Roadmap and Gate Tracking

> **Owner:** Abdullah Muzher · **Status:** ACTIVE · **Spec:** §13, §14, §17 · **Last updated:** 2026-11-13

Phase definitions and exit gates are defined in spec §13; this file tracks status only.

| Phase | Focus | Status |
|---|---|---|
| 0 | Research and reproducibility foundation | **Complete except** Priority A full-text review (8 of 10 items drafted from full text, owner verification pending; P01 unavailable, P21 paywalled; see `LITERATURE_REVIEW.md`) |
| 1 | Validated four-spacecraft dynamics and mission geometry | **Complete**: Gate P1 signed off 2026-11-03 (DL-037); open follow-ups listed there |
| 2 | Decentralized nominal science operations | **Complete**: Gate P2 signed off 2026-11-03 (DL-049); open follow-ups listed there |
| 3 | Deterministic faults and protection supervisor | **Complete**: Gate P3 signed off 2026-11-04 (DL-061); open follow-ups listed there |
| 4 | External data and probabilistic/ML experiments | **Complete**: Gate P4 signed off 2026-11-10 (DL-076); open follow-ups listed there |
| 5 | Storm-aware distributed recovery | **Complete**: Gate P5 signed off 2026-11-13 (DL-110); open follow-ups listed there |
| 6 | Research conclusion and public demonstration | **In progress** (DL-111) |

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
| 8 | License/terms documentation for external data; no large downloads | Done in Phase 0 (registry started, no downloads); since Phase 4 every dataset used has verified terms (`DATASET_REGISTRY.md`) |

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

## Phase 6 increments (DL-111)

| # | Increment | Status |
|---|---|---|
| 1 | Held-out storm design and data: storms after May 2024 chosen by a rule fixed in advance, new pinned GOES-18 and OMNI data, frozen forecasts and methods; expectations stated before any run | **In progress**: DL-111 approved 2026-11-13; design DL-113 proposed (reserve one third, seeds 1 – 3, v3-0-3 storms reported separately) |
| 2 | Basilisk comparison (spec §4.1 D3): selected propagation cases (two-body, J2, drag) with tolerances fixed before running | Not started |
| 3 | Negative-result analysis: the open questions carried in `GATE_P5.md`, answered by recorded diagnostics | Not started |
| 4 | Plots from committed results and an MP4 demonstration from a recorded storm run | Not started |
| 5 | Technical report (`docs/REPORT.md`), README and Gate P6 write-up | Not started |

## Gate P6 checklist (spec §13)

- [ ] Every reported result traces to a commit/config/data version
- [ ] Limitations disclosed
- [ ] Novelty only claimed if supported by full-text prior-work comparison and experimental evidence

## Phase 5 increments (DL-077)

| # | Increment | Status |
|---|---|---|
| 1 | Literature and design for the G3 candidate (decentralized protection-mode coordination); falsifiable hypothesis, baselines, scenarios, metrics and the tuning/test split fixed before any implementation | **Done**: literature `7a38007`, `1e40e87`; design DL-078 (`dee5190`), RL amendment DL-079 (`e88c6e5`); approved 2026-11-10 |
| 2 | Atmospheric drag: D1 nominal drag with validation tests; then D2 storm-time density (separate approval: new dependency and a new pinned F10.7/Ap dataset) | **Done**: D1 design DL-080, code `de82cca` (DL-081), results `7fbb215` (DL-083); D2 design `53552c9` (DL-084), code `460ccaf` (DL-085), results `505b8fc` (DL-086); approved 2026-11-10 |
| 2b | Formation keeping against differential drag (DL-087): along-track spacing control with the 0.5 mN cold-gas thruster, Δv, propellant and energy charged to the ledgers; validation tests and a recorded closed-loop drift study | **Done**: design DL-087 (option A), code `d7ab81a` (DL-088), results in [`docs/results/FORMATION_KEEPING.md`](results/FORMATION_KEEPING.md) (DL-089); approved 2026-11-10 – 11 |
| 3 | Per-spacecraft risk (DL-082): heterogeneous knowledge (late, stale or missing inputs; partitions) and payload tolerances; position-based risk built and its (small) differences reported | **Done**: design DL-090 (`be2a800`), values DL-091 and code `45430aa` (DL-092), results `0388e4e` in [`docs/results/PER_SPACECRAFT_RISK.md`](results/PER_SPACECRAFT_RISK.md) (DL-093); approved 2026-11-11 |
| 4 | Candidate method (as a policy slot, DL-079) and baselines; combined scenarios (S11 with per-spacecraft risk, storm + partition, storm + critical fault, tighter schedule) | **In progress**: design DL-094 approved 2026-11-11 (February tuning storm, B4 correction, B3 secondaries on 5 seeds); code `a7b2046` (DL-095); tuning `fd5abc3` (DL-096); **Done**: [`docs/results/HANDOVER_COMPARISON.md`](results/HANDOVER_COMPARISON.md) (DL-097); approved 2026-11-12. Room for methods (DL-098 scope A): evaluation storms `f25e224` (DL-099); [`docs/results/MULTI_STORM.md`](results/MULTI_STORM.md) (DL-100); approved 2026-11-12. Spread constellation checked first (owner choice): protection does not separate (DL-101); next: shorter, pass-following protection (DL-101, approved 2026-11-12; scripts `29f1b3f`, DL-102; tuning [`docs/results/PROTECTION_TUNING.md`](results/PROTECTION_TUNING.md), DL-103) before 4b; evaluation storms [`docs/results/PROTECTION_COMPARISON.md`](results/PROTECTION_COMPARISON.md): rejected for both planners (DL-104). Spread formation previewed: no room (DL-105). **Closed** (DL-105, approved 2026-11-13): neither candidate beats the baseline; the storm loss is set by geometry |
| 4b | RL policies (DL-079): task handover first, then early protection timing; algorithm, library and training budget fixed in an RL design entry; the supervisor keeps the final say | **Dropped** (DL-105, approved 2026-11-13; amends DL-079): no room for either role |
| 5 | Frozen comparison with ablations; Gate P5 write-up | Design DL-106 approved 2026-11-13: four ablations (no look-ahead, no forecast, no hysteresis, no reconciliation) on five storms, both planners; recorded spread run; recorded diagnostics and wording fixes (F1 – F3); then Gate P5 write-up. Code DL-107; results DL-108 ([`ABLATIONS.md`](results/ABLATIONS.md), [`SPREAD_FORMATION.md`](results/SPREAD_FORMATION.md)); approved 2026-11-13; **Done**: Gate P5 write-up [`GATE_P5.md`](results/GATE_P5.md) `eab2682` (DL-109); approved 2026-11-13 |

Maneuvers return as rule-based formation keeping (increment 2b, DL-086 meets the DL-082 condition); low-thrust maneuver *optimization* stays deferred (DL-077); attitude-based drag control is out of scope (spec §16).

## Gate P5 checklist (spec §13)

- [x] Combined failure/science/protection scenarios reproducible (storm + forecast outage, + 2 + 2 partition, + critical fault in DL-097; 729 runs recorded from clean commits; every rerun of an earlier configuration matched it; [`GATE_P5.md`](results/GATE_P5.md))
- [x] No claims of radiation or flight safety beyond simulation assumptions (hazard modelled from a GEO proxy flux, a dipole cutoff model and synthetic tolerances; one phrase reworded, DL-109)
- [x] Baseline and candidate methods compared fairly (candidates fixed before tuning, tuned on a training-period storm, tested on held-out and out-of-sample storms; asymmetries stated in `GATE_P5.md`)

## Phase 4 increments

| # | Increment | Status |
|---|---|---|
| 1 | Data registry and pinned fetch: OPS-SAT-AD, OMNI 1-min and GOES-18 SGPS for May 2024; ESA-ADB sized only | **Done**: commit `5aa7e8b` (DL-062, DL-063); approved |
| 2 | Anomaly-detection benchmark on OPS-SAT-AD, independent of the simulation; official and time-ordered splits | **Done**: code `c557c6b` (DL-064), results `f0760f8` in [`docs/results/OPSSAT_BENCHMARK.md`](results/OPSSAT_BENCHMARK.md) (DL-065); approved 2026-11-05 |
| 3 | Calibrated probabilistic health model; adapter from detector scores to simulated beliefs; comparison with the timeout on S01/S03/S04 | **Done**: code `42c24a9` (DL-066), results `7f01b8e` in [`docs/results/HEALTH_COMPARISON.md`](results/HEALTH_COMPARISON.md) (DL-067); approved 2026-11-05 |
| 4 | May 2024 storm replay (OMNI, GOES protons) as S11, no future-data leakage; bounded COSMIC-2/GloTEC context | **Done**: design DL-068; training data and loaders `a1e839c`; forecasts and S11 replay `fc27fa3` (DL-069); metric fix `00372d9` (DL-070); results `c8451ca` in [`docs/results/STORM_FORECAST.md`](results/STORM_FORECAST.md) and [`docs/results/STORM_REPLAY.md`](results/STORM_REPLAY.md) (DL-071); approved 2026-11-09. COSMIC-2/GloTEC context left out of Phase 4 (DL-071) |
| 5 | Gate P4 comparison write-up | **Done**: [`docs/results/GATE_P4.md`](results/GATE_P4.md) `c598a4f` (DL-075); no new runs; approved 2026-11-10 |

## Gate P4 checklist (spec §13)

- [x] Data licences/provenance and train/test partitions documented (increment 1: licences, hashes and measured facts in `DATASET_REGISTRY.md`; increment 2: OPS-SAT-AD official and time splits, per-channel counts and CV folds in the DS-02 record; increment 4: DS-08/DS-09 training-only, forward-chaining folds, May 2024 held out, in the DS-06 – DS-09 records and `STORM_FORECAST.md`)
- [x] Anomaly results independently benchmarked (increment 2: real OPS-SAT telemetry, independent of the simulation, reproduces the published results; official and time splits; DL-065)
- [x] Synthetic-vs-real interface explicit (increment 3: the pinned score-sensor file is the only link from OPS-SAT data to the simulation; real and synthetic parts and the untested assumptions are listed in `HEALTH_COMPARISON.md`; increment 4: the pinned S11 series file is the only link from the storm data, listed in `STORM_REPLAY.md`)
- [x] Preliminary health/forecast comparisons complete with uncertainty (increment 3: H-A/H-B/H-C health comparison with 95 % t-intervals, n = 10, DL-067; increment 4: forecast skill on chronological folds and the held-out storm week, with day-bootstrap and Clopper-Pearson 95 % intervals and paired model differences (DL-072, DL-073), and the S11 P-A/P-B/P-C comparison, DL-071. The S11 runs are deterministic apart from message loss, which did not matter, so the uncertainty is stated as one storm plus sensitivity variants, not as intervals)

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

# Roadmap and Gate Tracking

> **Owner:** Abdullah Muzher · **Status:** ACTIVE · **Spec:** §13, §14, §17 · **Last updated:** 2026-11-03

Phase definitions and exit gates are defined in spec §13; this file tracks status only.

| Phase | Focus | Status |
|---|---|---|
| 0 | Research and reproducibility foundation | **Complete except** Priority A full-text review (proceeding in parallel, DL-016) |
| 1 | Validated four-spacecraft dynamics and mission geometry | **In progress** (DL-016). Increment 1 (D0 two-body core) implemented |
| 2 | Decentralized nominal science operations | Not started |
| 3 | Deterministic faults and protection supervisor | Not started |
| 4 | External data and probabilistic/ML experiments | Not started |
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
| 4b | Mean-element initialization (DL-026/027): reference orbit as mean elements; mean-matched formation | Implemented; §B.6 tolerances pending owner review |
| 5 | Dynamics scenario config (unit-suffixed schema), 24 h baseline run with manifest `dynamics_model`, basic plots | Not started |
| 6 | Synthetic science opportunities from modeled geometry; finite resource accounting (energy, storage, Δv) | Not started |

## Gate P0 checklist (spec §13)

- [x] Clean environment setup (`uv sync --locked`)
- [x] Unit-test runner and CI passing (first CI run on commit `0522165`: success)
- [x] Repeatable toy experiment (byte-identical replay, golden hash)
- [ ] First priority references **reviewed** — metadata only so far; full-text review not started
- [x] Exact simulation epoch/frames/units specified — `CONVENTIONS.md`, approved 2026-11-03
- [x] Physics acceptance plan signed off — `NUMERICAL_MISSION_DESIGN.md` Part B, approved 2026-11-03

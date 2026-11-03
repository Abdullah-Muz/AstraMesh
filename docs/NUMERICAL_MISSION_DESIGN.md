# Numerical Mission Design and Physics Acceptance Plan

> **Owner:** Abdullah Muzher · **Status:** DRAFT — physics acceptance plan requires sign-off for Gate P0 · **Spec:** §3.2–§3.3, §4.1, §4.4, §14.3, §18 · **Last updated:** 2026-11-03

## Purpose

1. Record the numerical derivations behind the reference mission (orbit, formation geometry, resource budgets) as they are worked out.
2. Define the **Phase 1 physics acceptance tests** *before* the propagator is written, so the tests cannot be tuned to fit the implementation.

No dynamics code exists yet. Nothing in this document is a measured result.

## Part A — Mission design derivations

Not started. To be filled in Phase 1, answering open validation questions 1, 2, 4, and 5 (spec §18):

- [ ] Near-sun-synchronous behaviour of 525 km / 97.5° under J2 (nodal precession rate vs. the ~0.9856 °/day target).
- [ ] Orbital elements that realize ~20 km along-track spacing without unintended secular drift.
- [ ] Eclipse fraction and eclipse-aware power balance for the 25 W / 100 Wh candidate.
- [ ] Feasibility of the 0.5 mN / 5 m/s propulsion candidate (spec §3.3 notes ~33.3 h of accumulated thrust for 5 m/s).

## Part B — Phase 1 physics acceptance test design

**Tolerance policy (spec §4.4):** numerical tolerances are **not** set in this document. Each is set from an independent reference-error study recorded here before the test is enabled, and must state how it was derived. Until then, a tolerance is `TBD (reference study pending)`.

| ID | Test | Method | Independent reference | Tolerance | Test location |
|---|---|---|---|---|---|
| PA-01 | Two-body propagation accuracy | Propagate each spacecraft over the defined horizon (24 h nominal) and compare positions/velocities | Analytic Kepler solution (universal-variable or eccentric-anomaly form), independently implemented; optionally a high-accuracy integrator at tight tolerances | TBD (reference study pending) | `tests/physics_validation/` |
| PA-02 | Conservation in the unperturbed model | Track specific orbital energy and specific angular-momentum vector over the horizon | Exact invariants of the two-body problem | TBD — relative drift bound from integrator error study | `tests/physics_validation/` |
| PA-03 | Step-size convergence | Repeat a fixed scenario at Δt, Δt/2, Δt/4; check that the error decreases at the integrator's expected order | Richardson-style comparison against the finest run and PA-01 analytic reference | Observed order within a stated band of the theoretical order | `tests/physics_validation/` |
| PA-04 | Frame round trips | ECI → ITRS → ECI and ECI → RIC → ECI for randomized states (Hypothesis) | Identity; Astropy transforms as an external check | TBD — set from float64 round-off study | `tests/unit/`, `tests/physics_validation/` |
| PA-05 | Units are explicit | Constructors reject ambiguous inputs; configs reject unit-less physical fields | Code inspection + schema tests | Pass/fail | `tests/unit/` |
| PA-06 | Formation initialization | Four initial states from consistent orbital elements reproduce the intended along-track spacing and phasing | Independent element → state → element round trip; geometric check of the spacing | TBD | `tests/physics_validation/` |
| PA-07 | Relative-motion cross-check | Compare relative motion against Clohessy–Wiltshire/Hill **only** within its assumptions (circular reference, small separation, short horizon) | CW closed-form solution | TBD — must reflect known CW linearization error at ~20 km | `tests/physics_validation/` |
| PA-08 | J2 before SSO claims | With J2 enabled, measured nodal precession matches the analytic secular J2 rate before any sun-synchronous claim is made | Analytic secular J2 formula | TBD | `tests/physics_validation/` |
| PA-09 | Determinism | Gravity-only and zero-thrust runs are bit-for-bit repeatable with the same config/seeds | Replay comparison (as already done for the Phase 0 toy scenario) | Exact equality | `tests/regression/` |
| PA-10 | Visible failure on invalid input | NaN/Inf states, non-physical parameters (e.g. r below Earth radius, e ≥ 1 for an orbit expected to be bound) raise explicit errors | Negative tests | Pass/fail | `tests/unit/` |

### Reference-error studies to perform before enabling tolerances

- [ ] Characterize float64 round-off for the analytic Kepler reference over 24 h (PA-01, PA-02).
- [ ] Characterize the chosen integrator's error constant and order (PA-03).
- [ ] Quantify CW linearization error at 20 km separation over the test horizon (PA-07).

### Sign-off

| Item | Decision | Date |
|---|---|---|
| Test list PA-01 … PA-10 | ☐ approved | |
| Tolerance policy (set only from reference studies) | ☐ approved | |

# Numerical Mission Design and Physics Acceptance Plan

> **Owner:** Abdullah Muzher · **Status:** Part B (physics acceptance plan) APPROVED 2026-11-03; §B.2 D0 reference studies recorded, derived tolerances PROPOSED (owner review); Part A not started · **Spec:** §3.2–§3.3, §4.1, §4.4, §14.3, §18 · **Last updated:** 2026-11-03

## Purpose

1. Record the numerical derivations behind the reference mission (orbit, formation geometry, resource budgets) as they are worked out.
2. Define the **Phase 1 physics acceptance tests** *before* the propagator is written, so the tests cannot be tuned to fit the implementation.

Phase 1 increment 1 (D0 two-body core) is implemented in `src/astramesh/dynamics/`. The only measured results in this document are the numerical reference-error studies in §B.2. They are integrator/round-off characterizations, not mission results.

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
| PA-01 | Two-body propagation accuracy | Propagate each spacecraft over the defined horizon (24 h nominal) and compare positions/velocities | Analytic Kepler solution (universal-variable or eccentric-anomaly form), independently implemented; optionally a high-accuracy integrator at tight tolerances | **Proposed** §B.2.4 (0.9 m / 1e-3 m/s circular; 0.5 m / 4e-4 m/s e = 0.1) | `tests/physics_validation/test_two_body.py` |
| PA-02 | Conservation in the unperturbed model | Track specific orbital energy and specific angular-momentum vector over the horizon | Exact invariants of the two-body problem | **Proposed** §B.2.4 | `tests/physics_validation/test_two_body.py` |
| PA-03 | Step-size convergence | Repeat a fixed scenario at Δt, Δt/2, Δt/4; check that the error decreases at the integrator's expected order | Richardson-style comparison against the finest run and PA-01 analytic reference | **Proposed** observed order in [3.9, 5.1] at 20/10/5 s (§B.2.3) | `tests/physics_validation/test_two_body.py` |
| PA-04 | Frame round trips | ECI → ITRS → ECI and ECI → RIC → ECI for randomized states (Hypothesis) | Identity; Astropy transforms as an external check | RIC: **Proposed** 0.5 ε‖x_chief‖ (§B.2.5). ITRS: not implemented yet | `tests/physics_validation/test_frames_ric.py` |
| PA-05 | Units are explicit | Constructors reject ambiguous inputs; configs reject unit-less physical fields | Code inspection + schema tests | Pass/fail. Constructors done; dynamics config schema pending | `tests/unit/test_dynamics_inputs.py` |
| PA-06 | Formation initialization | Four initial states from consistent orbital elements reproduce the intended along-track spacing and phasing | Independent element → state → element round trip; geometric check of the spacing | TBD | `tests/physics_validation/` |
| PA-07 | Relative-motion cross-check | Compare relative motion against Clohessy–Wiltshire/Hill **only** within its assumptions (circular reference, small separation, short horizon) | CW closed-form solution | TBD — must reflect known CW linearization error at ~20 km | `tests/physics_validation/` |
| PA-08 | J2 before SSO claims | With J2 enabled, measured nodal precession matches the analytic secular J2 rate before any sun-synchronous claim is made | Analytic secular J2 formula | TBD | `tests/physics_validation/` |
| PA-09 | Determinism | Gravity-only and zero-thrust runs are bit-for-bit repeatable with the same config/seeds | Replay comparison (as already done for the Phase 0 toy scenario) | Exact equality (gravity-only done, golden SHA-256 pinned) | `tests/regression/test_two_body_determinism.py` |
| PA-10 | Visible failure on invalid input | NaN/Inf states, non-physical parameters (e.g. r below Earth radius, e ≥ 1 for an orbit expected to be bound) raise explicit errors | Negative tests | Pass/fail | `tests/unit/test_dynamics_inputs.py` |

### Reference-error studies to perform before enabling tolerances

- [x] Characterize float64 round-off for the analytic Kepler reference over 24 h (PA-01, PA-02). See §B.2.1.
- [x] Characterize the chosen integrator's error constant and order (PA-03). See §B.2.2–§B.2.3.
- [x] Float64 round-off of the RIC round trip (PA-04, RIC part). See §B.2.5.
- [ ] Float64 round-off of the ITRS round trip (PA-04, ITRS part). Needs Astropy (next increment).
- [ ] Quantify CW linearization error at 20 km separation over the test horizon (PA-07).

## B.2 D0 reference-error studies (2026-11-03)

**Reproduce:** `uv run python scripts/studies/d0_reference_errors.py`. It is deterministic and runs in about 15 s. **Environment:** Python 3.12.3, NumPy 2.5.4, x86_64, Ubuntu 24.04 on WSL2. **Constants:** WGS 84 GM = 3.986004418e14 m³/s², a = 6 378 137.0 m (`src/astramesh/dynamics/constants.py`). These values come from NGA.STND.0036 Table 3.1, but the citation has **not yet been checked against the source document**.

**Implementation under test:**

- **Integrator:** fixed-step classical RK4 on the integer-ns clock grid, point-mass two-body (`dynamics/twobody.py`).
- **Reference:** universal-variable Lagrange f/g with Stumpff functions (Curtis), Newton on χ (`dynamics/kepler.py`). It shares no code with the integrator and uses no orbital elements.

**Test orbits** (horizon 24 h):

| Case | a | e | i | Ω, ω, ν₀ | Period |
|---|---|---|---|---|---|
| `ref_525km_circular` | R⊕ + 525 km | 0 | 97.5° | 0°, 0°, 0° | 5 707.96 s |
| `eccentric_e0.1` | 8 000 km | 0.1 | 51.6° | 40°, 30°, 10° | 7 121.08 s |

### B.2.1 Analytic-reference uncertainty

The universal-variable reference (one jump from t₀) is compared every 600 s with a second, independent analytic route: advance the mean anomaly, solve Kepler's equation, then convert elements to a state.

| Case | max ‖Δr‖ UV vs elements | max ‖Δv‖ | max ‖Δr‖ UV one-jump vs 8 640 chained 10 s jumps |
|---|---|---|---|
| circular | 3.6e-7 m | 4.2e-10 m/s | 1.4e-4 m |
| e = 0.1 | 1.6e-6 m | 1.5e-9 m/s | 6.5e-6 m |

The two analytic routes agree at the micrometre level, which bounds the reference's own error. Chaining many short jumps accumulates round-off, so the tests always use **one jump from t₀**. The self-consistency tolerance is **1e-5 m** (≥ 6× the observed value; round-off only). This is ≤ 1e-3 of every PA-01 position tolerance, so reference error cannot mask integrator error.

### B.2.2 RK4 error vs step size (24 h; max over all grid points)

| Step | circular max ‖Δr‖ | circular max ‖Δv‖ | circular rel. energy drift | circular rel. ‖Δh‖ | e = 0.1 max ‖Δr‖ | e = 0.1 max ‖Δv‖ | e = 0.1 rel. energy drift | e = 0.1 rel. ‖Δh‖ |
|---|---|---|---|---|---|---|---|---|
| 80 s | 7 790 m | 8.58 m/s | 1.4e-5 | 7.0e-6 | 2 849 m | 2.90 m/s | 5.2e-6 | 2.3e-6 |
| 40 s | 271 m | 0.299 m/s | 4.4e-7 | 2.2e-7 | 102 m | 0.105 m/s | 1.7e-7 | 7.2e-8 |
| 20 s | 10.2 m | 1.13e-2 m/s | 1.4e-8 | 6.8e-9 | 4.37 m | 4.15e-3 m/s | 5.4e-9 | 2.3e-9 |
| **10 s** | **0.429 m** | **4.73e-4 m/s** | **4.27e-10** | **2.13e-10** | **0.215 m** | **1.85e-4 m/s** | **1.90e-10** | **7.03e-11** |
| 5 s | 2.02e-2 m | 2.24e-5 m/s | 1.3e-11 | 6.7e-12 | 1.16e-2 m | 9.2e-6 m/s | 7.3e-12 | 2.2e-12 |
| 2.5 s | 1.07e-3 m | 1.18e-6 m/s | 4.2e-13 | 2.1e-13 | 6.7e-4 m | 5.0e-7 m/s | 3.1e-13 | 6.6e-14 |
| 1.25 s | 6.0e-5 m | 6.6e-8 m/s | 1.7e-14 | 8.7e-15 | 3.3e-5 m | 2.2e-8 m/s | 2.9e-14 | 1.5e-14 |

At the 10 s candidate step, the worst 24 h position error is under 0.5 m. That is small compared with the ~20 km formation spacing and the 100 km synthetic ISL range. The 10 s step is therefore adequate for the **two-body** model. It must be re-checked once J2 and drag are added.

### B.2.3 Observed order of convergence

Observed order is p = log₂(e(2h)/e(h)), computed from the final position error.

| Step pair | 80→40 | 40→20 | 20→10 | 10→5 | 5→2.5 | 2.5→1.25 |
|---|---|---|---|---|---|---|
| circular, position | 4.84 | 4.73 | 4.58 | 4.41 | 4.25 | 4.17 |
| circular, energy | 5.00 | 5.00 | 5.00 | 5.00 | 4.98 | 4.60 |
| e = 0.1, position | 4.79 | 4.65 | 4.48 | 4.32 | 4.21 | 4.61 |
| e = 0.1, energy | 4.98 | 4.94 | 4.82 | 4.70 | 4.56 | 3.42 |

**Interpretation.** RK4's per-step phase error is O(h⁵), which gives an O(h⁴) along-track error. Its per-step energy (amplitude) error is O(h⁶), which gives O(h⁵) energy drift; the measured energy order is 5.00. Energy drift changes the mean motion, so it adds an along-track error that grows ∝ t²·h⁵. Over 15 revolutions this term is significant at large steps. The observed position order therefore lies between 4 and 5 and falls toward 4 as h → 0, which is consistent with the circular case. At 1.25 s the e = 0.1 case reaches the round-off and reference-uncertainty floor: its energy drift is ~100 ε and its position error is ~10× the reference uncertainty. The orders there are not meaningful.

**PA-03 criterion (proposed):**

- Use steps of 20, 10, and 5 s, all well above the floors.
- Errors must decrease strictly.
- Each observed position order must lie in **[3.9, 5.1]**. That is the theoretical band [4, 5] with a ±0.1 margin. The measured values were 4.32–4.58.

### B.2.4 Tolerance-derivation rule and PA-01/PA-02 tolerances (proposed)

**Rule:**

- The tolerance is 2× the measured worst case at the nominal 10 s step over 24 h, rounded **up** to one significant figure.
- The reference's own uncertainty (§B.2.1) must be ≤ 1e-3 × the tolerance. This is enforced by `test_reference_uncertainty_is_negligible_vs_tolerance`.
- The factor of 2 leaves room for libm and CPU differences between machines. It is small enough that a real integrator regression (e.g. a wrong RK coefficient, which produces errors of order km) fails clearly.

| Case | Position | Velocity | Rel. energy drift | Rel. ‖Δh‖ drift |
|---|---|---|---|---|
| circular | 0.9 m | 1e-3 m/s | 9e-10 | 5e-10 |
| e = 0.1 | 0.5 m | 4e-4 m/s | 4e-10 | 2e-10 |

### B.2.5 RIC round-off (PA-04, RIC part)

The study used 20 000 random chiefs and deputies:

- **Chiefs:** a ∈ R⊕ + [200, 2000] km, e ∈ [0, 0.02], with any orientation.
- **Deputies:** within ±100 km and ±100 m/s of the chief.

The worst ECI→RIC→ECI round-trip errors were 1.2e-10 m and 1.1e-13 m/s. That is **0.077 ε‖r_c‖** and **0.074 ε‖v_c‖** (ε = 2.2e-16). The proposed tolerance is **0.5 ε‖x_c‖**, about 6.5× the observed worst case. A wider margin than the 2× rule is used because Hypothesis searches inputs adversarially beyond the study sample.

### Sign-off

| Item | Decision | Date |
|---|---|---|
| Test list PA-01 … PA-10 | ☑ approved — Abdullah Muzher | 2026-11-03 |
| Tolerance policy (set only from reference studies) | ☑ approved — Abdullah Muzher | 2026-11-03 |
| D0 derived tolerances, PA-03 order band, and derivation rule (§B.2.3–§B.2.5) | ☐ pending owner review | — |

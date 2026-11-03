# Numerical Mission Design and Physics Acceptance Plan

> **Owner:** Abdullah Muzher · **Status:** Part B (physics acceptance plan) APPROVED 2026-11-03; §B.2 D0 reference studies recorded, derived tolerances APPROVED 2026-11-03; §B.3 ITRS study recorded, tolerances APPROVED 2026-11-03; §B.4 formation/CW study recorded, tolerances APPROVED 2026-11-03; §B.5 J2 study recorded, tolerances PROPOSED; Part A questions 1–2 answered (decisions pending); Part A in progress · **Spec:** §3.2–§3.3, §4.1, §4.4, §14.3, §18 · **Last updated:** 2026-11-03

## Purpose

1. Record the numerical derivations behind the reference mission (orbit, formation geometry, resource budgets) as they are worked out.
2. Define the **Phase 1 physics acceptance tests** *before* the propagator is written, so the tests cannot be tuned to fit the implementation.

Phase 1 increment 1 (D0 two-body core) is implemented in `src/astramesh/dynamics/`. The only measured results in this document are the numerical reference-error studies in §B.2. They are integrator/round-off characterizations, not mission results.

## Part A — Mission design derivations

Not started. To be filled in Phase 1, answering open validation questions 1, 2, 4, and 5 (spec §18):

- [x] Near-sun-synchronous behaviour of 525 km / 97.5° under J2 (nodal precession rate vs. the ~0.9856 °/day target). **Answer (§B.5.3):** it depends on whether 525 km / 97.5° are *mean* or *osculating* elements.
  - **Read as mean elements:** the secular rate is 0.98605 °/day against the 0.98565 °/day target, which is +0.04% and a node drift of about 0.15°/yr. The exact sun-synchronous inclination is 97.497°. **Near-sun-synchronous: yes.**
  - **Read as osculating elements at the ascending node** (as the code does today): the mean altitude comes out ~9.4 km lower (515.6 km). The measured rate is 0.99097 °/day, which is +0.54% and a drift of about 1.9°/yr (~8 min of local time per year). That is still "near" for 24 h scenarios (0.005°/day).
  - **Recommendation:** define the reference orbit by mean elements (decision pending, DL-026).
- [ ] Orbital elements that realize ~20 km along-track spacing without unintended secular drift. **Two-body part answered (§B.4.2):** equal osculating a, e, i, Ω, ω with mean-anomaly offsets of 20 km / a give no secular drift; the separation changes by 2e-5 m over 24 h (integrator error only). **J2 part (§B.5.4): equal osculating elements are NOT acceptable.** J2 short-period terms make mean a depend on the argument of latitude, so neighbours get different mean a and different periods. The resulting 24 h change in adjacent separation depends on where the formation starts:

| Start (argument of latitude) | Change in separation over 24 h |
|---|---|
| 0° | 107 m |
| 22.5° | 5.5 km |
| 45° | 7.7 km (20 km closes to 12.3 km; the formation collapses in ~3 days) |
| 90° | 160 m |

A different initialization is needed; decision pending (DL-022 revision).
- [ ] Eclipse fraction and eclipse-aware power balance for the 25 W / 100 Wh candidate.
- [ ] Feasibility of the 0.5 mN / 5 m/s propulsion candidate (spec §3.3 notes ~33.3 h of accumulated thrust for 5 m/s).

## Part B — Phase 1 physics acceptance test design

**Tolerance policy (spec §4.4):** numerical tolerances are **not** set in this document. Each is set from an independent reference-error study recorded here before the test is enabled, and must state how it was derived. Until then, a tolerance is `TBD (reference study pending)`.

| ID | Test | Method | Independent reference | Tolerance | Test location |
|---|---|---|---|---|---|
| PA-01 | Two-body propagation accuracy | Propagate each spacecraft over the defined horizon (24 h nominal) and compare positions/velocities | Analytic Kepler solution (universal-variable or eccentric-anomaly form), independently implemented; optionally a high-accuracy integrator at tight tolerances | **Approved** §B.2.4 (0.9 m / 1e-3 m/s circular; 0.5 m / 4e-4 m/s e = 0.1) | `tests/physics_validation/test_two_body.py` |
| PA-02 | Conservation in the unperturbed model | Track specific orbital energy and specific angular-momentum vector over the horizon | Exact invariants of the two-body problem | **Approved** §B.2.4 | `tests/physics_validation/test_two_body.py` |
| PA-03 | Step-size convergence | Repeat a fixed scenario at Δt, Δt/2, Δt/4; check that the error decreases at the integrator's expected order | Richardson-style comparison against the finest run and PA-01 analytic reference | **Approved** observed order in [3.9, 5.1] at 20/10/5 s (§B.2.3) | `tests/physics_validation/test_two_body.py` |
| PA-04 | Frame round trips | ECI → ITRS → ECI and ECI → RIC → ECI for randomized states (Hypothesis) | Identity; Astropy transforms as an external check | RIC: **Approved** 0.5 ε‖x_chief‖ (§B.2.5). ITRS: **Approved** §B.3 | `tests/physics_validation/test_frames_ric.py`, `test_frames_itrs.py`, `tests/unit/test_timescales.py` |
| PA-05 | Units are explicit | Constructors reject ambiguous inputs; configs reject unit-less physical fields | Code inspection + schema tests | Pass/fail. Constructors done; dynamics config schema pending | `tests/unit/test_dynamics_inputs.py` |
| PA-06 | Formation initialization | Four initial states from consistent orbital elements reproduce the intended along-track spacing and phasing | Independent element → state → element round trip; geometric check of the spacing | **Approved** §B.4 | `tests/physics_validation/test_formation.py` |
| PA-07 | Relative-motion cross-check | Compare relative motion against Clohessy–Wiltshire/Hill **only** within its assumptions (circular reference, small separation, short horizon) | CW closed-form solution | **Approved** §B.4: second-order error scaling, plus the 20 km error matched to its analytic curvature form | `tests/physics_validation/test_cw.py` |
| PA-08 | J2 before SSO claims | With J2 enabled, measured nodal precession matches the analytic secular J2 rate before any sun-synchronous claim is made | Analytic secular J2 formula | **Proposed** §B.5: 2e-3 relative (circular), 4e-4 (e = 0.1), against mean elements | `tests/physics_validation/test_j2.py` |
| PA-09 | Determinism | Gravity-only and zero-thrust runs are bit-for-bit repeatable with the same config/seeds | Replay comparison (as already done for the Phase 0 toy scenario) | Exact equality (gravity-only done, golden SHA-256 pinned) | `tests/regression/test_two_body_determinism.py` |
| PA-10 | Visible failure on invalid input | NaN/Inf states, non-physical parameters (e.g. r below Earth radius, e ≥ 1 for an orbit expected to be bound) raise explicit errors | Negative tests | Pass/fail | `tests/unit/test_dynamics_inputs.py` |

### Reference-error studies to perform before enabling tolerances

- [x] Characterize float64 round-off for the analytic Kepler reference over 24 h (PA-01, PA-02). See §B.2.1.
- [x] Characterize the chosen integrator's error constant and order (PA-03). See §B.2.2–§B.2.3.
- [x] Float64 round-off of the RIC round trip (PA-04, RIC part). See §B.2.5.
- [x] Float64 round-off of the ITRS round trip (PA-04, ITRS part), plus independent checks of Astropy's transform. See §B.3.
- [x] Quantify CW linearization error at 20 km separation over the test horizon (PA-07). See §B.4.3.

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

**PA-03 criterion (approved 2026-11-03):**

- Use steps of 20, 10, and 5 s, all well above the floors.
- Errors must decrease strictly.
- Each observed position order must lie in **[3.9, 5.1]**. That is the theoretical band [4, 5] with a ±0.1 margin. The measured values were 4.32–4.58.

### B.2.4 Tolerance-derivation rule and PA-01/PA-02 tolerances (approved 2026-11-03)

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

The worst ECI→RIC→ECI round-trip errors were 1.2e-10 m and 1.1e-13 m/s. That is **0.077 ε‖r_c‖** and **0.074 ε‖v_c‖** (ε = 2.2e-16). The approved tolerance is **0.5 ε‖x_c‖**, about 6.5× the observed worst case. A wider margin than the 2× rule is used because Hypothesis searches inputs adversarially beyond the study sample.

## B.3 GCRS ↔ ITRS reference-error study (2026-11-03)

**Reproduce:** `uv run python scripts/studies/itrs_reference_errors.py`. It is deterministic and takes about 40 s.

**Data:** `astropy-iers-data==0.2026.11.2.0.34.55; pyerfa==2.0.1.5` (Astropy 8.0.2), offline.

**Samples:** two epochs, the reference 2025-06-01 and the candidate storm epoch 2024-05-10. Each has 2 000 random LEO states (a ∈ R⊕ + [200, 2000] km, e ≤ 0.02, any orientation) at random times within +30 days.

The transform is Astropy's, so a round trip alone would only test self-consistency. The checks therefore also compare against **independent formulas** that share no code with Astropy:

| Check | Independent reference | Expected agreement (analytic) | Observed worst (both epochs) | Tolerance (DL-019) |
|---|---|---|---|---|
| Round trip, position | identity | float64 round-off | 3.8 ε‖r‖ (5.6e-9 m) | **20 ε‖r‖**: ~5× margin, because Hypothesis searches adversarially |
| Round trip, velocity | identity | round-off of Astropy's finite-difference velocity transform | 9.6e-9 m/s | **5e-8 m/s**: ~5× margin, same reason |
| Earth rotation | ITRS longitude of the GCRS x-axis = −ERA(UT1), using ERA from IERS Conventions 2010 eq. 5.15 | second order in the ~0.14° pole offset, plus polar motion; ≲ 3e-6 rad | 9.4e-8 rad | **2e-7 rad**. This catches using UTC instead of UT1, which would give ~2e-6 rad |
| Pole offset | angle between the GCRS and ITRS z-axes vs the IAU 2006 CIP X, Y polynomial (eq. 5.16), with nutation and polar motion omitted | nutation (≈ 17.2″·sin ε + 9.2″) and polar motion (≲ 0.6″), so ≲ 8″ | 2.39″ (the measured pole angle is 486–513″) | **5″**. This catches using a frame without precession (e.g. CIRS/TETE confusion), which would be off by ~500″ |
| ITRS velocity | central finite difference (h = 0.1 s) of ITRS positions, with states at t ± h from the analytic Kepler reference | finite-difference truncation, about h²·‖jerk‖/6 ≈ 1.5e-5 m/s | 2.3e-5 m/s | **5e-5 m/s** |

**Time-scale checks** (`tests/unit/test_timescales.py`) use exact or defining values rather than studied tolerances:

- TT − UTC = 69.184 s at the reference epoch.
- |UT1 − UTC| < 0.9 s.
- Crossing the leap second at 2016-12-31T23:59:60Z works correctly.
- 1 ns resolution is kept after 24 h (Astropy's precision is about 10 ps).
- Times outside the bundled table raise an error.

## B.4 Formation initialization and CW cross-check study (2026-11-03)

**Reproduce:** `uv run python scripts/studies/formation_cw_reference_errors.py`. It is deterministic and takes about 20 s.

**Implementation:**

- **Formation** (`dynamics/formation.py`): spacecraft k shares the reference orbit's a, e, i, Ω and ω, and trails the leader (k = 0) by k·s/a radians of mean anomaly. For e = 0 this is an along-track arc of exactly s between neighbours.
- **State to elements** (`elements.rv_to_elements`): uses atan2 and applies no near-circular cut-off. A first version had one, and Hypothesis found that it misplaced positions by ~a·e (≈ 7e-6 m at e = 1e-12). The cut-off was removed and a 200 000-sample edge-case stress test passes.
- **CW** (`dynamics/relative.py`): closed-form state-transition matrix, in rectilinear RIC.

### B.4.1 Element round trips (20 000 random LEO states; i ∈ [0.01, π − 0.01] with the low end oversampled, half with e = 0)

| Quantity | Observed worst | Tolerance (Hypothesis-searched, ≥ 5× margin) |
|---|---|---|
| state → elements → state, position | 10.1 ε‖r‖ | 60 ε‖r‖ |
| state → elements → state, velocity | 9.9 ε‖v‖ | 60 ε‖v‖ |
| a (relative) | 1.7e-15 | 1e-14 |
| e (absolute) | 1.0e-15 | 6e-15 |
| i | 4.4e-16 rad | 3e-15 rad |
| Ω × sin i | 8.9e-16 rad | 5e-15 rad |
| u = ω + ν, × sin i | 2.3e-15 rad | 2e-14 rad |

Angles measured from the node are scaled by sin i, because the node direction has absolute error of about ε, so their error grows as ε / sin i.

### B.4.2 Formation geometry (4 spacecraft, s = 20 km, 525 km / 97.5° circular reference)

Analytic expectations:

- Adjacent chord: 2a sin(Δu/2) = 19 999.993 m.
- Follower position in the leader's rectilinear RIC frame: (−a(1 − cos Δu), −a sin Δu, 0) = (**−28.97 m**, −19 999.97 m, 0).

The ~29 m radial offset is pure curvature: both spacecraft are on the same circular orbit.

| Check | Observed worst | Tolerance (2× rule) |
|---|---|---|
| Chord at t₀ vs formula (all pairs) | 1.1e-11 m | 3e-11 m |
| RIC position at t₀ vs formula (all pairs) | 1.4e-9 m | 3e-9 m |
| RIC velocity at t₀ (all pairs; truth 0) | 7.8e-13 m/s | 2e-12 m/s |
| 24 h RK4: change in adjacent separation | 2.0e-5 m | 5e-5 m |
| 24 h RK4: change in follower RIC position | 2.0e-5 m | 5e-5 m |
| 24 h RK4: follower RIC velocity | 5.1e-9 m/s | 2e-8 m/s |

**Result:** under two-body dynamics this initialization has no secular relative drift, only integrator error.

### B.4.3 CW cross-check (truth: RK4 at 10 s for chief and deputy; horizon 5 700 s ≈ 1 orbit)

**(a) Within its assumptions.** The relative states have separation ρ in a random direction and velocity ρ·n in a random direction. CW error is exactly second order in ρ, because CW is the first-order linearization. The observed order across ρ = 125 → 2000 m was 1.9987–2.0010. **Band: [1.9, 2.1].**

The absolute error grows quickly when the initial velocity makes the relative orbit drift, up to 1.4e-4·ρ² per metre over one orbit (2.1 m at ρ = 125 m).

**(b) At the 20 km in-train spacing.** CW treats the −29 m curvature offset as a lower orbit and predicts an along-track drift that truth does not have:

- Error after one orbit: **1 092 m**.
- The CW − truth difference matches the analytic form Δx = 3(1 − cos nt)x₀, Δy = 6(sin nt − nt)x₀ to within **9.4e-6 m** (tolerance 2e-5 m).

The disagreement is therefore entirely the known linearization (curvature) error; the dynamics, the frames and the CW code are all correct.

**Implication:** rectilinear CW must **not** be used to predict or plan the 20 km formation's relative motion beyond very short horizons. Curvilinear coordinates or the full nonlinear propagator should be used instead.

## B.5 D1 (point mass + J2) reference study (2026-11-03)

**Reproduce:** `uv run python scripts/studies/j2_reference_errors.py`. It is deterministic and takes about 2 min.

**Model** (`dynamics/forces.py`): point mass + J2, with J2 = −√5·C̄₂₀(EGM2008) = 1.0826262e-3. The source check is pending (DL-024).

**Pole:** the J2 axis is the ITRS z-axis expressed in GCRS at the scenario epoch, from Astropy (`earth_pole_gcrs`). At the reference epoch it is (0.0024746, 3.44e-5, 0.9999969), 510″ from GCRS z, consistent with §B.3. It is held fixed for the run (DL-025). Over 24 h, precession and nutation move it by < 1e-6 rad, so the effect is negligible.

### B.5.1 Force-model checks

| Check | Independent reference | Observed worst | Tolerance |
|---|---|---|---|
| J2 acceleration vs ∇ of the J2 potential | central finite difference (h = 10 m) of an independently written potential expression, 5 000 random LEO positions | 2.4e-10 relative | 5e-10 |
| `forces.potential` J2 part vs the independent expression | — | 5.2e-13 relative | 2e-12 |
| j2 = 0 vs point mass | — | bit-identical | exact |

### B.5.2 Invariants and step convergence with J2 (24 h)

The pole is fixed in inertial space and the field is axisymmetric, so two quantities are exact invariants: energy v²/2 − V(r) and the angular-momentum component along the pole.

| Case | Rel. energy drift at 10 s | Rel. h·p̂ drift at 10 s | Max ‖r(10 s) − r(5 s)‖ | Observed order (20/10/5) |
|---|---|---|---|---|
| circular 525 km | 4.3e-10 (tolerance 9e-10) | 2.1e-10 (tolerance 5e-10) | 0.41 m (tolerance 0.9 m) | 4.58 |
| e = 0.1 | 1.9e-10 (tolerance 4e-10) | 7.0e-11 (tolerance 2e-10) | 0.20 m (tolerance 0.5 m) | 4.49 |

The error at 10 s against a 1.25 s solution is 0.43 m and 0.22 m, the same as D0. **The 10 s step remains adequate with J2 (DL-017 re-check: passed).** The order band is [3.9, 5.1], as in §B.2.3.

### B.5.3 Nodal precession (PA-08)

**Method:** the secular RAAN rate about the pole is a least-squares fit to the osculating RAAN over 24 h at 10 s. The analytic rate is −(3/2) n J2 (R/p)² cos i, evaluated at *mean* a and i, which are 24 h averages of the osculating values. A first-order theory is expected to agree to O(J2) ≈ 1e-3.

| Case | Measured | Analytic (mean elements) | Relative difference | Tolerance | Analytic at initial *osculating* elements |
|---|---|---|---|---|---|
| circular 525 km / 97.5° | +0.99097 °/day | +0.99167 °/day | −7.0e-4 | 2e-3 | +0.98605 °/day (+0.50% off) |
| e = 0.1, 51.6° | −2.86449 °/day | −2.86495 °/day | −1.6e-4 | 4e-4 | −2.85741 °/day (+0.25% off) |

For the circular case, the mean a is 9 350 m below the initial osculating a. The osculating a at the ascending node sits near the top of its short-period oscillation. This is why the choice between mean and osculating elements matters for both open questions 1 and 2.

**Sun-synchronous target** = 360°/365.2422 d = 0.98565 °/day. Exact sun-synchronous inclination:

- 97.461° at the measured mean a (515.6 km);
- 97.497° if 525 km is the mean altitude.

### B.5.4 Formation under J2 (open question 2)

**Setup:** the formation of DL-022 (equal osculating a, e, i, Ω, ω; 20 km mean-anomaly offsets), propagated 24 h at 10 s.

- **Two-body:** the separations change by 2e-5 m.
- **With J2:** the separations drift by 107 m to 7.7 km depending on the start angle (Part A table). The drift is largest at 45°, where d(osculating − mean a)/du is greatest.
- **At a 0° start:** the mean-a differences between neighbours are 0.26, 0.57 and 0.89 m.
- **At a 45° start:** the drift is ~7.7 km/day, consistent with a mean-a difference of about 50 m (3π·Δā per orbit).

**Conclusion:** formation initialization must equalize **mean** semi-major axis, not osculating. The options are in DL-026.

### Sign-off

| Item | Decision | Date |
|---|---|---|
| Test list PA-01 … PA-10 | ☑ approved — Abdullah Muzher | 2026-11-03 |
| Tolerance policy (set only from reference studies) | ☑ approved — Abdullah Muzher | 2026-11-03 |
| D0 derived tolerances, PA-03 order band, and derivation rule (§B.2.3–§B.2.5) | ☑ approved — Abdullah Muzher | 2026-11-03 |
| ITRS (PA-04) tolerances and independent checks (§B.3) | ☑ approved — Abdullah Muzher | 2026-11-03 |
| Formation (PA-06) and CW (PA-07) tolerances and bands (§B.4) | ☑ approved — Abdullah Muzher | 2026-11-03 |
| J2 (PA-08 and D1 checks) tolerances (§B.5) | ☐ pending owner review | — |

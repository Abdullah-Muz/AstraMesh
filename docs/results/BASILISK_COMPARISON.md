# Basilisk cross-check of the truth dynamics

> **Status:** recorded 2026-11-14 from clean commit `21c5db9` (`git_dirty: false`). Phase 6 increment 2 (DL-116 design, DL-117 code, DL-118 results); spec §4.1 D3. The cases and tolerances were fixed in DL-116 before any run. The recorded files are byte-identical to the unrecorded trial disclosed in DL-117. Approved by the owner 2026-11-14.

## Setup

- **Basilisk:** `bsk` 2.12.2 (ISC licence; DL-116), in the separate environment `tools/basilisk/` (its own `uv.lock`; numpy 2.4.6, Python 3.12.3). The main environment and lock are unchanged.
- **Shared inputs:** both sides read one case file, [`basilisk_cases.json`](basilisk_cases.json). It holds AstraMesh's constants (μ 3.986004418e14 m³/s², R 6 378 137 m, C̄20 −4.84165143790815e-4 from EGM2008, ω 7.292115e-5 rad/s), the initial GCRS states of sc00 and sc01, and the density table. The initial states come from the 20 km formation of `formation_24h_j2.yaml` (mean 525 km, 97.5°, epoch 1 Jun 2025).
- **Run settings:** 8 days of fixed-step RK4 at 10 s on both sides, unless an RKF78 run is named.
- **Basilisk setup:**
  - Earth at the origin with an identity orientation; μ and R set explicitly; a degree-2 field file written from the case constants.
  - Drag from `tabularAtmosphere`, `zeroWindModel` (atmosphere co-rotation) and `dragDynamicEffector`, with C_D A / m equal to B.
  - No Basilisk support data used.
- **Cases (DL-116):**
  - **K1 two-body.** Also compared with AstraMesh's analytic Kepler solution.
  - **K2 J2,** with the pole on GCRS z.
  - **K3 J2 + drag on sc00, models matched:**
    - USSA 1976 density on the spherical altitude |r| − R: AstraMesh through `density_fn`, Basilisk through a table of AstraMesh's density every 100 m from 480 to 700 km;
    - atmosphere co-rotating about z;
    - B = 0.0092 m²/kg.
  - **K4:** sc00 and sc01, 20 km apart, under the K3 models, with sc01 at 1.2 B (the DL-083 case). Compared on their spacing.
  - **M1 (reported only):**
    - AstraMesh's production model (WGS 84 ellipsoidal altitude, pole at the epoch) against the matched runs;
    - Basilisk RKF78 (relative tolerance 1e-12, absolute 1e-9) on K2 and K3.
- **Reproduce:**

  ```
  uv run --locked python scripts/experiments/basilisk_comparison.py cases --out <dir>
  uv run --locked --project tools/basilisk python tools/basilisk/propagate.py <dir>
  uv run --locked python scripts/experiments/basilisk_comparison.py compare --out <dir>
  ```

  - Run times: about 10 min for the AstraMesh side and under 1 min for Basilisk.
  - Files: [`basilisk_comparison.csv`](basilisk_comparison.csv) (every measure, with its tolerance), [`basilisk_daily.csv`](basilisk_daily.csv) (differences at each whole day) and [`basilisk_comparison_meta.json`](basilisk_comparison_meta.json). The meta file holds the commit, both lockfile hashes, the case-file hash, the production config hash and the verdicts.
  - The trajectories themselves (about 50 MB) are not committed; `cases` and `propagate.py` regenerate them.

## Results

**Tolerances (DL-116): all passed.**

| Test | Case | Measure (max over 8 days, every 10 s step) | Value | Tolerance | |
|---|---|---|---|---|---|
| T1 | K1 two-body | AstraMesh − Basilisk, position | 0.13 mm | 1 m | pass |
| T1 | K1 two-body | AstraMesh − Basilisk, velocity | 1.5e-7 m/s | 1e-3 m/s | pass |
| T1 | K2 J2 | AstraMesh − Basilisk, position | 0.22 mm | 1 m | pass |
| T1 | K2 J2 | AstraMesh − Basilisk, velocity | 2.4e-7 m/s | 1e-3 m/s | pass |
| T2 | K3 J2 + drag | AstraMesh − Basilisk position ÷ drag's own effect | 8.0 cm ÷ 63.3 km = 1.3e-6 | 0.005 | pass |
| T3 | K4 spacing | AstraMesh − Basilisk spacing ÷ spacing change | 1.6 cm ÷ 12.35 km = 1.3e-6 | 0.005 | pass |

Under K3, the velocity difference is at most 8.8e-5 m/s. Under K4, the largest position difference on either spacecraft is 9.6 cm. Over the 8 days, the K4 spacing falls from 20.018 km to 7.665 km, and the two sides agree to the centimetre.

**Growth over the run** (from `basilisk_daily.csv`):

| Day | K1 Δr | K2 Δr | K3 Δr | K3 drag effect | K4 spacing | K4 Δspacing |
|---|---|---|---|---|---|---|
| 1 | 0.009 mm | 0.002 mm | 3.1 mm | 0.99 km | 19.850 km | −0.6 mm |
| 2 | 0.017 mm | 0.021 mm | 7.9 mm | 3.95 km | 19.287 km | −1.6 mm |
| 4 | 0.059 mm | 0.080 mm | 24 mm | 15.8 km | 17.009 km | −4.8 mm |
| 8 | 0.13 mm | 0.22 mm | 80 mm | 63.3 km | 7.665 km | −16 mm |

**Model differences (M1, reported only):**

| Comparison | Max over 8 days |
|---|---|
| RK4 at 10 s against the analytic Kepler solution (K1), AstraMesh and Basilisk alike | 15.04 m, 0.017 m/s |
| Basilisk RK4 against Basilisk RKF78, K2 / K3 | 15.09 m / 15.10 m |
| AstraMesh RK4 against Basilisk RKF78, K2 / K3 | 15.09 m / 15.18 m |
| AstraMesh production model against the matched model, sc00 (K3) | 9.15 km |
| Spacing change, production / matched (K4) | 10.81 km / 12.35 km (final spacing 9.206 km / 7.665 km) |

The production run reproduces DL-083's recorded result exactly: 20.0177 → 9.2059 km for the sc00 – sc01 spacing with sc01 at 1.2 B ([`drag_drift.csv`](drag_drift.csv)).

## Findings

1. **AstraMesh's two-body, J2 and drag implementations agree with Basilisk** when both are given the same models and constants. The agreement is about 0.2 mm without drag and 8 cm with drag over 8 days. The tolerances were 1 m and 0.5 % of drag's effect. A modelling error of the kinds the tolerances were set to catch would show at the km level: the J2 sign or normalization, the wrong μ, a missing atmosphere co-rotation (about 2 % of drag on this orbit) or a wrong ballistic coefficient.
2. **Basilisk's step-hold of the drag inputs matters far less than estimated.** Basilisk holds the density and wind messages constant over each 10 s step. The resulting difference is 1.3e-6 of drag's effect, against the 5e-4 estimated in DL-116. Why the estimate was pessimistic was not investigated.
3. **The integration error is the same in both codes:** RK4 at 10 s is about 15 m from the analytic and RKF78 solutions over 8 days. That is consistent with the PA-01 tolerance of 0.9 m over 24 h (§B.2.4), and small against the 20 km spacing and the km-level drag drift.
4. **AstraMesh's own modelling choices matter far more than the implementation.**
   - **sc00:** under the production model (WGS 84 ellipsoidal altitude, pole at the epoch), sc00 is up to 9.15 km from the matched run. That is 14 % of drag's 63.3 km effect, but the figure mixes the altitude definition and the pole, which were not separated.
   - **Spacing:** the formation spacing is a difference between two spacecraft that share the pole. It changes 12 % less under the production model: 10.81 km instead of 12.35 km, ending at 9.2 km instead of 7.7 km.
   - **Likely cause:** on this near-polar orbit, the ellipsoidal altitude is up to about 21 km higher near the poles, so the density there is lower.

## Limits

- **This checks the implementation, not the physics.** Both codes ran the same models by construction: USSA 1976, a cannonball drag model and J2 only. Whether those models represent the real atmosphere and gravity field is outside this comparison. Storm-time density (NRLMSIS 2.0, DL-085) was not compared; Basilisk's MSIS module is NRLMSISE-00.
- **One orbit, one formation and one 8-day window,** with a single ballistic coefficient pair.
- **Basilisk was configured to match AstraMesh** in its frame, constants and atmosphere. Its own defaults, such as `createEarth`'s μ and R, the GGM03S field files and SPICE orientation, were not used, so this is not a comparison with Basilisk as it is usually run.
- **No control cases** (formation keeping) and no Vizard, as decided in DL-116.

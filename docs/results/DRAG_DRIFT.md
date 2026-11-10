# Formation drift under nominal drag (D1)

> **Status:** recorded 2026-11-10 from clean commit `9cd0016` (`git_dirty: false`). Truth dynamics only: no agents, no maneuvers. Phase 5 increment 2 (DL-080, DL-081, DL-082). Approved 2026-11-10 (DL-083).

## Setup

- **Base:** `configs/experiments/formation_24h_j2.yaml` (four spacecraft, 20 km along-track spacing, mean 525 km / 97.5°, point mass + J2, RK4 at 10 s), run for 24 h and for 8 days (the S11 length).
- **Drag (DL-080):** USSA 1976 density, co-rotating atmosphere, nominal B = C_D A / m = 0.0092 m²/kg (modelled).
- **Variants:** no drag; equal B for all four; B on sc01 only ×0.8 and ×1.2 (a credible spread for one design) or ×0.5 and ×2 (stress), DL-082.
- **Measure:** distance between adjacent spacecraft at every 10 s step: initial, final, minimum (and when), maximum.
- **Reproduce:** `uv run python scripts/experiments/drag_drift_study.py --out <dir>` (about 5 min). Files: [`drag_drift.csv`](drag_drift.csv), [`drag_drift_meta.json`](drag_drift_meta.json) (commit, lockfile, config hashes).

## Results (8 days)

| Variant | sc00–sc01, km (final / min) | sc01–sc02, km (final / min) | sc02–sc03, km (final) |
|---|---|---|---|
| No drag | 20.015 / 20.000 | 20.015 / 20.000 | 20.015 |
| Equal B | 20.015 / 19.999 | 20.015 / 19.999 | 20.015 |
| sc01 B ×0.8 | 30.82 / 20.00 | **9.21** / 9.21 (at the end) | 20.015 |
| sc01 B ×1.2 | **9.21** / 9.21 (at the end) | 30.82 / 20.00 | 20.015 |
| sc01 B ×0.5 | 47.03 / 20.00 | 7.00 / **0.041** (day 6.9) | 20.015 |
| sc01 B ×2 | 34.05 / **0.058** (day 4.9) | 74.08 / 20.00 | 20.015 |

After 24 h the shifts are 0.17 km (±20 %), 0.42 km (×0.5) and 0.84 km (×2).

## Findings

1. **Drag itself does not move the formation.** With equal B, every spacing stays within 0.02 km of the no-drag run over 8 days.
2. **Differential drag does, roughly with the square of time.** A 20 % difference halves one spacing (20 → 9.2 km) within the storm week, and the gap is still closing at the end.
3. **A factor-2 difference threatens separation.** The faster-decaying (×2) or slower-decaying (×0.5) spacecraft comes within 58 m or 41 m of a neighbour within the week. These are distances between point masses; the simulation does not model collisions.
4. **Decision rule (DL-082):** the ±20 % cases do not threaten separation within 8 days, so maneuvers stay deferred. Longer runs, or larger B differences, would need formation keeping.

## Limits

- One density model (mid-activity, no storm-time density; D2 is separate). Storm heating raises density and would speed every drift up.
- B is modelled, constant and attitude-independent; only one spacecraft differs at a time.
- Effect on science geometry not computed. A 10 km shift moves a spacecraft by about 1.3 s along the orbit, small against opportunity windows of minutes (§B.7), so it is expected to be negligible over 8 days.

## Storm-time density (D2, NRLMSIS 2.0)

> **Status:** recorded 2026-11-10 from clean commit `460ccaf` (`git_dirty: false`). Phase 5 increment 2 (DL-084, DL-085, DL-086). Approved 2026-11-10 (DL-086).

- **Setup:** as above, but drag density from NRLMSIS 2.0 with DS-10 drivers (§B.10), over the S11 storm week: epoch 8 May 2024 00:10 UT, 690 600 s. Variants equal B and sc01 B ×0.8 / ×1.2, each at density scale 0.8, 1.0 and 1.25 (`density_scale_ratio`: the sensitivity to MSIS storm-time density error that DL-084 requires).
- **Reproduce:** `uv run python scripts/experiments/drag_drift_study.py --msis --out <dir>` (about 18 min). Files: [`drag_drift_msis.csv`](drag_drift_msis.csv), [`drag_drift_msis_meta.json`](drag_drift_msis_meta.json).

| Variant | Density scale | Closing pair: min, m (day) | Closing pair final, km | Opening pair final, km |
|---|---|---|---|---|
| Equal B | 0.8 / 1.0 / 1.25 | all spacings stay within 19.997 – 20.018 km | 20.003 | 20.003 |
| sc01 B ×0.8 (closes on sc02) | 0.8 | **47** (6.2) | 13.73 | 53.74 |
| | 1.0 | **51** (5.6) | 22.19 | 62.20 |
| | 1.25 | **59** (5.0) | 32.78 | 72.78 |
| sc01 B ×1.2 (closes on sc00) | 0.8 | **47** (6.2) | 13.75 | 53.76 |
| | 1.0 | **52** (5.6) | 22.22 | 62.22 |
| | 1.25 | **60** (5.0) | 32.82 | 72.83 |

Findings:

1. **Equal B still leaves the formation unchanged** under storm-time density: every spacing stays within 0.02 km of 20 km.
2. **A ±20 % B difference now threatens separation.** Under the D1 table the same case only halved one spacing in 8 days (20 → 9.21 km). With 2024 storm-time density, sc01 comes within 47 – 60 m of a neighbour between days 5.0 and 6.2, for every density scale tried, and then passes it: the final "closing pair" distance is measured after the crossing. These are distances between point masses; the simulation does not model collisions.
3. **Decision rule (DL-082) is met:** the ±20 % cases threaten separation within the 8-day storm week, so maneuvers (deferred, DL-077) return to Phase 5 as formation keeping against differential drag. The design is a separate entry for owner approval.


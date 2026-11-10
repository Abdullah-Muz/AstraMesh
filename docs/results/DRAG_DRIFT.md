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

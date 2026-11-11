# Formation keeping over the storm week

> **Status:** recorded 2026-11-10 from clean commit `d7ab81a` (`git_dirty: false`). Phase 5 increment 2b (DL-087, DL-088, DL-089). Truth dynamics with the onboard controller; no agents. Approved by the owner 2026-11-11.

## Setup

- **Base:** `configs/experiments/mission_geometry_24h.yaml` (the four-spacecraft, 20 km along-track formation of the drift studies, with the `spacecraft` propulsion values: 0.5 mN cold gas, Isp 70 s, 12 kg, 5 m/s budget, 2 W while thrusting).
- **Environment:** the DL-086 storm week (8 May 2024 00:10 UT, 690 600 s), NRLMSIS 2.0 density with DS-10 drivers (§B.10), RK4 at 10 s.
- **Controller (DL-088):** followers keep slots behind sc00; decisions once per orbit from a Kalman filter on orbit-sampled spacings; whole 10 s steps of tangential thrust when the slot error exceeds 0.5 km; sunlight only. Navigation error 10 m per axis unless stated.
- **Cases:** equal B; B on sc01 ×0.8, ×1.2 (credible spread, DL-082) and ×0.5, ×2 (stress) at density scale 1.0; ×0.8 and ×1.2 at scales 0.8 and 1.25; ×1.2 with navigation error 0 and 100 m.
- **Pass criteria (DL-087):** every adjacent spacing within 20 ± 2 km at every 10 s step and never below 1 km.
- **Reproduce:** `uv run python scripts/experiments/formation_keeping_study.py --out <dir>` (about 20 min). Files: [`formation_keeping.csv`](formation_keeping.csv) (spacings), [`formation_keeping_dv.csv`](formation_keeping_dv.csv) (per spacecraft), [`formation_keeping_meta.json`](formation_keeping_meta.json) (commit, lockfile, config hashes).

## Results

| Case (B on sc01) | Density scale | Nav. error | Spacings, km (min – max, all pairs) | sc01 largest slot error, km | sc01 Δv, m/s | Thrust, s | Commands |
|---|---|---|---|---|---|---|---|
| Equal B | 1.0 | 10 m | 19.998 – 20.018 | 0.018 | 0 | 0 | 0 |
| ×0.8 | 1.0 | 10 m | 19.349 – 20.660 | 0.66 | 0.043 | 1 030 | 12 |
| ×1.2 | 1.0 | 10 m | 19.316 – 20.692 | 0.68 | 0.039 | 940 | 8 |
| ×0.5 | 1.0 | 10 m | 19.120 – 20.888 | 0.89 | 0.102 | 2 440 | 21 |
| ×2 | 1.0 | 10 m | 18.697 – 21.311 | 1.30 | 0.201 | 4 820 | 44 |
| ×0.8 | 0.8 | 10 m | 19.392 – 20.616 | 0.62 | 0.030 | 720 | 6 |
| ×1.2 | 0.8 | 10 m | 19.363 – 20.647 | 0.64 | 0.034 | 810 | 10 |
| ×0.8 | 1.25 | 10 m | 19.307 – 20.700 | 0.70 | 0.052 | 1 240 | 16 |
| ×1.2 | 1.25 | 10 m | 19.296 – 20.710 | 0.70 | 0.051 | 1 230 | 15 |
| ×1.2 | 1.0 | 0 m | 19.327 – 20.682 | 0.67 | 0.041 | 990 | 10 |
| ×1.2 | 1.0 | 100 m | 19.297 – 20.707 | 0.70 | 0.039 | 940 | 8 |

sc00, sc02 and sc03 never burn in any case; sc02 and sc03 stay within 0.053 km of their slots (their offset at the start). No decision was held (no faults in this study). Propellant for the largest case (×2) is 3.5 g and thruster energy 2.7 Wh.

## Findings

1. **Formation keeping removes the DL-086 separation threat.** Without control, B ±20 % brought sc01 within 47 – 60 m of a neighbour in this week (DL-086); with control every spacing stays within 0.70 km of 20 km at all three density scales.
2. **The cost is small against the budget.** ±20 % costs 0.030 – 0.052 m/s for the storm week (under 1.1 % of 5 m/s); the ×2 stress case 0.20 m/s (4 %). Only the spacecraft whose B differs spends Δv.
3. **Even the stress cases pass.** B ×0.5 and ×2, which reach 41 – 58 m without control (DL-083, D1 density), stay within 0.89 and 1.30 km of their slots.
4. **Navigation error of 0 – 100 m hardly matters:** the largest slot error moves between 0.67 and 0.70 km and Δv between 0.039 and 0.041 m/s, because the filter averages over orbits and errors are far below the 0.5 km deadband.
5. **Equal B costs nothing:** the controller never commands a burn, so the G3 scenarios (equal B, DL-082) are unaffected whether it is on or off.

## Limits

- One week of one storm; Δv over a mission depends on solar activity and on the actual B spread. Not extrapolated here.
- B and mass are constant in the drag term; thrust is ideal (no pointing error, no minimum impulse bit below 10 s, no thruster failure).
- Navigation is modelled (truth plus Gaussian error); no relative-navigation filter or GNSS outages.
- No faults in this study; the fault rules are tested in MK-05 only. A silent leader makes sc01 the uncontrolled leader (DL-088).
- Collision is not modelled; spacings are point-mass distances.

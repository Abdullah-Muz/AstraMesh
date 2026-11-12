# Per-spacecraft risk over the storm week

> **Status:** recorded 2026-11-11 from clean commit `45430aa` (`git_dirty: false`). Phase 5 increment 3 (DL-090, DL-091, DL-092, DL-093). Agents with the protection supervisor; position-based access is a model, not a measurement. Awaiting owner review.

## Setup

- **Base:** the Phase 4 S11 setup (`scripts/experiments/storm_replay_comparison.py`): S00 moved to 8 May 2024 00:10 UT, 690 600 s; forecast P-B median; planner B4; seed 1. Modes depend on the planner only through recovery peer contact.
- **Position model (DL-090 option A, values DL-091):** GOES ≥ 10 MeV flux reaches a spacecraft only while its invariant latitude (IGRF-14 centred dipole) is at or above Λ_c = 65.2° + SYM-H / 19.11 (SYM-H < 0; shift capped at 15°). The onboard radiation input is the forecast next-hour maximum over the spacecraft's own tolerance, 0 when its own track over the next hour stays below the cutoff. Inputs expire 3600 s after issue.
- **Cases:** `phase4` (no position model, the Phase 4 P-B run); `position`; `position+tolerances` (100 / 100 / 50 / 200 pfu for sc00–sc03); `position+outage` (no forecast reaches sc01 from 1 h before the first onset ≥ 100 pfu, 10 May 17:20 UT, to 5 h after); `main` (all three); cutoff sensitivity on `main`: cap 8°, no cap, slope × 0.5 and × 1.5, and the Störmer cutoff (R09 eq. 6.17 at 525 km, 71.95° invariant) with no storm shift.
- **Metrics:** hazard (flux at the spacecraft ≥ its tolerance), unprotected hazard (hazard outside PROTECTIVE / RECOVERY), exposure (payload on during hazard), false protection (protected outside hazard); time in which spacecraft are in different modes; time in which one is protected while another can do science; **handover opportunity** (DL-090): tasks with a window for a spacecraft that is not in a science mode at the window's first tick while another spacecraft with a window is.
- **Reproduce:** `uv run python scripts/experiments/per_spacecraft_risk_study.py --out <dir>` (about 2.5 min on 10 workers). Files: [`per_spacecraft_risk.csv`](per_spacecraft_risk.csv) (per case and spacecraft), [`per_spacecraft_risk_cases.csv`](per_spacecraft_risk_cases.csv) (per case), [`per_spacecraft_risk_meta.json`](per_spacecraft_risk_meta.json) (commit, lockfile, config hashes).

## Results

| Case | Utility (tasks of 346) | Duplicates | Modes differ, h | Protected while a peer can do science, h | Handover opportunity: tasks (priority) |
|---|---|---|---|---|---|
| phase4 | 980 (295) | 0 | 0 | 0 | 0 |
| position | 980 (295) | 0 | 0 | 0 | 0 |
| position+tolerances | 1 122 (337) | 170 | 74.8 | 50.1 | 91 (304) |
| position+outage | 1 008 (303) | 137 | 2.5 | 1.6 | 8 (28) |
| main | 1 136 (341) | 290 | 75.5 | 50.8 | 95 (318) |
| main, any cutoff variant | identical to main | | | | |

Per spacecraft (h; exposure was 0 s in every case):

| Case | sc | Tolerance, pfu | In caps | Hazard | Unprotected hazard | False protection | Protected | PROTECTIVE entries |
|---|---|---|---|---|---|---|---|---|
| phase4 | each | 100 | – | 6.67 | 0.08 | 14.25 | 20.83 | 3 |
| position | sc00 – sc03 | 100 | 60.53 – 60.56 | 1.97 – 1.98 | 0 | 18.86 | 20.83 | 3 |
| main | sc00 | 100 | 60.56 | 1.98 | 0 | 18.86 | 20.83 | 3 |
| main | sc01 | 100 | 60.53 | 1.97 | 0.19 | 17.47 | 19.25 | 2 |
| main | sc02 | 50 | 60.54 | 13.71 | 0.08 | 37.13 | 50.83 | 4 |
| main | sc03 | 200 | 60.54 | 0 | 0 | 0.75 | 0.75 | 1 |

Cutoff sensitivity (main; decisions unchanged, only the hazard moves): time in the caps 58.7 h (cap 8°), 61.1 h (no cap), 56.2 / 63.4 h (slope × 0.5 / × 1.5) and 33.4 h (Störmer, no shift), against 60.5 h; sc02's hazard 12.7, 13.9, 12.1 / 14.4 and 6.7 h against 13.7 h.

## Findings

1. **Position alone does not separate the spacecraft, as DL-082 predicted.** The four are in the polar caps for the same 60.5 h of the 191.8 h week (32 %), within 0.03 h of each other, and option A keeps every decision of the Phase 4 run (utility 980, 20.8 h protected each).
2. **Position changes what the hazard was.** At the spacecraft the hazard is 1.97 – 1.98 h per spacecraft, not the 6.67 h of the GEO proxy, so most of the protected time (18.9 of 20.8 h) falls outside the hazard. The one-hour input protects through every gap between cap passes; protecting pass by pass (option B) is a later H3 question.
3. **Tolerances and knowledge make the spacecraft differ.** With 100 / 100 / 50 / 200 pfu, sc02 protects 50.8 h and sc03 0.75 h, and the spacecraft are in different modes for 74.8 h. The sc01 outage over the first onset leaves sc01 0.19 h of unprotected hazard, which it could not avoid with expired inputs.
4. **DL-078's hypothesis is testable.** In the main scenario, 95 tasks of total priority 318 fall in one spacecraft's protected time while a peer with a window can do science; this is the room a handover method has.
5. **B4 duplicates when modes differ.** B4 made 290 duplicate observations in the main case and 137 even with only 2.5 h of differing modes (0 in Phase 4). Utility counts each task once, so it rises with tolerances (1 136 against 980) partly because sc03 keeps observing; the duplicate-charging utility of DL-078 is needed in increment 4.
6. **Under option A the cutoff uncertainty matters only for the hazard figures.** The cap, the slope and even the Störmer cutoff change hazard totals (sc02: 6.7 – 14.4 h), never a decision, because every case reaches the caps within the hour.

## Limits

- One storm, one seed, one planner. Increment 4 fixes run counts, planners (B3 + timeout and B4) and seeds.
- The cutoff is a model: a centred dipole, a Dst-driven shift measured only to about −150 nT (extrapolated beyond, capped at 15°), no local-time dependence, no Dst lag, step access at 10 MeV, no South Atlantic Anomaly (trapped protons).
- GOES at GEO stands for the interplanetary flux; tolerances are synthetic modelled limits.
- Exposure counts payload-on time only and was 0 here; unprotected hazard is the more robust measure.
- The outage window was placed using the known onset time (scenario definition, not tuning).

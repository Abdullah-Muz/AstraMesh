# Forecast handover against the reactive baseline, May 2024

> **Status:** recorded 2026-11-12 from clean commit `fd5abc3` (`git_dirty: false`; 229 runs, 4.7 h on 8 workers). Phase 5 increment 4 (DL-078, DL-094 – DL-097). The held-out storm, used once with the setting frozen in DL-096 (θ = 0.9, L = 30 min). Approved by the owner 2026-11-12.

## Setup

- **Storm:** 8 May 2024 00:10 UT, 690 600 s (S11), position-based access, age rule 3600 s, tolerances 100 / 100 / 50 / 200 pfu.
- **Scenarios:** **S11-H** (the DL-093 main case, with the sc01 forecast outage over the first onset); **S11-H+partition** ({sc00, sc01} | {sc02, sc03}, 10 May 12:00 – 11 May 12:00 UT); **S11-H+fault** (critical fault on sc00, 2 h from the first onset); **S00** (no environment; identity check). The tight-schedule scenario was dropped (DL-096).
- **Arms:** baseline (no policy; B4 with the DL-094 correction), candidate (DL-078 rule, frozen setting), candidate without sharing (S11-H, P-B), QUIET (same scenario without environment, for retention).
- **Forecasts:** P-B median (main), P-A, P-C (S11-H only). **Planners:** B3 + timeout, B4. **Seeds:** 1 – 10 for the main comparison and every B4 run; 1 – 5 for B3 elsewhere.
- **Hypothesis (DL-094):** for each planner, on S11-H with P-B, rejected if the paired 95 % t-interval of the retention difference (candidate − baseline, ÷ QUIET) includes 0 or lies below it.
- **Reproduce:** `uv run python scripts/experiments/handover_comparison.py --out <dir>` (about 4.7 h on 8 workers). Files: [`handover_runs.csv`](handover_runs.csv), [`handover_summary.csv`](handover_summary.csv), [`handover_value.csv`](handover_value.csv), [`handover_meta.json`](handover_meta.json).

## Results

Every run of a group gave the same utility on every seed (message loss of 1 % changed no outcome; the only seed-to-seed difference in the whole study is one duplicate in some P-C B3 runs). Unprotected hazard and exposure are identical between the arms in all 24 comparisons.

| Scenario | Forecast | Planner | Baseline | Candidate | QUIET | Retention gain [95 % CI] | Wilcoxon p (exact) |
|---|---|---|---|---|---|---|---|
| **S11-H** | **P-B** | **B3 + timeout** | 1 132 (340) | **1 136 (341)** | 1 136 | **+0.0035 [+0.0035, +0.0035]**, 10 seeds | 0.002 |
| **S11-H** | **P-B** | **B4** | 1 129 (339) | 1 129 (339) | 1 136 | **0 [0, 0]**, 10 seeds | 1.0 |
| S11-H | P-B, no sharing | B3 + timeout | 1 132 | 1 136 | 1 136 | +0.0035, 5 seeds | 0.06 |
| S11-H | P-B, no sharing | B4 | 1 129 | 1 129 | 1 136 | 0, 10 seeds | 1.0 |
| S11-H | P-A | B3 + timeout | 1 136 | 1 136 | 1 136 | 0, 5 seeds | 1.0 |
| S11-H | P-A | B4 | 1 129 | 1 129 | 1 136 | 0, 10 seeds | 1.0 |
| S11-H | P-C | B3 + timeout | 1 132 | 1 136 | 1 136 | +0.0035, 5 seeds | 0.06 |
| S11-H | P-C | B4 | 1 129 | 1 129 | 1 136 | 0, 10 seeds | 1.0 |
| S11-H+partition | P-B | B3 + timeout | 1 132 | 1 136 | 1 136 | +0.0035, 5 seeds | 0.06 |
| S11-H+partition | P-B | B4 | 1 129 | 1 129 | 1 136 | 0, 10 seeds | 1.0 |
| S11-H+fault | P-B | B3 + timeout | 1 132 | 1 136 | 1 136 | +0.0035, 5 seeds | 0.06 |
| S11-H+fault | P-B | B4 | 1 129 | 1 129 | 1 136 | 0, 10 seeds | 1.0 |

Utilities in points (tasks of 346 in brackets). The duplicate-charging utility gives the same gains (the 33 duplicates in the partition scenario occur in both arms). The script leaves the Wilcoxon cell empty when all differences are equal and non-zero; the exact two-sided values (0.002 for ten, 0.0625 for five equal positive differences) were computed separately with SciPy. S00: both arms identical under both planners.

**Unprotected hazard (all four spacecraft, h; identical in both arms):** P-A 0.64, P-B 0.27, P-C 0.19 on S11-H; 0.46 with the critical fault; 0.27 with the partition. **Cost-loss value V** of the protection decisions (identical in both arms): at C/L = 0.05 / 0.1 / 0.2 / 0.5, P-A 0.78 / 0.59 / 0.11 / −2.4, P-B 0.76 / 0.52 / −0.07 / −3.2, P-C 0.72 / 0.41 / −0.31 / −4.2 (full curves in `handover_value.csv`).

## Findings

1. **B3 + timeout: the hypothesis is not rejected by the pre-registered rule, but the effect is one task.** The candidate recovers the only task the B3 baseline loses (priority 4; 1 136 against 1 132, equal to QUIET) on every seed, in every scenario with P-B or P-C. Because the seeds do not change the outcome, the t-interval collapses to the point +0.0035 and excludes 0; the ten seeds are effectively one sample, so this is a deterministic result for one storm, not a measured spread.
2. **B4: the hypothesis is rejected.** The candidate changes no outcome under any forecast or scenario (gain 0, interval [0, 0]), as on the tuning storm: B4 already hands tasks on when protection starts, and the 7 points it loses against QUIET are tasks no unprotected peer can take.
3. **Sharing the window adds nothing measurable.** Without sharing the B3 gain is the same, so it comes from the protecting spacecraft releasing its own claim early; under B4 the shared window changes nothing.
4. **Protection is identical by construction and verified.** Unprotected hazard and exposure match in all 24 comparisons (the payload-in-protected-mode count is not recorded by this script; HO-04 tests it).
5. **The storm costs little science here.** Baseline retention is 0.996 (B3) and 0.994 (B4): with per-spacecraft risk (DL-093) most protected time lies outside the hazard, but the schedule has enough slack (four spacecraft share every window) that peers absorb almost all of it. This, more than the method, bounds what any handover rule can gain on this storm.
6. **Forecast comparison:** P-C leaves the least unprotected hazard (0.19 h) and P-A the most (0.64 h); at low cost/loss ratios all three have positive value, above about 0.2 (P-B, P-C) all are negative because protection lasts far longer than the hazard at the spacecraft.

## Limits

- One storm. The seeds vary only message loss and navigation noise, which changed no outcome; the intervals therefore say nothing about variation across storms.
- The B3 setting was frozen from B4-only tuning (DL-094, owner choice); B3 was not tuned.
- The schedule has slack; the tight-schedule scenario could not be built by density (DL-096).
- A pipeline dry run executed three of these runs before the recorded run (DL-096); the recorded values agree with it (B4 seed 1: 1 129 / 1 129 / 1 136).

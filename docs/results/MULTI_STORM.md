# Frozen forecast handover on four more storms

> **Status:** recorded 2026-11-12 from clean commit `f25e224` (`git_dirty: false`; 72 runs, 88 min on 12 workers). Phase 5 increment 4, room for methods (DL-098 scope A, DL-099, DL-100). Nothing was tuned: the setting is the one frozen in DL-096 (θ = 0.9, L = 30 min). Approved by the owner 2026-11-12.

## Setup

- **Storms:** four out-of-sample episodes from the training-period fold blocks (DL-098), each an 8-day pinned series with P-B fitted only before its fold's start (DL-099): **18 Jul 2023** (peak 668 pfu), **29 Jul 2023** (166 pfu), **29 Jan 2024** (153 pfu), **23 – 24 Mar 2024** (1 048 pfu, SYM-H −170 nT). Each run is 690 600 s from 00:10 UT on the window's first day.
- **Model:** DL-093 per-spacecraft risk (position-based access, age rule 3600 s, tolerances 100 / 100 / 50 / 200 pfu, no forecast outage), forecast P-B median.
- **Arms:** baseline (no policy; B4 with the DL-094 correction), candidate (DL-078 rule, frozen setting), QUIET (same window without environment, for retention). **Planners:** B3 + timeout, B4. **Seeds:** 1 – 3.
- **Test:** retention gain (candidate − baseline, ÷ QUIET) per storm, then pooled over the four storms (paired over storms, not seeds) with a 95 % t-interval and Wilcoxon test; DL-094's rule rejects the hypothesis when the interval includes 0 or lies below it.
- **Reproduce:** `uv run python scripts/experiments/multi_storm_comparison.py --out <dir>` (about 1.5 h on 12 workers; each B3 run takes 23 – 30 min, each B4 run about 2 min). Files: [`multi_storm_runs.csv`](multi_storm_runs.csv), [`multi_storm_summary.csv`](multi_storm_summary.csv), [`multi_storm_meta.json`](multi_storm_meta.json).

## Results

Every group gave the same outcome on all three seeds, so each cell below is one value.

| Storm | Planner | Baseline | Candidate | QUIET | Baseline retention | Gain | Window releases |
|---|---|---|---|---|---|---|---|
| 18 Jul 2023 | B3 + timeout | 1 067 (320) | 1 067 (320) | 1 133 (340) | 0.942 | 0 | 0 |
| 18 Jul 2023 | B4 | 1 060 (318) | 1 060 (318) | 1 133 (340) | 0.936 | 0 | 1 |
| 29 Jul 2023 | B3 + timeout | 1 131 (339) | 1 131 (339) | 1 140 (342) | 0.992 | 0 | 6 |
| 29 Jul 2023 | B4 | 1 131 (339) | 1 131 (339) | 1 140 (342) | 0.992 | 0 | 1 |
| 29 Jan 2024 | B3 + timeout | 1 136 (341) | 1 136 (341) | 1 136 (341) | 1.000 | 0 | 1 |
| 29 Jan 2024 | B4 | 1 136 (341) | 1 136 (341) | 1 136 (341) | 1.000 | 0 | 2 |
| 23 Mar 2024 | B3 + timeout | 969 (291) | 969 (291) | 1 136 (341) | 0.853 | 0 | 2 |
| 23 Mar 2024 | B4 | 969 (291) | 969 (291) | 1 136 (341) | 0.853 | 0 | 1 |
| **Pooled over storms** | **B3 + timeout** | | | | | **0 [0, 0]**, Wilcoxon p = 1.0 | |
| **Pooled over storms** | **B4** | | | | | **0 [0, 0]**, Wilcoxon p = 1.0 | |

Utilities in points (tasks completed of 345 – 347 in brackets). The duplicate-charging utility gives the same values (no duplicates in any run). Window releases are the candidate's early claim releases per run (0 in every baseline). The baseline count of tasks handed on (B4 `task_taken_over`, 226 – 246 per run) differs from the candidate by at most one.

**Protection (identical in both arms, every storm and planner):** hazard at the spacecraft 17.4 h (18 Jul), 8.8 h, 3.0 h, 37.9 h (23 Mar), summed over the four spacecraft; protected time 75 h, 54 h, 16 h, 136 h. Unprotected hazard is 0 except on 18 Jul 2023: 600 s each on sc00, sc01 and sc02 (0.5 h in all), with 50 s of exposure, in both arms. No payload step ran in a protected mode in any run.

**Why nothing could be recovered (diagnostic, B4, seed 1; not part of the recorded run).** A separate script reran QUIET and baseline from the same commit and, for each task completed in QUIET but not in the baseline, checked every spacecraft with an access window to that task's region: was it in a tasking mode (NOMINAL or STORM_WATCH) for its whole window? **23 Mar 2024:** 50 tasks lost; for 49, every spacecraft with access was protected for that task's entire window (32 priority 3, 17 priority 4); for 1, a peer was available throughout. **18 Jul 2023:** 22 lost; 19 with no spacecraft available, 3 with a peer available throughout. Most of the storm loss therefore happens while every spacecraft that can see the region is protected, which fits a close formation (four spacecraft 20 km apart in one train, a few seconds apart) passing through the same radiation environment. No handover rule, learned or not, can move a task to a spacecraft that is also protected.

## Findings

1. **The candidate changes no outcome on any of the four storms, under either planner.** The pooled gain is exactly 0 with a degenerate interval [0, 0]; by DL-094's rule the hypothesis is **rejected for both planners** on these storms. The candidate does act (1 – 6 early releases per run), but every released task is completed or lost exactly as in the baseline.
2. **The May 2024 B3 gain (+1 task, DL-097) does not recur.** On the five storms now measured (May plus these four), the candidate's total effect is one task on one storm under one planner.
3. **These storms do cost science, unlike May.** Retention falls to 0.853 on 23 Mar 2024 and 0.94 on 18 Jul 2023 (against 0.994 – 0.996 on May), so DL-098's search for room worked. But the room sits where no peer can absorb it: 68 of the 72 lost tasks the diagnostic classified (94 %) had no spacecraft in a tasking mode for their whole window.
4. **What remains recoverable is small.** The diagnostic finds 4 tasks across the two costly storms that a peer could in principle have taken; neither arm takes them. Why B4 misses them was not investigated.
5. **18 Jul 2023 leaves 0.5 h of unprotected hazard** (sc00 – sc02, 600 s each) in both arms. The handover rule cannot change protection by design (DL-079); this is a property of the forecast and supervisor on that storm and is recorded as a follow-up.
6. **Seeds again change nothing** (as in DL-096 and DL-097); three seeds per group are effectively one sample, and the variation that matters here is between storms.

## Limits

- Four storms; with zero difference on all of them the pooled test has no spread to measure, and the result says nothing about storms of other shapes.
- The diagnostic is one seed, B4 only, from a script outside the repository; its counts are not part of the recorded run. The B3 losses were not classified.
- The setting was frozen on B4-only tuning (DL-094); B3 was not tuned.
- The formation geometry (four spacecraft, 20 km along-track spacing) makes simultaneous protection likely; a more spread-out constellation, where peers sit in different radiation environments, was not tested.

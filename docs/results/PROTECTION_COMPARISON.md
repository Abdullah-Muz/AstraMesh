# Shorter protection on the four evaluation storms

> **Status:** recorded 2026-11-12 from clean commit `0935e98` (`git_dirty: false`; 72 runs, 113 min on 12 workers). Phase 5 increment 4, before 4b (DL-101 – DL-104). Nothing was tuned: the setting is the one frozen in DL-103 (H = 600 s, D = 600 s, no margin). Awaiting owner review.

## Setup

- **Storms, model, seeds:** as in [`MULTI_STORM.md`](MULTI_STORM.md) (DL-099, DL-100): 18 Jul 2023, 29 Jul 2023, 29 Jan 2024 and 23 – 24 Mar 2024, each 690 600 s; per-spacecraft risk (position-based access, age rule 3600 s, tolerances 100 / 100 / 50 / 200 pfu, no outage), P-B median; planners B3 + timeout and B4; seeds 1 – 3.
- **Arms:** baseline and QUIET (config hashes equal the recorded DL-100 runs) and the candidate: the baseline with look-ahead H = 600 s (`environment.replay.access.horizon_s`, baseline 3600 s) and release dwell D = 600 s (`supervisor.release_dwell_s`, baseline 1800 s).
- **Test (DL-101):** retention gain (candidate − baseline, ÷ QUIET) per storm, pooled over the four storms with a 95 % t-interval and a Wilcoxon test. The hypothesis is rejected for a planner if the interval includes 0 or lies below it, or if any spacecraft's unprotected hazard exceeds the baseline's by more than 600 s on any storm and seed.
- **Reproduce:** `uv run python scripts/experiments/protection_comparison.py --out <dir>` (about 2 h on 12 workers; candidate B3 runs take 36 – 45 min against 27 – 37 min for the baseline, most likely from the extra task re-auctions after each protection entry). Files: [`protection_runs.csv`](protection_runs.csv), [`protection_summary.csv`](protection_summary.csv), [`protection_meta.json`](protection_meta.json).

## Results

Every group gave the same outcome on all three seeds, so each cell below is one value.

| Storm | Planner | Baseline | Candidate | QUIET | Gain | Extra unprotected (s) |
|---|---|---|---|---|---|---|
| 18 Jul 2023 | B3 + timeout | 1 067 (320) | 1 078 (323) | 1 133 (340) | +0.0097 | 0 |
| 18 Jul 2023 | B4 | 1 060 (318) | 1 075 (322) | 1 133 (340) | +0.0132 | 0 |
| 29 Jul 2023 | B3 + timeout | 1 131 (339) | 1 140 (342) | 1 140 (342) | +0.0079 | 0 |
| 29 Jul 2023 | B4 | 1 131 (339) | 1 140 (342) | 1 140 (342) | +0.0079 | 0 |
| 29 Jan 2024 | B3 + timeout | 1 136 (341) | 1 132 (340) | 1 136 (341) | −0.0035 | 0 |
| 29 Jan 2024 | B4 | 1 136 (341) | 1 136 (341) | 1 136 (341) | 0 | 0 |
| 23 Mar 2024 | B3 + timeout | 969 (291) | 985 (295) | 1 136 (341) | +0.0141 | 410 |
| 23 Mar 2024 | B4 | 969 (291) | 969 (291) | 1 136 (341) | 0 | 410 |

Utility with tasks completed in brackets. No run has duplicates, exposure or payload steps in protected modes.

| Planner | Pooled gain | 95 % t-interval | Wilcoxon p | Worst extra unprotected | Verdict |
|---|---|---|---|---|---|
| B3 + timeout | +0.0070 | [−0.0049, +0.0190] | 0.25 | 410 s | **rejected** (interval includes 0) |
| B4 | +0.0053 | [−0.0050, +0.0156] | 0.50 | 410 s | **rejected** (interval includes 0) |

Charging duplicates changes nothing (there are none). The safety limit held everywhere: the only extra unprotected hazard is on 23 Mar 2024, 410 s on sc00 and sc01 (the 100 pfu spacecraft) and 10 s on sc02. The 600 s of unprotected hazard on sc00 – sc02 on 18 Jul 2023 (DL-100) is unchanged; it is the same in both arms.

**Protection time** (hours per spacecraft sc00 / sc01 / sc02 / sc03, the same under both planners; baseline → candidate):

| Storm | Hazard | Protected | Protected outside hazard | Protection entries |
|---|---|---|---|---|
| 18 Jul 2023 | 3.6 / 3.6 / 7.5 / 2.6 | 15.7 / 15.7 / 32.3 / 11.6 → 10.6 / 10.6 / 23.3 / 8.9 | 12.2 / 12.2 / 25.0 / 9.0 → 7.1 / 7.1 / 16.0 / 6.3 | 1 / 1 / 1 / 1 → 17 / 17 / 37 / 14 |
| 29 Jul 2023 | 1.7 / 1.7 / 5.4 / 0 | 12.4 / 12.4 / 26.6 / 2.8 → 5.8 / 5.8 / 19.7 / 0.5 | 10.7 / 10.7 / 21.2 / 2.8 → 4.2 / 4.2 / 14.2 / 0.5 | 2 / 2 / 1 / 1 → 10 / 10 / 31 / 1 |
| 29 Jan 2024 | 0.7 / 0.7 / 1.6 / 0 | 3.7 / 3.7 / 9.1 / 0 → 1.8 / 1.8 / 5.9 / 0 | 3.0 / 3.0 / 7.4 / 0 → 1.1 / 1.1 / 4.3 / 0 | 1 / 1 / 2 / 0 → 3 / 3 / 10 / 0 |
| 23 Mar 2024 | 9.3 / 9.3 / 11.5 / 7.7 | 32.2 / 32.2 / 44.1 / 27.6 → 25.8 / 25.8 / 34.4 / 22.3 | 22.9 / 22.9 / 32.6 / 19.9 → 16.5 / 16.5 / 22.9 / 14.6 | 2 / 2 / 1 / 1 → 40 / 40 / 53 / 34 |

## Diagnostic (not recorded): why 23 March recovers nothing under B4

B4, seed 1, scratchpad scripts run from the clean tree after the recording.

- The candidate loses the **same 50 tasks** against QUIET as the baseline.
- Every candidate protection entry is on radiation ≥ 1.0. The 40 – 53 protected spans per spacecraft each last about 40 min (median 39.5 – 39.8 min, longest 43 min): roughly the 10 min look-ahead, the pass through the hazard region, the 10 min dwell and the 5 min minimum recovery.
- With the 20 km formation the four spacecraft cross each region together, so **all four are out of the tasking modes at once for 22.2 h** (baseline 27.6 h).
- Of the 50 lost tasks, 38 have no window on any spacecraft in a tasking mode, 9 only part of a window, and 3 a whole window on a free peer (baseline: 49, 0, 1).

Shorter protection removes about a fifth of the protected time on this storm, but not the time that matters: the passes carrying these tasks are the hazardous passes themselves.

## Findings

1. **The tuning gain does not carry over.** On the February tuning storm the frozen setting recovered 35 of 74 lost points (DL-103). On the four evaluation storms it recovers 15 of 73 (B4) and 11 of 66 (B3) on 18 Jul, all 9 on 29 Jul, nothing on 29 Jan (no loss under B4; B3 loses 4 points to re-auction churn) and 0 (B4) or 16 (B3) of 167 on 23 Mar, the storm with the largest loss.
2. **Protected time falls by 20 – 82 % per spacecraft, science by at most 16 points.** On 23 Mar 2024 the time released does not cover the windows of the lost tasks (diagnostic above).
3. **On the strongest storm the limit is that the formation is together.** The spacecraft enter hazard together, so shorter protection cannot leave a peer free for the lost tasks. This is the question a spread constellation would answer; at the 20 km spacing it is not a protection-length question.
4. **Cycling has a cost under B3:** up to 53 entries per spacecraft a run instead of at most 2 coincide with longer B3 runs (wall time +30 – 40 %) and a 4-point loss on 29 Jan 2024. Cycling still has no modelled physical cost.

## Limits

- Four evaluation storms, so the pooled interval is wide (n = 4); seeds change no outcome.
- One frozen setting from one tuning storm and one planner (B4); B3 + timeout was not tuned.
- The diagnostic covers one storm, one planner and one seed and is not recorded.

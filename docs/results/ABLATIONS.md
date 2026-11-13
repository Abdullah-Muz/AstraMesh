# Ablations of the baseline protection system

> **Status:** recorded 2026-11-13 from clean commit `16f038e` (`git_dirty: false`; 180 runs, 3.7 h on 12 workers). Phase 5 increment 5 (DL-106 design, DL-107 code, DL-108 results). Descriptive: no hypothesis is accepted or rejected, nothing was tuned, and the expectations below were written into DL-106 before any run. Awaiting owner review.

## Setup

- **Storms:** the four DL-099 evaluation storms in the DL-100 setup ([`MULTI_STORM.md`](MULTI_STORM.md): 18 Jul 2023, 29 Jul 2023, 29 Jan 2024, 23 – 24 Mar 2024; per-spacecraft risk, tolerances 100 / 100 / 50 / 200 pfu, P-B median, no outage) and **May 2024** in the DL-097 S11-H main case ([`HANDOVER_COMPARISON.md`](HANDOVER_COMPARISON.md): P-B, sc01 forecast outage). May 2024 was the held-out test; this is a second use, disclosed in DL-106, and nothing is tuned on it.
- **Arms**, one change each against the full baseline:
  - **A1 no look-ahead:** `environment.replay.access.horizon_s` 10 s (one time step) instead of 3600 s, so the radiation input is the current position. The forecast is still P-B.
  - **A2 no forecast:** P-A (the latest measurement) instead of the P-B median.
  - **A3 no hysteresis:** `release_exposure_ratio` 0.99 (the schema needs it below the protect ratio 1.0); `release_dwell_s`, `watch_release_dwell_s` and `recovery_min_dwell_s` 0.
  - **A4 no reconciliation:** planner B0 (`static_b0`: the B4 ground plan, never redistributed) with the baseline protection, compared with each planner's baseline.
- **Planners:** A1 – A3 under B3 + timeout and under B4; A4 is one B0 arm per storm. Baseline and QUIET are rerun; their config hashes equal the recorded DL-100 and DL-097 runs (tested). B0 also has a QUIET run. **Seeds:** 1 – 3.
- **Measures:** retention change (ablation − baseline, ÷ that planner's QUIET) per storm; pooled over the five storms (n = 5) with a 95 % t-interval and a Wilcoxon test; unprotected hazard per spacecraft and its excess over the baseline; protected time, protection entries, exposure, payload steps in protected modes and duplicates. Under spec §10.2 a higher utility is never called better if it adds unprotected hazard.
- **Reproduce:** `uv run python scripts/experiments/ablation_study.py --out <dir>` (about 3.7 h on 12 workers; B3 runs take 21 – 41 min, B4 and B0 runs 2 – 4 min). Files: [`ablation_runs.csv`](ablation_runs.csv), [`ablation_summary.csv`](ablation_summary.csv), [`ablation_meta.json`](ablation_meta.json).

## Results

Every group gave the same outcome on all three seeds, so each cell is one value. Protection is identical under B3 + timeout, B4 and B0 for the same arm and storm; only the science differs.

**Utility** (points; QUIET is the same for B3 + timeout, B4 and B0):

| Storm | QUIET | Planner | Baseline | A1 no look-ahead | A2 no forecast | A3 no hysteresis | A4 no reconciliation (B0) |
|---|---|---|---|---|---|---|---|
| 18 Jul 2023 | 1 133 | B3 + timeout | 1 067 | 1 067 | 1 067 | 1 085 | 1 027 |
| | | B4 | 1 060 | 1 064 | 1 060 | 1 078 | 1 027 |
| 29 Jul 2023 | 1 140 | B3 + timeout | 1 131 | 1 137 | 1 140 | 1 137 | 1 061 |
| | | B4 | 1 131 | 1 140 | 1 140 | 1 140 | 1 061 |
| 29 Jan 2024 | 1 136 | B3 + timeout | 1 136 | 1 136 | 1 136 | 1 136 | 1 109 |
| | | B4 | 1 136 | 1 136 | 1 136 | 1 136 | 1 109 |
| 23 – 24 Mar 2024 | 1 136 | B3 + timeout | 969 | 973 | 976 | 972 | 939 |
| | | B4 | 969 | 973 | 976 | 972 | 939 |
| May 2024 (S11-H) | 1 136 | B3 + timeout | 1 132 | 1 136 | 1 136 | 1 132 | 985 |
| | | B4 | 1 129 | 1 129 | 1 129 | 1 129 | 985 |

No run has duplicates or payload steps in protected modes. Exposure is 50 s on 18 Jul 2023 in every arm and 60 s on 29 Jan 2024 under A2; it is 0 everywhere else.

**Pooled retention change** (n = 5 storms; mean, 95 % t-interval, Wilcoxon p) and the largest extra unprotected hazard on any spacecraft, storm and seed:

| Ablation | B3 + timeout | B4 | Worst extra unprotected hazard |
|---|---|---|---|
| A1 no look-ahead | +0.0025 [−0.0005, +0.0054], p 0.25 | +0.0030 [−0.0011, +0.0070], p 0.25 | 390 s (29 Jul, sc02) |
| A2 no forecast | +0.0035 [−0.0009, +0.0079], p 0.25 | +0.0028 [−0.0020, +0.0077], p 0.50 | 600 s (May, sc02) |
| A3 no hysteresis | +0.0048 [−0.0034, +0.0129], p 0.25 | +0.0053 [−0.0031, +0.0137], p 0.25 | 410 s (23 Mar, sc00 and sc01) |
| A4 no reconciliation | −0.0553 [−0.1099, −0.0006], p 0.0625 | −0.0535 [−0.1078, +0.0008], p 0.0625 | 0 |

With n = 5, 0.0625 is the smallest p a two-sided Wilcoxon test can give (all five storms with the same sign).

**Protection** (sums over the four spacecraft, the same under every planner; baseline / A1 / A2 / A3; A4 equals the baseline):

| Storm | Hazard (h) | Protected (h) | Protection entries | Unprotected hazard (s) |
|---|---|---|---|---|
| 18 Jul 2023 | 17.4 | 75.3 / 66.5 / 73.6 / 63.5 | 4 / 85 / 4 / 9 | 1 800 / 1 800 / 1 800 / 1 800 |
| 29 Jul 2023 | 8.8 | 54.2 / 40.7 / 40.9 / 35.5 | 6 / 52 / 3 / 17 | 0 / 390 / 50 / 370 |
| 29 Jan 2024 | 3.0 | 16.4 / 11.7 / 15.2 / 10.4 | 4 / 15 / 4 / 5 | 0 / 0 / 1 510 / 0 |
| 23 – 24 Mar 2024 | 37.9 | 136.2 / 130.3 / 134.3 / 125.8 | 6 / 161 / 6 / 30 | 0 / 670 / 820 / 1 020 |
| May 2024 | 17.7 | 91.7 / 72.5 / 77.3 / 60.3 | 10 / 61 / 12 / 35 | 970 / 1 010 / 2 310 / 1 570 |

**Unprotected hazard per spacecraft** (s, sc00 / sc01 / sc02 / sc03; only storms where an arm differs from the baseline):

| Storm | Baseline | A1 | A2 | A3 |
|---|---|---|---|---|
| 29 Jul 2023 | 0 / 0 / 0 / 0 | 0 / 0 / 390 / 0 | 0 / 0 / 50 / 0 | 0 / 0 / 370 / 0 |
| 29 Jan 2024 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 560 / 560 / 390 / 0 | 0 / 0 / 0 / 0 |
| 23 – 24 Mar 2024 | 0 / 0 / 0 / 0 | 270 / 270 / 130 / 0 | 410 / 410 / 0 / 0 | 410 / 410 / 200 / 0 |
| May 2024 | 0 / 680 / 290 / 0 | 0 / 680 / 330 / 0 | 370 / 1 050 / 890 / 0 | 300 / 980 / 290 / 0 |

On 18 Jul 2023 every arm has 600 / 600 / 600 / 0.

## Expectations (DL-106, before any run) against the outcome

| Ablation | Expected | Outcome |
|---|---|---|
| A1 no look-ahead | Raises retention most; adds unprotected hazard | **Partly.** It adds unprotected hazard on 3 of 5 storms (up to 390 s on one spacecraft). Its retention gain is the smallest of A1 – A3, not the largest. Not expected: it cycles most, with 15 – 161 entries per storm against 4 – 10. |
| A2 no forecast | Adds hazard at onsets; changes little else | **Mostly.** It adds the most unprotected hazard (4 of 5 storms, up to 600 s on one spacecraft) and the only new exposure (60 s on 29 Jan 2024), with entries unchanged (3 – 12). Where in each storm the extra hazard falls was not located, so "at onsets" is not checked. |
| A3 no hysteresis | Adds protection entries and little hazard | **Partly.** Entries rise (5 – 35 against 4 – 10), but it adds unprotected hazard on 3 of 5 storms (up to 410 s on one spacecraft, against A1's 390 s). It has the largest retention gain and the largest cut in protected time (6 – 31 h per storm). |
| A4 no reconciliation | Lowers retention little | **Wrong.** It has the largest effect: −0.053 to −0.055 pooled, negative on every storm under both planners, from −27 points (29 Jan) to −144 and −147 (May). |

**Why the A4 expectation was wrong.** The DL-100 diagnostic classified the tasks still lost *after* B4 had redistributed (49 of 50 on 23 Mar had no spacecraft in a tasking mode). It said nothing about what redistribution itself recovers. The spacecraft do not protect for the same time, because their tolerances differ: on 23 Mar 2024 sc02 (50 pfu) is protected for 44.1 h and sc03 (200 pfu) for 27.6 h. Peers therefore take tasks, and B4 hands on 226 – 246 tasks per run (DL-100). Without protection, reconciliation is worth nothing here: B0's QUIET utility equals B4's on every storm. The May 2024 loss is largest because S11-H adds a forecast outage on sc01.

## 18 Jul 2023 onset (DL-106 follow-up)

From [`storm_diagnostics.json`](storm_diagnostics.json) (B4, seed 1, baseline). On 18 Jul 2023, sc00 and sc01 entered STORM_WATCH at 01:15 UTC. Hazard began at 01:45, when the true flux was 163.9 pfu against their 100 pfu tolerance and the radiation input the supervisor saw was 0.626. They entered PROTECTIVE at 01:55. sc02 entered STORM_WATCH and hazard at the same step, 00:55 (51.6 pfu against 50, input 0.860), and protected at 01:05. sc03 (200 pfu) had no unprotected hazard.

Each interval is exactly 600 s, and no ablation changes it: not P-A, not the current-position input, not the release settings. 600 s equals the series' data latency (`latency_s` 600 in `configs/data/fold_jul18_2023_series.json`: a value reaches the spacecraft 10 min after its time stamp). The onset is therefore consistent with latency, not with the forecast model or the supervisor; this was not tested by varying the latency.

## Findings

1. **Reconciliation is the component that protects science.** Removing it costs 5.3 – 5.5 % of QUIET utility pooled (up to 13 % on May 2024) and changes no protection outcome. The B3 + timeout interval excludes 0; the B4 interval reaches +0.0008.
2. **Each protection component costs little science and buys hazard reduction.** Removing look-ahead, forecast or hysteresis gains at most 18 points on any storm and +0.0025 to +0.0053 pooled. The intervals include 0; their upper bounds are +0.005 to +0.014 of QUIET utility, so gains that small are not excluded. Each removal adds unprotected hazard on 3 or 4 of the 5 storms, so by spec §10.2 none is better than the baseline.
3. **What each component buys.** The forecast prevents the most unprotected hazard (up to 600 s per spacecraft) and the only new exposure. Look-ahead prevents heavy cycling (up to 27 times the entries) and up to 390 s. Hysteresis prevents up to 410 s and some cycling, at the largest cost in protected time (6 – 31 h per storm, at most 18 points).
4. **The 18 Jul 2023 onset is not a protection-design question.** The 600 s per spacecraft is the same in every arm and matches the data latency.
5. **Planners and seeds.** Protection is planner-independent. Under A1 – A3 the retention changes of B3 + timeout and B4 differ by at most 4 points (0.0035) on any storm, and seeds change no outcome.

## Limits

- **n = 5 storms;** seeds change no outcome, so three seeds per group are one sample. Effects of a few points are within what these storms can resolve.
- **One change at a time;** interactions between components were not tested. A3 sets the release ratio to 0.99, not 1.0, because the schema requires it below the protect ratio.
- **May 2024 is a second use** of the held-out storm (disclosed in DL-106), and its case includes the sc01 forecast outage, which enlarges the A4 loss.
- **Not investigated:** why A1's many entries add only a few hundred seconds of hazard, and where in the storm A2's extra hazard falls. Cycling has no modelled physical cost.
- **Generality (DL-106 F3):** the formation is four spacecraft 20 km apart, so every task has windows on all four. The results hold for this close formation; the spread run is in [`SPREAD_FORMATION.md`](SPREAD_FORMATION.md).

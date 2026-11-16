# Held-out storms after May 2024

> **Status:** recorded 2026-11-14 from clean commit `32e005a` (`git_dirty: false`; 288 runs, 8.2 h of process time on 12 workers). Phase 6 increment 1 (DL-113 design, DL-114 data and code, DL-115 results). Every method, setting and forecast was frozen before the run, and the expectations below were written into DL-113 before any held-out run. The results are reported as they came out. Approved by the owner 2026-11-14.

## Setup

- **Storms:** the six test storms that the DL-113 rule selected from 1 Jun 2024 – 31 Oct 2026 (DL-114; data DS-11 GOES-18 SGPS and DS-12 OMNI 1-min). Two more qualifying windows are reserved and were not run or inspected beyond their start dates.

  | Storm (window start) | First record ≥ 100 pfu | Peak | Hours ≥ 100 pfu | SYM-H min | GOES processing |
  |---|---|---|---|---|---|
  | 6 Jun 2024 | 8 Jun 04:50 | 1 111 pfu | 18.3 | −52 nT | v3-0-2 |
  | 7 Oct 2024 | 9 Oct 07:35 | 3 298 pfu | 37.9 | −343 nT | v3-0-2 |
  | 25 Oct 2024 | 27 Oct 08:30 | 374 pfu | 54.3 | −33 nT | v3-0-2 |
  | 30 Mar 2025 | 1 Apr 01:55 | 160 pfu | 8.1 | −87 nT | v3-0-2 |
  | 9 Nov 2025 | 11 Nov 12:20 | 1 458 pfu | 34.0 | −253 nT | v3-0-2 |
  | 17 Jan 2026 | 19 Jan 04:35 | 39 231 pfu | 29.1 | −251 nT | v3-0-3 |

- **Setup:** the DL-100 setup (per-spacecraft risk, tolerances 100 / 100 / 50 / 200 pfu, P-B median, no outage, 20 km formation). The forecasts are the frozen S11 models, fitted on January 2023 – April 2024 only. The 17 Jan 2026 peak is 37 times the training maximum.
- **Arms:** each arm is defined exactly as in Phase 5; the code tests that the configs are equal.
  - Under B3 + timeout and under B4: baseline, QUIET, forecast handover (θ 0.9, L 30 min; DL-096), shorter protection (H 600 s, D 600 s, no margin; DL-103), A1 no look-ahead, A2 no forecast, A3 no hysteresis (DL-106).
  - Under B0: baseline and QUIET. B0 is A4, no reconciliation.
  - Seeds 1 – 3.
- **Measures (DL-113):**
  - Per storm: the retention change (arm − baseline, divided by that planner's QUIET); extra unprotected hazard per spacecraft; protected time; protection entries; exposure; payload steps in protected modes; duplicates and the duplicate-charged utility.
  - Pooled over storms (n = 6): mean, 95 % t-interval and Wilcoxon test, for all test storms and separately by GOES processing version.
  - Under spec §10.2, a higher utility is never called better if it adds unprotected hazard.
- **Reproduce:** `uv run python scripts/experiments/heldout_comparison.py --out <dir>`.
  - Files: [`heldout_runs.csv`](heldout_runs.csv), [`heldout_summary.csv`](heldout_summary.csv) and [`heldout_meta.json`](heldout_meta.json); the meta file holds E1 – E5 as evaluated by code.
  - Run times: B4 and B0 runs take 2 – 5 min; B3 + timeout runs take 20 – 96 min (median 38 min), the longest under shorter protection.
  - The laptop slept overnight during the run, so the elapsed time was 22.9 h. The run times come from the monotonic clock and are indicative only.

## Results

Every group gave the same outcome on all three seeds, so each cell is one value. Protection (hazard, protected time, entries and unprotected hazard) is identical under B3 + timeout, B4 and B0 for the same arm and storm. Exposure counts observation time spent in hazard, so it also depends on the plan.

**Utility** (points; QUIET is the same under every planner; 345 – 347 tasks per storm):

| Storm | QUIET | Planner | Baseline | Handover | Shorter | A1 no look-ahead | A2 no forecast | A3 no hysteresis | A4 no reconciliation (B0) |
|---|---|---|---|---|---|---|---|---|---|
| 6 Jun 2024 | 1 144 | B3 + timeout | 1 071 | 1 071 | 1 078 | 1 071 | 1 071 | 1 074 | 1 025 |
| | | B4 | 1 068 | 1 068 | 1 071 | 1 068 | 1 068 | 1 071 | 1 025 |
| 7 Oct 2024 | 1 136 | B3 + timeout | 919 | 919 | 950 | 919 | 919 | 933 | 898 |
| | | B4 | 919 | 919 | 922 | **347** | 919 | 933 | 898 |
| 25 Oct 2024 | 1 133 | B3 + timeout | 867 | 867 | 942 | 924 | 923 | 920 | 748 |
| | | B4 | 867 | 867 | 910 | 921 | 920 | 920 | 748 |
| 30 Mar 2025 | 1 137 | B3 + timeout | 1 137 | 1 137 | 1 137 | 1 137 | 1 137 | 1 137 | 1 077 |
| | | B4 | 1 134 | 1 134 | 1 134 | 1 134 | 1 134 | 1 134 | 1 077 |
| 9 Nov 2025 | 1 136 | B3 + timeout | 1 017 | 1 017 | 1 028 | 1 017 | 1 017 | 1 020 | 925 |
| | | B4 | 1 017 | 1 017 | 1 020 | 1 017 | 1 017 | 1 020 | 925 |
| 17 Jan 2026 | 1 133 | B3 + timeout | 971 | 968 | 990 | 988 | 974 | 995 | 903 |
| | | B4 | 974 | 974 | 992 | **919** | 974 | 1 001 | 903 |

No run has duplicates or payload steps in protected modes, so the duplicate-charged utility equals the utility. Exposure is 0 on every storm except:

- **25 Oct 2024 under A2:** 60 s (B3 + timeout) and 100 s (B4).
- **17 Jan 2026:**
  - B4: 50 s in every arm except A1 (0 s).
  - B3 + timeout: 50 s in the baseline and handover, 60 s under shorter, A1 and A3, and 120 s under A2.
  - B0: 0 s.

**Pooled retention change, all test storms** (n = 6; mean, 95 % t-interval, Wilcoxon p), the largest extra unprotected hazard on any spacecraft, storm and seed, and the number of storms with any extra unprotected hazard:

| Compared with the baseline | B3 + timeout | B4 | Worst extra unprotected | Storms with extra unprotected |
|---|---|---|---|---|
| Forecast handover | −0.0004 [−0.0016, +0.0007], p 1.0 | 0 [0, 0], p 1.0 | 0 | 0 of 6 |
| Shorter protection | +0.0210 [−0.0042, +0.0462], p 0.0625 | +0.0103 [−0.0051, +0.0257], p 0.0625 | 490 s (17 Jan, sc02) | 2 of 6 |
| A1 no look-ahead | +0.0109 [−0.0103, +0.0321], p 0.50 | −0.0841 [−0.3021, +0.1339], p 0.50 | 490 s (17 Jan, sc02) | 3 of 6 |
| A2 no forecast | +0.0087 [−0.0123, +0.0297], p 0.50 | +0.0078 [−0.0122, +0.0278], p 1.0 | 430 s (17 Jan, sc00) | 5 of 6 |
| A3 no hysteresis | +0.0143 [−0.0044, +0.0329], p 0.0625 | +0.0147 [−0.0042, +0.0336], p 0.0625 | 1 680 s (17 Jan, sc02) | 3 of 6 |
| A4 no reconciliation | −0.0596 [−0.0915, −0.0276], p 0.031 | −0.0591 [−0.0916, −0.0267], p 0.031 | 0 | 0 of 6 |

The Wilcoxon test drops storms with a zero change. With six nonzero changes the smallest two-sided p is 0.031; with five it is 0.0625. The protection counts are the same under both planners.

**By GOES processing version.** v3-0-2 is five storms (n = 5); v3-0-3 is one storm, 17 Jan 2026, so it has no interval.

| Compared with the baseline | v3-0-2, B3 + timeout | v3-0-2, B4 | v3-0-3, B3 + timeout | v3-0-3, B4 |
|---|---|---|---|---|
| Forecast handover | 0 [0, 0] | 0 [0, 0] | −0.0026 | 0 |
| Shorter protection | +0.0219 [−0.0114, +0.0551] | +0.0092 [−0.0109, +0.0292] | +0.0168 | +0.0159 |
| A1 no look-ahead | +0.0101 [−0.0179, +0.0380] | −0.0912 [−0.3785, +0.1962] | +0.0150 | −0.0485 |
| A2 no forecast | +0.0099 [−0.0176, +0.0373] | +0.0094 [−0.0166, +0.0353] | +0.0026 | 0 |
| A3 no hysteresis | +0.0129 [−0.0114, +0.0371] | +0.0129 [−0.0114, +0.0371] | +0.0212 | +0.0238 |
| A4 no reconciliation | −0.0595 [−0.1018, −0.0172] | −0.0584 [−0.1014, −0.0155] | −0.0600 | −0.0627 |

The v3-0-3 storm's retention changes lie within the range of the five v3-0-2 storms on every comparison except forecast handover under B3 + timeout (−3 points, against 0 on every v3-0-2 storm). Its A1 loss under B4 is the same B4 defect as on 7 Oct 2024 (see below). It does have the largest extra unprotected hazard, and the baseline's only exposure. With one storm, neither result can be separated from the storm's size: its peak is 37 times the training maximum.

**Protection** (sums over the four spacecraft, the same under every planner; baseline / shorter / A1 / A2 / A3; handover and A4 equal the baseline):

| Storm | Hazard (h) | Protected (h) | Protection entries | Unprotected hazard (s) |
|---|---|---|---|---|
| 6 Jun 2024 | 20.8 | 86.2 / 62.0 / 77.4 / 83.5 / 76.3 | 4 / 98 / 98 / 4 / 4 | 480 / 480 / 480 / 1 160 / 480 |
| 7 Oct 2024 | 44.2 | 156.2 / 125.2 / 154.2 / 154.8 / 152.2 | 4 / 193 / 178 / 4 / 4 | 0 in every arm |
| 25 Oct 2024 | 60.5 | 268.2 / 189.9 / 235.2 / 253.0 / 236.5 | 4 / 303 / 293 / 4 / 23 | 0 / 0 / 410 / 290 / 300 |
| 30 Mar 2025 | 9.5 | 45.7 / 31.1 / 35.4 / 37.8 / 36.0 | 5 / 50 / 45 / 3 / 9 | 120 / 120 / 120 / 420 / 120 |
| 9 Nov 2025 | 44.3 | 142.2 / 116.1 / 134.9 / 140.1 / 133.3 | 4 / 169 / 101 / 6 / 8 | 0 / 520 / 520 / 10 / 510 |
| 17 Jan 2026 | 36.4 | 140.1 / 110.5 / 132.3 / 133.8 / 122.5 | 15 / 172 / 147 / 13 / 34 | 500 / 1 400 / 1 400 / 1 600 / 2 590 |

**Unprotected hazard per spacecraft** (s, sc00 / sc01 / sc02 / sc03; only storms where an arm differs from the baseline):

| Storm | Baseline | Shorter | A1 | A2 | A3 |
|---|---|---|---|---|---|
| 6 Jun 2024 | 240 / 240 / 0 / 0 | as baseline | as baseline | 540 / 540 / 80 / 0 | as baseline |
| 25 Oct 2024 | 0 / 0 / 0 / 0 | as baseline | 0 / 0 / 0 / 410 | 0 / 0 / 100 / 190 | 0 / 0 / 0 / 300 |
| 30 Mar 2025 | 0 / 0 / 120 / 0 | as baseline | as baseline | 0 / 0 / 420 / 0 | as baseline |
| 9 Nov 2025 | 0 / 0 / 0 / 0 | 260 / 260 / 0 / 0 | 260 / 260 / 0 / 0 | 0 / 10 / 0 / 0 | 260 / 250 / 0 / 0 |
| 17 Jan 2026 | 0 / 0 / 0 / 500 | 210 / 200 / 490 / 500 | 210 / 200 / 490 / 500 | 430 / 420 / 0 / 750 | 210 / 200 / 1 680 / 500 |

The baseline has unprotected hazard on three storms: 240 s on sc00 and sc01 on 6 Jun 2024, 120 s on sc02 on 30 Mar 2025, and 500 s on sc03 on 17 Jan 2026. Whether these onsets come from the 600 s data latency, as on 18 Jul 2023 (DL-108), was not checked.

## Expectations (DL-113, before any run) against the outcome

| Expectation | Rule | Outcome |
|---|---|---|
| E1 Forecast handover gains nothing reliable | Not held if the pooled interval lies above 0 under either planner | **Held.** Under B4 it changes no outcome on any storm. Under B3 + timeout it changes one storm, 17 Jan 2026, by −3 points. As in Phase 5, the candidate acts but does not change which tasks are done. |
| E2 Shorter protection gains nothing reliable | Not held if the pooled interval lies above 0 with the worst extra unprotected hazard ≤ 600 s | **Held.** Both intervals include 0. However, the change is ≥ 0 on all six storms under both planners. The B3 + timeout mean, +0.021, is three times its Phase 5 value (+0.007), mostly from 25 Oct 2024 (+75 points). It also adds unprotected hazard on 2 of 6 storms (up to 490 s on one spacecraft), so by spec §10.2 it is not better. |
| E3 Removing reconciliation costs science | Held only if the pooled interval lies below 0 under both planners | **Held.** −0.0596 and −0.0591 pooled, negative on every storm under both planners: from −21 points (7 Oct 2024) to −119 (25 Oct 2024). This is close to Phase 5 (−0.053 to −0.055), and both intervals now exclude 0. |
| E4 Each of A1 – A3 adds unprotected hazard on more than half the storms | Held for an ablation if it adds unprotected hazard on more than half the storms under each planner | **Held for A2 only.** A2 adds it on 5 of 6 storms. A1 and A3 each add it on exactly 3 of 6, which is not more than half. Phase 5 had 3 of 5 for both. A3 has the largest single excess: 1 680 s on sc02 on 17 Jan 2026. |
| E5 Seeds change no outcome | Not held if any group's seeds differ in utility or unprotected hazard | **Held.** No group differs across seeds. |

## Not expected: B4 loses tasks to a split ownership view

Under A1 (no look-ahead), B4 completes 104 tasks on 7 Oct 2024 against 276 in its baseline. That is a retention change of −0.50, and far below B0's 270. On 17 Jan 2026 it completes 276 against 293. B3 + timeout has the same protection in both runs and loses nothing, so the loss is in B4, not in protection.

**Diagnostic (not recorded):** the B4 seed 1 runs of both storms were rerun from the clean tree with a scratch script, which is not committed.

- **7 Oct 2024:** 172 tasks are completed in the baseline but not under A1. 17 Jan 2026 has 18 such tasks.
- **Availability:** in every case but one, a spacecraft with a window was in a tasking mode for the whole window. No spacecraft attempted any of these tasks.
- **When:** on 7 Oct 2024 the lost tasks lie on days 3 – 7 of the window, mostly after the storm (11 – 14 Oct). On 17 Jan 2026 all are on day 3 (20 Jan).
- **Ownership:** at the end of both runs the agents disagree on who owns these tasks. sc00, sc01 and sc02 record sc03 as the owner; sc03 records sc02.

Each B4 agent applies the hand-on rule to its own copy of the task table. B4 has no handback (DL-102) and no step that reconciles ownership again. A split, once it forms, therefore lasts for the rest of the run. In these two A1 runs each spacecraft enters protection 25 – 45 times, so B4 hands on far more often than in the baseline (4 – 15 entries per storm, summed over the spacecraft). Shorter protection cycles as much, but lost no tasks this way on these storms. When and how the split forms was not located; it is added to the increment 3 analysis.

This is a robustness defect in the B4 baseline. By DL-113, no result changes a method, so B4 is reported as frozen. The A1 B4 interval, [−0.30, +0.13], measures this defect, not the cost or gain of look-ahead.

## Findings

1. **The Phase 5 main result holds on six unseen storms.** Neither G3 candidate improves on the baseline. Forecast handover changes almost nothing, as in Phase 5. Shorter protection gains a little science on five of six storms and ties on 30 Mar 2025 (up to 75 points; corrected 2026-11-16, DL-129: this finding first said "on every storm", which the utility table and E2 do not support). Its pooled interval still includes 0, and it adds unprotected hazard on 2 of 6 storms.
2. **Reconciliation is what protects science.** Without it, 5.9 – 6.0 % of QUIET utility is lost pooled, on every storm, and both intervals exclude 0. Protection is unchanged.
3. **Each protection component costs little science and prevents hazard, but less consistently than Phase 5 suggested.** The forecast prevents extra unprotected hazard on 5 of 6 storms. Look-ahead and hysteresis prevent it on 3 of 6 each, and when they do, by up to 490 s and 1 680 s on one spacecraft. Removing any one gains at most 57 points on any storm (+0.008 to +0.015 pooled, excluding A1 under B4); every interval includes 0.
4. **B4's rule-based hand-on can deadlock under heavy protection cycling.** Two of the 30 B4 storm × arm comparisons lose tasks that a spacecraft was available for, because the agents' ownership views split and nothing repairs them. B3 + timeout re-auctions and is not affected. This is new; Phase 5 did not show it.
5. **The v3-0-3 storm is not an outlier in science.** 17 Jan 2026 is the most hazardous storm for protection: the baseline's only exposure, and the largest extra unprotected hazard under every ablation. It is one storm, and far outside the training range.
6. **Seeds change no outcome**, so the sample is the six storms.

## Limits

- **n = 6 storms,** and only one under v3-0-3. Seeds change no outcome, so three seeds per group are one sample. Gains up to the upper bounds above (+0.046 of QUIET utility for shorter protection under B3 + timeout) are not excluded.
- **Frozen methods and forecasts.** The forecasts never saw v3-0-3 data or a peak like January 2026's. Nothing was tuned on these storms, and B4 was not repaired.
- **The B4 split was diagnosed on seed 1 only,** with a scratch script, from the final state. Increment 3 is to repeat it as a recorded diagnostic and locate when the split forms.
- **Not checked:** whether the baseline's unprotected hazard at onsets matches the data latency, as on 18 Jul 2023. The model limits of Phase 5 apply unchanged: one formation (four spacecraft, 20 km apart), synthetic tolerances, a GEO proxy flux and a dipole cutoff.
- **The two reserved windows** (from 19 Nov 2024 and 30 May 2025) remain unused for any later method.

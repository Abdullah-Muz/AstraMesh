# B4 ownership re-sync

> **Status:** recorded 2026-11-15 from clean commit `a94b654` (`git_dirty: false`; 214 runs, 1 h 20 min on 12 workers). Phase 6 increment 3b (DL-122 design, DL-123 code, DL-124 results). Approved by the owner 2026-11-15. The mechanism, its settings and the expectations R1 – R6 were fixed in DL-122 before any test-storm run, and nothing was changed after it. The results are reported as they came out.

## Setup

- **Variants:** B4 as recorded, and "B4 + re-sync": the same config with `agents.ownership_sync: {horizon_s: 10800, grace_status_intervals: 2}` (DL-122). Nothing else differs; the code tests this.
- **Re-sync in brief:** each STATUS from a spacecraft in a tasking mode lists the tasks it owns and has planned whose slot starts within 3 h or is in progress (its *claims*). A receiver resolves a claimed task its view gives to someone else in favour of the claimant already observing, then the lowest ID (*conflict*). It hands on by B4's rule a task its view gives to a sender that does not claim it, after a grace of 2 status intervals, for slots within the horizon that have not begun (*orphan*). Claims older than the status lifetime (60 s) are ignored.
- **Test storms** (DL-113's two reserved windows, never inspected before this run; facts from DL-123):

  | Storm (window start) | First record ≥ 100 pfu | Peak | Hours ≥ 100 pfu | SYM-H min | GOES processing |
  |---|---|---|---|---|---|
  | 19 Nov 2024 | 21 Nov 23:45 | 149.5 pfu | 6.9 | −45 nT | v3-0-2 |
  | 30 May 2025 | 1 Jun 05:40 | 706.2 pfu | 7.1 | −151 nT | v3-0-2 |

  Both are mild (the held-out storms reach 39 231 pfu and 54 h), which DL-123 stated before the run.
- **Test runs:** the held-out setup (DL-113): QUIET, baseline, shorter protection, A1 no look-ahead, A2 no forecast, A3 no hysteresis; B4 and B4 + re-sync; seeds 1 – 3. A B3 + timeout QUIET and baseline per test storm (seed 1) as a reference.
- **Development runs** (seed 1): the 69 B4 jobs of `negative_results.py` without the latency and handover variants: the five Phase 5 storms (shorter protection on the four DL-099 storms only), the six held-out storms, and the 2 000 and 5 000 km spread formations (QUIET, baseline). All were inspected in DL-121 and five of their jobs were used by the prototype, so they show how the re-sync behaves, not whether it generalises.
- **Measures (DL-122):** utility and the retention change (re-sync − B4, divided by that storm's QUIET); tasks lost while available (completed in the storm's B4 QUIET, not completed here, while some spacecraft was in a tasking mode for a whole window of the task) and how many of them are split (the four agents' owner views differ at the end); duplicates; a digest of the protection record (transitions, hazard, unprotected intervals); bytes sent.
- **Reproduce:** `uv run python scripts/experiments/resync_comparison.py --out <dir>`. Files: [`resync_runs.csv`](resync_runs.csv), [`resync_pairs.csv`](resync_pairs.csv) and [`resync_meta.json`](resync_meta.json); the meta file holds R1 – R6 as evaluated by code. Run times (monotonic clock, indicative): B4 106 – 313 s, B4 + re-sync 199 – 534 s, B3 + timeout 2 058 – 2 328 s.

## Expectations (DL-122, before any test run) against the outcome

| | Expectation | Test storms | Development storms |
|---|---|---|---|
| R1 | No task lost while available is split, in any re-sync run | **Held** (36 pairs) | **Held** (69) |
| R2 | Re-sync utility ≥ B4 in every run (checked on the storm arms; QUIET is R5, where they are equal) | **Held** (30) | **Held** (56) |
| R3 | No duplicates | **Held** (36) | **Not held:** 2 000 km spread, QUIET (B4 49 → re-sync 65) and baseline (15 → 111). B4 already has duplicates there, so the reading "adds no duplicates" (DL-122's question) fails on the same two pairs |
| R4 | Protection identical to B4 | **Held** (36) | **Held** (69) |
| R5 | QUIET utility unchanged | **Held** (6) | **Held** (13). The 2 000 km QUIET utility is unchanged, but its duplicates rise (R3) |
| R6 | Bytes sent rise by at most 20 % | **Held** (36; +9.3 – 9.7 %) | **Not held:** 5 000 km spread, QUIET (+25.3 %) and baseline (+21.9 %) |

DL-122 made the test storms decide the verdict: **all six held there.** But the re-sync changed nothing on them that the measures can see (next section), so the test shows that it does no harm on these two storms, not that it helps.

## Test storms

Every seed gave the same values, so each cell is one value for seeds 1 – 3. Utility (points):

| Storm | QUIET | Baseline | Shorter | A1 no look-ahead | A2 no forecast | A3 no hysteresis |
|---|---|---|---|---|---|---|
| 19 Nov 2024 | 1 136 | 1 136 | 1 132 | 1 136 | 1 133 | 1 136 |
| 30 May 2025 | 1 134 | 1 100 | 1 100 | 1 100 | 1 100 | 1 100 |

- **B4 and B4 + re-sync are equal in every one of the 36 pairs** (retention change 0). Duplicates are 0 in all of them, and protection is identical.
- **B4 lost nothing to a split here.** On 19 Nov 2024 the shorter and no-forecast arms each lose one task while a spacecraft was available, in every seed and under both variants. Neither task is split.
- **Split views:** only 30 May 2025 under shorter protection ends with split views (10, 6 and 6 tasks in seeds 1 – 3), identical under the re-sync. None of these tasks was lost while a spacecraft was available. Why the re-sync left them was not checked.
- **Bytes sent:** +9.3 – 9.7 % in every pair.
- **B3 + timeout reference** (seed 1): QUIET 1 136 and 1 134, baseline 1 136 and 1 100, 0 duplicates: the same utilities as B4.

## Development storms

Utility (points), B4 → B4 + re-sync where they differ (bold); the last column sums all arms:

| Storm | QUIET | Baseline | Shorter | A1 no look-ahead | A2 no forecast | A3 no hysteresis | Lost while available (split), B4 → re-sync |
|---|---|---|---|---|---|---|---|
| 29 Jan 2024 | 1 136 | 1 136 | 1 136 | 1 136 | 1 136 | 1 136 | 0 (0) → 0 (0) |
| 18 Jul 2023 | 1 133 | 1 060 → **1 067** | 1 075 → **1 078** | 1 064 → **1 067** | 1 060 → **1 067** | 1 078 → **1 085** | 13 (8) → 5 (0) |
| 29 Jul 2023 | 1 140 | 1 131 | 1 140 | 1 140 | 1 140 | 1 140 | 0 (0) → 0 (0) |
| 23 Mar 2024 | 1 136 | 969 | 969 → **985** | 973 | 976 | 972 | 6 (2) → 4 (0) |
| May 2024 | 1 136 | 1 129 → **1 136** | — | 1 129 → **1 136** | 1 129 → **1 136** | 1 129 → **1 136** | 8 (8) → 0 (0) |
| 6 Jun 2024 | 1 144 | 1 068 → **1 071** | 1 071 → **1 078** | 1 068 → **1 071** | 1 068 → **1 071** | 1 071 → **1 074** | 5 (5) → 0 (0) |
| 7 Oct 2024 | 1 136 | 919 | 922 → **950** | 347 → **919** | 919 | 933 | 178 (178) → 1 (0) |
| 25 Oct 2024 | 1 133 | 867 | 910 → **942** | 921 → **930** | 920 | 920 | 9 (8) → 1 (0) |
| 30 Mar 2025 | 1 137 | 1 134 → **1 137** | 1 134 → **1 137** | 1 134 → **1 137** | 1 134 → **1 137** | 1 134 → **1 137** | 5 (5) → 0 (0) |
| 9 Nov 2025 | 1 136 | 1 017 | 1 020 → **1 032** | 1 017 | 1 017 | 1 020 | 0 (0) → 0 (0) |
| 17 Jan 2026 | 1 133 | 974 | 992 → **1 004** | 919 → **994** | 974 | 1 001 | 28 (25) → 3 (0) |

- **Utility** rises in 28 of the 56 storm pairs and falls in none (spread runs included). The retention change is 0 – 0.504, mean 0.014; the largest is 7 Oct 2024 without look-ahead, where the re-sync recovers B4's split loss (347 → 919, the baseline value).
- **Lost while available:** 261 tasks (248 split) under B4 → 14 (none split) under the re-sync, over all development pairs. The 14 remaining are not split; DL-121's N2 class (protected after the slot began) fits them but was not checked.
- **Split views at the end** fall from 924 to 648 tasks. Splits on tasks whose slots have passed are not claimed and cost nothing.
- **Bytes sent:** +8.4 – 9.7 % outside the spread runs.

## Spread formations: duplicates and bytes

| Spacing | Arm | Utility, B4 → re-sync | Duplicates, B4 → re-sync | Duplicate-charged utility, B4 → re-sync | Bytes |
|---|---|---|---|---|---|
| 2 000 km | QUIET | 2 549 → 2 549 | 49 → 65 | 2 388 → 2 336 | +16.8 % |
| 2 000 km | baseline | 2 095 → 2 126 | 15 → 111 | 2 046 → **1 758** | +16.0 % |
| 5 000 km | QUIET | 4 536 → 4 536 | 0 → 0 | 4 536 → 4 536 | +25.3 % |
| 5 000 km | baseline | 3 746 → 3 746 | 0 → 0 | 3 746 → 3 746 | +21.9 % |

(Duplicate-charged: each duplicate costs its task's priority, as defined in DL-094. The B4 baseline value, 2 046, equals the one in [`SPREAD_FORMATION.md`](SPREAD_FORMATION.md).)

**Why the 2 000 km duplicates rise** (unrecorded diagnostic of the same four configs, seed 1; the utilities and duplicate counts equal the recorded ones):
- At 2 000 km spacing sc00 and sc03 are 6 000 km apart along track. That is beyond line of sight at 525 km altitude (about 5 400 km, [`SPREAD_FORMATION.md`](SPREAD_FORMATION.md)), so they never hear each other; at the start of every duplicate (240 cases) they were 5 814 – 5 819 km apart in a straight line and out of line of sight. Every duplicate, under both variants, is a task sc00 completed and sc03 then repeated.
- **Under B4** these already occur (49 in QUIET): sc00 hears nothing from sc03, believes it lost, and takes over its tasks, which sc03 still does.
- **Under the re-sync** all of B4's duplicates remain and more are added: 16 in QUIET and 96 in the baseline. Two routes add them, and both start from claims that never reach the spacecraft that needs them:
  - **Orphan flipping at sc03** (all 16 added in QUIET; 3 of the 96 in the baseline). sc00 owns the task and claims it, but sc03 cannot hear the claim. In sc03's view the task belongs to sc01 or sc02. Neither claims it, because their own views give it to sc00. So sc03's orphan rule hands it from one to the other, mostly every 60 s (the grace of 2 status intervals): 2 812 hand-ons on these 16 QUIET tasks. When only sc03's own slot is still ahead, sc03 assigns the task to itself and observes it again, starting 780 – 790 s after sc00 began.
  - **Both take it** (67 of the 96 in the baseline): sc00 through the orphan rule or B4's take-over, and sc03 through B4's take-over. In 26 more, only sc00 took over a task sc03 still did. sc01 and sc02 hear both claims and resolve the conflict, but only in their own views: the re-sync does not relay views.
- **Cause:** the rules assume that spacecraft sharing a task hear each other's claims. DL-122 did not state this. The 20 km formation meets it. The 5 000 km formation is not fully connected either (sc00 and sc02 are about 9 150 km apart), but there no task is shared, and the re-sync added no duplicates. The 2 000 km formation shares tasks between sc00 and sc03, which never hear each other.

**Why the 5 000 km bytes rise more** (unrecorded measurement by a subagent of 8 runs: B4 and re-sync, each QUIET at 20 km (23 Mar 2024), 2 000 km and 5 000 km, and the 5 000 km baseline. Every config hash and byte total equals the recorded run):
- The whole added cost is the claims list in each STATUS: 12 bytes for an empty list plus 11 bytes per task ID, on a STATUS of about 275 bytes. The number of STATUS messages is identical under both variants, and nothing is relayed or re-sent: the network counts each message's bytes once per send, whatever the number of receivers.
- The lists are longer when tasks are not shared. In the 20 km formation every task has windows on all four spacecraft, B4 gives each about 85, and a QUIET STATUS carries 1.33 claims on average (+9.4 %). At 5 000 km no task is shared, each spacecraft owns all of its own windows, and a QUIET STATUS carries 5.3 claims (+25.3 %). 2 000 km lies between them (+16.8 %).
- The 5 000 km baseline rises less (+21.9 %) because protected spacecraft claim nothing, and STORM_WATCH adds STATUS messages to the B4 total.
- The 20 % limit is crossed at about 4 claims per STATUS. Shorter IDs, sending only changes or a shorter horizon would reduce it; none was tested.

## Findings

1. **On the two test storms the re-sync is neutral:** every expectation held, and every utility, duplicate count and protection record equals B4's. B4 lost no task to a split on these mild storms, so there was nothing to recover. The test supports "does no harm here", not "helps".
2. **Where B4 splits, the re-sync recovers the loss** (development storms only, seed 1, in the 20 km formation where all four spacecraft hear each other; recovery on unseen storms is untested, since the test storms had no split loss): no lost task is split, utility never falls, and the largest loss (7 Oct 2024 without look-ahead, 347) returns to the baseline value (919). These storms were used to develop the mechanism.
3. **The re-sync needs spacecraft that share tasks to hear each other.** In the 2 000 km formation, where sc00 and sc03 share tasks but never have line of sight, it adds to B4's existing duplicates (15 → 111 in the baseline, 49 → 65 in QUIET) and churns owner views. With duplicates charged, its baseline utility falls from 2 046 to 1 758 (−0.113 of QUIET), although the uncharged utility rises by 31. It should stay off for such formations until it relays claims or views. That would be a new method (not built).
4. **Cost:** 8 – 10 % more bytes in the close formation; 16 – 25 % in the spread ones, where each spacecraft owns more tasks and so claims more. R6's 20 % limit was set after the prototype measured about 10 % in the 20 km formation (DL-122); it fails where tasks are not shared.
5. Protection is identical in all 105 pairs.

## Limits

- Two test storms, both mild; n = 2, so values are per storm without intervals. No untouched storm remains in the period, so a stronger test needs new data.
- Development results are seed 1 only, and the development storms were inspected while designing the mechanism.
- Lost while available uses the B4 QUIET of the same storm and seed as reference, and "available" uses the recorded mode transitions, as in DL-121.
- The duplicate diagnosis and the charged utilities come from an unrecorded re-run of the four 2 000 km configs (identical results); the diagnostic script is not part of the repo.
- The test-storm split views under shorter protection were not traced.
- `resync_runs.csv` keeps only the counts of tasks lost while available, not their IDs (the script drops the lists when writing it), so those counts, and R1, cannot be re-derived from the committed files. An independent recount (subagent) rebuilt every other pair value and every R1 – R6 verdict from `resync_runs.csv` and found no mismatch.

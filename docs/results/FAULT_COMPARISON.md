# Fault scenarios S01–S10: B0–B4 under faults and hazards

> **Status:** recorded 2026-11-04 from clean commit `311477a` (`git_dirty: false`). **Not a research result:** the faults and hazards are synthetic, and no proposed method exists yet. This run characterises the baselines and checks the Phase 3 safety properties at scale (spec §10.1, §13).

## Setup (DL-058)

- **Base configuration:** `configs/experiments/nominal_ops_b0_24h.yaml`, the same one used for the S00 comparison. The only things that change are `operations.algorithm`, `random.seed` (1…10) and the scenario's `faults` / `environment`.
- **Size of the run:** 10 scenarios × 6 methods × 10 seeds gives **600 runs** of 24 h each.
- **Paired fault draws:** each seed draws its fault parameters once, from the spec's `faults` stream, and every method uses them:
  - the affected spacecraft `a`;
  - a second spacecraft `b`;
  - a start time `t0` on the 10 s grid between 4 h and 10 h.

  The draws are listed in [`fault_comparison_meta.json`](fault_comparison_meta.json).
- **Retention** is U_fault / U_healthy for the same method and seed, where the healthy run is S00 (spec §3.4). Utility is the sum of priorities over completed tasks, out of 144 (DL-041).
- **Intervals:** brackets are 95% t-intervals with n = 10; a single number means every seed gave the same value. Wide intervals here usually mean that one or two seeds differ from the rest, not that the results are noisy (see finding 2).
- **Reproduce:** `uv run python scripts/experiments/fault_comparison.py --out docs/results`. On 8 workers this takes about 37 min. The run rows match the preview run exactly, except for B4, which the DL-059 fix changed, and the wall-time column.
- **Files:**
  - [`fault_comparison.csv`](fault_comparison.csv): one row per run;
  - [`fault_comparison_summary.csv`](fault_comparison_summary.csv): one row per scenario and method;
  - [`fault_comparison_meta.json`](fault_comparison_meta.json): commit, lockfile and config hashes, and the draws.

| Scenario | Injected condition (synthetic) |
|---|---|
| S01 | `a` permanently unavailable from t0 |
| S02 | `a` unavailable from t0, `b` from t0 + 6 h (both permanent) |
| S03 | `a` payload degraded for 12 h (observations are invalid; nothing in telemetry shows it) |
| S04 | `a` radio off for 3 h; the spacecraft keeps working (a false outage) |
| S05 | partition {a, b} \| {others} for 6 h, then the network reconnects |
| S07 | radiation risk on `a` at 1.2 × tolerance for 6 h |
| S08 | radiation risk on `a` at 1.1 × tolerance for 10 min (a brief alert) |
| S09 | S07 and S05 at the same t0 |
| S10 | S07, plus a critical fault on `a` from t0 + 1 h for 2 h |

S06 (stale or conflicting health reports) is deferred. S11 (the May 2024 storm) belongs to Phase 4.

## Safety invariants (Gate P3)

These held in **all 600 runs**:

- **Payload steps while protected:** 0. The payload was never commanded in PROTECTIVE, RECOVERY or SAFE.
- **Confirmed-failed beliefs about a spacecraft that was actually available:** 0. This includes S04 and S05, where peers wrongly believed `a` (or the other side of the partition) was lost for hours.
- **Same tasks for every method:** for every seed, all six methods saw the same task catalogue.
- **Mode sequence:** in S10, SAFE overrode PROTECTIVE. It exited only through RECOVERY, after the fault had cleared and the battery had been at or above 50% for 10 min. It then returned to PROTECTIVE because the hazard was still active.

## Results (mean over 10 seeds)

**Retention** (U_fault / U_healthy; 1.00 means no science lost):

| Scenario | B0 static | B1 central† | B2 auction | B3 CBBA | B3 + timeout | B4 rule |
|---|---|---|---|---|---|---|
| S01 | 0.81 [0.79, 0.83] | 0.93 [0.77, 1.09] | 0.93 [0.77, 1.09] | 0.93 [0.77, 1.09] | 1.00 | 1.00 |
| S02 | 0.68 [0.65, 0.70] | 0.74 [0.54, 0.94] | 0.74 [0.54, 0.94] | 0.74 [0.54, 0.94] | 1.00 | 1.00 [0.99, 1.00] |
| S03 | 0.88 [0.86, 0.89] | 0.95 [0.84, 1.06] | 0.95 [0.84, 1.06] | 0.95 [0.84, 1.06] | 0.95 [0.84, 1.06] | 0.88 [0.86, 0.89] |
| S04 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| S05 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| S07 | 0.93 [0.92, 0.93] | 0.97 [0.91, 1.04] | 0.97 [0.91, 1.04] | 1.00 | 1.00 | 1.00 |
| S08 | 0.99 [0.98, 1.00] | 1.00 [0.98, 1.01] | 1.00 [0.98, 1.01] | 1.00 | 1.00 | 1.00 |
| S09 | 0.93 [0.92, 0.93] | 0.97 [0.91, 1.04] | 0.97 [0.91, 1.04] | 1.00 | 1.00 | 1.00 |
| S10 | 0.93 [0.92, 0.93] | 0.97 [0.91, 1.04] | 0.97 [0.91, 1.04] | 1.00 | 1.00 | 1.00 |

† B1 plans with privileged truth: it is a reference, not a candidate.

**Duplicate observations** (repeats of an already completed task, which use energy and storage but earn nothing); the number of runs with duplicates is in parentheses:

| Scenario | B0 static | B1 central† | B2 auction | B3 CBBA | B3 + timeout | B4 rule |
|---|---|---|---|---|---|---|
| S01–S03 | 0 | 0 | 0 | 0 | 0 | 0 |
| S04 | 0 | 0 | 0 | 0 | 6.1 [4.1, 8.1] (10/10) | 33.1 [31.3, 34.9] (10/10) |
| S05 | 0 | 0 | 0 | 0 | 11.4 [11.0, 11.8] (10/10) | 33.1 [31.3, 34.9] (10/10) |
| S07 | 0 | 0 | 0 | 0 | 0 | 5.1 [4.5, 5.7] (10/10) |
| S08 | 0 | 0 | 0 | 0 | 0 | 7.8 [7.0, 8.6] (10/10) |
| S09 | 0 | 0 | 0 | 0 | 11.4 [11.0, 11.8] (10/10) | 38.2 [36.0, 40.4] (10/10) |
| S10 | 0 | 0 | 0 | 0 | 0 | 5.1 [4.5, 5.7] (10/10) |

**Other measures:**

- **Detection:** peers believed a lost spacecraft lost 296–300 s after it went silent, which is the 300 s timeout (DL-052) less up to one status interval.
- **False-unavailable time** is summed over observers, in observer-seconds:
  - S04: about 63 000 (six observer–peer pairs for about 3 h: three peers believe `a` is lost, and `a` believes all three are lost);
  - S05 and S09: about 170 500 (eight observer–peer pairs for about 6 h).
- **Messages per day:**
  - B0, B1, B2 and B4: about 11 500 (3.1 MB);
  - B3 and B3 + timeout: about 46 000 (about 59 MB).

  In S01 and S02, counts fall in proportion to the spacecraft lost.
- **Invalid observations in S03** (payload degraded):
  - B0 and B4: 5.4 [4.9, 5.9];
  - B1, B2, B3 and B3 + timeout: 2.1 [−2.7, 6.9], all of it from seed 4, where `a` = sc00.

## Findings

1. **Reacting to a loss recovers the science.**
   - In S01 and S02, B3 + timeout and B4 keep everything that is still observable: retention is 1.00 in every run, except one S02 run for B4 that kept 141 of 144.
   - The methods that do not react lose science: B0 keeps 0.81 in S01 and 0.68 in S02.
   - **The one B4 shortfall is a detection limit, not a planning fault:**
     - The run is S02, seed 5. Task TEC_0024's only slots open at 52 330–52 340 s, as `b` is lost (52 340 s), and peers detect the loss 300 s later.
     - Any timeout-based method has this cost. It shrinks only with faster detection.
2. **Without reaction, the damage depends on which spacecraft fails, not on the method.**
   - With q = 1, every spacecraft scores the same, so B1, B2 and B3 break ties towards sc00 and give it all 43 tasks. B0's greedy scheduler spreads them 11/11/11/10.
   - B1–B3 therefore lose nothing unless `a` (or, in S02, `b`) is sc00. This explains their wide intervals:
     - S01: one bad seed, utility 43;
     - S02: five bad seeds.
   - B0 loses the failed spacecraft's remaining tasks in every seed, which is 16–21% of utility in S01.
   - **Do not rank B0 against B1–B3 on these means.** The difference comes from tie-breaking, not from planning quality.
3. **The cost of reacting is duplication under false outages.**
   - When a spacecraft only goes quiet (S04 radio outage, S05/S09 partition), both reacting methods take over tasks it still performs. Every one of those runs has duplicates: B3 + timeout 6–11 per run, B4 33–38.
   - Pure CBBA never duplicates. It keeps the silent spacecraft's claims, and since nothing was actually lost, it loses no science either.
   - Because U does not penalise duplicates (DL-041), the reacting methods look free on utility alone. **They are not:** the energy and storage were spent, and on a tighter resource budget this would cost science.
   - Telling a real loss from a false outage (spec H2) is the trade-off a proposed method would have to improve.
4. **CBBA moves work away from a protected spacecraft cleanly; B4 duplicates when it returns.**
   - In S07–S10, the protected spacecraft stops bidding (TASKING_MODES) and its peers take its tasks. B3 and B3 + timeout keep 1.00 with no duplicates.
   - B4 also keeps 1.00, but has 5–8 duplicates per run. When the spacecraft returns to NOMINAL, it resumes its original plan, because B4 does not hand tasks back.
   - B0, B1 and B2 lose the science the protected spacecraft would have done.
5. **A brief alert costs far longer than the alert itself (S08).**
   - A 10 min alert at 1.1 × tolerance keeps the spacecraft out of science for about 45 min: 40 min in PROTECTIVE (the 30 min release dwell, DL-056) plus the 5 min minimum in RECOVERY.
   - Methods that cannot move tasks lose up to 1% of utility.
   - This is the deliberate price of no mode chatter. Whether the dwell is too long is a question for Phase 4, once real forecasts are used.
6. **No method detects a degraded payload (S03).**
   - The degradation does not show in telemetry, so every method keeps observing with the bad payload, and those observations are invalid.
   - Retention follows the same tie-breaking pattern as finding 2.
   - Detecting this needs a data-quality check, which no baseline has.

## Limits

- Synthetic faults and hazards: the timings, durations and exposure ratios are chosen, not data-informed. One fleet size (4), one day per run, ten seeds.
- **S01–S10 leave little room between methods.** All four spacecraft can see every pass, and resources are ample. A fleet that is short of energy or storage, or has unequal coverage, would separate the methods more.
- The q = 1 utility makes ownership depend on tie-breaking (finding 2). Duplicates are counted but not charged.
- Message cost is counted in canonical-JSON bytes, not modelled radio bandwidth. CPU time per run (`wall_s`) is not deterministic, so it is not summarised.
- The DL-059 B4 fix was found while checking the preview of this run; the preview is superseded. These results are from the fixed commit.

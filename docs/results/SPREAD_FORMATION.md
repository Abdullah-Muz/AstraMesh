# Spread formation on 23 – 24 March 2024

> **Status:** recorded 2026-11-13 from clean commit `16f038e` (`git_dirty: false`; 36 runs, 7 min on 12 workers). Phase 5 increment 5 (DL-105 preview, DL-106 design, DL-108 results). Descriptive; nothing was tuned. Awaiting owner review.

## Setup

- **Storm and model:** 23 – 24 Mar 2024 in the DL-100 setup ([`MULTI_STORM.md`](MULTI_STORM.md)): per-spacecraft risk, tolerances 100 / 100 / 50 / 200 pfu, P-B median, no outage. Planner B4. Seeds 1 – 3.
- **Spacing:** along-track 20 / 500 / 2 000 / 5 000 km in one orbit plane (at 5 000 km neighbours are 41.5° apart). The crosslink range is 6 000 km at every spacing, with line of sight still applied; at 525 km altitude neighbours lose line of sight beyond about 5 400 km.
- **Arms:** QUIET, the baseline protection, and the DL-103 shorter protection (look-ahead 600 s, release dwell 600 s, no margin). Spacing changes the task set, so retention is against QUIET at the same spacing.
- **Check against DL-100:** the 20 km baseline differs from the recorded DL-100 run only in crosslink range (100 → 6 000 km). It gives the same result, 969 points and 27.6 h with all four spacecraft out of the tasking modes. Every number also equals the DL-105 preview.
- **Reproduce:** `uv run python scripts/experiments/spread_formation.py --out <dir>` (about 7 min on 12 workers). Files: [`spread_runs.csv`](spread_runs.csv), [`spread_summary.csv`](spread_summary.csv), [`spread_meta.json`](spread_meta.json).

## Results

Every group gave the same outcome on all three seeds.

| Spacing | Tasks | Tasks with windows on > 1 spacecraft | QUIET | Baseline (retention) | Shorter (retention) | All four out of tasking modes (h) | Lost against QUIET | Duplicates |
|---|---|---|---|---|---|---|---|---|
| 20 km | 346 | 346 | 1 136 | 969 (0.853) | 969 (0.853) | 27.6 → 22.2 | 50 → 50 | 0 → 0 |
| 500 km | 367 | 344 | 1 164 | 987 (0.848) | 1 013 (0.870) | 27.6 → 20.5 | 53 → 46 | 0 → 0 |
| 2 000 km | 789 | 220 | 2 549 | 2 095 (0.822) | 2 195 (0.861) | 27.6 → 14.8 | 136 → 109 | 15 → 108 |
| 5 000 km | 1 383 | 0 | 4 536 | 3 746 (0.826) | 3 856 (0.850) | 27.6 → 8.4 | 237 → 208 | 0 → 0 |

Arrows are baseline → shorter protection. Utilities are in points. **With duplicates charged** at 2 000 km, the utilities are 2 046 (retention 0.803) for the baseline and 1 837 (0.721) for shorter protection. The other spacings have no duplicates.

**Protection** (per spacecraft sc00 / sc01 / sc02 / sc03):

| Spacing | Hazard, all four (h) | Protected, all four (h): baseline → shorter | Unprotected hazard (s), baseline | Unprotected hazard (s), shorter | Exposure (s) |
|---|---|---|---|---|---|
| 20 km | 37.9 | 136.2 → 108.2 | 0 / 0 / 0 / 0 | 410 / 410 / 10 / 0 | 0 |
| 500 km | 37.9 | 136.2 → 108.6 | 0 / 0 / 30 / 0 | 410 / 350 / 30 / 0 | 0 |
| 2 000 km | 38.1 | 136.2 → 108.6 | 0 / 0 / 420 / 0 | 410 / 150 / 420 / 0 | 0 |
| 5 000 km | 37.6 | 136.2 → 108.0 | 0 / 140 / 280 / 150 | 410 / 140 / 280 / 150 | 60 (both arms) |

The baseline's protected time is the same at every spacing, to the second on each spacecraft (116 100 / 116 100 / 158 700 / 99 300 s), and so are its protection entries (2 / 2 / 1 / 1). Shorter protection has 40 / 40 / 53 – 54 / 34 entries at every spacing. No run has payload steps in protected modes.

## Findings

1. **Spreading the formation does not reduce the storm's science cost under the baseline protection.** Retention is 0.853, 0.848, 0.822 and 0.826 from 20 to 5 000 km. At 5 000 km no task is shared, yet all four spacecraft are still out of the tasking modes together for 27.6 h.
2. **The baseline protects the same at every spacing.** The likely reason is the look-ahead. Each spacecraft's input is the forecast maximum over its own track for the next hour, and at 525 km an orbit takes about 95 min. Within any hour every spacecraft reaches the high-latitude region, whatever its phase, so all four protect on the forecast alone. This was not tested separately.
3. **Spacing matters only for shorter protection.** With look-ahead and dwell cut to 600 s, the time with all four out falls from 22.2 h to 8.4 h as the spacing grows. Retention gains 0, +0.022, +0.039 and +0.024 over the baseline. None of these gains is clean:
   - sc00 has 410 s of extra unprotected hazard at every spacing, the DL-104 result.
   - At 2 000 km, shorter protection makes 108 duplicates. Charged, it is 0.08 *below* the baseline.
   - By spec §10.2, no spacing makes shorter protection better than the baseline.
4. **Spreading adds a little unprotected hazard in the baseline itself:** up to 420 s on sc02 at 2 000 km, and 140 – 280 s on three spacecraft at 5 000 km with 60 s of exposure. The cause was not investigated.
5. **This answers DL-106 F3 for this storm.** The finding that "the storm loss is set by geometry" holds for the 20 km formation. At larger spacing the loss does not go away; it comes from the protection design (finding 2), not from shared tasks.

## Limits

- One storm, one planner (B4), and seeds that change no outcome: one sample per cell.
- QUIET rows record utility, tasks and completions but not duplicates, so the duplicate-charged retention uses the QUIET utility as its denominator.
- Along-track spacing in one plane, four spacecraft; spreads across planes, and the B3 + timeout planner, were not run.
- Finding 2's mechanism is an inference from the identical protected time and the one-hour horizon; no run varies the horizon with spacing.

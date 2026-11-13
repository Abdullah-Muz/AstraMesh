# Shorter protection: tuning on the February 2024 storm

> **Status:** recorded 2026-11-12 from clean commit `29f1b3f` (`git_dirty: false`; 60 runs, 21 min on 12 workers alongside the test suite). Phase 5 increment 4, before 4b (DL-101, DL-102, DL-103). Identical, apart from wall time, to the dirty-tree preview reported in DL-102. Awaiting owner review.

## Setup

- **Storm:** the DL-096 tuning storm, 8 – 16 Feb 2024 (out-of-sample fold forecasts, P-B median), 690 600 s from 00:10 UT; per-spacecraft risk (position-based access, age rule 3600 s, tolerances 100 / 100 / 50 / 200 pfu, no outage). **Planner:** B4. **Seeds:** 1 – 3.
- **Arms:** QUIET and the baseline (config hashes equal the recorded DL-096 runs) and 18 settings: look-ahead H ∈ {300, 600, 1200} s × release dwell D ∈ {300, 600} s × entry margin ∈ {none, protect at ratio 0.9, P-B q90 forecast}. The baseline is H = 3600 s, D = 1800 s, no margin.
- **Selection (DL-101, owner choice; tie-breaks DL-102):** among arms with at most 600 s more unprotected hazard than the baseline on every spacecraft and seed, the highest mean retention (utility ÷ QUIET); ties to the longer H, the longer D, then the more conservative margin; nothing unless it beats the baseline.
- **Reproduce:** `uv run python scripts/experiments/protection_tuning.py --out <dir>` (about 15 min on 12 workers). Files: [`protection_tuning.csv`](protection_tuning.csv), [`protection_tuning_summary.csv`](protection_tuning_summary.csv), [`protection_tuning_meta.json`](protection_tuning_meta.json).

## Results

Every arm gave the same outcome on all three seeds. QUIET: 1 136 (341 tasks).

| H / D (s) | Margin | Utility (tasks) | Retention | Extra unprotected (s) | Protected h (sc00 / 01 / 02 / 03) | Protection entries |
|---|---|---|---|---|---|---|
| 3600 / 1800 (baseline) | none | 1 062 (319) | 0.935 | 0 | 49.2 / 49.2 / 75.0 / 12.7 | 3 / 3 / 3 / 2 |
| 300 / 300 | none | 1 110 (333) | 0.977 | **750** (not eligible) | 20.2 / 20.2 / 38.6 / 2.9 | 46 / 46 / 84 / 7 |
| 300 / 600 | none | 1 110 (333) | 0.977 | **750** (not eligible) | 24.0 / 24.0 / 45.6 / 3.5 | 46 / 46 / 84 / 7 |
| 600 / 300 | none | 1 097 (329) | 0.966 | 370 | 25.9 / 25.9 / 45.3 / 4.5 | 50 / 50 / 84 / 9 |
| **600 / 600** | **none** | **1 097 (329)** | **0.966** | **370** | **30.1 / 30.1 / 52.3 / 5.2** | **50 / 50 / 84 / 9** |
| 1200 / 300 | none | 1 094 (328) | 0.963 | 370 | 35.5 / 35.5 / 59.9 / 6.2 | 54 / 54 / 85 / 10 |
| 1200 / 600 | none | 1 090 (327) | 0.960 | 370 | 39.6 / 39.7 / 66.1 / 6.9 | 54 / 54 / 85 / 10 |
| 300 – 1200 / 300 – 600 | ratio 0.9 | 1 006 – 1 067 | 0.886 – 0.939 | 70 | 26.0 – 45.8 (sc00) | 58 – 61 (sc00) |
| 300 – 1200 / 300 – 600 | q90 | 587 – 651 | 0.517 – 0.573 | 0 | 30.9 – 52.6 (sc00) | 70 – 71 (sc00) |

Extra unprotected hazard is the worst spacecraft's excess over the baseline (all of it on sc00 and sc01, the 100 pfu spacecraft; sc02 and sc03 have none in any arm). Exposure and payload steps in protected modes are 0 in every run.

**Chosen: H = 600 s, D = 600 s, no margin** (tied with D = 300 s; the longer dwell wins). Retention 0.966 against 0.935 (+35 points, +10 tasks), protected time down 39 % on sc00 / sc01, 30 % on sc02, 59 % on sc03, for 360 s and 370 s of extra unprotected hazard on sc00 and sc01.

## Findings

1. **Shorter protection recovers about half of the storm's loss on the tuning storm** (+35 of 74 points under the 600 s rule; +48 with H = 300 s, which breaks it). The look-ahead matters more than the dwell: at H = 1200 s the gain is already 28 – 32 points.
2. **The extra unprotected hazard comes from forecast error near the limit**, not from onset: in the DL-101 preview it fell in STORM_WATCH late in the storm at 105 – 107 pfu against 100 pfu, minutes the long baseline hold had covered. Halving the look-ahead from 600 s to 300 s doubles it (370 to 750 s).
3. **Protection now cycles:** 50 / 50 / 84 / 9 entries a week instead of 3 / 3 / 3 / 2. The model gives cycling no cost.
4. **Both margins remove most or all of the extra hazard but lose science through the planner, not through protection time.** B4 hands its whole future plan to peers each time it protects and has no handback; with q90 (70 – 97 entries a week) 112 of 148 tasks lost against QUIET had a free spacecraft with access for their whole window (DL-102 diagnostic). This penalises the margins under B4-only tuning; it is not a property of the margins themselves.

## Limits

- One storm, one planner (B4) for tuning; B3 + timeout is first seen on the evaluation storms.
- The selected setting trades 6 min of unprotected hazard per 100 pfu spacecraft for the gain; the owner's 600 s limit admits it with 230 s to spare.
- Cycling has no modelled cost (thermal, power, command load).

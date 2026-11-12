# Forecast-handover tuning on the February 2024 storm

> **Status:** recorded 2026-11-11 from clean commit `a7b2046` (`git_dirty: false`). Phase 5 increment 4 (DL-094, DL-095, DL-096). Tuning only: May 2024 is not touched here. Awaiting owner review.

## Setup

- **Storm:** 8 Feb 2024 00:10 UT, 690 600 s, from `configs/data/tuning_feb2024_series.json` (P-B median fitted only on rows whose target window ends before 1 Jan 2024; 2024 Q1 fold, owner choice in DL-094).
- **Scenario:** the S11 setup with position-based access, the 3600 s age rule and tolerances 100 / 100 / 50 / 200 pfu; no outage. Planner B4 (DL-094: tuned on B4 only, owner confirmed 2026-11-11). Seeds 1 – 3.
- **Arms:** QUIET (no environment), the reactive baseline (with the DL-094 B4 correction), and the candidate on θ ∈ {0.5, 0.7, 0.9} × L ∈ {30, 60, 120} min.
- **Selection (fixed in DL-094):** the largest mean retention gain over the baseline under the duplicate-charging utility; ties go to the larger θ, then the shorter L.
- **Reproduce:** `uv run python scripts/experiments/handover_tuning.py --out <dir>` (about 7 min on 12 workers). Files: [`handover_tuning.csv`](handover_tuning.csv) (one row per run), [`handover_tuning_summary.csv`](handover_tuning_summary.csv) (mean gains), [`handover_tuning_meta.json`](handover_tuning_meta.json) (commit, hashes, chosen setting).

## Results

| Arm | Utility, every seed (tasks of 346) | Duplicates | Unprotected hazard |
|---|---|---|---|
| QUIET | 1 136 (341) | 0 | – |
| Baseline | 1 062 (319) | 0 | 0 |
| Candidate, all nine (θ, L) | 1 062 (319) | 0 | 0 |

Mean retention gain over the baseline: 0.000 for every setting, under both utilities. **Frozen setting: θ = 0.9, L = 30 min** (chosen by the tie rule), written into `scripts/experiments/handover_comparison.py` for both planners.

## Findings

1. **On B4 the candidate changes no outcome on this storm, at any setting.** The option A input already forecasts the next hour, so a protecting B4 spacecraft hands its tasks on before they start even without an early window; the 74 points the baseline loses against QUIET are tasks no unprotected peer can take, which an earlier window cannot change.
2. **The seeds do not matter here:** message loss changed nothing in any B4 run.
3. **The B4 correction removes the protection duplicates:** 0 in every run (290 in DL-093 before it).
4. **The frozen setting is the most cautious one on the grid.** The previews in DL-095 showed that under B3 + timeout a longer window loses science (1 041 at θ 0.7, 60 min; 952 at θ 0.5, 120 min, against 1 062); B3 was not tuned (DL-094, owner choice).

## Limits

- One storm, three seeds, one planner; B3 is tested on May 2024 at a setting chosen without B3 data.
- No outage in the tuning scenario (the main test scenario has one).
- The tight-schedule scenario planned in DL-094 is dropped: densifying the regions left QUIET completion at 98.3 – 98.8 % (DL-096).

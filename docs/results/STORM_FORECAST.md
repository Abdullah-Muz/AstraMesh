# Proton forecasts P-A / P-B / P-C: skill on real data

> **Status:** recorded 2026-11-05 from clean commit `00372d9` (`git_dirty: false`); awaiting owner review. Real data only, independent of the simulation. Phase 4 increment 4 (DL-068, DL-069, DL-070, DL-071). The protection comparison that uses these forecasts is in [`STORM_REPLAY.md`](STORM_REPLAY.md).

## Setup (DL-068, DL-069)

- **Question (spec §7.3):** can a forecast of the ≥ 10 MeV proton flux warn of a hazard before the latest measurement shows it, and at what cost in false alarms?
- **Data:**
  - **Training and calibration:** GOES-18 SGPS 5-min averages and OMNI 1-min, 1 Jan 2023 – 30 Apr 2024 (DS-08, DS-09); 139 968 records.
  - **Test:** 8–15 May 2024 (DS-07, DS-06); 2 304 records. Held out completely: never used for fitting, settings or features.
  - The ≥ 10 MeV flux is integrated from the 13 differential channels plus > 500 MeV, using the larger of the two sensor units (DL-068).
- **Availability:** a record is available 10 min after it starts (5-min average plus 5 min delivery). OMNI is averaged into the same bins and obeys the same rule. Tests check that changing any later record leaves every earlier feature unchanged.
- **Target:** log10 of the largest flux in the H after issue, for H = 30 min, 1 h (the main horizon) and 3 h.
- **Models** (settings fixed before any evaluation):

  | Model | Forecast |
  |---|---|
  | P-A | the latest available measurement (persistence; it reacts, it cannot forecast) |
  | P-B | current level + the empirical quantile of the next-H rise, by level (0.25 dex bins) and 1 h trend (±0.05 dex); bins with < 50 rows fall back to the level bin, then to all rows |
  | P-C | `HistGradientBoostingRegressor`, quantile loss, 14 features: level, changes over 5 min – 3 h, 3 h and 24 h maxima, spectral hardness, SYM-H, AE and their 3 h extremes, Bz; settings in the meta file |

  P-B and P-C are fitted for the median (q0.5) and the 0.9 quantile. P-A gives the same forecast for both.
- **Evaluations:**
  - **cv:** forward-chaining folds inside the training period. Test blocks are 2023 Q3, 2023 Q4, 2024 Q1 and April 2024; each fold trains only on rows whose whole target window ends before its block starts.
  - **storm:** one fit on all training data, tested once on the storm week.
- **Scores:**
  - **Pinball loss** (log10 units; lower is better) and **coverage** (fraction of rows where the truth is at or below the forecast; ideal = the quantile).
  - **Row-wise POD and false-alarm ratio (FAR)** for "the next-H maximum reaches the threshold", at 50, 100 and 200 pfu (the 100 pfu tolerance × 0.5, 1 and 2).
  - **Onsets:** a record at or above the threshold after ≥ 1 h below it. An onset is *warned* if a forecast reaching the threshold was issued no earlier than one horizon before the record starts and after the previous episode ended (DL-070). The lead time runs from that first issue to the start of the onset record. A lead of 0 means the forecast arrived exactly as the record started.
- **Reproduce:** `uv run python scripts/experiments/storm_forecast_benchmark.py` (needs DS-06 – DS-09; about 4 min). The recorded run wrote outside the repository and the files were copied in. Before the DL-070 fix, a run from `fc27fa3` gave identical pinball, coverage, POD and FAR; only the onset columns changed.
- **Files:** [`storm_forecast.csv`](storm_forecast.csv): one row per split, fold, horizon, quantile and model (90 rows); [`storm_forecast_meta.json`](storm_forecast_meta.json): commit, lockfile, features and settings.

## 1. Storm week, 8–15 May 2024 (held out)

1 h horizon. The week has 4 onsets above 100 pfu (10, 11 and 14 May), 5 above 50 pfu and 1 above 200 pfu (peak 221 pfu, 10 May 17:45 UT).

| Model | Pinball | Coverage | 100 pfu: POD / FAR | 100 pfu: onsets warned, median lead | 50 pfu: onsets warned, median lead | 200 pfu: onsets warned |
|---|---|---|---|---|---|---|
| P-A | 0.044 | 0.15 | 0.57 / 0.10 | 0 of 4 | 0 of 5 | 0 of 1 |
| P-B q0.5 | **0.030** | 0.43 | 0.73 / 0.18 | 3 of 4, 55 min | 4 of 5, 28 min | 0 of 1 |
| P-C q0.5 | 0.033 | 0.37 | **0.80** / 0.29 | **4 of 4**, 28 min | 4 of 5, 58 min | 0 of 1 |
| P-B q0.9 | **0.020** | 0.87 | 0.87 / 0.61 | 4 of 4, 43 min | 4 of 5, 60 min | 1 of 1, 30 min |
| P-C q0.9 | 0.022 | 0.76 | 0.80 / 0.50 | 4 of 4, 35 min | 5 of 5, 60 min | 1 of 1, 30 min |

P-A's pinball and coverage are for q0.5; for q0.9 its pinball is 0.076.

Other horizons, 100 pfu, median forecasts:

| Horizon | P-A: POD / FAR, warned | P-B: POD / FAR, warned, lead | P-C: POD / FAR, warned, lead |
|---|---|---|---|
| 30 min | 0.70 / 0.10, 0 of 4 | 0.77 / 0.19, 2 of 4, 15 min | 0.88 / 0.37, 3 of 4, 30 min |
| 1 h | 0.57 / 0.10, 0 of 4 | 0.73 / 0.18, 3 of 4, 55 min | 0.80 / 0.29, 4 of 4, 28 min |
| 3 h | 0.32 / 0.10, 0 of 4 | 0.48 / 0.16, 4 of 4, 50 min | 0.49 / 0.29, 4 of 4, 108 min |

## 2. Chronological folds inside the training period (1 h)

| Fold (test block) | Onsets ≥ 100 / ≥ 50 pfu | Pinball q0.5 P-A / P-B / P-C | Coverage q0.5 P-B / P-C | 100 pfu warned P-B / P-C (q0.5) | 50 pfu warned P-B / P-C (q0.5) |
|---|---|---|---|---|---|
| 2023 Q3 | 2 / 7 | 0.048 / **0.025** / 0.029 | 0.58 / 0.69 | 0 / 0 | 6 / 3 |
| 2023 Q4 | 0 / 0 | 0.051 / 0.024 / **0.017** | 0.65 / 0.67 | – | – |
| 2024 Q1 | 10 / 8 | 0.047 / 0.024 / **0.022** | 0.50 / 0.55 | 6 / 9 | 6 / 6 |
| Apr 2024 | 0 / 0 | 0.052 / 0.023 / **0.016** | 0.58 / 0.65 | – | – |

At q0.9, coverage is 0.88–0.95 for P-B and P-C in every fold. P-A warns of no onset in any fold.

## Findings

1. **Both forecasts warn ahead of the hazard, which persistence never can.**
   - On the held-out storm week at 1 h, P-C (median) warns of all 4 rises above 100 pfu and P-B of 3, with median leads of 28 and 55 min. P-A warns of none: it learns of an onset 10 min after the record starts.
   - The gain is real in row-wise skill too: POD at 100 pfu rises from 0.57 (P-A) to 0.73 (P-B) and 0.80 (P-C).
2. **The price is false alarms.** At 100 pfu, the FAR rises from 0.10 (P-A) to 0.18 (P-B) and 0.29 (P-C). The 0.9 quantiles warn of every onset at every threshold but raise the FAR to 0.50–0.61. In the replay these false alarms become protected time outside the hazard ([`STORM_REPLAY.md`](STORM_REPLAY.md)).
3. **Neither forecast wins everywhere.**
   - **Pinball:** P-C is best in 2023 Q4, 2024 Q1 and April 2024. P-B is best in 2023 Q3 and on the storm week, where the flux goes beyond most of the training data.
   - **Calibration:** both medians are biased low on the storm week (coverage 0.43 and 0.37, ideal 0.5) and biased high in the folds (0.50–0.69). The 0.9 quantiles cover 0.87 (P-B) and 0.76 (P-C) on the storm week.
4. **P-C cannot forecast beyond its training range.**
   - In the 2023 Q3 fold, trained on Jan–Jun 2023 (nothing above 100 pfu), P-C never forecasts 100 pfu: POD 0 at 100 and 200 pfu. Tree models cannot exceed the targets they were trained on.
   - P-B adds a learned rise to the current level, so it extrapolates in level. It still warns of neither 100 pfu onset in that fold.
   - At 200 pfu on the storm week, neither median reaches the threshold before the onset; P-A's 200 pfu forecasts are all false alarms (FAR 1.0): by the time the peak record is available, the following hour stays below 200 pfu.
5. **Longer horizons give longer leads, as expected.** At 3 h, P-C's median lead at 100 pfu is 108 min, but row-wise POD falls to about 0.5 for all three models, because the target (the 3 h maximum) is harder.

## Limits

- **One storm.** The test week has 4 onsets above 100 pfu and 1 above 200 pfu, so the onset counts are very small samples. The folds add 12 onsets above 100 pfu, but in 2023 Q3 and 2024 Q1 only; there are no intervals here.
- **GEO, one spacecraft.** GOES-18 measures at geostationary orbit, with no geomagnetic shielding. LEO fluxes are lower and vary along the orbit (DL-068: an upper-bound proxy).
- **Integration method.** The ≥ 10 MeV flux depends on the interpolation across 10–12 MeV (the 10 May peak: 221 pfu with this method, 404 pfu from a flat-band sum; DL-068). Thresholds are relative to this flux, not to NOAA's integral channel.
- **No tuning, no alternatives.** The model settings were fixed once and not searched. Other models (e.g. physics-based or proton-event probability forecasts) are not compared.

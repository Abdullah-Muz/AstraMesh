# Proton forecasts P-A / P-B / P-C: skill on real data

> **Status:** point values recorded 2026-11-05 from clean commit `00372d9` (`git_dirty: false`); approved 2026-11-09 (DL-071). Intervals and model differences (DL-072) recorded 2026-11-09 from clean commit `cedaec1` (`git_dirty: false`), with every point value unchanged; awaiting owner review (DL-073). Real data only, independent of the simulation. Phase 4 increment 4 (DL-068 – DL-073). The protection comparison that uses these forecasts is in [`STORM_REPLAY.md`](STORM_REPLAY.md).

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
- **Intervals (DL-072, `astramesh.forecast.uncertainty`):** 95 % percentile bootstrap over UTC days (2 000 resamples, fixed seed) for pinball, coverage, POD and FAR. All models are resampled on the same days, so differences between models get intervals too. A forecast belongs to the UTC day of its record start (it is issued 10 min later), so the storm week splits into 8 whole days. A POD or FAR with no event (or no warning) on the drawn days is undefined in that resample and left out; the number of resamples where it is defined is recorded (`_boot_n`) and shown below when it is under 2 000. The fraction of onsets warned gets an exact Clopper-Pearson interval. The storm week has only 8 days and neighbouring days are treated as independent, so these intervals are coarse and probably somewhat too narrow.
- **Reproduce:** `uv run python scripts/experiments/storm_forecast_benchmark.py` (needs DS-06 – DS-09; about 3 min with the bootstrap). The recorded run wrote outside the repository and the files were copied in. Before the DL-070 fix, a run from `fc27fa3` gave identical pinball, coverage, POD and FAR; only the onset columns changed.
- **Files:** [`storm_forecast.csv`](storm_forecast.csv): one row per split, fold, horizon, quantile and model (90 rows), with `_lo` / `_hi` interval columns; [`storm_forecast_pairs.csv`](storm_forecast_pairs.csv): differences between models (720 rows); [`storm_forecast_meta.json`](storm_forecast_meta.json): commit, lockfile, data versions (file count and sha256 of the pinned hashes per dataset), features and settings.

## 1. Storm week, 8–15 May 2024 (held out)

1 h horizon. The week has 4 onsets above 100 pfu (10, 11 and 14 May), 5 above 50 pfu and 1 above 200 pfu (peak 221 pfu, 10 May 17:45 UT).

| Model | Pinball | Coverage | 100 pfu: POD / FAR | 100 pfu: onsets warned, median lead | 50 pfu: onsets warned, median lead | 200 pfu: onsets warned |
|---|---|---|---|---|---|---|
| P-A | 0.044 | 0.15 | 0.57 / 0.10 | 0 of 4 | 0 of 5 | 0 of 1 |
| P-B q0.5 | **0.030** | 0.43 | 0.73 / 0.18 | 3 of 4, 55 min | 4 of 5, 28 min | 0 of 1 |
| P-C q0.5 | 0.033 | 0.37 | **0.80** / 0.29 | **4 of 4**, 28 min | 4 of 5, 58 min | 0 of 1 |
| P-B q0.9 | **0.020** | 0.87 | 0.87 / 0.61 | 4 of 4, 43 min | 4 of 5, 60 min | 1 of 1, 30 min |
| P-C q0.9 | 0.022 | 0.76 | 0.80 / 0.50 | 4 of 4, 35 min | 5 of 5, 60 min | 1 of 1, 30 min |

P-A's pinball and coverage are for q0.5; for q0.9 its pinball is 0.076. Bold in this table marks the best point value in its column, not a tested difference; the differences with intervals follow.

With 95 % intervals (1 h, 100 pfu):

| Model | Pinball | Coverage | POD | FAR | Onsets warned |
|---|---|---|---|---|---|
| P-A | 0.044 [0.026, 0.062] | 0.15 [0.10, 0.20] | 0.57 [0.13, 0.80] | 0.10 [0.03, 0.50] | 0 of 4 [0.00, 0.60] |
| P-B q0.5 | 0.030 [0.018, 0.043] | 0.43 [0.34, 0.53] | 0.73 [0.33, 0.95] | 0.18 [0.07, 0.60] | 3 of 4 [0.19, 0.99] |
| P-C q0.5 | 0.033 [0.022, 0.046] | 0.37 [0.29, 0.46] | 0.80 [0.44, 1.00] | 0.29 [0.08, 0.71] | 4 of 4 [0.40, 1.00] |
| P-B q0.9 | 0.020 [0.011, 0.032] | 0.87 [0.78, 0.95] | 0.87 [0.44, 1.00] | 0.61 [0.33, 0.90] | 4 of 4 [0.40, 1.00] |
| P-C q0.9 | 0.022 [0.011, 0.033] | 0.76 [0.66, 0.86] | 0.80 [0.44, 1.00] | 0.50 [0.33, 0.86] | 4 of 4 [0.40, 1.00] |

POD is undefined in 47 of the 2 000 resamples (no day with a 100 pfu event drawn); FAR in 47 for P-A and 9 for P-B and P-C (no warning on the drawn days).

Differences between models on the same days (1 h, median forecasts; negative pinball is better, B − A):

| Pair | Pinball | POD, 100 pfu | FAR, 100 pfu |
|---|---|---|---|
| P-B − P-A | **−0.014 [−0.023, −0.007]** | **+0.17 [+0.06, +0.27]** | +0.08 [−0.05, +0.17] |
| P-C − P-A | **−0.011 [−0.023, −0.0002]** | **+0.23 [+0.17, +0.33]** | **+0.19 [+0.05, +0.35]** |
| P-C − P-B | +0.003 [−0.001, +0.007] | **+0.06 [+0.05, +0.11]** | **+0.12 [+0.01, +0.22]** |

Bold: the interval excludes 0; P-C − P-A in pinball only just does (upper bound −0.0002). The POD and FAR differences are defined in 1 953 of the 2 000 resamples (FAR for P-C − P-B: 1 991). At 30 min, P-C − P-A in pinball is −0.005 [−0.014, +0.004], which includes 0; at 3 h both forecasts are clearly better than P-A.

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

Bold marks the lowest point value. At q0.9, coverage is 0.88–0.95 for P-B and P-C in every fold. P-A warns of no onset in any fold.

Pinball differences at 1 h, median forecasts, on the same days:

| Fold | P-B − P-A | P-C − P-A | P-C − P-B |
|---|---|---|---|
| 2023 Q3 | −0.024 [−0.026, −0.022] | −0.019 [−0.024, −0.013] | **+0.005 [+0.001, +0.010]** |
| 2023 Q4 | −0.027 [−0.028, −0.026] | −0.033 [−0.034, −0.033] | **−0.006 [−0.007, −0.006]** |
| 2024 Q1 | −0.023 [−0.025, −0.021] | −0.025 [−0.029, −0.021] | −0.002 [−0.004, +0.001] |
| Apr 2024 | −0.029 [−0.030, −0.028] | −0.036 [−0.038, −0.035] | **−0.007 [−0.008, −0.006]** |

Both forecasts beat persistence in every fold. In the P-C − P-B column, bold marks an interval that excludes 0. In 2024 Q1, the fold with the most onsets, P-C's FAR at 100 pfu is higher than P-B's by 0.16 [0.06, 0.29], while their POD cannot be told apart (−0.04 [−0.29, +0.18]).

## Findings

1. **Both forecasts warn ahead of the hazard, which persistence never can.**
   - On the held-out storm week at 1 h, P-C (median) warns of all 4 rises above 100 pfu and P-B of 3, with median leads of 28 and 55 min. P-A warns of none: it learns of an onset 10 min after the record starts.
   - The gain is real in row-wise skill too: POD at 100 pfu rises from 0.57 (P-A) to 0.73 (P-B) and 0.80 (P-C). On the same days, the gain over P-A is +0.17 [+0.06, +0.27] for P-B and +0.23 [+0.17, +0.33] for P-C; both intervals exclude 0.
   - The onset counts alone do not establish this: with 4 onsets, 4 of 4 has the interval [0.40, 1.00] and 0 of 4 has [0.00, 0.60]. The evidence is the row-wise POD differences and, in the folds, the onsets of 2024 Q1: P-C warns of 9 of 10 [0.55, 1.00] and P-B of 6 of 10 [0.26, 0.88], against 0 of 10 [0.00, 0.31] for P-A. The folds do not show a POD gain for P-C (2024 Q1: −0.00 [−0.26, +0.27] against P-A).
2. **The price is false alarms.** At 100 pfu, the FAR rises from 0.10 (P-A) to 0.18 (P-B) and 0.29 (P-C). Only P-C's increase is clear: +0.19 [+0.05, +0.35] over P-A and +0.12 [+0.01, +0.22] over P-B; P-B's +0.08 [−0.05, +0.17] over P-A is not. The 0.9 quantiles warn of every onset at 100 and 200 pfu (P-C q0.9 at 50 pfu too; P-B q0.9 warns of 4 of 5 there) but raise the FAR to 0.50–0.61. In the replay these false alarms become protected time outside the hazard ([`STORM_REPLAY.md`](STORM_REPLAY.md)).
3. **Neither forecast wins everywhere.**
   - **Pinball:** P-C is clearly better than P-B in 2023 Q4 and April 2024 and P-B in 2023 Q3. In 2024 Q1 and on the storm week, where the flux goes beyond most of the training data, the two cannot be told apart (storm week: +0.003 [−0.001, +0.007]). Both beat persistence at 1 h in every fold and on the storm week, although P-C's margin on the storm week only just excludes 0, and at 30 min it does not (−0.005 [−0.014, +0.004]).
   - **Calibration:** on the storm week, P-C's median is biased low (coverage 0.37 [0.29, 0.46], ideal 0.5), while P-B's cannot be told from 0.5 (0.43 [0.34, 0.53]). In the folds both medians are biased high (0.55–0.69), except P-B in 2024 Q1 (0.50 [0.48, 0.53]). The 0.9 quantiles cover 0.87 [0.78, 0.95] (P-B) and 0.76 [0.66, 0.86] (P-C) on the storm week; again only P-C's interval excludes the ideal.
4. **P-C cannot forecast beyond its training range.**
   - In the 2023 Q3 fold, trained on Jan–Jun 2023 (nothing above 100 pfu), P-C never forecasts 100 pfu: POD 0 at 100 and 200 pfu. Tree models cannot exceed the targets they were trained on.
   - P-B adds a learned rise to the current level, so it extrapolates in level. It still warns of neither 100 pfu onset in that fold.
   - At 200 pfu on the storm week, neither median reaches the threshold before the onset; P-A's 200 pfu forecasts are all false alarms (FAR 1.0): by the time the peak record is available, the following hour stays below 200 pfu.
5. **Longer horizons give longer leads, as expected.** At 3 h, P-C's median lead at 100 pfu is 108 min, but row-wise POD falls to about 0.5 for P-B and P-C and to 0.32 for P-A, because the target (the 3 h maximum) is harder.

## Limits

- **One storm.** The test week has 4 onsets above 100 pfu and 1 above 200 pfu, so the onset counts are very small samples (see the Clopper-Pearson intervals). The folds add 12 onsets above 100 pfu, but in 2023 Q3 and 2024 Q1 only.
- **Coarse intervals.** The day bootstrap has only 8 days on the storm week and treats neighbouring days as independent, although a proton event can last more than a day. The intervals show the sampling spread; they are not exact. Where only one day holds the events (e.g. 200 pfu in 2023 Q3), the interval collapses to the point value.
- **GEO, one spacecraft.** GOES-18 measures at geostationary orbit, with no geomagnetic shielding. LEO fluxes are lower and vary along the orbit (DL-068: an upper-bound proxy).
- **Integration method.** The ≥ 10 MeV flux depends on the interpolation across 10–12 MeV (the 10 May peak: 221 pfu with this method, 404 pfu from a flat-band sum; DL-068). Thresholds are relative to this flux, not to NOAA's integral channel.
- **No tuning, no alternatives.** The model settings were fixed once and not searched. Other models (e.g. physics-based or proton-event probability forecasts) are not compared.

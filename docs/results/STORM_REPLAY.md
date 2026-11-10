# S11: the May 2024 storm replay, protection P-A / P-B / P-C

> **Status:** recorded 2026-11-06 from clean commit `fc27fa3` (`git_dirty: false`); approved 2026-11-09 (DL-071). The environment inputs are real data, but the risk map, payload tolerance and the identical exposure of all four spacecraft are assumptions (see "Synthetic-vs-real interface"). **Preliminary, not a research result.** Phase 4 increment 4 (DL-068, DL-069, DL-071). The forecast skill behind P-B and P-C is in [`STORM_FORECAST.md`](STORM_FORECAST.md).

## Setup (DL-068, DL-069)

- **Question (spec §7.3):** given the same supervisor, does feeding it a forecast (P-B, P-C) instead of the latest measurement (P-A) reduce exposure to a defined radiation hazard, and what does it cost in science?
- **Scenario S11:** the S00 base configuration (four spacecraft, 346 tasks), moved to 8 May 2024 00:10 UT and run to 16 May 00:00 (690 600 s). No faults.
- **Environment inputs** (from `configs/data/s11_storm_series.json`, sha256 pinned in every configuration), the same for all four spacecraft:

  | Supervisor input | Source | Ratio |
  |---|---|---|
  | radiation | P-A: latest measured ≥ 10 MeV flux; P-B / P-C: 1 h forecast of its maximum | ÷ tolerance (100 pfu) |
  | nav/comms | OMNI AE | ÷ 2000 nT |
  | orbital | OMNI −SYM-H | ÷ 250 nT |

  Every input is available 10 min after its 5-min record starts. Nav/comms and orbital can raise STORM_WATCH but never PROTECTIVE (DL-056).
- **Supervisor (unchanged from Phase 3, DL-054/056):** PROTECTIVE at radiation ratio ≥ 1.0; released after 30 min below 0.8, then RECOVERY (≥ 300 s). STORM_WATCH at any ratio ≥ 0.6, released after 30 min below 0.5. The payload is off in PROTECTIVE and RECOVERY.
- **Variants:** the median forecasts (q0.5) are the main comparison. Sensitivities are the 0.9 quantiles and tolerances of 50 and 200 pfu. QUIET is the same week with no environment input, the reference for retention.
- **Truth metrics** (from the measured flux, never shown to the agents; summed over the four spacecraft):
  - **hazard:** time with measured flux ≥ tolerance;
  - **unprotected hazard:** hazard time not in PROTECTIVE or RECOVERY;
  - **exposure:** payload-on time during the hazard. The payload is on only while observing, so exposure ≤ unprotected hazard;
  - **false protection:** time in PROTECTIVE or RECOVERY outside the hazard.
- **Runs:** 12 variants × 2 planners (B3 + timeout, B4) × seeds 1–10 = 240 runs of 8 days. The seeds change only message loss.
- **Reproduce:** `uv run python scripts/experiments/storm_replay_comparison.py`.
  - A B4 run takes about 90 s and a B3 + timeout run about 20 min (see Limits), so the full set needs about 8.5 h on 6 workers. The recorded `total_wall_s` (64 175 s) also includes an overnight suspension of the machine.
  - The recorded run wrote its outputs outside the repository, and the files were then copied in.
  - DL-070 (`00372d9`) changed only the forecast-skill metric; nothing that S11 uses changed after `fc27fa3`.
- **Files:**
  - [`storm_replay.csv`](storm_replay.csv): one row per run;
  - [`storm_replay_summary.csv`](storm_replay_summary.csv): one row per planner and variant, with 95 % t-intervals;
  - [`storm_replay_meta.json`](storm_replay_meta.json): commit, lockfile, series hash and variants.

## Synthetic-vs-real interface

| Real (NOAA GOES-18, NASA OMNI, May 2024) | Synthetic (AstraMesh) |
|---|---|
| the ≥ 10 MeV proton flux every 5 min (integrated from SGPS channels, DL-068) and the forecasts made from it | the 100 pfu payload tolerance, and the ratios 2000 nT (AE) and 250 nT (SYM-H) |
| AE and SYM-H every 5 min | that all four LEO spacecraft see the GEO flux unshielded and at the same time |
| the 10 min data latency | the spacecraft, tasks, schedule, links and losses |

- **The only link between real and synthetic** is [`configs/data/s11_storm_series.json`](../../configs/data/s11_storm_series.json). The simulation reads nothing else from the storm data.
- **Assumptions this rests on, untested:** GEO flux is an upper bound for LEO (no geomagnetic shielding, no orbit dependence), and a payload is at risk at 100 pfu. Exposure is reported, not converted into damage or lost science.

## 1. Main comparison (tolerance 100 pfu, 1 h median forecasts)

Every seed and both planners gave the same value for every metric shown, so no intervals are given (see finding 4).

| Model | Retention | Tasks completed (of 346) | Hazard, h | Unprotected hazard, h | Exposure, s | False protection, h | PROTECTIVE entries |
|---|---|---|---|---|---|---|---|
| QUIET | 1.000 | 341 | – | – | – | – | 0 |
| P-A | **0.912** | 311 | 26.7 | 2.67 | 60 | **34.3** | 16 |
| P-B | 0.863 | 295 | 26.7 | 0.33 | **0** | 57.0 | 12 |
| P-C | 0.833 | 285 | 26.7 | **0** | **0** | 84.3 | 24 |

Hours and entries are summed over the four spacecraft (all four see the same inputs, so divide by 4 for one spacecraft). STORM_WATCH lasts 42–49 h per spacecraft under every model. Safety invariants held in all 240 runs: 0 payload steps in protected modes and 0 confirmed-failed beliefs about an available spacecraft.

## 2. Sensitivity

| Variant | What changes | Retention | Hazard, h | Unprotected hazard, h | Exposure, s | False protection, h |
|---|---|---|---|---|---|---|
| P-B/q90 | 0.9 quantile | 0.798 | 26.7 | 0 | 0 | 122.3 |
| P-C/q90 | 0.9 quantile | 0.811 | 26.7 | 0 | 0 | 115.0 |
| P-A/tol50 | tolerance 50 pfu | 0.729 | 153.0 | 2.67 | 60 | 44.0 |
| P-B/tol50 | tolerance 50 pfu | 0.720 | 153.0 | 0.67 | 0 | 50.7 |
| P-C/tol50 | tolerance 50 pfu | 0.700 | 153.0 | 0.33 | 0 | 69.3 |
| P-A/tol200 | tolerance 200 pfu | 0.988 | 0.33 | 0.33 | 60 | 3.0 |
| P-B/tol200 | tolerance 200 pfu | 0.988 | 0.33 | 0.33 | 60 | 3.0 |
| P-C/tol200 | tolerance 200 pfu | 0.984 | 0.33 | 0.33 | 60 | 4.7 |

One B3 + timeout run (P-A/tol50, seed 7) had one duplicate observation; every other run had none.

## Findings

1. **The forecasts close the reaction gap, as designed.**
   - P-A learns of each rise 10 min after the record starts. Over the 4 onsets above 100 pfu that leaves 40 min of unprotected hazard per spacecraft (2.67 h in total). One of these windows caught a scheduled observation: 60 s of exposure on one spacecraft.
   - P-B leaves 5 min per spacecraft unprotected (the onset it did not warn of; [`STORM_FORECAST.md`](STORM_FORECAST.md)) and P-C none. Neither had any exposure.
2. **The price is science lost to false protection.**
   - False protection grows from 8.6 h per spacecraft (P-A) to 14.3 h (P-B) and 21.1 h (P-C). Retention falls from 0.912 to 0.863 and 0.833.
   - Removing P-A's 40 min of unprotected hazard per spacecraft costs P-C 26 more tasks (8 % of the QUIET utility) over the week.
   - Even P-A spends more time protected outside the hazard than inside it (8.6 h against 6 h per spacecraft). This comes from the supervisor's release rule (30 min below 0.8, then RECOVERY), which all three share.
   - The 0.9 quantiles buy nothing more at 100 pfu (P-C q0.5 already leaves no unprotected hazard) and cost more retention: 0.798 against 0.863 for P-B, 0.811 against 0.833 for P-C.
3. **The tolerance matters more than the forecast.**
   - At 50 pfu the hazard lasts 38 h per spacecraft, and all three models keep only 0.70–0.73 of the science, within 3 % of each other.
   - At 200 pfu the hazard is a single 5-min record. No median forecast reaches 200 pfu before it, so all three react late, and the forecasts add nothing.
   - What a payload can tolerate, which is synthetic here, decides most of the outcome.
4. **The planner and message loss make no difference here.**
   - B3 + timeout and B4 give identical results in every variant, and all seeds agree, except for one duplicate observation in one B3 + timeout run (P-A/tol50, seed 7).
   - All four spacecraft see the same inputs, so they enter PROTECTIVE together. A task whose slot falls in protection cannot move to a peer, because every peer is protected too. Every other task is completed under both planners.
   - A distributed mission can gain from forecasts only when the spacecraft see different risks (e.g. different positions in orbit). This replay cannot show that.
5. **STORM_WATCH costs almost nothing.** Geomagnetic indices hold every spacecraft in STORM_WATCH for 45–51 h at 200 pfu (36–51 h across all storm variants; time in PROTECTIVE is not counted as STORM_WATCH). At 200 pfu, where PROTECTIVE lasts about 1 h or less per spacecraft, retention is still 0.984–0.988.

## Limits

- **One storm, one GEO proxy, common to all four spacecraft.** LEO flux is lower and depends on orbit position; with orbit-dependent inputs, both the hazard and the value of a forecast would differ between spacecraft. This is an upper-bound case.
- **Exposure counts payload-on time only.** It depends on where the tasks fall: P-A's 2.67 h of unprotected hazard gave 60 s of exposure because the payload observes only a small fraction of the time. Unprotected hazard is the more robust measure. No damage model links exposure to lost science (DL-069, approved 2026-11-09).
- **The cost side counts only tasks.** Utility does not charge for STORM_WATCH or the longer status traffic in it.
- **No intervals.** The runs are deterministic apart from message loss, which did not matter (finding 4), so n = 10 seeds adds no information here. The uncertainty is in the one storm and the assumptions, not in the seeds.
- **CBBA run time grows with run length.** B3 messages carry every claim made so far, including tasks finished days earlier; this is faithful to the published algorithm, which never prunes. Per-message cost grows through the run, so an 8-day run takes about 20 min against 46 s for 1 day. Message size only feeds the byte counter in this simulator, so no result is affected. A faster encoding with identical behaviour is a later performance item (DL-071 (b)).

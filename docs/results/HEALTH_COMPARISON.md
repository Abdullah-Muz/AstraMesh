# Health models H-A / H-B / H-C on S01, S03 and S04

> **Status:** recorded 2026-11-05 from clean commit `42c24a9` (`git_dirty: false`); approved by the owner 2026-11-05 (DL-067). **Preliminary, not a research result:** the faults are synthetic. The payload detector's scores are real (OPS-SAT-AD), but the way they are attached to simulated faults is an assumption (see "Synthetic-vs-real interface"). Phase 4 increment 3 (DL-066, DL-067).

## Setup (DL-066)

- **Question (spec §7.2):** with downstream planning held fixed, does a probabilistic health model (H-B) or a detector-aided one (H-C) keep more science than the timeout (H-A)?
- **Models.** All parameters were fixed before any scenario was run and were not tuned on these results.

  | Model | Peer loss (from silence) | Own payload |
  |---|---|---|
  | H-A | SUSPECTED after 90 s without a message, LOST after 300 s (DL-052) | no evidence |
  | H-B | P(unavailable \| silence) from a prior rate (mean time to unavailability 30 days) and a learned message-loss rate (Beta(1, 30) prior per peer); SUSPECTED at 0.5, LOST at 0.95 | no evidence |
  | H-C | as H-B | two-state filter fed by the onboard detector every 300 s; DEGRADED at 0.9, cleared at 0.1 |

- **Planning held fixed:**
  - two planners: B3 + timeout (CBBA) and B4 (rule-based);
  - one shared response: a spacecraft that believes its payload is degraded stops observing and reports `payload: degraded` in its status. B3 gives up its claims; B4 hands its tasks on by the fixed rule.
  - Only the health model changes between runs.
- **Scenarios and draws:** the same base configuration, scenarios and paired per-seed fault draws as the fault comparison ([`FAULT_COMPARISON.md`](FAULT_COMPARISON.md), DL-058):

  | Scenario | Injected condition (synthetic) |
  |---|---|
  | S00 | no fault (the reference for retention) |
  | S01 | `a` permanently unavailable from t0 |
  | S03 | `a` payload degraded for 12 h (observations invalid; nothing in telemetry shows it) |
  | S04 | `a` radio off for 3 h; the spacecraft keeps working (a false outage) |

- **Size of the run:** 440 runs of 24 h, with seeds 1–10 and both planners:
  - main comparison: 3 models × 4 scenarios = 240 runs;
  - sensitivity variants: 200 runs.
- **Retention:** U_fault / U_S00 for the same model, planner and seed.
- **Belief metrics:** summed over observer–peer pairs, sampled every 10 s.
  - In S04, the radio-off spacecraft and its three peers each lose contact with the other side. That makes 6 pairs × 3 h = 64 800 pair-seconds of possible false outage.
  - *Detection latency* is the slowest observer's time from the fault start to a LOST belief.
- **Payload metrics:** summed over the four spacecraft.
  - *Payload detection latency* runs from the fault start to the first DEGRADED belief. It is 0 if a false alarm was already active at the fault start.
- **Intervals:** 95 % t-intervals, n = 10. A single number means every seed gave the same value. Intervals are not clipped to the possible range: with one outlying seed (S03, B3 + T) they extend below 0 or above 1.
- **Consistency check:** every H-A run (80) reproduces the corresponding run of the recorded fault comparison exactly: utility, completions, duplicates and messages. Making the timeout explicit changes nothing.
- **Reproduce:** `uv run python scripts/experiments/health_comparison.py`. It takes about 38 min on 6 workers.
  - The recorded run wrote its outputs outside the repository, and the files were then copied in.
  - It matches a preview run from a dirty tree except in three places:
    - the config hashes (payload-check fields were renamed after the preview);
    - the wall times;
    - one seed's payload latency, which the latency-metric fix changed (DL-067).
- **Files:**
  - [`health_comparison.csv`](health_comparison.csv): one row per run;
  - [`health_comparison_summary.csv`](health_comparison_summary.csv): one row per scenario, planner and model;
  - [`health_comparison_meta.json`](health_comparison_meta.json): commit, lockfile, sensor hash, model settings and draws.

## Synthetic-vs-real interface

| Real (OPS-SAT, ESA, 2022) | Synthetic (AstraMesh) |
|---|---|
| 527 calibrated anomaly probabilities from histogram gradient boosting (seed 0), scored on the time split's test segments: 351 nominal, 176 anomalous | when a payload fault starts and ends (S03), and which spacecraft it hits |
| the training anomaly rate (16.2 %) that the filter uses as its reference | the spacecraft, the radio links, losses, outages and the schedule |

- **The only link between real and synthetic** is [`configs/data/opssat_score_sensor.json`](../../configs/data/opssat_score_sensor.json). Its SHA-256 is pinned in every configuration, and the simulation reads nothing else from OPS-SAT.
- **How a check works:** every 300 s, each available simulated spacecraft draws one probability from that file, using its own random stream:
  - from the nominal pool while its payload is healthy;
  - from the anomalous pool while a `payload_degraded` fault is active.
- **Assumptions this rests on:**
  - checks are independent given the payload state;
  - an AstraMesh payload fault looks to the detector like an OPS-SAT anomaly.

  Neither is tested here. The `shift05` variant probes the first in one direction only: it makes healthy checks look anomalous.

## 1. Main comparison

| Scenario | Planner | Retention H-A / H-B / H-C | Invalid observations H-A / H-B / H-C | Detection latency, s H-A / H-B / H-C | Duplicates (all models) |
|---|---|---|---|---|---|
| S00 | B3 + T | 1.000 / 1.000 / 1.000 | 0 / 0 / 0 | – | 0 |
| S00 | B4 | 1.000 / 1.000 / 1.000 | 0 / 0 / 0 | – | 0 |
| S01 (loss) | B3 + T | 1.000 / 1.000 / 1.000 | 0 / 0 / 0 | loss: 300 / 108 [97, 119] / 108 [97, 119] | 0 |
| S01 (loss) | B4 | 1.000 / 1.000 / 1.000 | 0 / 0 / 0 | loss: 296 [292, 300] / 104 [94, 114] / 104 [94, 114] | 0 |
| S03 (payload) | B3 + T | 0.951 [0.841, 1.061] / same / **1.000** | 2.1 [−2.7, 6.9] / same / **0** | payload: never / never / **733 [544, 922]** | 0 |
| S03 (payload) | B4 | 0.876 [0.864, 0.889] / same / **1.000** | 5.4 [4.9, 5.9] / same / **0** | payload: never / never / **733 [544, 922]** | 0 |
| S04 (radio off) | B3 + T | 1.000 / 1.000 / 1.000 | 0 / 0 / 0 | – | 6.1 [4.1, 8.1] |
| S04 (radio off) | B4 | 1.000 / 1.000 / 1.000 | 0 / 0 / 0 | – | 33.1 [31.3, 34.9] |

Safety invariants held in all 440 runs: 0 payload steps in protected modes and 0 confirmed-failed beliefs about an available spacecraft.

## 2. Sensitivity

| Variant | What changes | S00: false alarms | S01 loss latency, s (B3 + T / B4) | S03 payload latency, s | S03 retention (B3 + T / B4) | S03 false-degraded, s |
|---|---|---|---|---|---|---|
| H-B | (reference) | 0 | 108 / 104 | – | – | – |
| H-B/mtbf3d | prior mean time to unavailability 3 days | one 10 s false LOST (B4, seed 3) | 90 / 86 | – | – | – |
| H-B/mtbf300d | prior mean time to unavailability 300 days | 0 | 120 / 116 | – | – | – |
| H-C | (reference) | 0 | – | 733 [544, 922] | 1.000 / 1.000 | 1 423 [1 003, 1 843] |
| H-C/official | sensor from the official split (training rate 20.1 %) | 0 | – | 583 [461, 705] | 1.000 / 1.000 | 913 [730, 1 096] |
| H-C/shift05 | 5 % of healthy checks drawn from anomalous scores | 4 650 s [2 401, 6 899] payload false-degraded per day (600–9 300) | – | 665 [363, 967] | 0.997 [0.991, 1.004] / 1.000 | 5 045 [3 229, 6 861] |

## Findings

1. **Only the detector-aided model saves science, and only where silence carries no information (S03).**
   - A degraded payload keeps transmitting, so H-A and H-B see nothing. They give identical results: B4 makes 5.4 invalid observations per run and keeps 0.876 of its utility.
   - The CBBA mean is higher (0.951) only because tie-breaking gives sc00 all 43 tasks (fault comparison, finding 2). The 9 seeds where `a` is not sc00 lose nothing. Seed 4 (`a` = sc00) makes 21 invalid observations and keeps 0.514.
   - H-C flags the payload after a mean of 733 s, about 2.4 checks. Its tasks then move to peers: 0 invalid observations and retention 1.000 in all 20 runs.
   - This is the first result in which a health model changes utility.
2. **Faster loss detection costs nothing and gains nothing here.**
   - H-B declares a lost spacecraft LOST after about 105 s, compared with H-A's 300 s.
   - Retention in S01 is 1.000 under every model, because a 24 h schedule with slack absorbs a 200 s delay.
   - Time believed available while lost is the same for both models (about 90 s per observer). Both leave the "available" belief about 90 s after the last status; the gain is in the time to LOST, which is what triggers reallocation.
3. **No model helps with a false outage (S04, spec H2).**
   - Silence alone cannot separate a radio outage from a loss.
   - H-B declares LOST sooner, so it adds about 200 s per pair of false-outage time: 64 269 vs 63 060 pair-seconds out of 64 800 under B3 + T.
   - The duplicates are the same as under H-A (6.1 for B3 + T, 33.1 for B4), because both models react well inside the 3 h outage.
   - The detector does not help either: it watches only the spacecraft's own payload.
4. **H-C's costs are false-degraded time, not lost science.**
   - **Clearing lag:** after the S03 repair the filter clears about 1 400 s late, because it waits for the probability to fall below 0.1.
   - **Stress test (`shift05`):** with 5 % of healthy checks looking anomalous, the filter wrongly flags payloads for 4 650 s per day in total across the four spacecraft. Peers cover the tasks, so no S00 utility is lost.
   - **One loss under stress:** in S03, one B3 + T seed (seed 4, `a` = sc00, which holds every CBBA task) had a false alarm on `a` before the fault. After the alarm cleared, the real fault took 1 630 s to detect, and one invalid observation got through (retention 0.972).
   - With no stress, there were 0 false alarms across 40 healthy S00 runs (4 spacecraft × 24 h each).
5. **The results are robust to the prior choices tested.**
   - Changing H-B's prior from 30 days to 3 or 300 days moves loss latency by under ±20 s. The 3-day prior gave one 10 s false LOST in 20 healthy runs.
   - The official-split sensor detects faster (583 s) and has less clearing lag. Its test segments are interleaved in time with the training segments, so its scores separate better (DL-065, finding b). It also uses a higher reference rate (20.1 %).
   - The time-split sensor is the default because the later-period data is the harder and more honest case.

## Limits

- **Synthetic faults, one detector, one data source.** The sensor assumptions above are untested.
- **Detection latency is not tested hard:**
  - The utility metric does not charge for duplicates (DL-041) or for idle time while a spacecraft is falsely degraded.
  - The schedule has enough slack that a few minutes of latency costs nothing.
  - In S03, B4 under H-A makes about 0.45 invalid observations per hour, so H-C's roughly 12 min of missed time would cost about 0.1 observation per run on average. Retention 1.000 does not mean H-C misses nothing.
- **Small samples:**
  - n = 10 seeds;
  - CBBA's tie-breaking concentrates every loss in the seeds where `a` is sc00, so its intervals are wide.
- **Preliminary:** forecasts and the storm replay (increment 4) are not part of this comparison. The Gate P4 write-up is increment 5.

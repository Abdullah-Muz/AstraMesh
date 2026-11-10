# Phase 4 comparison write-up (Gate P4)

> **Status:** written 2026-11-10 from the recorded Phase 4 results; no new runs. Awaiting owner review (DL-075). Gate P4 sign-off is a separate decision. **Preliminary, not a research result:** every comparison that involves the simulation uses synthetic faults or a synthetic risk map, and the real data cover one mission and one storm. Phase 4 increment 5 (DL-062).

This page checks the four Gate P4 criteria (spec §13) against the evidence, and sets the health and protection comparisons side by side. Every number here is quoted from the results files linked in each section; where a number is derived (for example, per spacecraft instead of summed), the derivation is stated.

## Phase 4 build list (spec §13)

| Spec item | Done | Where |
|---|---|---|
| Bounded OPS-SAT and ESA telemetry samples | OPS-SAT-AD downloaded and pinned (DS-02). ESA-ADB sized only: 11.6 GB compressed, more than the 14 GB RAM visible in WSL once unpacked (DL-062) | [`DATASET_REGISTRY.md`](../DATASET_REGISTRY.md) |
| GloTEC / COSMIC-2 science context | Left out of Phase 4: GloTEC starts in 2025 and cannot cover May 2024; COSMIC-2's licence is unverified (DL-071) | DL-071 |
| Historical environment streams | OMNI 1-min and GOES-18 SGPS 5-min, Jan 2023 – May 2024 (DS-06 – DS-09) | [`STORM_FORECAST.md`](STORM_FORECAST.md), [`STORM_REPLAY.md`](STORM_REPLAY.md) |
| Baseline anomaly detector | 9 detectors on OPS-SAT-AD, official and time-ordered splits | [`OPSSAT_BENCHMARK.md`](OPSSAT_BENCHMARK.md) |
| Calibrated probabilistic health model | H-B (probabilistic silence model) and H-C (H-B plus a calibrated detector filter), against the H-A timeout | [`HEALTH_COMPARISON.md`](HEALTH_COMPARISON.md) |
| Optional light learned model | Not pursued: H-C already recovers all S03 science, so increment 3 gave no reason for it (DL-072) | DL-072 |

## Criterion 1: data licences, provenance and train/test partitions documented

Every dataset an experiment used has a complete registry record (spec §8.2) and is opened only through `require_pinned`, which checks the SHA-256 of every file (DL-063).

| Dataset | Licence / terms | Used for | Partition |
|---|---|---|---|
| DS-02 OPS-SAT-AD | CC BY 4.0 and MIT; attribution met | Anomaly benchmark; score sensor for H-C | Official split (stratified, interleaved in time) **and** per-channel time split, earliest 75 % trains (DL-064) |
| DS-06 OMNI, May 2024 | No restrictions; citation and acknowledgement requested | Forecast test; S11 nav/comms and orbital inputs | Test only |
| DS-07 GOES-18 SGPS, 8–15 May 2024 | "may be redistributed and used without restriction" | Forecast test; S11 radiation input | Test only |
| DS-08 GOES-18 SGPS, Jan 2023 – Apr 2024 | As DS-07 | Forecast training | Training only; forward-chaining folds inside it |
| DS-09 OMNI, Jan 2023 – Apr 2024 | As DS-06 | Forecast training | Training only, as DS-08 |

- **Provenance in every result:** each meta file records the commit, the lockfile hash, `git_dirty: false`, and the data versions (data hashes for OPS-SAT-AD; per dataset, file count and the sha256 of the pinned hashes for the forecasts, DL-072; the pinned series hash for S11).
- **Gaps between training and test:** the storm week starts 8 days after the training period ends, and each forecast fold trains only on rows whose whole target window ends before its test block (EXPERIMENT_PROTOCOL §3.5).
- **Not downloaded, so no licence claim:** DS-01 ESA-ADB (its `LICENSE` file says CC BY 3.0 IGO, the Zenodo record carries none; to confirm before any use), DS-03 GloTEC, DS-04 CelesTrak and DS-05 COSMIC-2.

**Assessment: met.**

## Criterion 2: anomaly results independently benchmarked

The benchmark runs on real OPS-SAT telemetry and does not touch the simulation (spec §7.2). Recorded from clean commit `c557c6b` (DL-065).

- **It reproduces the published results.** XGBOD, logistic regression, one-class SVM and Isolation Forest match Ruszczak et al. (2025, Table 3) within 0.025 on every metric the paper reports. MO-GAAL reproduces in ranking (AUC) but not in its default decisions (F1 0.638 against 0.726). The paper used PyOD 1.1.2 and we use 3.6.7, whose MO-GAAL is a reimplementation; the old version was not run.
- **The time-ordered split shows what a shuffled split hides.** Supervised methods lose 0.013–0.025 AUC-ROC on it; unsupervised and classical methods lose 0.05–0.30, and three of them fall to or below chance. The gap mixes possible leakage with genuine drift: the later period has twice the anomaly rate.
- **Calibration:** the supervised models' probabilities are well calibrated on both splits (ECE ≤ 0.05, logistic regression on the time split 0.051). With thresholds fixed on training data, gradient boosting, random forest and XGBOD keep precision of at least 0.92 on the time split but miss 14–20 % of anomalies in the anomaly-heavier later period.
- **Cost** (spec §7.4): fit time, scoring time per segment and model size are measured for all nine detectors. XGBOD gives no gain over random forest or gradient boosting at 36–80× the scoring cost.

**Limits:** one feature set (the 18 published features), the paper's best model (a fully connected network) not run, and no interval over the fixed test set, only the spread over 5 seeds.

**Assessment: met.**

## Criterion 3: synthetic-vs-real interface explicit

Each use of real data in the simulation goes through exactly one pinned file. The simulation reads nothing else from the real data.

| | Health (increment 3) | Protection (increment 4) |
|---|---|---|
| The one link | [`configs/data/opssat_score_sensor.json`](../../configs/data/opssat_score_sensor.json): 527 calibrated test-set anomaly probabilities (time split; 529 for the official-split variant) and the training anomaly rate | [`configs/data/s11_storm_series.json`](../../configs/data/s11_storm_series.json): the ≥ 10 MeV flux, the P-A / P-B / P-C forecasts, AE and SYM-H, every 5 min |
| Real | detector scores from real OPS-SAT segments | measured flux, the forecasts made from it, geomagnetic indices, the 10 min data latency |
| Synthetic | when a payload fault starts and ends, which spacecraft it hits; everything about the spacecraft and links | the 100 pfu payload tolerance, the AE and SYM-H scale factors, the spacecraft, tasks and links |
| Assumptions, untested | detector checks are independent given the payload state; an AstraMesh payload fault looks to the detector like an OPS-SAT anomaly | all four LEO spacecraft see the GEO flux unshielded and at the same time (an upper bound); a payload is at risk at 100 pfu |
| Stress tests | `shift05` (5 % of healthy checks drawn from anomalous scores) and the official-split sensor | tolerance × 0.5 and × 2; 0.9 quantiles |

- **Domain shift (spec §7.2)** is tested in one direction only: `shift05` makes healthy checks look anomalous. A detector that misses AstraMesh faults (anomalous checks that look nominal) is not tested.
- **Never claimed** (spec §8.2): OPS-SAT data are not AstraMesh telemetry, an anomaly label is not a confirmed failure, and simulated exposure is not observed hardware damage.

**Assessment: met.**

## Criterion 4: preliminary health and forecast comparisons complete with uncertainty

| Comparison | Runs | Uncertainty | Recorded from |
|---|---|---|---|
| Health H-A / H-B / H-C on S00, S01, S03, S04, plus sensitivity variants (200 of the runs) | 440 × 24 h, seeds 1–10, B3 + timeout and B4 | 95 % t-intervals, n = 10 | `42c24a9` (DL-067) |
| Forecast skill P-A / P-B / P-C, four forward-chaining folds and the storm week | one deterministic fit per fold, and one on all training data for the storm week | 95 % day bootstrap (2 000 resamples), paired model differences; Clopper-Pearson for onsets warned | `00372d9` (point values, DL-071), `cedaec1` (intervals, DL-073) |
| Protection P-A / P-B / P-C on S11 (+ 8 sensitivity variants) | 240 × 8 days, seeds 1–10, both planners | none: deterministic apart from message loss, which changed nothing; stated as one storm plus sensitivity variants | `fc27fa3` (DL-071) |

The S11 choice follows EXPERIMENT_PROTOCOL §3.3: when every seed and both planners give the same value, a seed interval would have zero width and would hide the real uncertainty, which is in the one storm and the assumptions.

**Assessment: met,** with the S11 exception stated as above.

## The comparisons side by side

### Health (spec §7.2), planning held fixed

| Scenario | What happens | H-A (timeout) | H-B (probabilistic) | H-C (H-B + detector) |
|---|---|---|---|---|
| S01, spacecraft lost | silence carries the information | LOST after about 300 s | LOST after about 105 s | as H-B |
| S03, payload degraded | the spacecraft keeps talking | never detected; B4 keeps 0.876 [0.864, 0.889] of its utility, 5.4 invalid observations | as H-A | detected after 733 s [544, 922]; retention 1.000, 0 invalid observations |
| S04, radio off 3 h | a false outage | 6.1 (B3 + T) and 33.1 (B4) duplicates | same duplicates; LOST sooner, so slightly more false-outage time | as H-B |

- **The detector adds value only where the classical signal is blind** (S03). Where silence does carry the information (S01), the probabilistic model is about 3× faster than the timeout, but a 24 h schedule with slack absorbs the 200 s difference, so retention is 1.000 under every model.
- **No model separates a radio outage from a loss** (S04): silence alone cannot, and the detector watches only the spacecraft's own payload.
- **H-C's costs** are false-degraded time, not lost science: about 1 400 s of clearing lag after the S03 repair, and 4 650 s per day across the fleet under the `shift05` stress, covered by peers.

### Protection (spec §7.3), same supervisor

Storm week at 1 h, median forecasts, 100 pfu tolerance. Forecast skill from [`STORM_FORECAST.md`](STORM_FORECAST.md); replay results from [`STORM_REPLAY.md`](STORM_REPLAY.md), divided by 4 for one spacecraft (all four see the same inputs).

| | P-A (persistence) | P-B (empirical quantile) | P-C (gradient boosting) |
|---|---|---|---|
| Onsets warned (of 4) | 0 [0.00, 0.60] | 3 [0.19, 0.99] | 4 [0.40, 1.00] |
| POD gain over P-A | – | +0.17 [+0.06, +0.27] | +0.23 [+0.17, +0.33] |
| FAR change over P-A | – | +0.08 [−0.05, +0.17] | +0.19 [+0.05, +0.35] |
| Unprotected hazard per spacecraft (S11) | 40 min | 5 min | 0 |
| False protection per spacecraft (S11) | 8.6 h | 14.3 h | 21.1 h |
| Retention (S11) | 0.912 | 0.863 | 0.833 |

- **Forecasts close the reaction gap.** Both forecasts warn ahead of the hazard, and at 1 h both beat persistence in POD and pinball loss on the same days (P-C's pinball margin only just excludes 0, and at 30 min it does not). Persistence cannot warn at all.
- **On this storm, the classical forecast is the better trade.** P-B and P-C cannot be told apart in pinball loss (+0.003 [−0.001, +0.007]); P-C's higher false-alarm ratio is clear (+0.12 [+0.01, +0.22] over P-B). In the replay, closing P-B's last 5 min of unprotected hazard per spacecraft costs P-C 6.8 h more false protection per spacecraft and 0.030 of retention. One storm and one tolerance cannot settle this in general, and P-C cannot forecast above its training range (2023 Q3 fold).
- **The assumptions decide more than the forecast.** At 50 pfu all three keep 0.70–0.73 of the science; at 200 pfu no median forecast anticipates the one 5-min hazard. The tolerance is synthetic.

### What the two comparisons share

1. **The learned methods help where the classical ones are blind or late, and pay in false positives.**
   - **Health:** the gain is all H-C's. H-B sees nothing a timeout does not in S03, because a degraded payload keeps talking; H-C is the only model that saves science there. Its price is false-degraded time.
   - **Protection:** most of the gain is already P-B's. P-B closes 35 of P-A's 40 min of unprotected hazard per spacecraft; P-C closes the last 5 min, at a clearly higher false-alarm ratio and 6.8 h more false protection.
   - In these two comparisons, then, what decided the value of the learned method was whether a classical method could see the signal at all.
2. **The distributed part of the mission is not yet exercised.** In S01 the schedule's slack absorbs detection delay; in S11 all four spacecraft see the same risk and protect together, so no task can move to a peer, and the planner and message loss make no difference. A distributed mission can only gain from better beliefs or forecasts when spacecraft differ in what they see, or when schedules are tight. This is the main input to Phase 5.
3. **Safety held throughout.** 0 payload steps in protected modes and 0 confirmed-failed beliefs about an available spacecraft in all 440 health runs and all 240 S11 runs.

## Not done in Phase 4

- ESA-ADB (sized only), GloTEC and COSMIC-2 (left out), the optional learned model (not justified).
- OPS-SAT: no raw-sequence models; the paper's fully connected network and 23 other methods not run; no interval over the test set.
- Forecasts: one storm (4 onsets above 100 pfu on the test week); coarse day-bootstrap intervals (8 days, neighbouring days treated as independent); no physics-based or event-probability forecasts compared; CPU latency and memory of the forecasters not measured (spec §7.4 lists them; the detectors' are).
- Health: domain shift tested in one direction; the utility metric charges neither duplicates (DL-041) nor idle false-degraded time.

## Carried forward (not blocking)

- **To Phase 5:** orbit-dependent radiation inputs (e.g. by magnetic latitude), so spacecraft see different risks (DL-071 (c)); scenarios with less schedule slack, so detection latency can cost science; a utility that charges duplicates and false-degraded idle time.
- **Supervisor release rule:** DL-061 asked to revisit the 30 min release dwell with real forecasts. S11 shows that even P-A spends more time protected outside the hazard than inside it (8.6 h against 6 h per spacecraft), because of the shared release rule (30 min below 0.8, then RECOVERY). The rule was not changed in Phase 4; it stays open.
- **CBBA run time:** an 8-day B3 run still takes 15–20 min after DL-074; a further speedup would change code the B3 results rest on (DL-074).
- **Earlier carry-overs remain** (DL-037, DL-049, DL-061): the literature drafts await owner verification; P01/P01S are unread, so no novelty claim; CBBA has no stop rule; S06 is deferred; B4 has no handback.

## Reproduce

| Result | Script | Clean commit | Time |
|---|---|---|---|
| [`OPSSAT_BENCHMARK.md`](OPSSAT_BENCHMARK.md) | `scripts/experiments/opssat_benchmark.py` | `c557c6b` | about 2.5 min, 6 workers |
| [`HEALTH_COMPARISON.md`](HEALTH_COMPARISON.md) | `scripts/experiments/health_comparison.py` | `42c24a9` | about 38 min, 6 workers |
| [`STORM_FORECAST.md`](STORM_FORECAST.md) | `scripts/experiments/storm_forecast_benchmark.py` | `cedaec1` | about 3 min |
| [`STORM_REPLAY.md`](STORM_REPLAY.md) | `scripts/experiments/storm_replay_comparison.py` | `fc27fa3` | about 8.5 h, 6 workers |

Data: `uv run python scripts/data/fetch_data.py` downloads every pinned file (DL-063).

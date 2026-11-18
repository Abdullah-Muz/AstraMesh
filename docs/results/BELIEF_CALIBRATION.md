# Calibration of the agents' health beliefs

> **Status:** recorded 2026-11-17 from clean commit `92555d4` (`git_dirty: false`; 360 runs, 57 min on 6 workers). Maintenance after v2.0.2 (design DL-142, code DL-143, results DL-144). Every run reruns a recorded configuration of [`HEALTH_COMPARISON.md`](HEALTH_COMPARISON.md) unchanged and reproduced it exactly. **Synthetic faults; simulation truth.** The H-C detector's scores are real (OPS-SAT-AD), as in the health comparison. These numbers describe the models under this scenario mix, not calibration in general.

## Setup (DL-142)

- **Question (spec §10.2):** when an agent holds P(peer unavailable) = p (H-B) or P(own payload degraded) = p (H-C), how often is that true in the simulator?
- **Beliefs measured:**
  - **Peer (H-B):** the posterior from silence, a prior failure rate (mean 30 days; 3 and 300 days in the sensitivity arms) and a learned message-loss rate. Agents act on it at 0.5 (SUSPECTED) and 0.95 (LOST).
  - **Payload (H-C):** the two-state filter fed by the onboard detector every 300 s. Agents act on it at 0.9 (DEGRADED) and clear it at 0.1.
- **Runs:** every non-H-A run of the health comparison (H-A holds no probability): H-B and H-C on S00, S01, S03 and S04; H-B/mtbf3d and H-B/mtbf300d on S00, S01 and S04; H-C/official and H-C/shift05 on S00 and S03; B3 + timeout and B4; seeds 1 – 10. 360 runs of 24 h.

  | Scenario | Injected condition (synthetic) | Truth for peer samples |
  |---|---|---|
  | S00 | none | every peer available |
  | S01 | `a` permanently unavailable from t0 (4 – 10 h) | `a` unavailable from t0 |
  | S03 | `a` payload degraded for 12 h | every peer available; `a`'s payload degraded |
  | S04 | `a` radio off for 3 h; it keeps working | every peer available (silent, not failed) |

- **Samples:**
  - **Peer:** after every agent step (10 s), for each available observer and each of its three peers: `p_unavailable(peer, t)` against whether the peer is unavailable. A spacecraft that is down is not stepped, so it never contributes samples.
  - **Payload:** after every detector check an agent receives: the filter's p against whether its payload is degraded.
  - The truth comes from the run's own fault schedule; agents never see it.
- **Metrics:** base rate (fraction of samples that are true); Brier score (mean squared error of p); Brier skill against a constant forecast at the base rate; a reliability table with 10 equal-width bins; expected calibration error (ECE: count-weighted \|mean p − observed frequency\| over the bins). Brier and ECE are computed per seed and reported as the mean with a 95 % t-interval (n = 10), not clipped to the possible range. Reliability tables pool the seeds. Bins with fewer than 30 samples are shown in the data but not interpreted.
- **Unchanged behaviour:** every run's utility, completions, messages sent, bytes sent and config hash equal its row in `health_comparison.csv` (360 of 360).
- **Reproduce:** `uv run --locked python scripts/experiments/belief_calibration.py --out <dir> [--workers 6]` (about an hour on 6 workers on the shared laptop).
  - Files: [`belief_calibration.csv`](belief_calibration.csv) (one row per run and kind: sample sums and per-bin sums), [`belief_calibration_summary.csv`](belief_calibration_summary.csv) (per model, kind, planner and scenario, and pooled), [`belief_calibration_bins.csv`](belief_calibration_bins.csv) (reliability tables) and [`belief_calibration_meta.json`](belief_calibration_meta.json).

**Two identities, checked in the data:**

- H-B and H-C send exactly the same messages in every recorded run, and peer beliefs depend only on what arrives, so H-C's peer results equal H-B's in every case. They are shown once, as H-B.
- The payload belief depends only on the detector's draws and the fault, so the payload results are identical under both planners. They are shown once.

## Results

**Peer beliefs (H-B), by scenario** (Brier and ECE: mean [95 % CI] over 10 seeds; S03 equals S00 in every column):

| Planner | Scenario | Samples | Base rate | Brier | ECE | Samples at p ≥ 0.9 | … of which true | Samples at 0.1 ≤ p < 0.9 |
|---|---|---|---|---|---|---|---|---|
| B3 + T | S00 | 1 036 920 | 0 | 1.2 × 10⁻¹¹ | 3.5 × 10⁻⁶ | 0 | – | 0 |
| B3 + T | S01 | 849 651 | 0.221 | 2.8 × 10⁻⁴ [2.6, 2.9 × 10⁻⁴] | 3.0 × 10⁻⁴ [2.9, 3.1 × 10⁻⁴] | 22.0 % | 100 % | 0.011 % |
| B3 + T | S04 | 1 036 920 | 0 | 0.062 | 0.062 | 6.20 % | 0 % | 0.018 % |
| B3 + T | pooled | 3 960 411 | 0.047 | 0.016 | 0.016 | 6.35 % | 74.4 % | 0.007 % |
| B4 | S00 | 1 036 920 | 0 | 6.2 × 10⁻⁶ [2.7, 9.7 × 10⁻⁶] | 4.7 × 10⁻⁵ [3.7, 5.7 × 10⁻⁵] | 0 | – | 0.008 % |
| B4 | S01 | 849 651 | 0.221 | 2.7 × 10⁻⁴ [2.5, 2.8 × 10⁻⁴] | 2.6 × 10⁻⁴ [2.4, 2.7 × 10⁻⁴] | 22.0 % | 100 % | 0.018 % |
| B4 | S04 | 1 036 920 | 0 | 0.062 | 0.062 | 6.21 % | 0 % | 0.025 % |
| B4 | pooled | 3 960 411 | 0.047 | 0.016 | 0.016 | 6.35 % | 74.4 % | 0.015 % |

Intervals narrower than the rounding are not shown. The pooled Brier skill is 0.63 under both planners (S01 alone: 0.998).

**Prior sensitivity (peer):** with a mean time to unavailability of 3 or 300 days instead of 30, S04 is unchanged (Brier 0.062, 6.2 % of samples at p ≥ 0.9, none true, under both planners). In S00 under B4, the 3-day prior raises the Brier score from 6.2 × 10⁻⁶ to 5.2 × 10⁻⁵ [3.1, 7.3 × 10⁻⁵] and the 300-day prior lowers it to 1.7 × 10⁻⁷. The middle bins hold 0.007 – 0.018 % of the pooled samples in every arm, and at most 0.026 % in any one scenario.

**Payload beliefs (H-C)** (same under both planners; S04 holds no payload fault and scores exactly as S00; S01, with `a` down and not checked, has Brier 3.3 × 10⁻⁷ and ECE 1.1 × 10⁻⁴):

| Arm | Scenario | Samples | Base rate | Brier | ECE | Samples at p ≥ 0.9 | … of which true |
|---|---|---|---|---|---|---|---|
| H-C | S00 | 11 520 | 0 | 1.1 × 10⁻⁷ [0.8, 1.4 × 10⁻⁷] | 1.0 × 10⁻⁴ [0.97, 1.1 × 10⁻⁴] | 0 | – |
| H-C | S03 | 11 520 | 0.125 | 0.0032 [0.0026, 0.0039] | 0.0034 [0.0027, 0.0042] | 12.5 % | 98.7 % |
| H-C/official | S03 | 11 520 | 0.125 | 0.0018 [0.0014, 0.0022] | 0.0019 [0.0015, 0.0023] | 12.5 % | 99.4 % |
| H-C/shift05 | S00 | 11 520 | 0 | 0.011 [0.008, 0.015] | 0.020 [0.015, 0.025] | 0.52 % | 0 % |
| H-C/shift05 | S03 | 11 520 | 0.125 | 0.012 [0.008, 0.016] | 0.017 [0.012, 0.021] | 12.9 % | 95.6 % |

## Expectations (stated in DL-142 before any run)

| | Expectation | Result |
|---|---|---|
| E1 | Most peer samples have p < 0.1 or p > 0.9; the middle bins hold under 1 % | **Held:** 0.007 – 0.018 % pooled in every arm and planner; at most 0.026 % in any one scenario |
| E2 | In S04 the top bin is badly over-confident: observed frequency below 0.5 | **Held:** 0 under both planners. It holds by construction, since no peer is unavailable in S04; the substance is how much time is spent there (finding 2) |
| E3 | In S00 the peer Brier score is below 0.001 | **Held:** 1.2 × 10⁻¹¹ (B3 + T), 6.2 × 10⁻⁶ (B4) |
| E4 | The prior moves the middle bins but not E2 | **Held:** S04's top bin is 0 % true under the 3- and 300-day priors |
| E5 | H-C's top payload bin in S03 is at least 80 % true, and shift05 has a higher ECE than H-C on S00 | **Held:** 98.7 %; ECE 0.020 [0.015, 0.025] against 1.0 × 10⁻⁴ |

## Findings

1. **Peer beliefs are almost always near 0 or 1** (E1). With the initial loss-rate prior, p stays below 0.02 for the first 80 s of silence, then rises at each missed status message (every 30 s): 0.16 at 90 s, 0.68 at 120 s, 0.95 at 150 s. Silences longer than 80 s are rare except after a failure or an outage, so the middle bins hold about one sample in 10 000. Calibration in the middle range cannot be judged from these runs.
2. **A silent spacecraft that still works is believed dead.** In S04, 6.2 % of peer samples are at p ≥ 0.9 and none is true. Per seed that is 64 310 (B3 + T) and 64 434 (B4) pair-seconds out of the 64 800 that the 3 h outage silences (6 observer–peer pairs), so the observers are nearly certain of a failure for over 99 % of the outage. Silence is the only evidence H-B uses, and the prior cannot fix this: the 3- and 300-day priors give the same result (E4). Pooled over the four scenarios, p ≥ 0.9 is true 74 % of the time; every false sample comes from S04.
3. **When a peer really fails, the belief is right and fast.** In S01, every sample at p ≥ 0.9 is true, and about 0.1 % of the unavailable-peer samples (186 and 179 of 187 269) sit below 0.1. These are the first steps after the loss, before the silence is long enough: about 60 s per observer, consistent with the 104 – 108 s H-B detection latency recorded in the health comparison (latency counts to p ≥ 0.95).
4. **The payload belief is well calibrated with the detector as trained** (E5): 98.7 % of S03's confident samples are true (99.4 % with the official-split sensor). When 5 % of healthy checks look anomalous (shift05), confident false alarms appear (0.52 % of S00 samples, none true) and the ECE rises from 1.0 × 10⁻⁴ to 0.020.
5. **Consistency with the health comparison.** Finding 2 is the probabilistic form of what [`HEALTH_COMPARISON.md`](HEALTH_COMPARISON.md) reported for S04: H-B believed peers LOST (p ≥ 0.95) for 64 269 of the 64 800 pair-seconds under B3 + T, and silence alone cannot separate a radio outage from a loss.

## Limits

- **Simulation truth and one scenario mix.** Four scenarios with one scripted fault each, a 24 h horizon, and the recorded settings. The pooled figures depend on the mix (here 22 % of S01 samples, and so 4.7 % of all peer samples, have an unavailable peer). The H-B prior assumes random failures; the scenarios do not.
- **Samples are not independent.** Consecutive 10 s samples of one pair are strongly correlated, so the sample counts overstate the evidence; the intervals are over seeds (n = 10), not samples.
- **The middle bins are nearly empty** (finding 1), so these runs say little about calibration between 0.1 and 0.9.
- **H-A and the storm scenarios are not measured:** H-A holds no probability, and the storm runs use the timeout model, so an H-B storm arm would be a new configuration, not a rerun (DL-142).
- **Synthetic-vs-real interface for H-C** as in the health comparison: the detector's scores are real, but the way they are attached to simulated faults is an assumption.

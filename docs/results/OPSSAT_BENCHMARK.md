# OPS-SAT-AD anomaly-detection benchmark

> **Status:** recorded 2026-11-04 from clean commit `c557c6b` (`git_dirty: false`). Real spacecraft telemetry (ESA OPS-SAT, 2022), **independent of the AstraMesh simulation** (spec §7.2): nothing here says anything about AstraMesh's four fictional spacecraft. An anomaly label is not a confirmed failure. Phase 4 increment 2 (DL-064, DL-065).

## Setup (DL-064)

- **Data:** OPS-SAT-AD (DS-02, pinned; [`DATASET_REGISTRY.md`](../DATASET_REGISTRY.md)). There are 2 123 telemetry segments from 9 channels, 434 of them anomalous. Each segment is described by the 18 features published with the dataset. A test recomputes 7 of those features from the raw telemetry, for every segment, and they match.
- **Splits:**

  | Split | Train (anomalous) | Test (anomalous) | Notes |
  |---|---|---|---|
  | `official` | 1 594 (321, 20 %) | 529 (113, 21 %) | The dataset's own split: stratified random, interleaved in time. Comparable with the paper. |
  | `time` | 1 596 (258, 16 %) | 527 (176, 33 %) | Per channel, the earliest 75 % of segments train. Every test segment is later than its channel's training segments (spec §7.4). |

  The time split's test period has twice the training anomaly rate. This is a property of the data, not of the split rule: for example, 35 of the last 48 segments of channel CADC0874 are anomalous.
- **Detectors (9):**
  - **classical:** robust z-score (the largest feature deviation, measured with median and MAD);
  - **unsupervised (PyOD):** Isolation Forest, LOF, one-class SVM, MO-GAAL;
  - **supervised:** logistic regression, random forest and histogram gradient boosting (scikit-learn), and XGBOD (PyOD).

  Features are standardised with statistics of the nominal training rows only, as in the dataset authors' notebook.
- **Protocols:**
  - **`paper`:** the library's default decision. For the unsupervised methods that is PyOD defaults with contamination 0.2, as in the paper; for the supervised ones it is `predict`.
  - **`calibrated`:** the decision threshold maximises out-of-fold F1, and isotonic regression turns scores into probabilities. Both are fitted with 5-fold cross-validation inside the training rows only. The folds are stratified random for `official` and contiguous time blocks per channel for `time`. The test set is used once.
- **Seeds:** 0–4. Mean ± sd over seeds; a single number means all five seeds agree (deterministic methods).
- **Reproduce:** `uv run python scripts/experiments/opssat_benchmark.py`. It takes about 2.5 min on 6 workers. A repeat run reproduced every column except the CPU times exactly. The recorded run wrote its outputs outside the repository, and the files were then copied in; see DL-065.
- **Files:**
  - [`opssat_benchmark.csv`](opssat_benchmark.csv): one row per split, method, seed and protocol;
  - [`opssat_benchmark_summary.csv`](opssat_benchmark_summary.csv): mean and sd, plus the `all_anomalous` reference;
  - [`opssat_reliability.csv`](opssat_reliability.csv): calibration bins;
  - [`opssat_benchmark_meta.json`](opssat_benchmark_meta.json): commit, lockfile and data hashes.

## 1. Reproduction of the paper (official split, `paper` protocol)

Paper values are from Ruszczak et al. (2025), Table 3, which reports one run per method. Ours are the mean of 5 seeds.

| Method | AUC-PR (paper) | AUC-ROC (paper) | Accuracy | F1 (paper) | Precision | Recall | MCC (paper) |
|---|---|---|---|---|---|---|---|
| XGBOD | **0.974** ± 0.001 (0.975) | **0.991** ± 0.001 (0.992) | 0.966 | 0.918 ± 0.006 (0.918) | 0.947 | 0.890 | 0.897 (0.897) |
| Hist. gradient boosting | 0.970 | 0.989 | 0.964 | 0.914 | 0.935 | 0.894 | 0.892 |
| Random forest | 0.966 ± 0.004 | 0.987 ± 0.002 | 0.968 | **0.922** ± 0.004 | 0.974 | 0.874 | **0.904** |
| Logistic regression | 0.931 (0.931) | 0.968 (0.969) | 0.924 | 0.800 (0.800) | 0.920 | 0.708 | 0.764 (0.764) |
| MO-GAAL | 0.760 ± 0.026 (0.779) | 0.850 ± 0.017 (0.865) | 0.842 | 0.638 ± 0.017 (0.726) | 0.624 | 0.653 | 0.537 (0.710) |
| One-class SVM | 0.661 (0.659) | 0.789 (0.787) | 0.851 | 0.655 (0.647) | 0.647 | 0.664 | 0.560 (0.548) |
| LOF | 0.587 | 0.774 | 0.830 | 0.583 | 0.612 | 0.558 | 0.478 |
| Isolation Forest | 0.356 ± 0.010 (0.347) | 0.635 ± 0.019 (0.635) | 0.694 | 0.278 ± 0.027 (0.295) | 0.281 | 0.276 | 0.084 (0.105) |
| Robust z-score | 0.282 | 0.511 | 0.626 | 0.132 | 0.130 | 0.133 | −0.107 |
| *Flag every segment* | 0.214 | 0.500 | 0.214 | 0.352 | 0.214 | 1.000 | 0.000 |

- **XGBOD, logistic regression, one-class SVM and Isolation Forest reproduce the paper** within 0.025 on every metric where the paper reports them.
- **MO-GAAL's ranking quality reproduces, but its decisions do not.** Its AUCs are within one seed standard deviation of the paper's. Its default-decision F1 and MCC are lower than the paper's (0.638 vs 0.726, 0.537 vs 0.710), and the paper's very high precision (0.985) does not appear in any of our seeds. The paper used PyOD 1.1.2; we use PyOD 3.6.7, whose MO-GAAL is a PyTorch reimplementation. We did not run the old version.
- **The paper's best model, a fully connected network (F1 0.946), was not run.** Our best F1 is 0.922 (random forest).

## 2. Official vs time-ordered split (possible leakage)

AUC-ROC is used for the comparison because it does not depend on the anomaly rate. AUC-PR does: it rises with prevalence, and the time split's test set has 33 % anomalies against 21 %.

| Method | AUC-ROC official | AUC-ROC time | Change | F1 time (`paper`) | False-alert rate time |
|---|---|---|---|---|---|
| Hist. gradient boosting | 0.989 | 0.977 | −0.013 | 0.900 | 0.014 |
| Random forest | 0.987 | 0.973 | −0.015 | 0.898 | 0.012 |
| Logistic regression | 0.968 | 0.955 | −0.014 | 0.866 | 0.040 |
| XGBOD | 0.991 | 0.965 | −0.025 | 0.878 | 0.051 |
| MO-GAAL | 0.850 | 0.802 | −0.049 | 0.560 | 0.418 |
| One-class SVM | 0.789 | 0.711 | −0.078 | 0.594 | 0.342 |
| Isolation Forest | 0.635 | 0.425 | −0.210 | 0.252 | 0.416 |
| LOF | 0.774 | 0.522 | −0.252 | 0.401 | 0.350 |
| Robust z-score | 0.511 | 0.211 | −0.300 | 0.082 | 0.302 |
| *Flag every segment* | 0.500 | 0.500 | — | 0.501 | 1.000 |

- **Supervised methods lose little (0.013–0.025 AUC-ROC).** The official split's mixing of time inflates their results only slightly.
- **Unsupervised and classical methods lose much more (0.05–0.30).** Isolation Forest, LOF and the robust z-score fall to or below chance, and their F1 is below that of flagging every segment. They learn what is unusual in the training period; anomalies in the later period are, in these features, less unusual than that. This is distribution shift, which a time-shuffled split hides.
- **This gap is not proof of leakage.** The two splits also differ in anomaly rate and in which segments are tested, so the change mixes leakage with genuine drift.

## 3. Calibrated decisions (`calibrated` protocol)

| Method | Split | F1 | Precision | Recall | MCC | False alerts | Missed / anomalies | ECE | Brier |
|---|---|---|---|---|---|---|---|---|---|
| Random forest | official | 0.918 | 0.948 | 0.890 | 0.897 | 1.3 % | 12.4 / 113 | 0.020 | 0.030 |
| XGBOD | official | 0.913 | 0.924 | 0.904 | 0.891 | 2.1 % | 10.8 / 113 | 0.018 | 0.027 |
| Hist. gradient boosting | official | 0.909 | 0.911 | 0.906 | 0.884 | 2.4 % | 10.6 / 113 | 0.013 | 0.029 |
| Logistic regression | official | 0.831 | 0.864 | 0.807 | 0.791 | 3.6 % | 21.8 / 113 | 0.030 | 0.047 |
| Hist. gradient boosting | time | 0.898 | 0.949 | 0.852 | 0.854 | 2.3 % | 26.0 / 176 | 0.019 | 0.050 |
| Random forest | time | 0.893 | 0.929 | 0.860 | 0.844 | 3.4 % | 24.6 / 176 | 0.028 | 0.055 |
| XGBOD | time | 0.871 | 0.952 | 0.803 | 0.821 | 2.1 % | 34.6 / 176 | 0.041 | 0.065 |
| Logistic regression | time | 0.821 | 0.756 | 0.898 | 0.725 | 14.5 % | 18.0 / 176 | 0.051 | 0.080 |
| MO-GAAL | time | 0.659 ± 0.098 | 0.752 | 0.666 | 0.506 ± 0.235 | 21.7 % | 58.8 / 176 | 0.120 | 0.137 |
| One-class SVM | time | 0.669 | 0.667 | 0.670 | 0.502 | 16.8 % | 58.0 / 176 | 0.086 | 0.173 |

Unsupervised rows for the official split, and the other unsupervised methods on the time split, are in the summary CSV. On the time split, robust z-score, Isolation Forest and LOF stay below the flag-everything F1 (0.501).

- **The supervised models' probabilities are well calibrated on both splits:** ECE ≤ 0.05.
- **Thresholds chosen on training data do not adapt to the later period's anomaly rate.** On the time split, gradient boosting, random forest and XGBOD keep precision of at least 0.92 but miss 14–20 % of anomalies. In practice a deployed detector would need its threshold or prior re-estimated as the anomaly rate drifts.
- **Calibration makes a weak detector's probabilities honest, not useful.** Robust z-score and Isolation Forest get low ECE on the official split (≤ 0.012) because isotonic regression maps their uninformative scores to roughly the base rate.
- **MO-GAAL depends strongly on the seed.** On the time split, its five seeds give MCC from 0.20 to 0.68.

## 4. Cost (official split, mean over seeds, single thread)

| Method | Fit CPU | Score CPU per segment | Model size |
|---|---|---|---|
| Robust z-score | 0.003 s | 0.001 ms | 1.3 kB |
| Logistic regression | 0.17 s | 0.014 ms | 1.6 kB |
| LOF | 0.03 s | 0.020 ms | 537 kB |
| One-class SVM | 0.15 s | 0.050 ms | 153 kB |
| Isolation Forest | 0.19 s | 0.031 ms | 866 kB |
| Hist. gradient boosting | 0.35 s | 0.012 ms | 386 kB |
| Random forest | 0.42 s | 0.027 ms | 1.26 MB |
| MO-GAAL | 2.7 s | 0.002 ms | 3.2 kB* |
| XGBOD | 3.4 s | **0.96 ms** | **11.4 MB** |

\* The size counts only the kept discriminator network's parameters, because the PyOD model cannot be pickled. The other sizes are pickled bytes. CPU times vary between runs.

- **XGBOD gives no accuracy gain over a plain random forest or gradient boosting on these features, at 36–80× the scoring cost and 9–30× the size.** It runs a bank of unsupervised detectors to build its features before boosting.

## Findings

1. **The benchmark reproduces the published results** for XGBOD, logistic regression, one-class SVM and Isolation Forest. MO-GAAL reproduces on ranking but not on default decisions, with large seed variance.
2. **For anomaly detection on OPS-SAT, the supervised tree ensembles are the strongest and cheapest credible choice.** Gradient boosting and random forest reach AUC-ROC 0.97–0.99 on both splits, with calibrated probabilities (ECE ≤ 0.03).
3. **The time-ordered split matters most for the unsupervised methods.** Their apparent skill on the shuffled split largely disappears on later data. Any use of an unsupervised detector for health inference (increment 3) needs a time-ordered evaluation.
4. **Anomaly rates drift.** A threshold or prior fixed at training time under-detects in a later, anomaly-heavier period. Increment 3's adapter from detector scores to health beliefs should treat the prior as uncertain, not as a fixed number.

## Limits

- **Features:** one feature set, the 18 published features; no raw-sequence models. The paper's fully connected network and 23 of its other methods were not run.
- **Scope:** one mission, 9 channels, 5 months. Nothing here transfers to AstraMesh's simulated spacecraft without the documented adapter and domain-shift stress tests (spec §7.2), which are increment 3.
- **Segment-level evaluation:** each segment is one event, so detection latency within an event is not measured. Segments are pre-cut by the dataset authors, so detection also benefits from that segmentation.
- **Calibrated-protocol threshold:** chosen to maximise F1, which weighs false alerts and misses equally; an operational cost ratio was not set.
- **Unsupervised score scales:** for these methods, fold models and the final model can score on slightly different scales.
- **The paper's single run vs our five seeds:** some of the gaps we report are within the seed spread.

# Phase 6 write-up (Gate P6)

> **Status:** written 2026-11-16 from the recorded results; no new runs. Phase 6 increment 5 (DL-128 design, DL-129). Approved 2026-11-16 (DL-129); Gate P6 signed off 2026-11-16 (DL-130). **Simulation results, not flight or radiation results:** every spacecraft, task, link and tolerance is synthetic, and the radiation hazard is a model. The storms are measured.

This page checks the three Gate P6 criteria (spec §13) against the evidence. The full account of the results is the technical report, [`REPORT.md`](../REPORT.md).

## Phase 6 build list (spec §13)

| Spec item | Done | Where |
|---|---|---|
| Held-out Monte Carlo | Six storms after May 2024, chosen by a rule fixed before any run (DL-113); frozen methods, settings and forecasts; 288 runs; expectations E1 – E5 written before the run | [`HELDOUT.md`](HELDOUT.md) |
| Selected Basilisk comparisons | Two-body, J2, J2 + drag and formation spacing over 8 days, tolerances fixed before the run; all passed | [`BASILISK_COMPARISON.md`](BASILISK_COMPARISON.md) |
| Ablations | No look-ahead, no forecast, no hysteresis and no reconciliation on the six held-out storms (the Phase 5 ablations covered five more) | [`HELDOUT.md`](HELDOUT.md), [`ABLATIONS.md`](ABLATIONS.md) |
| Negative-result analysis | N1 – N6, hypotheses fixed before the run; plus the B4 ownership re-sync added by the owner (increment 3b), tested on the two reserved storms | [`NEGATIVE_RESULTS.md`](NEGATIVE_RESULTS.md), [`RESYNC_COMPARISON.md`](RESYNC_COMPARISON.md) |
| Technical report | Publication-style Markdown | [`REPORT.md`](../REPORT.md) |
| Project README | Status, results, figures, demonstration, stack and data actually used | [`README.md`](../../README.md) |
| Actual-result plots and demo video | F1 – F9 drawn from committed results and pinned series only; a 52 s MP4 rendered from a trace that reproduces a recorded run | [`docs/figures/`](../figures/README.md), [`docs/media/`](../media/README.md) |

## Criterion 1: every reported result traces to a commit / config / data version

**Rule followed throughout.** Each result was run from a clean commit, then committed with its meta file in a separate results commit. The meta file records the commit, `git_dirty: false`, the lockfile hash and every run's configuration hash, and for storm runs the SHA-256 of each series it read. The storm series themselves are committed under [`configs/data/`](../../configs/data/) and were built from the pinned registry files: DS-06 / DS-07 for May 2024, DS-08 / DS-09 for the training-period storms, DS-11 / DS-12 for the held-out and reserved storms ([`DATASET_REGISTRY.md`](../DATASET_REGISTRY.md)).

| Results page | Clean commit (meta file) | Results commit | Runs | Data |
|---|---|---|---|---|
| [`S00_LOSS_COMPARISON.md`](S00_LOSS_COMPARISON.md) | `dafa540` ([meta](s00_loss_comparison_meta.json)) | `60fbadf` | 120 | synthetic only |
| [`FAULT_COMPARISON.md`](FAULT_COMPARISON.md) | `311477a` ([meta](fault_comparison_meta.json)) | `e734eba` | 600 | synthetic only |
| [`OPSSAT_BENCHMARK.md`](OPSSAT_BENCHMARK.md) | `c557c6b` ([meta](opssat_benchmark_meta.json)) | `f0760f8` | 9 detectors × 2 splits × 5 seeds | DS-02 |
| [`HEALTH_COMPARISON.md`](HEALTH_COMPARISON.md) | `42c24a9` ([meta](health_comparison_meta.json)) | `7f01b8e` | 440 | DS-02 via `opssat_score_sensor.json` |
| [`STORM_FORECAST.md`](STORM_FORECAST.md) | `00372d9` point values, `cedaec1` intervals ([meta](storm_forecast_meta.json)) | `c8451ca` (point values), `bad9cec` (intervals) | 3 models, 4 folds and the storm week | DS-06 – DS-09 |
| [`STORM_REPLAY.md`](STORM_REPLAY.md) | `fc27fa3` ([meta](storm_replay_meta.json)) | `c8451ca` | 240 | `s11_storm_series.json` (DS-06, DS-07) |
| [`DRAG_DRIFT.md`](DRAG_DRIFT.md) | `9cd0016` D1, `460ccaf` D2 ([meta](drag_drift_meta.json), [meta](drag_drift_msis_meta.json)) | `7fbb215` (D1), `505b8fc` (D2) | 12 + 9 | DS-10 (D2) |
| [`FORMATION_KEEPING.md`](FORMATION_KEEPING.md) | `d7ab81a` ([meta](formation_keeping_meta.json)) | `d205d12` | 11 | DS-10 |
| [`PER_SPACECRAFT_RISK.md`](PER_SPACECRAFT_RISK.md) | `45430aa` ([meta](per_spacecraft_risk_meta.json)) | `0388e4e` | 10 | May 2024 series |
| [`HANDOVER_TUNING.md`](HANDOVER_TUNING.md) | `a7b2046` ([meta](handover_tuning_meta.json)) | `fd5abc3` | 33 | February 2024 series |
| [`HANDOVER_COMPARISON.md`](HANDOVER_COMPARISON.md) | `fd5abc3` ([meta](handover_meta.json)) | `a2121d5` | 229 | May 2024 series |
| [`MULTI_STORM.md`](MULTI_STORM.md) | `f25e224` ([meta](multi_storm_meta.json)) | `2c44ee3` | 72 | four training-period storm series |
| [`PROTECTION_TUNING.md`](PROTECTION_TUNING.md) | `29f1b3f` ([meta](protection_tuning_meta.json)) | `0935e98` | 60 | February 2024 series |
| [`PROTECTION_COMPARISON.md`](PROTECTION_COMPARISON.md) | `0935e98` ([meta](protection_meta.json)) | `af5b551` | 72 | four training-period storm series |
| [`ABLATIONS.md`](ABLATIONS.md) | `16f038e` ([meta](ablation_meta.json)) | `b97cb1a` | 180 | May 2024 and four training-period series |
| [`SPREAD_FORMATION.md`](SPREAD_FORMATION.md) | `16f038e` ([meta](spread_meta.json)) | `b97cb1a` | 36 | 23 Mar 2024 series |
| [`HELDOUT.md`](HELDOUT.md) | `32e005a` ([meta](heldout_meta.json)) | `e0d0d95` | 288 | six held-out series (DS-11, DS-12) |
| [`BASILISK_COMPARISON.md`](BASILISK_COMPARISON.md) | `21c5db9` ([meta](basilisk_comparison_meta.json); also the `tools/basilisk` lock hash) | `b157b52` | 4 cases, both codes | none (shared case file) |
| [`NEGATIVE_RESULTS.md`](NEGATIVE_RESULTS.md) | `f2a1b3a` ([meta](negative_results_meta.json)) | `5a85d68` | 96 | May 2024 (S11-H), training-period, spread and held-out series, with latency variants |
| [`RESYNC_COMPARISON.md`](RESYNC_COMPARISON.md) | `a94b654` ([meta](resync_meta.json)) | `0465610` | 214 | development series and the two reserved series |
| [`storm_diagnostics.json`](storm_diagnostics.json) (diagnostic cited by MULTI_STORM and PROTECTION_COMPARISON) | `16f038e` (in the file) | `b97cb1a` | 5 | the 23 Mar 2024 and 18 Jul 2023 series |
| Figures and demonstration | `74273a0` ([trace](demo_trace.json)) | `66ea3be` | 1 (trace) | committed results and series only |

The results commit is the commit that added the page, or the later commit that added a second meta file. Phase 1's dynamics and geometry results are physics acceptance tests (PA-01 – PA-10) that run in CI on every push.

**Checked by a test.** [`tests/unit/test_report_links.py`](../../tests/unit/test_report_links.py) checks that every meta file, `storm_diagnostics.json` and the demo trace carry a full commit hash and `git_dirty: false`, that every relative link in the report, this page and the README resolves, and that the report cites every results page. Before this page was committed, a separate reviewer that had seen only the report and the repository checked each number in the report against its source (DL-129).

**Disclosed exceptions.**
- **Unrecorded diagnostics.** The re-sync's spread-formation duplicate diagnosis and duplicate-charged utilities, and its explanation of the 5 000 km byte cost, came from unrecorded reruns of recorded configurations that gave identical results (RESYNC_COMPARISON.md says so). The held-out B4 split diagnosis was a scratch rerun, later replaced by the recorded N1. The N5 hypothesis noted in DL-129 is unrecorded and is not reported as a result. The 32 / 17 priority split of lost tasks (DL-108) was not recorded and is not used.
- **Superseded recordings.** The first negative-results run (`796563b`) was superseded, and its outputs that do not depend on the trace were byte-identical to the recorded ones (DL-120). The Phase 3 fault-comparison preview was superseded by the DL-059 fix.
- **Not byte-reproducible.** The PNG figures and the MP4 depend on the plotting and encoder builds, so they are not hashed; each figure lists its source files, and the demo trace carries the recorded configuration hash and utility.
- **Not stored.** Per-run artifacts (event logs, trajectories) are regenerated from their configurations.

**Assessment: met,** with the exceptions above disclosed.

## Criterion 2: limitations disclosed

The report's §8 lists them. In short:

- **Simulation only**, with a modelled hazard: a GEO proxy flux, a centred-dipole cutoff shifted by SYM-H, and synthetic tolerances. There is no shielding, local time or South Atlantic Anomaly.
- **One formation design.** Four spacecraft in one plane, mostly 20 km apart.
- **Small storm samples.** n = 1 – 6 per comparison, and seeds change no outcome.
- **Hypotheses not tested.** H4 and parts of the spec §10.3 ablation set were not run; B1 and B2 were never run on storms.
- **Not measured.** CPU time and memory per algorithm.
- **The B4 ownership defect.** The frozen comparisons report it rather than repair it.
- **Literature.** The literature rows are unverified drafts.

Every results page carries its own Limits section. The Phase 5 pages were reviewed at Gate P5 for labelling the tolerances and the cutoff as models (criterion 2). The Phase 6 pages that involve the hazard use the same model unchanged; `HELDOUT.md` restates its limits, and the report states every hazard assumption in §2 and §8.

**Assessment: met.**

## Criterion 3: novelty claimed only if supported by full-text prior-work comparison and experimental evidence

**No novelty is claimed.**
- **Evidence.** The one candidate contribution, G3 (decentralised protection-mode coordination), showed no supported improvement, either in Phase 5 (DL-100, DL-104) or on the six held-out storms (DL-115).
- **Prior-work comparison.** The comparison is incomplete. The literature rows are assistant drafts from full-text readings that the owner has not verified (carried since DL-049). P21 is paywalled, and Priorities B – D were not reviewed.
- **Wording.** The report, the README and this page say "no novelty is claimed". The report's related-work section marks every source as unverified.

**Assessment: met.**

## What Phase 6 found

1. **The Phase 5 main result holds on six unseen storms.** Neither candidate improves on the baseline: forecast handover changes almost nothing, and shorter protection gains on five storms and ties on the sixth, but with an interval that includes 0 and with extra unprotected hazard on 2 of 6 storms.
2. **Reconciliation is what protects science.** −0.0596 [−0.0915, −0.0276] (B3 + timeout) and −0.0591 [−0.0916, −0.0267] (B4) without it, on every storm.
3. **Protection components prevent hazard, less consistently than Phase 5 suggested:** the forecast on 5 of 6 storms, look-ahead and hysteresis on 3 of 6 each.
4. **B4's hand-on can split ownership** under heavy protection cycling, because it acts on peer views up to one status interval old. A re-sync recovered the loss on the development storms (seed 1, 20 km formation) and was neutral on the two test storms, which had no split loss; in the 2 000 km formation, where two spacecraft share tasks without line of sight, it adds duplicates.
5. **The remaining baseline hazard is at onsets** and falls with data latency (to 0 at 300 s on two of four storms).
6. **The dynamics agree with Basilisk**, given the same models and constants, to 0.22 mm without drag and 8 cm with drag over 8 days. AstraMesh's own modelling choices (ellipsoidal altitude, pole) matter far more than the implementation.

## Not done in Phase 6

- **New methods, retuning, RL, other fleet sizes and low-thrust optimisation:** not planned (DL-111).
- **The re-sync** is not part of any baseline, and its recovery is shown on development storms only.
- **Storm-time density against Basilisk** was not compared (NRLMSIS 2.0 against Basilisk's NRLMSISE-00).
- **N5** (why trailing spacecraft are protected late) is not established. A later, unrecorded investigation is listed in the report as an open hypothesis.

## Carried forward (not blocking)

- **Owner verification** of the literature drafts, and Priorities B – D. *(Update 2026-11-16, after the sign-off, DL-133: the claims AstraMesh relies on and all 20 items' metadata are now owner-verified ([`VERIFICATION.md`](../literature/VERIFICATION.md)); the other analysis cells and Priorities B – D remain.)*
- **Possible B4 fixes:** status on mode change, acknowledged hand-ons, or a re-sync that relays claims (DL-119, DL-124). Each would be a new method needing its own design and held-out test, and no untouched storm remains in the pinned period.
- **Earlier carry-overs:**
  - CBBA has no stop rule; an 8-day B3 + timeout run takes 20 – 96 min.
  - S06 is deferred.
  - CPU time and memory are not measured.
  - Refresh `astropy-iers-data` before 2027-06-28 (DL-021).

## Reproduce (Phase 6)

| Result | Script | Clean commit |
|---|---|---|
| [`HELDOUT.md`](HELDOUT.md) | `scripts/experiments/heldout_comparison.py` | `32e005a` |
| [`BASILISK_COMPARISON.md`](BASILISK_COMPARISON.md) | `scripts/experiments/basilisk_comparison.py` (`cases`, `compare`) and `tools/basilisk/propagate.py` | `21c5db9` |
| [`NEGATIVE_RESULTS.md`](NEGATIVE_RESULTS.md) | `scripts/experiments/negative_results.py` | `f2a1b3a` |
| [`RESYNC_COMPARISON.md`](RESYNC_COMPARISON.md) | `scripts/experiments/resync_comparison.py` | `a94b654` |
| Demo trace | `scripts/experiments/demo_trace.py` | `74273a0` |
| Figures, MP4 | `scripts/figures/make_figures.py`, `scripts/figures/make_demo.py` (`viz` group) | `74273a0` |

Data: `uv run python scripts/data/fetch_data.py` downloads every pinned file (DL-063); the storm series are committed under `configs/data/`.

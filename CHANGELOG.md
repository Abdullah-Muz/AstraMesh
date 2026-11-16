# Changelog

Release versions of the AstraMesh software and results. The specification has its own version history (`ASTRAMESH_MASTER_SPEC.md`, currently v1.0); a software release number is not a specification version.

## v2.0.0 — 2026-11-16

Second release: Phase 6 complete, with Gate P6 signed off on 2026-11-16 (DL-130). Phases 1 – 6 are now complete. This release adds the technical report, a held-out test on storms no method had seen, a Basilisk cross-check, diagnostics for the open Phase 5 results, figures and a demonstration video.

AstraMesh is an independent spacecraft-autonomy research project. Every result about the formation is a **simulation** result with synthetic spacecraft and a modelled radiation hazard driven by **measured** storm data. It is not flight software or a real constellation, and no novelty is claimed.

**Read first:** the technical report, [`docs/REPORT.md`](docs/REPORT.md).

### What is new in this release

- **Technical report** ([`REPORT.md`](docs/REPORT.md)): question and hypotheses, the simulated system, data, methods, every result with its interval, negative results, related work, limitations and reproduction. Hypothesis verdicts: H1 supported, H2 not supported, H3 partly supported, H4 not tested, H5 not supported.
- **Held-out storms** ([`HELDOUT.md`](docs/results/HELDOUT.md)): six storms from June 2024 – January 2026, chosen by a rule fixed before any run; frozen methods, settings and forecasts; 288 runs. New pinned GOES-18 and OMNI data (DS-11, DS-12).
- **Basilisk comparison** ([`BASILISK_COMPARISON.md`](docs/results/BASILISK_COMPARISON.md)): two-body, J2 and drag propagation against Basilisk, in a separate `tools/basilisk/` project.
- **Negative-result diagnostics** ([`NEGATIVE_RESULTS.md`](docs/results/NEGATIVE_RESULTS.md)) and a **B4 ownership re-sync** ([`RESYNC_COMPARISON.md`](docs/results/RESYNC_COMPARISON.md)), tested on two reserved storms.
- **Figures F1 – F9** ([`docs/figures/`](docs/figures/README.md)) and a **52 s demonstration video** of a recorded storm run ([`docs/media/`](docs/media/README.md)).
- **Gate P6 write-up** ([`GATE_P6.md`](docs/results/GATE_P6.md)): every results page with its clean commit, results commit, runs and data, checked by `tests/unit/test_report_links.py`.

### Main results

- **The Phase 5 main result holds on six unseen storms.** Neither candidate improves on the baseline: forecast handover changes almost nothing, and shorter protection gains on five storms and ties on the sixth, but with an interval that includes 0 and with extra unprotected hazard on 2 of 6 storms.
- **Reconciliation is what protects science.** Removing it costs −0.0596 [−0.0915, −0.0276] (B3 + timeout) and −0.0591 [−0.0916, −0.0267] (B4) in retention on the held-out storms, and both intervals exclude zero.
- **Protection components prevent hazard, less consistently than Phase 5 suggested:** the forecast on 5 of 6 storms, look-ahead and hysteresis on 3 of 6 each.
- **B4's hand-on can split ownership** under heavy protection cycling. A re-sync recovered the loss on the development storms (seed 1, 20 km formation) and was neutral on the two test storms, which had no split loss; in the 2 000 km formation it adds duplicates.
- **The remaining baseline hazard is at onsets** and falls with data latency.
- **The dynamics agree with Basilisk**, given the same models and constants, to 0.22 mm without drag and 8 cm with drag over 8 days.

### Reproducibility

Every result page names its script, its clean commit and its run time; every run records the commit, the lockfile hash and its config hash. Data: `uv run python scripts/data/fetch_data.py`. Figures and the video are regenerated from committed results (`viz` group); they are not byte-reproducible. Commands are in the README and in [`GATE_P6.md`](docs/results/GATE_P6.md).

### Known limits

- One formation design (four spacecraft in one plane, mostly 20 km apart), synthetic payload tolerances, and a modelled radiation hazard (GEO proxy flux, dipole cutoff).
- Small storm samples: n = 1 – 6 per comparison, and seeds change no storm outcome.
- H4 not tested; B1 and B2 not run on storms; CPU time and memory not measured.
- The literature rows are unverified drafts. Open questions are listed in [`GATE_P6.md`](docs/results/GATE_P6.md) under "Carried forward".

### Licences

Code: MIT. Documentation: CC BY 4.0. Third-party data keep their own terms ([`DATASET_REGISTRY.md`](docs/DATASET_REGISTRY.md)).

## v1.0.0 — 2026-11-13

First release: Phases 1 – 5 complete, each with its gate signed off (Gate P5 on 2026-11-13, DL-110). The Phase 6 plan (DL-111) is proposed but not started. Improvements and Phase 6 results will be released as later versions.

AstraMesh is an independent spacecraft-autonomy research project. Everything here is **simulated** or **model-based**; it is not flight software or a real constellation, and no novelty is claimed.

### What is in this release

- **Truth dynamics** for a four-spacecraft formation (525 km, 20 km along-track spacing): two-body, J2, atmospheric drag (USSA76 and NRLMSIS 2.0), with physics acceptance tests; rule-based formation keeping against differential drag.
- **Decentralised operations:** isolated spacecraft agents over a modelled crosslink network; baselines B0 (static), B1 (centralised reference), B2 (one-shot auction), B3 (CBBA, with a health timeout) and B4 (rule-based redistribution).
- **Faults and protection:** deterministic fault injection, per-agent health beliefs, and a five-mode local protection supervisor that no planner can override.
- **Real data, pinned by hash:** OPS-SAT-AD telemetry (anomaly benchmark and calibrated health models); OMNI and GOES-18 proton data, January 2023 – May 2024 (proton-flux forecasts P-A / P-B / P-C); OMNI2 hourly drivers for NRLMSIS.
- **Storm scenarios:** per-spacecraft radiation risk from a geomagnetic cutoff model; the May 2024 storm alone and combined with a forecast outage, a network partition or a critical fault; four more storms from 2023 – 2024.

### Main results

- **Phase 5 ([`GATE_P5.md`](docs/results/GATE_P5.md)):** two candidate methods for coordinating protection across the formation were tested against the baseline: forecast-driven task handover and shorter protection. **Neither improves on the baseline** on five storms. Task redistribution between spacecraft is what protects science: without it, 5.3 – 5.5 % of the storm-free science is lost. Each protection component (forecast, look-ahead, hysteresis) costs little science and prevents unprotected hazard. In this close formation most storm losses happen while every spacecraft that could take a task is itself protected.
- **Phase 4 ([`GATE_P4.md`](docs/results/GATE_P4.md)):** the anomaly benchmark reproduces published OPS-SAT results; a detector-aided health model recovers science that a timeout misses; forecasts close most of the reaction gap to storm onsets, at the cost of false protection.
- **Phases 1 – 3:** validated dynamics and geometry, allocation baselines compared under message loss, and nine synthetic fault and hazard scenarios ([`FAULT_COMPARISON.md`](docs/results/FAULT_COMPARISON.md)).

### Reproducibility

Every result page names its script, its clean commit and its run time; every run records the commit, the lockfile hash and its config hash. Phase 5 alone has 729 recorded runs, and every rerun of an earlier configuration matched it exactly. Data: `uv run python scripts/data/fetch_data.py`.

### Known limits

- One formation (four spacecraft, 20 km apart), synthetic payload tolerances, and a modelled radiation hazard (GEO proxy flux, dipole cutoff).
- Seeds change no storm outcome, so the storm comparisons rest on five storms; small gains (up to about 2 % of the science) are not excluded.
- Open questions are listed in [`GATE_P5.md`](docs/results/GATE_P5.md) under "Carried forward".

### Licences

Code: MIT. Documentation: CC BY 4.0. Third-party data keep their own terms ([`DATASET_REGISTRY.md`](docs/DATASET_REGISTRY.md)).

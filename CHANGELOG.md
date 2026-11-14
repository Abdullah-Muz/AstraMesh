# Changelog

Release versions of the AstraMesh software and results. The specification has its own version history (`ASTRAMESH_MASTER_SPEC.md`, currently v1.0); a software release number is not a specification version.

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

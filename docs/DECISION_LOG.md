# Decision Log

> **Owner:** Abdullah Muzher · **Spec:** §12 (authoritative-document rule), §16 · **Last updated:** 2026-11-03

Project-level decisions live in the master specification's Decision Register (§16). This log records implementation decisions and any change that affects scope, safety semantics, hypotheses, or acceptance criteria; such changes must also update the master specification.

| ID | Date | Decision | Status | Rationale / notes |
|---|---|---|---|---|
| DL-001 | 2026-11-03 | Public repository `Abdullah-Muz/AstraMesh` | APPROVED | Spec §16 "confirm availability when created". |
| DL-002 | 2026-11-03 | Licenses: MIT for code, CC BY 4.0 for documentation | APPROVED | See README "License". |
| DL-003 | 2026-11-03 | Python **3.12**, `requires-python >=3.12` | PROVISIONAL | Ubuntu 24.04's system Python; broad scientific-stack support. Re-check against Basilisk and atmospheric-model packages before Phase 4–5. |
| DL-004 | 2026-11-03 | `uv` + `uv_build` backend, `src/` layout, `uv.lock` committed | APPROVED (spec §11) | Reproducible installs; CI uses `uv sync --locked`. |
| DL-005 | 2026-11-03 | Config validation with **pydantic v2** | PROVISIONAL | Spec §11 requires "YAML with schema validation" without naming a library. Pydantic gives strict, unknown-key-rejecting validation and JSON Schema export; it is an addition beyond the §11 Phase 0 list. |
| DL-006 | 2026-11-03 | Simulation time = integer nanoseconds since epoch | APPROVED (implementation) | Eliminates float accumulation drift; exact replay across platforms. |
| DL-007 | 2026-11-03 | Random streams: PCG64 + `SeedSequence` with SHA-256 name keys; per-stream seed overrides | APPROVED (implementation) | Satisfies spec §10.3 separate seeds; stream identity independent of creation order. |
| DL-008 | 2026-11-03 | Added `astramesh.scenarios` package (not in spec §12 layout) | PROVISIONAL | Holds runnable scenario models; currently only the Phase 0 toy scenario. |
| DL-009 | 2026-11-03 | Phase 0 toy scenario `toy_heartbeat` | APPROVED (implementation) | Infrastructure check only; explicitly not a comms or mission model; its counts are not research metrics. |
| DL-010 | 2026-11-03 | Run artifacts named `summary.json` (not `metrics.json`) for the toy scenario | APPROVED (implementation) | Avoids implying research metrics; `metrics.json` reserved for real experiments (spec §10.4). |
| DL-011 | 2026-11-03 | CI on `ubuntu-24.04`, actions pinned to commit SHAs, read-only token | APPROVED (implementation) | Matches target OS; supply-chain hygiene; CI cannot push or create commits. |
| DL-012 | 2026-11-03 | `ruff` + `mypy --strict` + `pytest` + `hypothesis` as required checks | APPROVED (implementation) | Spec §13 Gate P0 "lint/test conventions". |
| DL-013 | 2026-11-03 | Units/time/frames/reference epoch per `docs/CONVENTIONS.md` | PROPOSED | Requires sign-off (Gate P0). |
| DL-014 | 2026-11-03 | Phase 1 physics acceptance tests PA-01…PA-10 per `docs/NUMERICAL_MISSION_DESIGN.md` | PROPOSED | Requires sign-off (Gate P0). |
| DL-015 | 2026-11-03 | Development environment: Windows-native `.venv` in the OneDrive workspace; tests also verified under WSL2 Ubuntu 24.04 with a separate environment | OPEN | Spec §11 names Ubuntu 24.04 WSL2 as the runtime. Moving the repository into the WSL filesystem would match the spec and avoid OneDrive sync interfering with `.git`; decision pending. |

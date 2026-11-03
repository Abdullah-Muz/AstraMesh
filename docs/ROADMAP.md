# Roadmap and Gate Tracking

> **Owner:** Abdullah Muzher · **Status:** ACTIVE · **Spec:** §13, §14, §17 · **Last updated:** 2026-11-03

Phase definitions and exit gates are defined in spec §13; this file tracks status only.

| Phase | Focus | Status |
|---|---|---|
| 0 | Research and reproducibility foundation | **In progress** |
| 1 | Validated four-spacecraft dynamics and mission geometry | Not started |
| 2 | Decentralized nominal science operations | Not started |
| 3 | Deterministic faults and protection supervisor | Not started |
| 4 | External data and probabilistic/ML experiments | Not started |
| 5 | Storm-aware distributed recovery | Not started |
| 6 | Research conclusion and public demonstration | Not started |

## Phase 0 deliverables (spec §17)

| # | Deliverable | Status |
|---|---|---|
| 1 | Repository and `astramesh` package | Done |
| 2 | `uv`, pinned Python, pytest, Hypothesis, minimal CPU dependency set | Done |
| 3 | Master spec + linked docs with owners/requirements | Done (this `docs/` set) |
| 4 | Validated scenario-config schema; units/time/frame conventions | Schema done; conventions **proposed**, awaiting sign-off |
| 5 | Deterministic clocks, random seeds, event logging, result manifests | Done |
| 6 | Tiny deterministic scenario proving same-seed replay; basic CI | Done locally (Windows + WSL2); CI runs on first push |
| 7 | First literature-matrix entries; initial physics-test design | Priority A metadata entered; physics test plan **drafted**, awaiting sign-off |
| 8 | License/terms documentation for external data; no large downloads | Registry started; 2 of 7 licenses checked; nothing downloaded |

## Gate P0 checklist (spec §13)

- [x] Clean environment setup (`uv sync --locked`)
- [ ] Unit-test runner **and CI** passing — local: yes; CI: pending first push
- [x] Repeatable toy experiment (byte-identical replay, golden hash)
- [ ] First priority references **reviewed** — metadata only so far; full-text review not started
- [ ] Exact simulation epoch/frames/units specified — proposed in `CONVENTIONS.md`, awaiting sign-off
- [ ] Physics acceptance plan signed off — drafted in `NUMERICAL_MISSION_DESIGN.md`, awaiting sign-off

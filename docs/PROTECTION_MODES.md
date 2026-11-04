# Protection Modes and Safety Supervisor

> **Owner:** Abdullah Muzher · **Status:** IN PROGRESS — NOMINAL / PROTECTIVE / SAFE implemented (Phase 3 increment 3); STORM_WATCH and RECOVERY in increment 4 · **Spec:** §6, §14.1 · **Target phase:** 3 · **Last updated:** 2026-11-04

## Purpose

Specify the five-mode local supervisor (`NOMINAL`, `STORM_WATCH`, `PROTECTIVE`, `RECOVERY`, `SAFE`): guards, hysteresis, dwell times, stale/missing-input policy, side effects, and the tests in spec §6.4.

## Requirements to satisfy (from spec)

- SAFE overrides from any mode on a critical local fault; never auto-clears on improved forecasts (§6.2).
- Mission planning cannot override SAFE/PROTECTIVE (§6.1, §14.1 hard stop).
- Three separate environmental risk dimensions; no averaging into one score (§6.3).
- Thresholds derive from modeled subsystem tolerances; the illustrative values 0.35/0.70/0.25 are **not** defaults (§6.2).
- Invalid forecast values must never silently become zero risk (§6.2).

## Content

### Implemented (Phase 3 increment 3, DL-054, DL-055): `agents/supervisor.py`

The supervisor runs inside each agent, at the start of every `payload_command`. The science payload may run only in NOMINAL. Plans, catalogues and messages cannot change the mode; only the agent's own housekeeping and forecast can.

| From → To | Guard (PROVISIONAL values) | Effect |
|---|---|---|
| any → SAFE | own battery ≤ 10% of capacity, or any critical flag in own housekeeping (checked first) | payload off; a running observation stops; CBBA claims released |
| SAFE → NOMINAL | no critical flag **and** battery ≥ 50%, held 10 min; a better forecast never clears SAFE | science may resume |
| NOMINAL → PROTECTIVE | valid forecast exposure ratio ≥ 1.0 (exposure ÷ modelled payload tolerance) | payload suspended; nav, comms and health continue; claims released |
| PROTECTIVE → NOMINAL | valid ratio < 0.8, held 30 min (hysteresis + dwell) | science may resume |
| invalid forecast | hold the current mode; restart the release dwell; logged once per episode (never zero risk) | — |

Mode goes in every status message. B4 and CBBA treat a non-NOMINAL peer as unavailable for new tasks, which is separate from its health belief.

**Tests:**
- override from every mode and SAFE-exit conditions;
- hysteresis and dwell, including restarts after spikes and invalid data;
- no chatter under 2 h of jitter;
- property tests: SAFE always wins, and the payload runs only in NOMINAL;
- arbitrary messages and plan uplinks cannot reactivate a protected payload;
- scenario truth check: payload steps outside NOMINAL = 0.

### Still to do (increment 4)

STORM_WATCH and RECOVERY, three separate risk dimensions, a full invalid-input policy, and the SAFE → RECOVERY path.

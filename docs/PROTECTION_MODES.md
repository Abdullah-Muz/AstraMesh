# Protection Modes and Safety Supervisor

> **Owner:** Abdullah Muzher · **Status:** IMPLEMENTED — five-mode machine (Phase 3 increments 3–4) · **Spec:** §6, §14.1 · **Target phase:** 3 · **Last updated:** 2026-11-04

## Purpose

Specify the five-mode local supervisor (`NOMINAL`, `STORM_WATCH`, `PROTECTIVE`, `RECOVERY`, `SAFE`): guards, hysteresis, dwell times, stale/missing-input policy, side effects, and the tests in spec §6.4.

## Requirements to satisfy (from spec)

- SAFE overrides from any mode on a critical local fault; never auto-clears on improved forecasts (§6.2).
- Mission planning cannot override SAFE/PROTECTIVE (§6.1, §14.1 hard stop).
- Three separate environmental risk dimensions; no averaging into one score (§6.3).
- Thresholds derive from modeled subsystem tolerances; the illustrative values 0.35/0.70/0.25 are **not** defaults (§6.2).
- Invalid forecast values must never silently become zero risk (§6.2).

## Content

### Implemented: five-mode machine (`agents/supervisor.py`; DL-054–DL-057)

The supervisor runs inside each agent, at the start of every `payload_command`. Science may run only in **NOMINAL** and **STORM_WATCH**. Plans, catalogues and messages cannot change the mode; only the agent's own housekeeping and risk forecast can.

**Inputs:**
- own battery and critical flags;
- three separate risk ratios, never averaged: radiation/electronics, navigation/communications, orbital disturbance. Each is the predicted risk divided by that subsystem's modelled tolerance, and `null` means invalid;
- recovery checks from the agent's own state.

| From → To | Guard (PROVISIONAL defaults) |
|---|---|
| any → SAFE | battery ≤ 10% or any critical flag (checked first) |
| SAFE → RECOVERY | no flag and battery ≥ 50%, held 10 min; never on forecast improvement |
| NOMINAL → STORM_WATCH | any valid risk ≥ 0.6, or invalid forecast for more than 10 min |
| STORM_WATCH → PROTECTIVE | valid **radiation** ≥ 1.0 (only radiation has a modelled vulnerable function) |
| STORM_WATCH → NOMINAL | all risks valid and < 0.5, held 30 min |
| PROTECTIVE → RECOVERY | valid radiation < 0.8, held 30 min |
| RECOVERY → PROTECTIVE | valid radiation ≥ 1.0 |
| RECOVERY → NOMINAL | ≥ 5 min in RECOVERY and checks pass: battery ≥ 20% reserve, navigation fix < 60 s old, a peer heard < 90 s ago (if any is believed up) |

**Invalid inputs:** never release a protected mode (the dwell restarts), never trigger PROTECTIVE alone, and are logged once per episode.

**Side effects:**
- STORM_WATCH sends status every 10 s; science continues.
- PROTECTIVE, RECOVERY and SAFE keep the payload off and release CBBA claims. Peers, told by the `mode` field in status messages, treat the spacecraft as unavailable for new tasks.

**Tests:**
- every guard;
- property tests: SAFE always wins; SAFE and PROTECTIVE exit only via RECOVERY; PROTECTIVE is never entered straight from NOMINAL; the payload runs only in science modes;
- no chatter under 3 h of jitter;
- arbitrary messages and plan uplinks cannot reactivate a protected payload;
- scenario truth check `payload_steps_in_protected_modes` = 0.

### Not modelled yet

- Effects of the navigation/comms and orbital risks on links and drag (Phase 5).
- Real space-weather inputs (Phase 4).

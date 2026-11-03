# Protection Modes and Safety Supervisor

> **Owner:** Abdullah Muzher · **Status:** NOT STARTED — placeholder · **Spec:** §6, §14.1 · **Target phase:** 3 · **Last updated:** 2026-11-03

## Purpose

Specify the five-mode local supervisor (`NOMINAL`, `STORM_WATCH`, `PROTECTIVE`, `RECOVERY`, `SAFE`): guards, hysteresis, dwell times, stale/missing-input policy, side effects, and the tests in spec §6.4.

## Requirements to satisfy (from spec)

- SAFE overrides from any mode on a critical local fault; never auto-clears on improved forecasts (§6.2).
- Mission planning cannot override SAFE/PROTECTIVE (§6.1, §14.1 hard stop).
- Three separate environmental risk dimensions; no averaging into one score (§6.3).
- Thresholds derive from modeled subsystem tolerances; the illustrative values 0.35/0.70/0.25 are **not** defaults (§6.2).
- Invalid forecast values must never silently become zero risk (§6.2).

## Content

Not yet written.

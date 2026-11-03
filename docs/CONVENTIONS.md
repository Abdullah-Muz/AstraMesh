# Units, Time, Frames, and Software Conventions

> **Owner:** Abdullah Muzher · **Status:** APPROVED (signed off 2026-11-03) · **Spec:** §3.2, §4.4, §10.3, §10.4, §13 (Gate P0) · **Last updated:** 2026-11-03

Gate P0 requires the "exact simulation epoch/frames/units" to be specified. This document specifies them. Items marked **IMPLEMENTED** already exist in code; items marked **APPROVED** were signed off on 2026-11-03 and are implemented in Phase 1. Changes require a new [DECISION_LOG.md](DECISION_LOG.md) entry.

---

## 1. Units — APPROVED (naming rule IMPLEMENTED)

- **Internal computation uses SI base/derived units only:** metres, seconds, kilograms, radians, watts, joules, newtons, metres per second.
- **Angles** are radians internally. Degrees are allowed only at input/output boundaries (configs, plots, reports).
- **Energy budgets** may be reported in watt-hours at I/O boundaries (spec §3.3 uses Wh); internal accounting uses joules.
- **Every configuration field that has a physical unit carries the unit as a name suffix** (IMPLEMENTED for time fields):

  | Suffix | Unit | Example |
  |---|---|---|
  | `_s` | seconds | `time_step_s` |
  | `_ns` | nanoseconds (integer) | `time_ns` |
  | `_m`, `_km` | metres, kilometres | `separation_km` |
  | `_mps` | metres per second | `delta_v_budget_mps` |
  | `_kg` | kilograms | `mass_kg` |
  | `_w`, `_wh`, `_j` | watts, watt-hours, joules | `science_load_w` |
  | `_n`, `_mn` | newtons, millinewtons | `max_thrust_mn` |
  | `_rad`, `_deg` | radians, degrees | `inclination_deg` |
  | `_mb`, `_gb` | megabytes, gigabytes | `storage_gb` |
  | `_probability` | dimensionless in [0, 1] | `packet_loss_probability` |

- Unit conversion happens exactly once, when a config is turned into an internal model object.

## 2. Time

### 2.1 Simulation clock — IMPLEMENTED (`astramesh.core.clock`)

- Simulation time is an **integer number of nanoseconds elapsed since the scenario epoch** (`t_ns`). Time point *k* is exactly `k × step_ns`; no floating-point accumulation.
- Durations and steps given in seconds must be exact multiples of 1 ns; the scenario duration must be an integer multiple of the step.
- Elapsed time is measured in **SI seconds** (a uniform time scale).
- The epoch is given as ISO 8601 UTC with an explicit `Z` (or `+00:00`) designator. Naive or non-UTC timestamps are rejected.
- `t_s` in outputs is derived from `t_ns` for readability; `t_ns` is authoritative.

### 2.2 Calendar conversion — APPROVED; IMPLEMENTED (`astramesh.dynamics.timescales`, Phase 1 increment 2)

- Converting `epoch + elapsed SI seconds` to a UTC calendar time requires a leap-second table. Phase 0 code intentionally provides **no** such conversion.
- Phase 1 will use **Astropy `Time`** for all time-scale conversions (UTC ↔ TAI ↔ TT ↔ UT1). The scenario epoch is interpreted as UTC and converted to TT for dynamics; Earth-rotation conversions use UT1 with Astropy's IERS data, whose version must be recorded in the run manifest.
- *Implementation notes:*
  - `scenario_time(epoch_utc, t_ns)` adds elapsed SI seconds to the UTC epoch through TAI, so leap seconds are handled; this is tested across 2016-12-31T23:59:60Z.
  - Earth-orientation and leap-second data come only from the locked `astropy-iers-data` and `pyerfa` packages; downloads are disabled.
  - The manifest's `software.packages` records `astropy-iers-data`; its version is the IERS data version.
  - Beyond the end of its bundled table, Astropy silently reuses the last UT1−UTC value. To prevent that, `require_eop_coverage` raises for any time outside the table. IERS-A *predictions* are accepted (DL-020).

### 2.3 Reference epoch — APPROVED

- **Phase 1 nominal reference epoch: `2025-06-01T00:00:00Z`.**
  - Inside the 2025+ operational period of NOAA GloTEC (spec §4.3, §8.1), so later scenarios can use it without changing the epoch.
  - Leap seconds can only be inserted at the end of June or December, so no leap-second boundary can fall within a 24 h scenario starting at this epoch.
- Historical replays (e.g. the May 10–13 2024 storm, scenario S11) use their own epochs, set in their scenario configs.

## 3. Reference frames — APPROVED (Phase 1)

| Role | Frame | Notes |
|---|---|---|
| Inertial (ECI) | **GCRS** as implemented by Astropy | Used for propagation. Differs from J2000/EME2000 by a small frame bias (tens of milliarcseconds); not interchangeable without explicit conversion. |
| Earth-fixed | **ITRS** as implemented by Astropy | Used for ground tracks and observation geometry. |
| Local orbital | **RIC** (radial, in-track, cross-track) | **R** = r / ‖r‖; **C** = (r × v) / ‖r × v‖; **I** = C × R. Right-handed. For a circular orbit, I is aligned with the velocity. Computed from the ECI state of the reference (chief) spacecraft. |

- Every state vector carries its frame and epoch explicitly; functions do not take "bare" position arrays without a frame.
- Frame transformations must pass round-trip tests (spec §4.4) before use.
- Attitude representation (quaternion convention) is deferred until attitude dynamics are in scope (D4).

## 4. Randomness — IMPLEMENTED (`astramesh.core.rng`)

- Five named streams: `tasks`, `comms`, `sensors`, `faults`, `algorithm` (spec §10.3).
- Each stream is a NumPy `PCG64` generator seeded from `SeedSequence(entropy=<stream seed>, spawn_key=(<SHA-256-derived key of the stream name>,))`.
- One root `seed` applies to every stream; `stream_seeds` overrides individual streams so a single factor (e.g. the fault schedule) can be varied while the others stay fixed.
- Consuming one stream never shifts another.
- Python's built-in `hash()`, the `random` module, and NumPy's global RNG are **not** used for simulation randomness.

## 5. Event log and run artifacts — IMPLEMENTED

- Event logs are canonical JSON Lines: sorted keys, compact separators, ASCII, no NaN/Infinity, LF line endings. Same config + same seeds ⇒ byte-identical `events.jsonl`.
- Events carry simulation time only, never wall-clock time.
- Each run directory contains `events.jsonl`, `summary.json`, `config.resolved.json`, and `manifest.json` (see [EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md)).
- `config_hash` is the SHA-256 of the validated configuration in canonical JSON form. It ignores YAML formatting, comments, and key order, but changes whenever an effective value changes.

## 6. Software conventions — IMPLEMENTED

- Python 3.12 (pinned in `.python-version`), dependencies locked in `uv.lock`.
- `ruff` (lint + format), `mypy --strict`, `pytest` + `hypothesis` must pass locally and in CI.
- Configuration schemas reject unknown keys.
- Files are committed with LF line endings (`.gitattributes`).

---

## Sign-off

| Item | Decision | Date |
|---|---|---|
| Units (§1) | ☑ approved — Abdullah Muzher | 2026-11-03 |
| Time scale and calendar handling (§2.2) | ☑ approved — Abdullah Muzher | 2026-11-03 |
| Reference epoch `2025-06-01T00:00:00Z` (§2.3) | ☑ approved — Abdullah Muzher | 2026-11-03 |
| Frames GCRS / ITRS / RIC (§3) | ☑ approved — Abdullah Muzher | 2026-11-03 |

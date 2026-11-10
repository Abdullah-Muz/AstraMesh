# Experiment Protocol

> **Owner:** Abdullah Muzher · **Status:** ACTIVE — run artifacts implemented; statistical design written 2026-11-09 (§3, DL-072) · **Spec:** §10 · **Last updated:** 2026-11-09

## 1. Run artifacts — IMPLEMENTED (Phase 0)

```bash
uv run astramesh validate configs/experiments/<scenario>.yaml
uv run astramesh run configs/experiments/<scenario>.yaml --out results/<run_dir>
```

Each run directory contains:

| File | Deterministic? | Content |
|---|---|---|
| `events.jsonl` | Yes | Canonical event log (simulation time only) |
| `summary.json` | Yes | Scenario bookkeeping counts |
| `config.resolved.json` | Yes | The validated configuration, canonical JSON |
| `trajectory.csv` | Yes | `formation_dynamics` and `mission_geometry`: GCRS states (m, m/s) sampled every `output.trajectory_sample_interval_s`; floats as shortest round-trip repr |
| `messages.jsonl` | Yes | `agent_network` only: one line per message send (sender, seq, type, bytes, lost/unreachable peers) and per delivery (receiver, accepted or rejection reason) |
| `plan.json` | Yes | `nominal_operations` only: the allocation's assignments (task, spacecraft, slot) and unassigned tasks, with a privileged-information flag |
| `observations.json` | Yes | `nominal_operations` only: every executed observation segment with its truth outcome (completed, duplicate, invalid, aborted_power, aborted_storage) |
| `opportunities.json` | Yes | `mission_geometry` only: science task records (spec §3.4 fields), each with the eligible spacecraft and their access windows (tick-exact), peak elevation, sunlit ticks, and payload energy (Wh) and data (MB) costs. Eligibility is geometry only (DL-033); costs follow DL-035 |
| `manifest.json` | No (contains wall-clock `run_timestamp_utc`) | Provenance record listing the SHA-256 of the deterministic files above |

`manifest.json` fields: `experiment_id`, `scenario_id`, `run_timestamp_utc`, `git_commit`, `git_dirty`, `config_hash`, `seed`, `stream_seeds`, `dynamics_model`, `science_data_version`, `telemetry_data_version`, `algorithm`, `software_lockfile_hash`, `software` (Python, platform, package versions — `astropy-iers-data` is the Earth-orientation/IERS data version), `artifacts`.

**Rule:** a result may be reported only if its manifest has `git_dirty: false` (run from a committed tree) and every data version it depends on is recorded. `results/` is Git-ignored; archive reported runs separately (to be decided, spec §11 mentions DVC/MLflow as later options).

Multi-run experiments live in `scripts/experiments/`. Their recorded outputs (CSV, summary, metadata with commit, dirty flag, lockfile and config hashes) are committed under `docs/results/` only when produced from a clean commit. The first is the S00 loss comparison ([`results/S00_LOSS_COMPARISON.md`](results/S00_LOSS_COMPARISON.md), DL-047/048).

Diagnostic figures: `uv run astramesh plot <run_dir>` writes PNGs to `<run_dir>/figures/`. These are **not** run artifacts and are not hashed in the manifest, because PNG encoding is not byte-reproducible.

## 2. Replay verification — IMPLEMENTED

- `tests/integration/test_toy_replay.py`: same config + seeds ⇒ byte-identical deterministic artifacts; different seed ⇒ different events.
- `tests/regression/test_toy_golden.py`: pinned SHA-256 of the toy event log, checked on Windows, WSL2/Ubuntu 24.04, and CI. The toy config hash is also pinned, so schema refactors cannot silently change it.
- `tests/integration/test_formation_run.py`: the formation scenario replays byte-identically, and the manifest lists every artifact.
- `tests/regression/test_formation_baseline.py`: pinned SHA-256 digests of the 24 h J2 baseline's events and trajectory. These are guaranteed only on the reference platform (Ubuntu 24.04 x86_64), because initialization uses libm and ERFA (DL-029). Scenario code avoids BLAS, so the digests do not depend on the CPU model (DL-031). The propagator-only digests in `test_two_body_determinism.py` are platform-independent.
- `tests/regression/test_agent_network_baseline.py`: pinned digests of the 24 h agent-network baseline's events, message trace and summary (comms and sensors streams, seed 1). Same scope (DL-029, DL-034).
- `tests/regression/test_fault_baselines.py`: pinned digests of fault scenario S01 with B3 (no health awareness: utility 34/144) and with B4 (detects in 280 s, redistributes: 144/144).
- `tests/regression/test_nominal_ops_baseline.py`: pinned digests of the 24 h S00 nominal-operations baselines with B0, B1, B2 and B3 (events, plan, observations, summary, messages). B0's and B1's message traces must equal the agent-network baseline's; B2's and B3's executed observations must equal B1's.
- `tests/regression/test_mission_geometry_baseline.py`: pinned digests of the 24 h mission-geometry baseline's events, `opportunities.json` and `summary.json` (resource accounting); its trajectory must equal the formation baseline's. The same scope applies (DL-029, DL-034).

## 3. Scenarios, metrics, statistical design — WRITTEN 2026-11-09 (DL-072)

**Written late.** Spec §10.3 asks for this section before any comparative experiment. It was not written then. Instead, each comparison fixed its design in its own decision entry before it was run: S00 (DL-047), faults (DL-058), OPS-SAT-AD (DL-064), health (DL-066), forecasts and S11 (DL-068, DL-069). This section records the rules those entries followed, so they can be checked in one place. It binds every later experiment.

### 3.1 Scenarios

- **Reference scenarios** are those of spec §10.1. S00 is the 24 h nominal base configuration (`configs/experiments/nominal_ops_*`). Fault scenarios live in `configs/experiments/faults/` or are built by the comparison scripts from the S00 base. S11 is the 8–15 May 2024 storm week (DL-069). S06 is deferred (DL-061).
- **Frozen:** each result's meta file records the config hash of every run. Changing a reference scenario after a result has been recorded needs a decision entry, and the affected results must be re-run.
- **Real-data test sets:** the OPS-SAT-AD official test split and per-channel time split (DL-064), and the May 2024 storm week (DL-068). Each is used once, after every setting is fixed. No setting is chosen by looking at a test result.

### 3.2 Pairing and random streams

- **Five independent streams:** `tasks`, `comms`, `sensors`, `faults` and `algorithm` (`astramesh.core.rng`). Each is seeded from the run seed and the stream name, so adding a stream or changing the order of use leaves the others unchanged.
- **Paired runs:** within one comparison, every method runs on the same configuration and the same seeds, and only the method under test differs. It sees the same tasks, faults and message-loss draws.
- **Seeds:** simulation comparisons use seeds 1–10. Stochastic real-data methods use seeds 0–4 (OPS-SAT-AD).

### 3.3 Sample counts and intervals

Every table states its *n*. All intervals are at 95 %.

| Kind of result | Interval |
|---|---|
| Simulation comparison, n = 10 seeds | Student-t interval of the mean (n − 1 degrees of freedom). Not clipped to the possible range. A single number means every seed agreed. |
| Simulation runs that are deterministic apart from a stream that turns out not to matter (S11) | No interval; one value, and that is stated. The uncertainty is described through sensitivity variants instead. |
| Real-data benchmark with one fixed test set (OPS-SAT-AD) | Mean ± sd over seeds for stochastic methods. No interval over the test set (a limitation, carried forward). |
| Forecast skill on time series (pinball, coverage, POD, false-alarm ratio) | Paired percentile bootstrap over UTC days, 2 000 resamples, fixed seed (`astramesh.forecast.uncertainty`). Differences between models are resampled on the same days. |
| Counts of rare events (onsets warned) | Clopper-Pearson exact interval for the fraction. |

- **Comparing methods:** where the runs are paired, the difference is the quantity of interest. Overlapping marginal intervals are not read as "no difference" without a paired check.
- **Small samples are named as such:** for example, 4 storm-week onsets, or one storm.

### 3.4 Metrics

- **Primary** (spec §10.2): raw science utility and retention relative to the healthy reference.
- **Safety, in parallel:** a higher utility that breaks a safety invariant is never reported as better.
  - Since Phase 3, every comparison checks two invariants in every run: no payload steps in protected modes, and no confirmed-failed belief about a spacecraft that is available.
  - Separation and collision constraints are added when maneuvers exist (Phase 5).
- **Secondary**, per experiment, as defined in its decision entry: duplicates, invalid observations, detection latency, messages and bytes, protected time inside and outside the hazard, exposure, and calibration (ECE, Brier, coverage).
- **Truth metrics** use simulation or measured truth. They are never visible to the agents.

### 3.5 Freezing, tuning and leakage

- Model and method settings are fixed in a decision entry before the evaluation. Settings are not searched on test data.
- Time-series data are split in time order. Training rows must have their whole target window before the test block starts (forward chaining).
- A gap between a random split and a time-ordered split is reported as a possible leakage effect (DL-062).

### 3.6 Reporting

- Results are recorded only from a clean commit (`git_dirty: false`). The meta file records the commit, lockfile hash, config hashes and data versions.
- **Negative results are reported:** for example, methods below the flag-everything F1, P-C's failure beyond its training range, and B3's tie-breaking loss on S03.
- Computational failures and solver timeouts are recorded explicitly.
- Corrections to recorded results get a new decision entry and a re-run (DL-059, DL-070), not a silent edit.
- Previews from a dirty tree may be quoted in a decision entry, labelled as previews.

### 3.7 Ablations

Spec §10.3 asks for ablations of components "when those components exist".

- **Done in Phase 4:**
  - The health comparison H-A / H-B / H-C ablates health uncertainty and the detector.
  - The forecast comparison P-A / P-B / P-C ablates forecasting.
- **Later phases:**
  - Ablations of protective hysteresis, plan reconciliation and maneuver feasibility belong to Phases 5–6, where those components are combined.
  - Fleet size stays at 4 (spec §10.3).

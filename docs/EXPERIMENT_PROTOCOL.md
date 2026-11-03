# Experiment Protocol

> **Owner:** Abdullah Muzher · **Status:** PARTIAL — run artifacts implemented; statistical protocol not started · **Spec:** §10 · **Last updated:** 2026-11-03

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
| `opportunities.json` | Yes | `mission_geometry` only: science task records (spec §3.4 fields), each with the eligible spacecraft and their access windows (tick-exact), peak elevation, sunlit ticks, and payload energy (Wh) and data (MB) costs. Eligibility is geometry only (DL-033); costs follow DL-035 |
| `manifest.json` | No (contains wall-clock `run_timestamp_utc`) | Provenance record listing the SHA-256 of the deterministic files above |

`manifest.json` fields: `experiment_id`, `scenario_id`, `run_timestamp_utc`, `git_commit`, `git_dirty`, `config_hash`, `seed`, `stream_seeds`, `dynamics_model`, `science_data_version`, `telemetry_data_version`, `algorithm`, `software_lockfile_hash`, `software` (Python, platform, package versions — `astropy-iers-data` is the Earth-orientation/IERS data version), `artifacts`.

**Rule:** a result may be reported only if its manifest has `git_dirty: false` (run from a committed tree) and every data version it depends on is recorded. `results/` is Git-ignored; archive reported runs separately (to be decided, spec §11 mentions DVC/MLflow as later options).

Diagnostic figures: `uv run astramesh plot <run_dir>` writes PNGs to `<run_dir>/figures/`. These are **not** run artifacts and are not hashed in the manifest, because PNG encoding is not byte-reproducible.

## 2. Replay verification — IMPLEMENTED

- `tests/integration/test_toy_replay.py`: same config + seeds ⇒ byte-identical deterministic artifacts; different seed ⇒ different events.
- `tests/regression/test_toy_golden.py`: pinned SHA-256 of the toy event log, checked on Windows, WSL2/Ubuntu 24.04, and CI. The toy config hash is also pinned, so schema refactors cannot silently change it.
- `tests/integration/test_formation_run.py`: the formation scenario replays byte-identically, and the manifest lists every artifact.
- `tests/regression/test_formation_baseline.py`: pinned SHA-256 digests of the 24 h J2 baseline's events and trajectory. These are guaranteed only on the reference platform (Ubuntu 24.04 x86_64), because initialization uses libm and ERFA (DL-029). Scenario code avoids BLAS, so the digests do not depend on the CPU model (DL-031). The propagator-only digests in `test_two_body_determinism.py` are platform-independent.
- `tests/regression/test_agent_network_baseline.py`: pinned digests of the 24 h agent-network baseline's events, message trace and summary (comms and sensors streams, seed 1). Same scope (DL-029, DL-034).
- `tests/regression/test_mission_geometry_baseline.py`: pinned digests of the 24 h mission-geometry baseline's events, `opportunities.json` and `summary.json` (resource accounting); its trajectory must equal the formation baseline's. The same scope applies (DL-029, DL-034).

## 3. Scenarios, metrics, statistical design — NOT STARTED

To be written before any comparative experiment (spec §10.1–§10.3), including: frozen reference scenarios S00–S11, paired-run design, per-stream seeds, sample counts, confidence intervals, ablations, and rules for reporting negative results and solver failures.

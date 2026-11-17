# Compute cost per baseline

> **Status:** recorded 2026-11-16 from clean commit `b7c97d8` (`git_dirty: false`; 50 runs, 38 min elapsed on 4 workers). Maintenance after v2.0.1 (DL-134 (B) design, DL-135 code, DL-138 results). Every run reruns a recorded configuration unchanged and was checked against it (below). **Measured on one shared laptop, in Python: not flight or onboard-processor results.** The simulated scenarios are those of the recorded results pages; only the CPU time and memory are new.

## Setup

- **Why:** spec §10.2 lists algorithm CPU time and peak memory as additional metrics. Phases 2 – 6 did not measure them (carried since DL-110).
- **Configurations** (seed 1), each built by the script that recorded it:
  - **S00 at 1 % loss** (the base 24 h scenario) under B0, B1, B2, B3, B3 + timeout and B4 (`fault_comparison.py`; [`FAULT_COMPARISON.md`](FAULT_COMPARISON.md)).
  - **S01** (one spacecraft permanently unavailable) and **S10** (radiation risk plus a critical fault) under B3 + timeout and B4 (same source).
  - **S00 at 30 % loss** under all six (`s00_loss_comparison.py`; [`S00_LOSS_COMPARISON.md`](S00_LOSS_COMPARISON.md)).
  - **May 2024 storm:** S11-H, forecast P-B, baseline arm, 8 days, under B3 + timeout and B4 (`handover_comparison.py`; [`HANDOVER_COMPARISON.md`](HANDOVER_COMPARISON.md)).
  - Three repeats of every 24 h run (medians reported), one of each 8-day run: 3 × 16 + 2 = 50 runs.
- **Onboard CPU** (`time.process_time_ns`, per agent and per call) at the four entry points the simulator calls on a spacecraft agent: `receive_messages` (one delivery), `step` (planner rounds, health beliefs, status), `payload_command` (the supervisor, and any re-planning a mode change triggers) and `observe` (sensor, forecast and ground packets, including B4's redistribution after a ground notice). Only the outermost call is timed; no entry point calls another. **Ground planning** (the B0 / B4 static plan, B1's centralised plan) is timed separately. **Run CPU** is the whole simulation.
- **Memory:** each run is a fresh worker process (`max_tasks_per_child=1`, spawn). `ru_maxrss` is read after the imports and the config and after the run. It is whole-process memory, simulator included.
- **Reproduce:** `uv run --locked python scripts/experiments/compute_cost.py --out <dir>`. Files: [`compute_cost.csv`](compute_cost.csv) (one row per run), [`compute_cost_summary.csv`](compute_cost_summary.csv) (median, minimum and maximum over repeats) and [`compute_cost_meta.json`](compute_cost_meta.json) (commit, dirty flag, lockfile hash, platform, settings, config hashes).

## Behaviour check: the timing changed nothing

- Every run's utility, completions, messages sent and bytes sent equal the recorded run's, and the config hash too for the 1 % S00, S01, S10 and storm runs (`fault_comparison.csv`, `handover_runs.csv`).
- **S00 at 30 % loss** was recorded in Phase 2, before the fields were renamed (DL-067), so its config hashes are not compared. Phase 3 added `,"health":"HEALTHY","mode":"NOMINAL"` (36 bytes) to every status message (DL-052, DL-055), so its bytes are checked against the recorded value plus 36 × 11 524 status messages = 414 864 bytes. B3 + timeout and B4 at 30 % loss were never recorded; their three repeats agree with each other.
- The first run (from `181d46b`) stopped on this check before that adjustment existed; nothing from it is used (DL-135).

## Measurement conditions

- **Machine:** AMD Ryzen 7 250, 16 logical CPUs, Linux under WSL2, Python 3.12.3; 4 workers in parallel.
- **Shared machine.** Other heavy processes ran throughout (load average 12 – 16 on 16 logical CPUs when sampled during the run and the calibration; not logged). Process CPU time excludes waiting but not slower execution under contention, so the repeats spread widely (table below).
- **Timer overhead.** On WSL2 each read of the process CPU clock is a system call. A calibration on the same machine after the run (`n` = 300 000 calls × 7 batches) gave 3.2 µs per timed call recorded inside the measured interval and 6.2 µs added to run CPU. Both raw and corrected values are given; the correction is an estimate.

## Results (raw)

**S00 at 1 % loss, 24 h, median of three repeats** (CPU in s; onboard ms per simulated hour per spacecraft; RSS in MB):

| Planner | Run CPU | Onboard CPU (share) | Onboard ms / sim-h / sc | `receive_messages` | `step` | `payload_command` | `observe` | Ground plan | Peak RSS (growth) |
|---|---|---|---|---|---|---|---|---|---|
| B0 static | 34.9 | 3.43 (11 %) | 35.7 | 0.788 | 1.15 | 0.932 | 0.555 | 0.00100 | 234 (92) |
| B1 centralised (ground reference) | 36.1 | 3.44 (11 %) | 35.8 | 0.810 | 1.20 | 0.900 | 0.553 | 1.14 | 234 (92) |
| B2 auction | 35.9 | 4.30 (12 %) | 44.8 | 1.14 | 1.45 | 1.12 | 0.596 | – | 234 (92) |
| B3 CBBA | 104 | 31.5 (33 %) | 328 | 20.2 | 9.52 | 1.19 | 0.655 | – | 257 (114) |
| B3 + timeout | 106 | 33.4 (32 %) | 348 | 21.4 | 10.1 | 1.25 | 0.672 | – | 258 (115) |
| B4 rule-based | 38.9 | 3.50 (10 %) | 36.4 | 0.799 | 1.22 | 0.961 | 0.518 | 0.00100 | 234 (92) |

**Largest single call (ms), S00 at 1 % loss, maximum over repeats:**

| Planner | `receive_messages` | `step` | `payload_command` | `observe` |
|---|---|---|---|---|
| B0 static | 12.4 | 12.3 | 26.9 | 12.2 |
| B1 centralised (ground reference) | 12.4 | 12.5 | 15.0 | 11.8 |
| B2 auction | 103 | 12.8 | 28.2 | 12.4 |
| B3 CBBA | 20.1 | 16.5 | 12.3 | 12.3 |
| B3 + timeout | 22.3 | 15.2 | 12.6 | 12.0 |
| B4 rule-based | 22.3 | 15.1 | 13.2 | 12.1 |

**Other cases** (medians for 24 h cases; one run for the storm):

| Case | Planner | Run CPU (s) | Onboard CPU (s, share) | Onboard ms / sim-h / sc | Largest call (ms, kind) | Peak RSS (MB) |
|---|---|---|---|---|---|---|
| S00 30 % loss | B0 static | 31.8 | 3.37 (11 %) | 35.1 | 21.6 (`receive_messages`) | 234 |
| S00 30 % loss | B1 centralised (ground reference) | 31.0 | 3.41 (11 %) | 35.5 | 12.8 (`step`) | 234 |
| S00 30 % loss | B2 auction | 29.8 | 3.35 (11 %) | 34.8 | 12.7 (`payload_command`) | 234 |
| S00 30 % loss | B3 CBBA | 96.6 | 28.6 (29 %) | 298 | 103 (`receive_messages`) | 242 |
| S00 30 % loss | B3 + timeout | 90.2 | 24.1 (29 %) | 251 | 139 (`receive_messages`) | 251 |
| S00 30 % loss | B4 rule-based | 32.6 | 3.44 (11 %) | 35.8 | 12.2 (`step`) | 234 |
| S01 | B3 + timeout | 90.5 | 24.2 (27 %) | 252 | 73.1 (`step`) | 234 |
| S01 | B4 rule-based | 32.3 | 3.02 (9 %) | 31.4 | 12.1 (`receive_messages`) | 235 |
| S10 | B3 + timeout | 121 | 32.0 (30 %) | 334 | 27.6 (`receive_messages`) | 259 |
| S10 | B4 rule-based | 33.9 | 4.07 (12 %) | 42.4 | 13.3 (`step`) | 234 |
| May 2024 storm, 8 days | B3 + timeout | 2 130 | 1 520 (71 %) | 1 980 | 4 000 (`step`) | 978 |
| May 2024 storm, 8 days | B4 rule-based | 320 | 54.4 (17 %) | 70.9 | 32.3 (`step`) | 494 |

**Repeat spread, 24 h cases** ((max − min) / median over the repeats):

| Case | Planner | Run CPU | Onboard CPU | Peak RSS |
|---|---|---|---|---|
| S00 1 % loss | B0 static | 17.5 % | 20.0 % | 8.7 % |
| S00 1 % loss | B1 centralised (ground reference) | 26.6 % | 14.6 % | 10.9 % |
| S00 1 % loss | B2 auction | 60.2 % | 66.8 % | 0.2 % |
| S00 1 % loss | B3 CBBA | 10.8 % | 11.3 % | 1.0 % |
| S00 1 % loss | B3 + timeout | 15.0 % | 16.4 % | 0.5 % |
| S00 1 % loss | B4 rule-based | 30.2 % | 53.4 % | 0.2 % |
| S00 30 % loss | B0 static | 27.5 % | 17.9 % | 0.1 % |
| S00 30 % loss | B1 centralised (ground reference) | 14.3 % | 11.6 % | 0.2 % |
| S00 30 % loss | B2 auction | 41.4 % | 65.3 % | 0.0 % |
| S00 30 % loss | B3 CBBA | 25.5 % | 19.0 % | 0.5 % |
| S00 30 % loss | B3 + timeout | 23.1 % | 25.0 % | 4.1 % |
| S00 30 % loss | B4 rule-based | 72.9 % | 8.9 % | 0.1 % |
| S01 | B3 + timeout | 17.4 % | 20.9 % | 0.1 % |
| S01 | B4 rule-based | 7.2 % | 12.1 % | 7.6 % |
| S10 | B3 + timeout | 36.0 % | 46.2 % | 0.5 % |
| S10 | B4 rule-based | 26.3 % | 28.9 % | 0.1 % |

## Results corrected for timer overhead (estimate)

Medians minus timer overhead. Per-kind and onboard CPU minus calls × 3.195 µs (recorded inside each timed call); run CPU minus all timed calls × 6.231 µs. Calibration: a no-op method wrapped exactly as in `compute_cost.py`, timed in 7 batches of 300 000 calls on the same machine after the run (load average about 14 at the time). CPU in s; share = corrected onboard / corrected run.

| Case | Planner | Timed calls | Run CPU raw → corr. | Onboard CPU raw → corr. (share) | `receive_messages` corr. | `step` corr. | `payload_command` corr. | `observe` corr. |
|---|---|---|---|---|---|---|---|---|
| S00 1 % loss | B0 static | 172 451 | 34.9 → 33.8 | 3.43 → 2.88 (9 %) | 0.679 | 1.04 | 0.822 | 0.334 |
| S00 1 % loss | B1 centralised (ground reference) | 172 451 | 36.1 → 35.0 | 3.44 → 2.88 (8 %) | 0.701 | 1.09 | 0.790 | 0.332 |
| S00 1 % loss | B2 auction | 172 463 | 35.9 → 34.9 | 4.30 → 3.75 (11 %) | 1.03 | 1.34 | 1.01 | 0.375 |
| S00 1 % loss | B3 CBBA | 275 033 | 104 → 103 | 31.5 → 30.6 (30 %) | 19.7 | 9.41 | 1.08 | 0.434 |
| S00 1 % loss | B3 + timeout | 275 033 | 106 → 105 | 33.4 → 32.5 (31 %) | 21.0 | 9.98 | 1.14 | 0.451 |
| S00 1 % loss | B4 rule-based | 172 451 | 38.9 → 37.8 | 3.50 → 2.95 (8 %) | 0.690 | 1.11 | 0.851 | 0.297 |
| S01 | B3 + timeout | 189 748 | 90.5 → 89.3 | 24.2 → 23.6 (26 %) | 13.5 | 8.70 | 0.976 | 0.385 |
| S01 | B4 rule-based | 129 660 | 32.3 → 31.5 | 3.02 → 2.60 (8 %) | 0.508 | 1.00 | 0.802 | 0.292 |
| S10 | B3 + timeout | 309 597 | 121 → 119 | 32.0 → 31.0 (26 %) | 19.4 | 9.59 | 1.45 | 0.551 |
| S10 | B4 rule-based | 207 015 | 33.9 → 32.6 | 4.07 → 3.41 (10 %) | 0.661 | 1.14 | 1.21 | 0.464 |
| S00 30 % loss | B0 static | 162 390 | 31.8 → 30.8 | 3.37 → 2.85 (9 %) | 0.558 | 1.15 | 0.861 | 0.288 |
| S00 30 % loss | B1 centralised (ground reference) | 162 390 | 31.0 → 30.0 | 3.41 → 2.89 (10 %) | 0.575 | 1.11 | 0.874 | 0.322 |
| S00 30 % loss | B2 auction | 162 396 | 29.8 → 28.8 | 3.35 → 2.83 (10 %) | 0.625 | 1.12 | 0.886 | 0.310 |
| S00 30 % loss | B3 CBBA | 234 924 | 96.6 → 95.2 | 28.6 → 27.9 (29 %) | 15.7 | 10.2 | 1.27 | 0.587 |
| S00 30 % loss | B3 + timeout | 234 924 | 90.2 → 88.8 | 24.1 → 23.4 (26 %) | 13.0 | 8.99 | 1.04 | 0.377 |
| S00 30 % loss | B4 rule-based | 162 390 | 32.6 → 31.6 | 3.44 → 2.92 (9 %) | 0.586 | 1.14 | 0.846 | 0.285 |
| May 2024 storm, 8 days | B3 + timeout | 2 605 322 | 2 130 → 2 110 | 1 520 → 1 510 (71 %) | 640 | 849 | 13.4 | 5.39 |
| May 2024 storm, 8 days | B4 rule-based | 1 784 918 | 320 → 309 | 54.4 → 48.7 (16 %) | 10.0 | 15.2 | 17.5 | 6.03 |

## Findings

1. **CBBA costs about ten times the onboard CPU of the other planners.** On S00 at 1 % loss, B3 and B3 + timeout use 30.6 – 32.5 s of onboard CPU per simulated day for the formation (corrected), against about 2.9 – 3.8 s for B0, B1, B2 and B4. Most of it is `receive_messages` (consensus messages), then `step`. B0, B1, B2 and B4 cannot be ranked against each other: their differences are smaller than the repeat spread.
2. **Under storm protection the difference grows.** In the 8-day May 2024 storm, B3 + timeout used about 1 510 s of onboard CPU (71 % of the run) against about 49 s for B4 (16 %), and one `step` call took 4 s. B4's largest kind there is `payload_command` (the supervisor and the re-planning it triggers).
3. **Message loss lowers CBBA's onboard cost** (fewer deliveries to process: about 23 – 28 s corrected at 30 % loss against 30.6 – 32.5 s at 1 %), and leaves the others unchanged within the spread.
4. **Memory is dominated by the simulator.** Every 24 h run peaks at 234 – 260 MB (about 143 MB after imports, then 91 – 117 MB of growth). The 8-day storm runs reach 494 MB (B4) and 978 MB (B3 + timeout).
5. **Per spacecraft, the onboard cost is small in absolute terms on this machine:** about 30 – 45 ms of CPU per simulated hour per spacecraft for B0, B1, B2 and B4 in the 24 h runs (71 ms for B4 in the storm), about 250 – 350 ms for CBBA, and about 2 s for CBBA in the storm (raw).

## Limits

- **Python on one shared x86 laptop,** under heavy contention from other processes. The times are not portable across hardware and say nothing about flight processors.
- **Wide repeat spread** (up to about 70 % of the median for some 24 h runs): only differences of several times, such as CBBA against the rest, are supported.
- **Timer overhead** is included in the raw figures; the correction uses one calibration on the same machine and is an estimate.
- **Memory is whole-process** (simulator, logs and libraries); it is not the onboard memory of a spacecraft.
- **B1 is a ground reference,** not an onboard planner: its plan is computed once with full information (the ground-plan column).
- **Seed 1 only,** one storm, one formation, the recorded settings. The repeats measure timing noise, not scenario variation.

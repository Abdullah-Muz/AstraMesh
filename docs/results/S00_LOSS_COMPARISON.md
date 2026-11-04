# S00 nominal operations: B0–B3 under crosslink message loss

> **Status:** recorded 2026-11-03 from clean commit `dafa540` (`git_dirty: false`). **Not a research result:** S00 has no faults. This run characterises the baselines before any proposed method exists (spec §10.3).

## Setup (DL-047)

- **Base configuration:** `configs/experiments/nominal_ops_b0_24h.yaml`. It covers the 24 h J2 formation, the 16-region grid with its 43 opportunities, the spacecraft resources (DL-035/036) and the crosslink network (DL-040).
- **What varies:** only `operations.algorithm`, `network.loss_probability` ∈ {1%, 10%, 30%} and `random.seed` ∈ 1…10. That gives **120 runs**.
- **Identical tasks and resources:** the task catalogue is checked to be identical across all four methods for every seed (Gate P2).
- **Loss realisations differ between methods,** because each sends a different number of messages from the same `comms` stream. Pairing is by seed and configuration.
- **Intervals:** 95% t-intervals with n = 10. Square brackets are the interval; for zero-variance cells it has zero width.
- **Reproduce:** `uv run python scripts/experiments/s00_loss_comparison.py`. That takes about 6 minutes on 8 workers. The run rows are byte-identical to the preview run apart from wall time.
- **Files:**
  - [`s00_loss_comparison.csv`](s00_loss_comparison.csv): per run.
  - [`s00_loss_comparison_summary.csv`](s00_loss_comparison_summary.csv): per method and loss.
  - [`s00_loss_comparison_meta.json`](s00_loss_comparison_meta.json): commit, lockfile and config hashes.

## Results (mean over 10 seeds; utility out of 144)

| Method | Loss | Utility [95% CI] | Completed (of 43) | Duplicate observations [95% CI] | Runs with duplicates | Runs with conflicting claims | Messages / day | MB / day | Settle time s [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| B0 static | 1% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 11,524 | 2.7 | 0 [0, 0] |
| B0 static | 10% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 11,524 | 2.7 | 0 [0, 0] |
| B0 static | 30% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 11,524 | 2.7 | 0 [0, 0] |
| B1 centralized (privileged) | 1% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 11,524 | 2.7 | 0 [0, 0] |
| B1 centralized (privileged) | 10% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 11,524 | 2.7 | 0 [0, 0] |
| B1 centralized (privileged) | 30% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 11,524 | 2.7 | 0 [0, 0] |
| B2 auction | 1% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 11,528 | 2.7 | 10 [10, 10] |
| B2 auction | 10% | 144 [144, 144] | 43 | 4.3 [-5.4, 14.0] | 1/10 | 1/10 | 11,528 | 2.7 | 10 [10, 10] |
| B2 auction | 30% | 144 [144, 144] | 43 | 4.3 [-5.4, 14.0] | 1/10 | 1/10 | 11,528 | 2.7 | 10 [10, 10] |
| B3 CBBA | 1% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 46,088 | 59.2 | 424 [419, 429] |
| B3 CBBA | 10% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 46,088 | 59.2 | 467 [451, 483] |
| B3 CBBA | 30% | 144 [144, 144] | 43 | 0.0 [0.0, 0.0] | 0/10 | 0/10 | 46,088 | 59.2 | 572 [551, 593] |

Duplicates are second observations of an already completed task: they use energy and storage but earn nothing (DL-041). Settle time is the last plan change by any agent; it is 0 for B0 and B1, whose plans arrive by uplink.

## Findings

1. **Utility is saturated in S00.** Every method completes all 43 tasks in all 120 runs, even at 30% loss. With all four spacecraft eligible for every pass and ample resources, a fault-free day leaves no room for one method to beat another on science. S00 cannot rank the methods on science; fault scenarios (Phase 3) are needed.
2. **B2 (one-shot auction) fails all at once.** In 2 of 30 lossy runs (10% seed 3, 30% seed 4), sc01 missed sc00's bid message and believed it had won every tie. It duplicated **all 43** observations. Science was unaffected, but the duplicated energy and storage were spent. One run each at 10% and 30% is fewer than a rough estimate would suggest (about 3 of 10 at 30%). With 10 seeds the rate is poorly resolved, so **do not quote it as a probability**.
3. **B3 (CBBA) stays consistent under loss, at a price.** It had no duplicates or conflicts in 30 runs. It sends 4× the messages and about 22× the bytes of the others, because it broadcasts every round all day (DL-045, no stop rule). Its settle time grows with loss, as lost messages need extra rounds, but stays far below the first task start (about 1 800 s).
4. **B0 and B1 do not depend on the network.** Their plans arrive by uplink, so loss only affects status messages. B1's equality with B0 here shows that S00 is easy, not that B1's information has no value.

## Limits

- One scenario (S00), one fleet size (4), one day. Ten seeds. The q = 1 utility (DL-041) gives every spacecraft the same score, so ties decide assignments (every method gives the tasks to sc00).
- Message cost is counted in canonical-JSON bytes, not modelled radio bandwidth.
- CPU time per run is in the per-run CSV (`wall_s`) but is not deterministic, so it is not summarised.

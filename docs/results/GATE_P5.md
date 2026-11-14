# Phase 5 write-up (Gate P5)

> **Status:** written 2026-11-13 from the recorded Phase 5 results; no new runs. Awaiting owner review (DL-109). Phase 5 increment 5 (DL-077, DL-106). **Simulation results, not flight or radiation results:** the radiation hazard is a model built from a GEO proxy flux, a dipole cutoff model and synthetic payload tolerances, and every spacecraft, task and link is synthetic.

This page checks the three Gate P5 criteria (spec §13) against the evidence and summarises what Phase 5 found. Every number is quoted from the results pages linked in each section; where a number is derived here, the derivation is stated.

## Phase 5 build list (spec §13)

| Spec item | Done | Where |
|---|---|---|
| Atmospheric drag disturbance extension | D1 nominal drag (USSA76) and D2 storm-time density (NRLMSIS 2.0, DS-10 drivers); drift study; rule-based formation keeping against differential drag (increment 2b) | [`DRAG_DRIFT.md`](DRAG_DRIFT.md), [`FORMATION_KEEPING.md`](FORMATION_KEEPING.md) |
| Event / forecast risk policies | Per-spacecraft risk (position-based access through a dipole cutoff model, per-spacecraft tolerances, forecast age rule, forecast outage and delay faults); forecasts P-A / P-B / P-C in the supervisor; a shorter, pass-following protection setting as a second candidate | [`PER_SPACECRAFT_RISK.md`](PER_SPACECRAFT_RISK.md), [`PROTECTION_TUNING.md`](PROTECTION_TUNING.md), [`PROTECTION_COMPARISON.md`](PROTECTION_COMPARISON.md) |
| Multi-spacecraft protection decisions | Local supervisor per spacecraft (`agents/supervisor.py` unchanged since Phase 3, `e3c675f`; its risk inputs are new, DL-092); the G3 candidate: forecast handover through a policy slot (DL-078, DL-079) | [`HANDOVER_TUNING.md`](HANDOVER_TUNING.md), [`HANDOVER_COMPARISON.md`](HANDOVER_COMPARISON.md), [`MULTI_STORM.md`](MULTI_STORM.md) |
| Network partitions | Storm plus a 2 + 2 partition for 24 h (S09-style) | [`HANDOVER_COMPARISON.md`](HANDOVER_COMPARISON.md) |
| Independent task recovery | B3 + timeout and B4 (with the DL-094 correction: a protecting B4 spacecraft hands its tasks on); B0 as the no-reconciliation ablation | [`HANDOVER_COMPARISON.md`](HANDOVER_COMPARISON.md), [`ABLATIONS.md`](ABLATIONS.md) |
| Optional low-thrust maneuver optimisation | Deferred (DL-077): the 0.5 mN / 5 m/s thruster is a small-correction capability; rule-based formation keeping covers the separation threat that D2 found | DL-077, DL-087 |

## Criterion 1: combined failure / science / protection scenarios reproducible

**The combined scenarios** (DL-097, 229 runs from clean commit `fd5abc3`): the May 2024 storm with per-spacecraft risk and a forecast outage on sc01 over the first onset (S11-H); the same with a {sc00, sc01} | {sc02, sc03} partition for 24 h (S09-style); the same with a critical fault on sc00 2 h after the first onset (S10-style); and S00 as the identity check. Each under P-A / P-B / P-C (P-B for the combined ones), B3 + timeout and B4, baseline and candidate, seeds 1 – 10 or 1 – 5. Four more storms with per-spacecraft risk, but no outage, partition or fault, extend the storm comparisons (not the combined failures) in DL-100, DL-104 and DL-108.

**Provenance.** Every Phase 5 result was recorded from a clean commit, with the commit, the lockfile hash and every run's config hash in its meta file, and for the storm runs the SHA-256 of each storm series:

| Result | Clean commit | Runs |
|---|---|---|
| Drag drift, D1 / D2 | `9cd0016` / `460ccaf` | 12 / 9 |
| Formation keeping | `d7ab81a` | 11 |
| Per-spacecraft risk | `45430aa` | 10 |
| Handover tuning / May 2024 comparison | `a7b2046` / `fd5abc3` | 33 / 229 |
| Four evaluation storms (handover) | `f25e224` | 72 |
| Shorter protection, tuning / evaluation | `29f1b3f` / `0935e98` | 60 / 72 |
| Ablations, spread formation, diagnostics | `16f038e` | 180 / 36 / 5 |

That is 729 recorded runs, all with `git_dirty: false`. Every storm series is a pinned file opened by hash; the evaluation-storm forecasts were fitted only on data before each storm's fold (DL-099).

**Reproduction, measured.** Later experiments reran earlier ones' configurations, and every rerun matched the earlier recording:

- **Ablations against DL-100 and DL-097:** the 60 B3 + timeout and B4 baseline and QUIET runs have the same config hashes as the earlier recordings (the 30 B0 runs have no earlier recording). They match them exactly in utility, completions and duplicates, and the 30 baseline runs also match per spacecraft in unprotected hazard.
- **Shorter-protection evaluation against DL-100:** its 48 baseline and QUIET runs match the DL-100 recording.
- **Dirty-tree previews against the clean recordings:** the DL-102 tuning preview, the DL-105 spread preview and the DL-107 diagnostic smoke run each matched their clean recording (DL-107 quotes its smoke values rounded, e.g. 27.6 h for 27.58 h). The two span figures that DL-108 corrected came from DL-104's earlier unrecorded diagnostic, not from these previews.
- **Replay of the same seed:** bit-identical replay is tested in CI on every push (Phase 1, spec §14.3).

**Limits.**
- The experiments ran on one machine (WSL2). CI runs the test suite, not the experiments.
- Per-run artifacts (event logs, trajectories) are regenerated from the config, not stored.
- The full Phase 5 set took about 13 h of wall time on 8 – 12 workers. B3 + timeout runs take 19.5 – 45 min each.

**Assessment: met.**

## Criterion 2: no claims of radiation or flight safety beyond simulation assumptions

What the simulation calls hazard, and what it assumes:

| Quantity | What it is | Assumption, untested |
|---|---|---|
| Flux at the spacecraft | GOES-18 ≥ 10 MeV flux at GEO, applied inside each spacecraft's modelled polar-cap access | GEO flux stands for the interplanetary flux. The cutoff is a centred dipole with a SYM-H shift measured only to about −150 nT. There is no local-time dependence, no South Atlantic Anomaly and no shielding (DL-090 – DL-092). |
| Hazard, unprotected hazard, exposure | Time with the modelled flux at or above a spacecraft's tolerance; the same outside PROTECTIVE / RECOVERY; the same with the payload on | Tolerances of 100 / 100 / 50 / 200 pfu are synthetic modelled limits, not hardware ratings. |
| The 600 s limit on extra unprotected hazard (DL-101) | An owner-set budget for comparing settings | It is a modelled quantity, not a dose or damage threshold. |
| Spacings, closest approach | Point-mass distances under modelled drag (constant B, ideal thrust) | Collision is not modelled. Formation-keeping burns have no pointing error or failure. |

**Review of the Phase 5 pages.** Every results page labels the cutoff and the tolerances as models. None claims that a spacecraft or payload would be protected or damaged in flight. One phrase could be read as a safety claim: "the safety limit held everywhere" in `PROTECTION_COMPARISON.md`. It is reworded in this commit to name the modelled 600 s limit (DL-109). The DL-104 decision-log entry uses the same words ("Safety limit held"); the log is left as written, and DL-109 records that it means this modelled limit. The README's scope statement (simulation and research project, not flight software or a flight-validated system) stands.

**Safety rules held throughout, inside the model.** The checked rules:
- No payload step ran in a protected mode in any of the 408 runs that record the count (protection tuning and evaluation, the four storms, ablations, and the non-QUIET spread runs). For the handover candidate, HO-04 tests the same rule on a 12 h S11 run with per-spacecraft risk; the handover script does not record the count.
- The handover candidate left protection identical to the baseline in all 24 comparisons, as designed.
- No planner can override PROTECTIVE or SAFE (spec §14.1; property tests since Phase 3).

These are statements about the simulated supervisor, not about radiation safety.

**Assessment: met,** with the one rewording above.

## Criterion 3: baseline and candidate methods compared fairly

Two candidates were tested against the reactive baseline (the Phase 4 supervisor and planners):

| | Forecast handover (G3, DL-078) | Shorter protection (DL-101) |
|---|---|---|
| Fixed before tuning | Design, hypothesis, rejection rule, metrics and scenarios (DL-078, DL-094) | Grid, eligibility limit of 600 s extra unprotected hazard, tie rule and evaluation storms (DL-101) |
| Tuned on | February 2024, a training-period storm with out-of-sample fold forecasts, under B4 | The same storm, under B4 |
| Tested on | May 2024 (held out, used once after the freeze), then four out-of-sample training-period storms | The four out-of-sample storms |
| Protection | Identical to the baseline by construction; verified in all 24 comparisons | Changed by design; extra unprotected hazard reported per spacecraft |
| Outcome | B3 + timeout: +1 task on May (+0.0035 on every seed; not rejected by the rule, but n = 1 storm), 0 on the four storms. B4: 0 everywhere. **Rejected** on the four storms under both planners (DL-100) | +0.0070 [−0.0049, +0.0190] (B3 + timeout), +0.0053 [−0.0050, +0.0156] (B4), worst extra unprotected 410 s. **Rejected** under both planners (DL-104) |

**What makes the comparison fair:**

- **Same inputs.** Same scenarios, task lists, forecasts and seeds in each pair. The baseline and QUIET config hashes are tested equal across experiments, so every comparison reuses the same baseline. The exception is the spread run, whose 20 km baseline differs only in crosslink range and gives the DL-100 result.
- **Baseline strengthened, not weakened.** The B4 correction (DL-094) went into the baseline as well as the candidate.
- **Duplicates checked.** Both utilities are reported: the Phase 4 utility and one that charges duplicates (DL-078).
- **Rules applied as written,** including when the result was a single task (May, B3 + timeout).
- **Test storms kept separate.** No setting was chosen on a test storm. The May storm's later second use in the ablations, where nothing is tuned, is disclosed (DL-106). So is the pipeline dry run of three May runs after the freeze, which the recorded values match (DL-096). DL-101 discloses that the 23 Mar 2024 baseline protection was inspected while shorter protection was designed; no candidate setting was run on an evaluation storm.
- **Ablations of the components that exist** (spec §10.3): no look-ahead, no forecast, no hysteresis and no reconciliation, on five storms under both planners (DL-108).

**Asymmetries, disclosed:**
- **Planner tuning.** Both candidates were tuned under B4 only (owner choice, DL-094); B3 + timeout ran at a setting chosen without B3 data, which can only disadvantage the candidates under B3.
- **Sample size.** Seeds vary only message loss and navigation noise, which changed no outcome. The sample is therefore the storms: n = 1 for May, n = 4 or 5 elsewhere, and the intervals are wide. The negative results state their upper bounds (DL-106 F2): gains up to +0.019 (B3 + timeout) and +0.016 (B4) of QUIET utility are not excluded for shorter protection.
- **One formation.** Every comparison uses one formation: four spacecraft 20 km apart in one plane. The spread run tests one storm at larger spacings (DL-108).
- **Ablations not run.** Two spec §10.3 ablations were not run, because those components are not active in the storm scenarios: health uncertainty (the storm runs use the default health settings and, apart from S11-H+fault, inject no spacecraft fault) and maneuver feasibility (equal B, so formation keeping never burns).

**Assessment: met,** with the asymmetries above stated.

## What Phase 5 found

1. **Neither G3 candidate improves on the baseline.** Forecast handover changes one task on one storm under one planner. Shorter protection recovers half the loss on its tuning storm (+35 of 74 points); on the four evaluation storms its pooled gain is +0.0070 (B3 + timeout) and +0.0053 (B4) with intervals that include 0, and it adds up to 410 s of unprotected hazard. Both are rejected by their pre-registered rules. RL (increment 4b) was dropped because there is no room for either role (DL-105).
2. **Where the storms cost science, a free peer is rare.** Retention falls to 0.853 on 23 – 24 Mar 2024 and 0.94 on 18 Jul 2023. On 23 Mar, 49 of the 50 lost tasks had no spacecraft with access in a tasking mode for any part of the window, and on 18 Jul 19 of 22 (B4, seed 1). In this close formation the four spacecraft cross each hazard region together.
3. **Task redistribution is what protects science.** Removing reconciliation (B0) costs 5.3 – 5.5 % of QUIET utility pooled over five storms, up to 13 % on May 2024. The spacecraft differ in tolerance, so they protect at different times and peers take their tasks.
4. **Each protection component costs little science and prevents unprotected hazard.** Removing look-ahead, forecast or hysteresis gains +0.0025 to +0.0053 pooled (point estimates; gains up to +0.005 to +0.014 are not excluded). Each adds unprotected hazard on 3 or 4 of the 5 storms: up to 390, 600 and 410 s on one spacecraft.
5. **Spreading the formation does not help under the baseline protection.** The baseline protects identically at 20 and 5 000 km, likely because the one-hour look-ahead covers most of a 95 min orbit. Shorter protection gains with spacing, but only with extra unprotected hazard, and with 108 duplicates at 2 000 km.
6. **The baseline's unprotected hazard that was located coincides with its inputs.** On 18 Jul 2023, sc00 – sc02 each have 600 s at a sharp onset in every arm, equal to the 600 s data latency (not tested by varying the latency). On May 2024, sc01's 680 s falls over its forecast outage (DL-093). sc02's 290 s on May 2024 was not located.
7. **Position alone does not separate the spacecraft; tolerances do** (DL-093). Within one storm week, differential drag of ±20 % brings two spacecraft within 47 – 60 m under storm-time density. Formation keeping holds every spacing within about 0.7 km of 20 km for 0.03 – 0.05 m/s (DL-086, DL-089).

**Novelty.** The G3 candidate shows no supported improvement, so no novelty claim is made (spec §9.2). Phase 5's contribution is a set of bounded, reproducible results, most of them negative, about where storm-time science loss comes from in a close formation and what each part of the protection system costs and buys.

## Not done in Phase 5

- **Dropped or deferred:** RL policies (increment 4b, DL-105); the tight-schedule scenario, which density could not create (QUIET completion stays at 98.3 – 98.8 %, DL-096); low-thrust maneuver optimisation (DL-077).
- **Baselines not run on storms:** B1 (centralised reference) and B2 (one-shot auction). The storm comparisons use B3 + timeout and B4, plus B0 in the ablations.
- **Not tested:** fleet sizes other than four; spreads across orbit planes; the data latency as a variable; the 32 / 17 priority split of the lost tasks in a recorded run (DL-108).
- **Not measured:** CPU time and peak memory per algorithm (spec §10.2); a physical cost of protection cycling; false-degraded idle time in the utility (Phase 4 carry-over; the health models are not part of the storm scenarios).

## Carried forward (not blocking; Phase 6 needs separate approval)

- **Results to explain in Phase 6's negative-result analysis:**
  - why B4 misses the 4 lost tasks a peer could have taken (DL-100);
  - where in each storm the no-forecast ablation's extra hazard falls;
  - why removing look-ahead cycles heavily but adds little hazard;
  - the unprotected hazard that spreading adds to the baseline.
- **Open model questions:**
  - the data latency at sharp onsets;
  - a look-ahead tied to the orbit, so that spread spacecraft could protect at different times;
  - B4 has no handback (DL-102).
- **Earlier carry-overs remain:**
  - CBBA has no stop rule, and an 8-day B3 run takes 19.5 – 45 min;
  - S06 is deferred;
  - the literature drafts still await owner verification.

## Reproduce

| Result | Script | Clean commit | Time (workers) |
|---|---|---|---|
| [`DRAG_DRIFT.md`](DRAG_DRIFT.md) | `scripts/experiments/drag_drift_study.py` (`--msis` for D2) | `9cd0016`, `460ccaf` | 5 min; 18 min |
| [`FORMATION_KEEPING.md`](FORMATION_KEEPING.md) | `scripts/experiments/formation_keeping_study.py` | `d7ab81a` | 20 min |
| [`PER_SPACECRAFT_RISK.md`](PER_SPACECRAFT_RISK.md) | `scripts/experiments/per_spacecraft_risk_study.py` | `45430aa` | 2.5 min |
| [`HANDOVER_TUNING.md`](HANDOVER_TUNING.md) | `scripts/experiments/handover_tuning.py` | `a7b2046` | 7 min |
| [`HANDOVER_COMPARISON.md`](HANDOVER_COMPARISON.md) | `scripts/experiments/handover_comparison.py` | `fd5abc3` | 4.7 h (8) |
| [`MULTI_STORM.md`](MULTI_STORM.md) | `scripts/experiments/multi_storm_comparison.py` | `f25e224` | 88 min (12) |
| [`PROTECTION_TUNING.md`](PROTECTION_TUNING.md) | `scripts/experiments/protection_tuning.py` | `29f1b3f` | 21 min (12) |
| [`PROTECTION_COMPARISON.md`](PROTECTION_COMPARISON.md) | `scripts/experiments/protection_comparison.py` | `0935e98` | 113 min (12) |
| [`ABLATIONS.md`](ABLATIONS.md) | `scripts/experiments/ablation_study.py` | `16f038e` | 3.7 h (12) |
| [`SPREAD_FORMATION.md`](SPREAD_FORMATION.md) | `scripts/experiments/spread_formation.py` | `16f038e` | 7 min (12) |
| [`storm_diagnostics.json`](storm_diagnostics.json) | `scripts/experiments/storm_diagnostics.py` | `16f038e` | 2 min |

Data: `uv run python scripts/data/fetch_data.py` downloads every pinned file (DL-063); the storm series are committed under `configs/data/`.

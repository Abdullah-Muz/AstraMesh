# AstraMesh: decentralised science operations and storm protection in a simulated four-spacecraft formation

**Technical report** · Abdullah Muzher · 2026-11-16 · Phase 6 increment 5 (DL-128) · licensed CC BY 4.0

> **What this is.** AstraMesh is an independent spacecraft-autonomy research project. Every result about the formation is a **simulation** result: the spacecraft, tasks, links and payload tolerances are synthetic, and the radiation hazard is a model. The storms that drive it are **measured** (GOES-18 proton flux and OMNI geomagnetic data). Two results do not involve the simulation: an anomaly-detection benchmark on **real** OPS-SAT telemetry (§5.3) and the skill of proton-flux forecasts scored against **measured** flux (§5.4). Nothing here is flight software, a real constellation or a flight-validated system, and no novelty is claimed.
>
> **How to read the numbers.** This report computes nothing new. Every number is copied from a committed results page in [`docs/results/`](results/) and cites it. Each results page names the clean commit, configuration hashes and data series it came from; [`GATE_P6.md`](results/GATE_P6.md) lists them. Intervals are 95 % t-intervals unless stated otherwise.

## Abstract

We built a reproducible simulation of a four-spacecraft formation in low Earth orbit (525 km, 97.5°, 20 km along-track spacing). Each spacecraft schedules ionospheric observations, coordinates over a modelled crosslink network, keeps its own health beliefs about its peers, and runs a local five-mode protection supervisor that no planner can override. We used it to test whether decentralised task allocation and space-weather-aware protection can preserve science during faults and solar proton events.

Fault-aware reallocation (CBBA with a health timeout, and a rule-based redistribution) keeps all observable science when one or two spacecraft are lost, where a static schedule keeps 0.81 or 0.68 of it. In storms, task reconciliation between spacecraft is what protects science: removing it costs 5.9 – 6.0 % of quiet-period utility on six held-out storms, with intervals that exclude zero. The protection supervisor's forecast, look-ahead and hysteresis each cost little science and prevent unprotected hazard on some storms.

The two candidate methods we proposed for coordinating protection across the formation, a forecast-based task handover and a shorter pass-following protection, were frozen after tuning and did not improve on the baseline, either on their Phase 5 test storms (May 2024 and four training-period storms) or on six later storms that no method had seen. We report this negative result and explain the remaining baseline losses: orbital geometry, data latency at sharp onsets, and an ownership-split defect in one baseline. A fix for that defect recovered the lost tasks on the storms used to develop it, was neutral on two test storms where there was nothing to recover, and fails where spacecraft that share tasks cannot hear each other. An independent cross-check against Basilisk agrees with AstraMesh's two-body, J2 and drag propagation to 0.22 mm and 8 cm over 8 days.

## 1. Question and hypotheses

**Primary question** (spec §2.1): can a decentralised spacecraft constellation preserve useful scientific operations during uncertain spacecraft-health events, communication disruption and hazardous space weather, while keeping local protection and manoeuvre constraints satisfied?

The specification stated five hypotheses (§2.2). They were hypotheses, not promised outcomes. Our verdicts, inside the simulation and its assumptions:

| | Hypothesis (spec §2.2, shortened) | Verdict | Evidence |
|---|---|---|---|
| H1 | Fault-aware task planning retains more utility than static scheduling when capacity is lost | **Supported** (simulation; synthetic faults, 10 seeds, one fleet size) | §5.2: retention 1.00 against 0.81 (S01) and 0.68 (S02); §5.5: removing reconciliation changes retention by −0.0596 [−0.0915, −0.0276] on held-out storms |
| H2 | Explicit health uncertainty reduces premature failure declarations and conflicting reallocations against timeout-only monitoring | **Not supported** | §5.3: the probabilistic model detects a real loss sooner but cannot tell a radio outage from a loss: duplicates under a false outage are unchanged, and false-outage time rises slightly (64 269 against 63 060 pair-seconds under B3 + timeout) |
| H3 | Space-weather-aware protection improves the hazard / downtime trade-off against naïve thresholds | **Partly supported** | §5.4 – §5.6: against the naïve threshold (A2: react to the measured flux), the forecast prevents extra unprotected hazard on 5 of 6 held-out storms at a science cost whose interval includes 0; look-ahead and hysteresis do the same on 3 of 6. But on May 2024 the forecasts traded science for hazard (retention 0.912 → 0.863 / 0.833), and the trade depends on synthetic tolerances |
| H4 | A local safety supervisor reduces invalid or unsafe manoeuvre proposals executed during recovery | **Not tested** | No planner proposes manoeuvres; formation keeping is rule-based. The supervisor's override property held in every run that records it and in property tests (§5.2), but the with / without comparison H4 asks for was not run |
| H5 | Forecast-informed protection may improve mission continuity at a given safety-risk budget | **Not supported** | §5.4, §5.6: forecasts reduced unprotected hazard but not science loss: on May 2024 persistence (P-A) kept the most science, and removing the forecast (A2) changes held-out retention by +0.0087 / +0.0078 with intervals that include 0. No comparison at a matched risk budget was run |

The specification allowed narrowing the contribution to one hypothesis. Phase 5 chose G3, decentralised protection-mode coordination during space-weather episodes (spec §9.2; DL-077), and that candidate failed (§5.5).

## 2. The simulated system

**Dynamics** ([`NUMERICAL_MISSION_DESIGN.md`](NUMERICAL_MISSION_DESIGN.md)). Four spacecraft, initialised from mean elements as a 20 km along-track formation, are propagated with fixed-step RK4 under two-body gravity, J2 (EGM2008 C̄20) and atmospheric drag: USSA 1976 (D1) or NRLMSIS 2.0 driven by measured F10.7 and ap (D2). Frames and time scales use Astropy (GCRS / ITRS, UTC / TT / UT1). Ten physics acceptance tests (PA-01 – PA-10: analytic two-body accuracy, invariants, step convergence, frame round trips, units, formation set-up, a Clohessy–Wiltshire cross-check, J2 nodal precession, determinism and invalid input) run in CI, with numerical tolerances set from reference-error studies and approved before the code was accepted. Formation keeping is a rule-based controller with a 0.5 mN thruster.

**Independent cross-check** ([`BASILISK_COMPARISON.md`](results/BASILISK_COMPARISON.md); [F8](figures/README.md#f8-astramesh-against-basilisk)). Basilisk 2.12.2, configured with AstraMesh's constants and atmosphere, agrees with AstraMesh to 0.13 mm (two-body) and 0.22 mm (J2) in position over 8 days, and to 8.0 cm with drag, which is 1.3e-6 of drag's own 63.3 km effect. Tolerances (1 m; 0.5 % of drag's effect) were fixed before the run. This checks the implementation, not the physics: both codes ran the same models by construction.

**Mission geometry and resources.** Illumination with a cylindrical shadow, WGS 84 region access, geometry-only science opportunities (dual-frequency GNSS TEC observation as a scheduling abstraction, not a retrieval), and energy, storage and Δv ledgers. A task's utility is its priority, summed over completed tasks (DL-041). From Phase 5 a second utility charges each duplicate observation its task's priority (DL-094).

**Agents and network** ([`AUTONOMY_ARCHITECTURE.md`](AUTONOMY_ARCHITECTURE.md)). Each spacecraft is an isolated agent that acts only on its own state and the messages it receives, never on the simulator's truth (spec §5; Gate P2). Crosslinks are a time-varying graph: one-hop links within a synthetic range whose line of sight clears the Earth, with delay, Bernoulli loss and injectable partitions; agents send status every 30 s (DL-040).

**Faults and health** ([`FAULT_COMPARISON.md`](results/FAULT_COMPARISON.md), [`HEALTH_COMPARISON.md`](results/HEALTH_COMPARISON.md)). Deterministic, seeded injection of loss, radio outage, partition, payload degradation and critical faults. Each agent keeps a health belief about each peer: H-A, a 300 s timeout; H-B, a probabilistic silence model; H-C, H-B plus a calibrated payload-anomaly detector fed with real OPS-SAT detector scores.

**Protection supervisor** ([`PROTECTION_MODES.md`](PROTECTION_MODES.md)). Five modes per spacecraft: NOMINAL, STORM_WATCH, PROTECTIVE, RECOVERY and SAFE. Transitions use hysteresis and minimum dwell times; SAFE overrides everything and is left only through RECOVERY. No planner can command the payload in a protected mode. In storms the supervisor's input is the proton forecast available at that time (median of P-B unless stated), compared with the spacecraft's own tolerance, and gated by a one-hour look-ahead along the spacecraft's own track.

**Hazard model** ([`PER_SPACECRAFT_RISK.md`](results/PER_SPACECRAFT_RISK.md)). The GOES-18 ≥ 10 MeV flux at geostationary orbit stands for the flux a spacecraft sees when it is inside the polar-cap access region. Access is where invariant latitude is at least a centred-dipole cutoff shifted by SYM-H (R08: observed only to about −150 nT). The tolerances are 100 / 100 / 50 / 200 pfu for sc00 – sc03: synthetic limits, not hardware ratings. *Hazard* is time with the modelled flux at or above a spacecraft's tolerance; *unprotected hazard* is hazard outside PROTECTIVE and RECOVERY. There is no shielding, no local-time dependence and no South Atlantic Anomaly.

## 3. Data

Every external file is pinned by SHA-256 in [`DATASET_REGISTRY.md`](DATASET_REGISTRY.md), with its licence or terms checked before download. The storm series the simulation reads are committed under `configs/data/`.

| Registry | Source | Use | Terms |
|---|---|---|---|
| DS-02 | ESA OPS-SAT-AD (19.5 MB) | anomaly benchmark; the H-C detector scores | CC BY 4.0 and MIT |
| DS-06, DS-09 | NASA OMNI 1-min (May 2024; Jan 2023 – Apr 2024) | SYM-H and AE for the cutoff and forecasts | citation requested |
| DS-07, DS-08 | GOES-18 SEISS / SGPS 5-min (May 2024; Jan 2023 – Apr 2024) | proton flux; forecast training | "may be redistributed and used without restriction" |
| DS-10 | OMNI2 hourly F10.7 and ap (2023 – 2024) | NRLMSIS drivers | as DS-06 |
| DS-11, DS-12 | GOES-18 SGPS and OMNI 1-min (Jun 2024 – Oct 2026) | held-out storms | as DS-07 and DS-06 |

**Partitions.** Forecasts were trained on January 2023 – April 2024 and never refitted. May 2024 was the Phase 4 held-out storm. Phase 5 tuned on February 2024 and tested on May 2024 and four out-of-sample storms from the training period, each with forecasts fitted only on data before its fold (DL-099). Phase 6 selected six test storms and two reserved windows from 1 Jun 2024 – 31 Oct 2026 by a rule fixed before any run (DL-113). One test storm (17 Jan 2026) has a peak 37 times the training maximum and a newer GOES processing version (v3-0-3).

**Planned but not used:** ESA-ADB (sized only, too large to unpack in the available memory; DL-062), NOAA GloTEC (starts in 2025) and UCAR COSMIC-2 (licence unverified) (DL-071), and CelesTrak GP / OMM.

## 4. Methods, baselines and protocol

**Planners** (spec §9.1):

| | Method | Notes |
|---|---|---|
| B0 | Static scheduler | plans by uplink; never reallocates; used as the no-reconciliation ablation (A4) |
| B1 | Centralised MILP reference | uses privileged truth; a reference, not a candidate |
| B2 | One-shot auction | |
| B3 | CBBA (P06) | synchronous rounds over the modelled network; no stop rule |
| B3 + timeout | CBBA with H-A health beliefs | drops a silent peer's claims after the timeout |
| B4 | Rule-based redistribution | a spacecraft that becomes unavailable or protected hands its tasks on by a fixed rule; no handback |

**Forecasts** ([`STORM_FORECAST.md`](results/STORM_FORECAST.md)): P-A persistence, P-B an empirical-quantile model and P-C gradient boosting, each issuing next-hour quantiles of the ≥ 10 MeV flux from data 600 s old.

**Candidates** (fixed before tuning; DL-078, DL-101):
- **Forecast handover** (G3): each spacecraft forecasts its own protection window from its risk forecast, shares it in its status messages and releases its claims on tasks inside that window as soon as the window is forecast, instead of when protection starts. Protection itself is unchanged by construction. Tuned settings: θ 0.9, L 30 min (DL-096).
- **Shorter protection:** a shorter look-ahead and release dwell (600 s and 600 s after tuning), so protection follows each pass, eligible only if it adds at most 600 s of unprotected hazard on any spacecraft.

**Ablations** ([`ABLATIONS.md`](results/ABLATIONS.md)): A1 no look-ahead, A2 no forecast (react to measured flux), A3 no hysteresis, A4 no reconciliation (B0).

**Protocol** ([`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md)).
- Every recorded result was run from a clean commit; its meta file records the commit, `git_dirty: false`, the lockfile hash, every run's configuration hash and, for storm runs, each series' SHA-256.
- Design, hypotheses, measures and rejection rules were written into a decision-log entry before each run; results are reported as they came out.
- *Retention* is utility divided by the same planner's utility in a QUIET run (the same window without the storm). Comparisons are paired: same tasks, forecasts and seeds.
- Seeds vary message loss and navigation noise. In the storm runs they changed no outcome, so the sample is the storms (n = 1 – 6 per comparison), and intervals are over storms.
- By spec §10.2, a science gain that adds unprotected hazard is never called better.

## 5. Results

### 5.1 Nominal operations: a fault-free day cannot rank the planners

([`S00_LOSS_COMPARISON.md`](results/S00_LOSS_COMPARISON.md)) On a fault-free day (43 tasks, utility 144) every planner completes every task in all 120 runs, even at 30 % message loss. The one-shot auction (B2) failed all at once in 2 of 30 lossy runs: one spacecraft missed a bid and duplicated all 43 observations. CBBA had no duplicates or conflicts in 30 lossy runs, at about 4 times the messages and 22 times the bytes of the others, because it broadcasts every round all day.

### 5.2 Faults: reacting to a loss recovers the science

([`FAULT_COMPARISON.md`](results/FAULT_COMPARISON.md); 600 runs, 10 seeds, synthetic faults)

- **Loss of a spacecraft:** B3 + timeout and B4 keep retention 1.00 in S01 and S02 (one B4 run kept 141 of 144 because the task's only slot opened as the spacecraft was lost). B0 keeps 0.81 [0.79, 0.83] and 0.68 [0.65, 0.70]. B1 – B3 without a timeout depend on tie-breaking (with equal scores they give all tasks to sc00), so their means are not a ranking.
- **The cost of reacting is duplication under false outages:** when a spacecraft only goes quiet (radio outage, partition) every reacting run duplicates its tasks: B3 + timeout 6 – 11 per run, B4 33 – 38. Pure CBBA never duplicates.
- **Safety invariants held in all 600 runs:** no payload step in a protected mode, no confirmed-failed belief about an available spacecraft, and SAFE overrode PROTECTIVE and was left only through RECOVERY.
- **A brief alert costs much longer than itself:** a 10 min alert keeps a spacecraft out of science for about 45 min (40 min in PROTECTIVE, the alert plus the 30 min release dwell, then the 5 min minimum in RECOVERY), the deliberate price of no mode chatter.

### 5.3 Health beliefs and a real-telemetry detector

([`OPSSAT_BENCHMARK.md`](results/OPSSAT_BENCHMARK.md), [`HEALTH_COMPARISON.md`](results/HEALTH_COMPARISON.md), [`GATE_P4.md`](results/GATE_P4.md))

- **The benchmark reproduces published results** on real OPS-SAT telemetry: four detectors match Ruszczak et al. (2025, Table 3) within 0.025 on every reported metric. A time-ordered split, which a shuffled split hides, costs supervised methods 0.013 – 0.025 AUC-ROC and unsupervised and classical ones 0.05 – 0.30.
- **H-B detects a real loss about 3 times sooner** than the timeout (about 105 s against about 300 s), but a 24 h schedule with slack absorbs the difference: retention 1.000 under every model.
- **No model separates a radio outage from a loss.** Under a 3 h radio outage, B3 + timeout makes 6.1 and B4 33.1 duplicates under H-A and the same under H-B, which declares the spacecraft lost sooner. This is why H2 is not supported.
- **The detector helps only where the classical signal is blind.** With a degraded payload that keeps talking, H-A never detects it (B4 retention 0.876 [0.864, 0.889]); H-C detects it after 733 s [544, 922] and keeps retention 1.000 with no invalid observations, at the price of false-degraded time (about 1 400 s of clearing lag).

### 5.4 Storm protection with forecasts

([`STORM_FORECAST.md`](results/STORM_FORECAST.md), [`STORM_REPLAY.md`](results/STORM_REPLAY.md); [F9](figures/README.md#f9-proton-forecast-skill-against-horizon); [F1](figures/README.md#f1-the-23---24-march-2024-storm) shows the same forecasts on the 23 Mar 2024 storm)

On the held-out May 2024 storm week (one storm, 4 onsets above 100 pfu), with one 100 pfu tolerance for all four spacecraft:

| | P-A persistence | P-B empirical quantile | P-C gradient boosting |
|---|---|---|---|
| Onsets warned (of 4) | 0 | 3 | 4 |
| POD gain over P-A (1 h, day bootstrap) | – | +0.17 [+0.06, +0.27] | +0.23 [+0.17, +0.33] |
| Unprotected hazard per spacecraft | 40 min | 5 min | 0 |
| False protection per spacecraft | 8.6 h | 14.3 h | 21.1 h |
| Retention | 0.912 | 0.863 | 0.833 |

Forecasts close the reaction gap and pay in false protection. P-B and P-C cannot be told apart in pinball loss (+0.003 [−0.001, +0.007]); P-C's false-alarm ratio is clearly higher. On this storm the classical forecast is the better trade, but the tolerance decides more than the forecast: at 50 pfu all three keep 0.70 – 0.73 of the science.

### 5.5 The candidates do not improve on the baseline

**Development and Phase 5 tests** ([`HANDOVER_TUNING.md`](results/HANDOVER_TUNING.md), [`HANDOVER_COMPARISON.md`](results/HANDOVER_COMPARISON.md), [`MULTI_STORM.md`](results/MULTI_STORM.md), [`PROTECTION_TUNING.md`](results/PROTECTION_TUNING.md), [`PROTECTION_COMPARISON.md`](results/PROTECTION_COMPARISON.md), [`GATE_P5.md`](results/GATE_P5.md); [F4](figures/README.md#f4-protection-tuning-on-the-february-2024-storm)):
- **Forecast handover** changed one task on May 2024 under B3 + timeout (+0.0035 on every seed; not rejected by its rule there, but n = 1 storm) and nothing under B4 or on the four further storms, where its pre-registered rule rejected it under both planners (DL-100).
- **Shorter protection** recovered half its tuning storm's loss (+35 of 74 points), but on four evaluation storms gained +0.0070 [−0.0049, +0.0190] (B3 + timeout) and +0.0053 [−0.0050, +0.0156] (B4) and added up to 410 s of unprotected hazard. Rejected (DL-104).

**Six held-out storms after May 2024** ([`HELDOUT.md`](results/HELDOUT.md); 288 runs; [F2](figures/README.md#f2-held-out-storms-retention-change-by-arm)). Methods, settings and forecasts were frozen and the expectations written before any run. Pooled retention change against the baseline (n = 6):

| Arm | B3 + timeout | B4 | Worst extra unprotected hazard | Storms with extra unprotected hazard |
|---|---|---|---|---|
| Forecast handover | −0.0004 [−0.0016, +0.0007] | 0 [0, 0] | 0 | 0 of 6 |
| Shorter protection | +0.0210 [−0.0042, +0.0462] | +0.0103 [−0.0051, +0.0257] | 490 s | 2 of 6 |
| A1 no look-ahead | +0.0109 [−0.0103, +0.0321] | −0.0841 [−0.3021, +0.1339] | 490 s | 3 of 6 |
| A2 no forecast | +0.0087 [−0.0123, +0.0297] | +0.0078 [−0.0122, +0.0278] | 430 s | 5 of 6 |
| A3 no hysteresis | +0.0143 [−0.0044, +0.0329] | +0.0147 [−0.0042, +0.0336] | 1 680 s | 3 of 6 |
| A4 no reconciliation | −0.0596 [−0.0915, −0.0276] | −0.0591 [−0.0916, −0.0267] | 0 | 0 of 6 |

The Phase 5 main result holds on unseen storms. Shorter protection gains on five of six storms and ties on the sixth (up to 75 points) but its interval includes 0, and it adds unprotected hazard on 2 of 6 storms, so by spec §10.2 it is not better. Gains up to the upper bounds (+0.046 of QUIET utility for shorter protection under B3 + timeout) are not excluded. The B4 interval under A1 measures a B4 defect, not the value of look-ahead (§6).

### 5.6 What each component costs and buys

([`ABLATIONS.md`](results/ABLATIONS.md), [`HELDOUT.md`](results/HELDOUT.md); [F3](figures/README.md#f3-ablations-science-against-hazard))

- **Reconciliation protects science.** Without it, 5.3 – 5.5 % of QUIET utility is lost pooled over the five Phase 5 storms and 5.9 – 6.0 % over the six held-out storms (both intervals exclude 0 on the held-out storms), with protection unchanged. The spacecraft differ in tolerance, so they protect at different times and peers take their tasks.
- **Each protection component costs little science and prevents unprotected hazard on some storms.** Removing look-ahead, forecast or hysteresis gains +0.0025 to +0.0053 pooled on the Phase 5 storms and +0.008 to +0.015 on the held-out storms (excluding A1 under B4); every interval includes 0. The forecast prevents extra unprotected hazard on 5 of 6 held-out storms, look-ahead and hysteresis on 3 of 6 each. Look-ahead also prevents heavy cycling: without it, up to 27 times the protection entries on the Phase 5 storms, and 293 against 4 on the held-out 25 Oct 2024 storm.

### 5.7 Where the storm losses come from

([`MULTI_STORM.md`](results/MULTI_STORM.md), [`SPREAD_FORMATION.md`](results/SPREAD_FORMATION.md); [F5](figures/README.md#f5-spread-formation-on-23---24-march-2024))

- **A free peer is rare.** Retention falls to 0.853 on 23 – 24 Mar 2024 and 0.94 on 18 Jul 2023. On 23 Mar, 49 of the 50 lost tasks had no spacecraft with access in a tasking mode for any part of the window (recorded diagnostic, B4, seed 1). In a 20 km formation the four spacecraft cross each hazard region together.
- **Spreading the formation does not help under the baseline protection.** The baseline protects identically at 20 and 5 000 km spacing (one storm, B4). Shorter protection gains at the larger spacings, but only with extra unprotected hazard, and with 108 duplicates at 2 000 km.
- **Position alone does not separate the spacecraft; tolerances do** ([`PER_SPACECRAFT_RISK.md`](results/PER_SPACECRAFT_RISK.md)). Under storm-time density, ±20 % differential drag brings two spacecraft within 47 – 60 m in one storm week; formation keeping holds every spacing within about 0.7 km of 20 km for 0.03 – 0.05 m/s ([`DRAG_DRIFT.md`](results/DRAG_DRIFT.md), [`FORMATION_KEEPING.md`](results/FORMATION_KEEPING.md)).

### 5.8 Demonstration

A 52 s video, [`astramesh_demo_mar2024.mp4`](media/astramesh_demo_mar2024.mp4), shows the simulated formation (B4, baseline protection, seed 1) through the measured 23 Mar 2024 storm: ground track and access region, flux against each tolerance, and each spacecraft's mode, hazard and task take-overs. It is rendered from [`demo_trace.json`](results/demo_trace.json), whose configuration hash and utility (969 points) equal the recorded run ([`docs/media/README.md`](media/README.md)).

## 6. Negative results

([`NEGATIVE_RESULTS.md`](results/NEGATIVE_RESULTS.md); 96 runs, hypotheses fixed before the run; [`RESYNC_COMPARISON.md`](results/RESYNC_COMPARISON.md); [F6](figures/README.md#f6-data-latency-and-onset-hazard), [F7](figures/README.md#f7-b4-ownership-re-sync-tasks-lost-while-available))

1. **B4's hand-on can split ownership.** Under A1, B4 completed 104 tasks on 7 Oct 2024 against 276 in its baseline (retention change −0.50); B3 + timeout lost nothing. Cause (N1): B4 hands tasks on using peer-mode views refreshed only every 30 s. In a close formation the spacecraft protect almost together, so a task can go to a successor that is already protected and never takes it, and with no handback the views never agree again. Cycling protection makes this frequent.
2. **B4's four "recoverable" Phase 5 losses** (N2): 2 of 4 are splits; the other 2 were protected after their slots had begun.
3. **Remaining baseline hazard is at onsets** (N3, N6). Every unprotected interval in every baseline, spread and latency run starts with its hazard episode, and all of A2's extra hazard is at onsets. It falls with data latency on all four storms tested and is 0 at 0 s latency (a non-causal bound) on all of them; at 300 s, the earliest physical value, it is 0 on two of four. On 18 Jul 2023, up to 600 s the onset is entirely latency-bound.
4. **Without look-ahead, protection follows the orbit, not the hazard** (N4): 89 % of its protection spans start and end outside hazard.
5. **Spreading adds hazard to trailing spacecraft** (N5): at 5 000 km, 140 / 280 / 150 s on sc01 – sc03 and none on sc00. The recorded analysis did not establish why. An open hypothesis from a later, unrecorded investigation is noted in DL-129; it is not a result.
6. **A fix for the split works only where peers hear each other** (DL-122 – DL-124). An ownership re-sync carried in status messages was designed, fixed and tested on the two reserved storms. There it was neutral (B4 had no split loss to recover). On the development storms, tasks lost while available fell from 261 (248 split) to 14 (none split), and the largest loss (347) returned to 919. In the 2 000 km formation, where two spacecraft share tasks without line of sight, it raised duplicates from 15 to 111 and lowered the duplicate-charged utility by 0.113 of QUIET. It costs 8 – 10 % more bytes in the close formation. It is not part of any baseline reported above.

## 7. Related work

From [`LITERATURE_REVIEW.md`](LITERATURE_REVIEW.md). **Every reviewed row there is an assistant draft from a full-text reading that the owner has not yet verified**, so this section is provisional. P01 is blocked (no full text; P01S was read instead), P21 was paywalled, R07 was not started, and Priorities B – D (spec §15.1) were not reviewed.

- **Flight precedent.** NASA's Starling 1.0 flew four CubeSats coordinating dual-band GPS ionospheric observations over crosslinks with distributed onboard planning (D01, D10, D11, P01S; unverified). AstraMesh cannot claim to be first at that. The Starling papers we read describe no space-weather response, protection modes or health beliefs.
- **Task allocation.** CBBA (P06; unverified) is B3; its guarantees assume synchronous rounds and a static connected network with no loss model, which AstraMesh violates by design. Satellite variants (P03) and decomposition-based scheduling (P19; with P02 as a related version) assume idealised networks (unverified). Rule-based redistribution after a loss (P09; unverified) is weak precedent for B4.
- **Faults.** Leader / follower fault separation in a swarm (P22; unverified) assumes instant communication.
- **Space weather.** Storm impact on a LEO network varies between planes and satellites (R01, preprint; unverified). Forecast value is framed as a cost-loss or false go / no-go decision (R02, R03; unverified). Operators trade service against hazard and ask for localised warnings (R05, preprint; unverified). The cutoff model rests on R08 and R09 (unverified).
- **Gap.** Searches on 2026-11-10 found no paper that coordinates protection modes across a decentralised constellation under per-spacecraft space-weather risk. That is a statement about those searches, not proof that none exists, and G3 showed no improvement, so it is not claimed as a contribution.

## 8. Limitations

- **Simulation only.** Synthetic spacecraft, tasks, links, faults and tolerances; a modelled hazard (GEO proxy flux, centred-dipole cutoff with a SYM-H shift measured only to about −150 nT, no shielding, local time or South Atlantic Anomaly). Nothing here is a radiation or flight-safety result.
- **One formation design:** four spacecraft in one plane, mostly 20 km apart; spreads tested on one storm. No other fleet size.
- **Small storm samples:** n = 1 – 6 storms per comparison (one for May 2024, the spread runs and the S11 replay; two for the re-sync test), one under GOES v3-0-3; seeds change no outcome. Intervals are wide, and modest gains are not excluded.
- **Untested or unrun:** B1 and B2 on storms; H4's with / without supervisor comparison; health uncertainty and manoeuvre feasibility in storm scenarios; the tight-schedule scenario (density could not create one, DL-096); RL (dropped, DL-105); low-thrust optimisation (deferred, DL-077); S06 (deferred).
- **Not measured:** CPU time and peak memory per algorithm (spec §10.2); a physical cost of protection cycling; false-degraded idle time in the utility.
- **Model limits of the data:** forecasts from data 600 s old and 5-min averages; P-C cannot forecast above its training range; the 17 Jan 2026 peak is 37 times that range.
- **B4 baseline defect:** the ownership split (§6) affects B4 under heavy cycling; it was reported, not repaired, in the frozen comparisons.
- **Literature:** unverified drafts, and the review covered Priority A and the G3 search only.
- **Unrecorded diagnostics:** the re-sync's spread-formation duplicate diagnosis and charged utilities came from unrecorded reruns of recorded configurations with identical results; the held-out B4 split diagnosis was a scratch rerun later replaced by the recorded N1; the 5 000 km byte explanation and the N5 hypothesis are unrecorded. Their pages (and DL-129) say so.

## 9. Reproduction

```bash
git clone https://github.com/Abdullah-Muz/AstraMesh.git && cd AstraMesh
uv sync --locked
uv run python scripts/data/fetch_data.py                 # pinned external data (hash-checked)
uv run python scripts/experiments/heldout_comparison.py --out <dir>   # e.g. the held-out storms
uv run python scripts/figures/make_figures.py            # F1 – F9 from committed results
uv run --group viz python scripts/figures/make_demo.py   # the MP4 (optional ffmpeg group)
```

Each results page names its script, clean commit and run time; [`GATE_P6.md`](results/GATE_P6.md) lists them all. The long experiments ran on one laptop (16 threads, 12 workers); an 8-day B3 + timeout run takes 20 – 96 min. CI runs the test suite (726 tests), not the experiments.

## 10. Conclusion

Inside this simulation, decentralised reconciliation is what preserves science when spacecraft drop out, whether through faults or storm protection, and a local supervisor with forecasts, look-ahead and hysteresis keeps unprotected hazard low at a science cost we could not distinguish from zero. Our attempts to do better by coordinating protection across the formation did not succeed on storms seen or unseen. In a close formation the spacecraft cross the hazard together, so there is rarely a free peer to take the work, and the remaining hazard sits at sharp onsets, where data latency limits what any protection design can do: fully on 18 Jul 2023 up to 600 s, partly on the other storms tested. The study's contribution is a reproducible platform and a set of bounded, mostly negative results, each traceable to a commit, configuration and data version. No novelty is claimed.

# Negative-result analysis

> **Status:** recorded 2026-11-15 from clean commit `f2a1b3a` (`git_dirty: false`; 96 runs, 31 min on 12 workers). Phase 6 increment 3 (DL-119 design, DL-120 code, DL-121 results). The hypotheses were written into DL-119 before any run; nothing was tuned and no method changed.
>
> **Earlier run superseded (disclosed):** a first recorded run from `796563b` could not explain two cases, so the trace was extended (DL-120 revision). Every output that does not depend on the trace is byte-identical between the two runs: the per-run table, N3 – N6, the config hashes and the latency series.
>
> Proposed for owner review.

## Setup

- **Runs:** planner B4, seed 1. Protection does not depend on the planner, and seeds change no outcome (DL-108, DL-115).
- **Configurations:** 80 runs reuse recorded configurations; a test checks their config hashes. They cover:
  - the five Phase 5 storms (QUIET, baseline, the three ablations and handover, plus shorter protection on four of them);
  - the six held-out storms (all seven arms);
  - the spread formation at 2 000 and 5 000 km.
- **Latency variants (N6):** 16 runs, latency 0, 300, 900 and 1 200 s on four storms. The variant series differ from the pinned ones only in `latency_s`.
- **Owner views:** in each worker, the one method where a B4 agent changes its view of a task's owner (`_respond_to_loss`) is wrapped read-only. Every call is recorded with its candidates, and outcomes are unchanged.
- **Hazard:** rebuilt per step from each run's own inputs. The run stops unless the rebuilt series equals the run's hazard total and unprotected intervals exactly.
- **Reproduce:** `uv run python scripts/experiments/negative_results.py --out <dir>`.
  - Files: [`negative_results.json`](negative_results.json) (every measure and trace detail), [`negative_runs.csv`](negative_runs.csv) (one row per run) and [`negative_results_meta.json`](negative_results_meta.json) (commit, config hashes, latency-series hashes).

**Terms:**

| Term | Meaning |
|---|---|
| Split | The four agents disagree at the end of the run on who owns a task |
| Onset interval | An unprotected interval that starts when the hazard episode starts |
| After-release interval | An unprotected interval that starts later, after a protection span inside the episode ended |
| Lost while available | A task completed in QUIET, not completed in the run, with some spacecraft in a tasking mode for its whole window |

## N1: the B4 ownership split (DL-115)

**How common** (11 storms; split tasks summed over the runs):

| Arm | Runs with a split | Split tasks | Lost while available |
|---|---|---|---|
| Baseline | 4 of 11 | 6 | 9 |
| Forecast handover | 5 of 11 | 7 | 9 |
| No forecast (A2) | 4 of 11 | 6 | 9 |
| No hysteresis (A3) | 4 of 11 | 6 | 8 |
| No look-ahead (A1) | 7 of 11 | 361 | 204 |
| Shorter protection | 8 of 10 | 267 | 22 |

Splits are rare in the baseline and common in the two arms that cycle protection, shorter protection and A1. Most split tasks would have been lost anyway, because no spacecraft was free during their windows. Large losses happen only in the two DL-115 runs: 172 tasks lost while available on 7 Oct 2024 and 23 on 17 Jan 2026. All 236 and 63 split tasks there were completed in QUIET. The spread run at 2 000 km also has 180 split tasks.

**How a split forms.** Every split task traced (299 in the two DL-115 runs, 2 in N2) follows one pattern. At the moment of the split (7 Oct 2024, 206 800 s; 17 Jan 2026, 195 500 s), all four spacecraft are in PROTECTIVE:

1. The owner (sc03) leaves the tasking modes and hands its tasks on by B4's rule. It chooses from its own view of its peers, which comes from their status reports (sent every 30 s). That view still shows the chosen peer in a tasking mode, although the peer is already protected. So the task moves to sc01 (7 Oct) or along sc00 → sc01 → sc02 (17 Jan) in sc03's view.
2. The chosen peer is itself protected by then. When it hears sc03 leave, it and every other peer run the same rule from their own views. They find no eligible spacecraft, because all are protected, so they keep sc03 as the owner.
3. B4 changes an owner only when the owner leaves the tasking modes or is believed lost. It has no handback and no step that compares owner views (DL-102). When the storm ends, sc03 believes sc02 (or sc01) owns the task, and the others believe sc03 does. Nobody observes it.

On 7 Oct 2024 sc03 had been back in a tasking mode for only 20 s, inside one of the short gaps of A1's cycling (N4). The peers did see it leave again: each ran its loss response for sc03 and found no candidate. **The smoke-run reading in DL-120, that the peers never saw sc03 return, was wrong.** The 7 Oct split has the same cause as 17 Jan.

**H1** (the split forms when spacecraft leave the tasking modes within one status interval, and each hands on by its own out-of-date view): **confirmed** for every split task traced.

## N2: B4's four recoverable losses (DL-100)

| Storm | Task | Cause |
|---|---|---|
| 18 Jul 2023 | TEC_0124 | **Split (H1).** At 179 100 s sc00 hands the task to sc01, which its view shows in STORM_WATCH. sc02 and sc03 also give it to sc01. sc01 is entering PROTECTIVE at the same moment, finds no candidate, and keeps sc00. Final views: sc01, sc00, sc01, sc01. |
| 18 Jul 2023 | TEC_0255 | **Split (H1),** the same events. |
| 18 Jul 2023 | TEC_0092 | **Protection during the observation.** The owner (sc01) protects at 179 100 s; the task's slots began at 178 930 s. B4 moves only tasks whose slots start after now, so no spacecraft is a candidate, including sc03, which stays in a tasking mode. |
| 23 Mar 2024 | TEC_0108 | **Protection during the observation.** The owner (sc00) protects at 213 300 s; the slots began at 213 260 s. |

**H2** (the same cause as H1): **confirmed for 2 of 4.** The other two could not be moved by any hand-on rule that needs a full slot.

## N3: where the no-forecast ablation's extra hazard falls

Extra unprotected hazard under A2 (no forecast) against the baseline, summed over the four spacecraft:

| Storm | Extra at onsets | Extra after a release |
|---|---|---|
| 29 Jul 2023 | 50 s | 0 |
| 29 Jan 2024 | 1 510 s | 0 |
| 23 – 24 Mar 2024 | 820 s | 0 |
| May 2024 | 1 340 s | 0 |
| 6 Jun 2024 | 680 s | 0 |
| 25 Oct 2024 | 290 s | 0 |
| 30 Mar 2025 | 300 s | 0 |
| 9 Nov 2025 | 10 s | 0 |
| 17 Jan 2026 | 1 100 s | 0 |

18 Jul 2023 and 7 Oct 2024 have none. **H3** (A2's extra hazard falls at onsets): **confirmed.** All of it is onset time. With P-A, the latest measurement, protection begins at about the time a record above tolerance arrives, later than with the P-B forecast of the next hour's maximum.

## N4: why removing look-ahead cycles but adds little hazard

Protected spans, by where they start and end relative to hazard (all 11 storms, four spacecraft):

| | Spans | Start and end outside hazard | Start inside, end outside | Start outside, end inside | Start and end inside |
|---|---|---|---|---|---|
| Baseline | 66 | 57 | 9 | 0 | 0 |
| No look-ahead (A1) | 336 | 298 | 32 | 5 | 1 |

On the storms where A1 cycles most (18 Jul 2023, 29 Jul 2023, 6 Jun 2024, 7 Oct 2024 and 25 Oct 2024), each spacecraft's median protected span is 47 min, with a median gap of 50 – 110 s.

Without look-ahead, the radiation input follows the spacecraft's current position. During these storms that position is above the cutoff except briefly near each equator crossing. Protection therefore releases for about a minute twice an orbit (a 47 min span plus a 1 min gap is half the 95 min orbit), and hazard rarely falls in those gaps.

A1's extra unprotected hazard (against the baseline) appears on six storms:

| Storm | Extra at onsets | Extra after a release |
|---|---|---|
| 29 Jul 2023 | 0 | 390 s |
| 23 – 24 Mar 2024 | 80 s | 590 s |
| May 2024 | 40 s | 0 |
| 25 Oct 2024 | 300 s | 110 s |
| 9 Nov 2025 | 520 s | 0 |
| 17 Jan 2026 | 900 s | 0 |

**H4** (most entries start and end inside a hazard episode): **refuted.** 89 % of A1's spans start and end outside hazard. The cycling follows the orbit, not the hazard, which is why it adds little hazard. Its short gaps are also where the N1 splits form.

## N5: the unprotected hazard that spreading adds

Baseline unprotected hazard, all at onsets (s, sc00 / sc01 / sc02 / sc03):

| Spacing | Unprotected hazard |
|---|---|
| 20 km | 0 / 0 / 0 / 0 |
| 2 000 km | 0 / 0 / 420 / 0 |
| 5 000 km | 0 / 140 / 280 / 150 |

The leading spacecraft (sc00) never has unprotected hazard. The others do once they trail by thousands of kilometres. With 2 000 km spacing that is only sc02, the 50 pfu spacecraft. Why trailing spacecraft are protected late was not established: each spacecraft uses its own track's look-ahead. Like A2's extra hazard, all of this is at onsets.

## N6: data latency at sharp onsets

Baseline unprotected hazard by series latency (s, summed over the four spacecraft; 600 s is the recorded setting). Every interval is at an onset.

| Storm | 0 s (non-causal) | 300 s | 600 s | 900 s | 1 200 s |
|---|---|---|---|---|---|
| 18 Jul 2023 | 0 | 900 (300 each, sc00 – sc02) | 1 800 (600 each) | 2 000 | 2 000 |
| 6 Jun 2024 | 0 | 0 | 480 | 1 080 | 1 740 |
| 30 Mar 2025 | 0 | 0 | 120 | 420 | 650 |
| 17 Jan 2026 | 0 | 200 | 500 | 1 190 | 1 610 |

At 900 and 1 200 s the first records arrive after t = 0, and no run entered protection in its first hour, so there is no start-up artefact.

**H5** (the onset hazard falls as latency falls, and is 0 at 300 s where the onset is latency-bound): **partly confirmed.**
- It falls with latency on all four storms and is 0 at 0 s on all of them.
- At 300 s, the earliest physical value, it is 0 on 6 Jun 2024 and 30 Mar 2025 only.
- **18 Jul 2023:** each spacecraft's unprotected time equals the latency (300 s at 300 s, 600 s at 600 s). The hazard begins in the same 5-min record that first shows it, so any physical latency is lost in full.
- **17 Jan 2026:** sc03 keeps 200 s at 300 s latency.

## Hypotheses

| | Hypothesis (DL-119) | Outcome |
|---|---|---|
| H1 | The split forms when spacecraft leave the tasking modes within one status interval and hand on by out-of-date views | **Confirmed** for every split task traced |
| H2 | B4's recoverable losses have the H1 cause | **Confirmed for 2 of 4;** the other 2 were protected after their observation had begun |
| H3 | A2's extra hazard falls at onsets | **Confirmed;** all of it |
| H4 | Without look-ahead, entries start and end inside hazard | **Refuted;** 89 % of spans start and end outside hazard |
| H5 | Onset hazard falls with latency and is 0 at 300 s where latency-bound | **Partly confirmed;** 0 at 300 s on 2 of 4 storms |

## What this explains

1. **Why B4 sometimes loses tasks a peer could do.** In a close formation every spacecraft protects at once, and B4's hand-on runs on views up to one status interval old. The owner and its successor can then disagree about ownership for good. Cycling protection (A1, shorter protection) makes this frequent. B3 + timeout re-auctions and is not affected. This is a defect of the B4 baseline, not of protection.
2. **Why the remaining baseline hazard is at onsets.** Every unprotected interval in every baseline, spread and latency run starts with its hazard episode. It is bounded by the data latency: zero on every storm at 0 s, and on two storms at 300 s.
3. **Why look-ahead matters little for hazard but much for cycling.** Without it, protection follows the orbit, not the hazard.

**Possible fixes (future work, not built; DL-119):** an ownership re-sync or handback in B4; status reports sent on mode changes rather than only every 30 s; hand-ons that the successor acknowledges; lower-latency data. Any of them would be a new method and would need its own design, tuning and held-out test.

## Limits

- B4 and seed 1 only; B3 + timeout was not traced.
- The trace shows what each agent decided and from which view. It does not replay message timing, so "up to one status interval old" is inferred from the 30 s status period and the recorded views.
- N2 classifies only the four tasks DL-100 named. N1's "lost while available" counts include tasks lost for the N2 slot reason.
- The latency variants change only the delivery latency. The forecasts and the 5-min averaging are unchanged, and 0 s is a non-causal bound.
- N5 does not establish why trailing spacecraft are protected late.

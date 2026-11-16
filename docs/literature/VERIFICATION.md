# Literature verification pack

> **Status:** prepared 2026-11-16 for owner verification (DL-132, approved 2026-11-16). **Verified 2026-11-16 (DL-133):** the owner approved every check, V1 – V29 and M1 – M20 ("all approved"); V29 was accepted as worded, without a repeat search. Every literature row in [`LITERATURE_REVIEW.md`](../LITERATURE_REVIEW.md) is an assistant draft that the owner has not verified, carried since DL-049. This pack lists the claims that AstraMesh actually relies on, each with the place in the source to check, so they can be verified without re-reading every paper. It adds no new readings.

## How to use it

1. Open the source at the location given. Most sources are local PDFs the owner downloaded (`data/literature/`, Git-ignored), and the rest are open links.
2. Compare the source with the **claim as AstraMesh states it**. The quotes and section references come from the per-item reports in this folder.
3. Mark the outcome:
   - **✓** if the source supports the claim as worded;
   - **✗ + correction** if the source says something different;
   - **?** if you cannot tell from the source.

   Edit the Outcome column, or reply with the check IDs (for example "V1–V9 ✓, V12 ✗: …").

**Order of importance:**

- **Part 1** covers numbers and rules built into the simulation code. If one is wrong, results change.
- **Part 2** covers claims made in the released report (§7).
- **Part 3** is the bibliographic metadata, which the spec requires before any row enters `references.bib`.

The remaining analysis cells in `LITERATURE_REVIEW.md` are not listed here. They stay drafts unless you read the full per-item reports.

## Sources and where to find them

| ID | Short reference | Copy to open |
|---|---|---|
| D01 | NASA, *What is Starling?* (web page, revised 2026-03-19) | https://www.nasa.gov/smallspacecraft/what-is-starling/ |
| D02 | Friesen (NASA), *What is NASA's Distributed Spacecraft Autonomy?* (2025) | https://www.nasa.gov/centers-and-facilities/ames/what-is-nasas-distributed-spacecraft-autonomy/ |
| D10 | Miller et al. 2024, Starling flight results (SSC24-I-06) | https://ntrs.nasa.gov/citations/20240006994 |
| D11 | Adams et al. 2026, DSA extended mission (SSC26-RAII-07) | https://ntrs.nasa.gov/citations/20260005696 |
| P01S | Adams et al. 2024, DSA on Starling 1.0 (SSC24-WV-01) | `data/literature/P01S.pdf` |
| P02 | Zilberstein et al. 2024, ICAPS (conference version of P19) | `data/literature/P02_Zilberstein_2024.pdf` |
| P03 | Song et al. 2023, *Algorithms* 16(2):114 | `data/literature/P03_Song_2023.pdf` |
| P06 | Choi, Brunet, How 2009, *IEEE T-RO* 25(4):912–926 | `data/literature/P06_Choi_2009.pdf` |
| P08 | Olfati-Saber, Fax, Murray 2007, *Proc. IEEE* 95(1) (read as TR06-004) | `data/literature/P08_OlfatiSaber_TR06-004.pdf` |
| P09 | Reid et al. 2026, AAAI SSS 2026 pp. 97–104 | `data/literature/P09_Reid_2026.pdf` |
| P19 | Zilberstein et al. 2025, *JAIR* 82:169–208 | `data/literature/P19_Zilberstein_2025.pdf` |
| P22 | Azadmanesh et al. 2026, *Aerospace* 13(2):176 | `data/literature/P22_Azadmanesh_2026.pdf` |
| R01 | Kang, Ramanathan, Abdu Jyothi 2025, arXiv:2509.19647 | https://arxiv.org/abs/2509.19647 |
| R02 | DeStefano, Goodman, Suggs 2018, NTRS 20180004195 (poster) | https://ntrs.nasa.gov/citations/20180004195 |
| R03 | Owens, Lockwood, Barnard 2020, *Space Weather* 18 | `data/literature/R03.pdf` |
| R04 | Cowlishaw, Riccardi, Arulselvan 2024, *IEEE JSTARS* 17 | https://doi.org/10.1109/JSTARS.2024.3459630 |
| R05 | LaNeve et al. 2025, arXiv:2512.22424 | https://arxiv.org/abs/2512.22424 |
| R06 | Bruno et al. 2015, arXiv:1511.00530 | https://arxiv.org/abs/1511.00530 |
| R08 | Leske, Mewaldt, Stone, von Rosenvinge 2001, *JGR* 106(A12) | `data/literature/R08.pdf` |
| R09 | Smart and Shea 1985, *Handbook of Geophysics and the Space Environment*, ch. 6 | `data/literature/R09.pdf` |

## Part 1: values and rules built into the code

If any of these fails, the affected results would need a design entry and a rerun.

| Check | Source, location | Claim as AstraMesh states it | Where AstraMesh uses it | Outcome |
|---|---|---|---|---|
| V1 | R08 §3.2 | The first-order Dst correction subtracts **Dst / 19.11** (degrees, Dst in nT), i.e. 0.052° per nT. | Storm slope `1 / 19.11` °/nT (`core/config.py` `storm_slope_deg_per_nt`; `forecast/access.py`) | ✓ |
| V2 | R08 §3.2, Fig. 7 | At Dst = 0 the 8–15 MeV/n He (Z2) cutoffs fit a circle of radius **25.85 ± 0.04°** (north) and **25.82 ± 0.04°** (south), i.e. a cutoff near **64.2°** invariant latitude. | Quiet cutoff, first part of 65.2° | ✓ |
| V3 | R08 Fig. 3 (November 1997 panel) | The ~10 MeV proton cutoffs are plotted with a **−1° offset** to overlay the He cutoffs, so ~10 MeV protons are cut off about 1° poleward of the He. **This is AstraMesh's reading of a plotting offset, not a value R08 states.** Please judge whether it is fair. | Quiet cutoff 64.2° + 1° = **65.2°** (`quiet_cutoff_deg`) | ✓ |
| V4 | R08 §4 (with Fig. 5) | No period had Dst below about −150 nT. "Linear extrapolation (which may not be warranted) from Figure 5 suggests that a cutoff suppression of 15° might be associated with a geomagnetic storm with Dst around −300." | 15° cap on the storm-time shift (`max_shift_deg`) | ✓ |
| V5 | R08 §2, Fig. 2 | The cutoff is the invariant latitude (cos²Λ = 1/L) at which the count rate falls to half its mean above 70°, and the transition is sharp (most of the rise within ~3°). | Step access model (`forecast/access.py`); invariant latitude from L (`dynamics/geomagnetic.py`) | ✓ |
| V6 | R06 §4, Figs. 2–4 | Cutoff variations correlate with Kp, Dst and SYM-H at **0.80, 0.78, 0.78**; the cutoff at ~80 MeV moved about 6° equatorward. | SYM-H as the Dst proxy | ✓ |
| V7 | R09 p. 6-12, eq. 6.17 | Vertical Störmer cutoff **P_c = 14.9 cos⁴λ / R² GV**. | RK-02 cross-check (`tests/physics_validation/test_per_spacecraft_risk.py`) | ✓ |
| V8 | R09 p. 6-12, eq. 6.18 and text | **P_c = 16.0 L⁻² GV**, with "a practical limit … within the domain of the L = 4 shell". | Why the quiet cutoff comes from R08, not from a dipole formula; the dipole is labelled a model | ✓ |
| V9 | P06 Table I (p. 917) against [`P06.md`](P06.md) §3(c) | The 17-row conflict-resolution table as transcribed in `P06.md` §3(c) matches the printed table row by row. | B3 Phase 2 (`agents/cbba.py`) | ✓ |
| V10 | P06 Eq. (5) (Sec. IV-B) | Timestamp rule: s_ik = τ_r if g_ik = 1, otherwise max over neighbours m of s_mk. | B3 timestamp update | ✓ |
| V11 | P06 Eq. (6), Sec. IV-B p. 916 | After an outbid, the agent releases the outbid task and every task added after it ("the agent also needs to release all the tasks added after the outbid task"). | B3 bundle release | ✓ |
| V12 | P06 Theorem 1 (p. 919) and Sec. V-C | Convergence assumes a DMG score, synchronised conflict resolution and a static network of diameter D; T_C ≤ N_min·D. Dynamic networks and asynchrony are discussed in prose only. | B3 run in synchronous rounds; REPORT §7 | ✓ |
| V13 | P06 Eqs. (20)–(21) and the whole paper | The paper gives **no local stopping rule**; convergence is defined after the fact. | B3 has no stop rule, labelled an implementation choice (DL-045) | ✓ |

## Part 2: claims in the released report (REPORT §7)

The released [`REPORT.md`](../REPORT.md) §7 marks each of these unverified. A ✓ here lets that label be removed for the row.

| Check | Source, location | Claim as AstraMesh states it | Outcome |
|---|---|---|---|
| V14 | D01, "Starling Technology Demonstrations: DSA" | NASA describes DSA as coordinating GPS-signal selection for ionospheric observation "across all Starling spacecraft", by sharing state over the crosslink network; the mission uses four CubeSats. | ✓ |
| V15 | D10 pp. 3, 7; P01S Table 1 | **DSA ran on three spacecraft**: Starling-1 never joined the DSA network (propulsion leak, uplink limit). See discrepancy 1 below. | ✓ |
| V16 | D10 p. 7 (Fig. 7); P01S pp. 4–5 (Fig. 3, Eqs. 1–4) | DSA allocates GPS channels by a MILP that each spacecraft solves from shared rewards at 1 Hz. | ✓ |
| V17 | D10, D11, P01S (search the PDFs for "radiation", "space weather", "safe mode", "health") | None of the three describes a space-weather response, protection modes or health beliefs. D11 p. 5 mentions safe mode only as something the radio duty cycle avoids for battery reasons. | ✓ |
| V18 | D11 p. 2 | The swarm plans and executes without enforced consensus: "This approach prioritizes agility of response over consistency of the swarm's behavior". | ✓ |
| V19 | P06 (whole paper) | No packet-loss, delay or clock model is analysed. | ✓ |
| V20 | P03 §2.3, §3.1 | Links are bidirectional ISLs (intra-plane always on, inter-plane by line of sight); latency and loss are not modelled; clocks are assumed synchronised. | ✓ |
| V21 | P19 §5.3 | No explicit crosslink topology, visibility, latency, bandwidth or loss model; message volume is reported only as a cost. | ✓ |
| V22 | P19 §1, p. 172 | P19 extends the ICAPS 2024 conference paper (P02): "This article extends on a previously published conference paper". | ✓ |
| V23 | P09 pp. 3–5 | No inter-agent communication model (no messages, crosslinks, latency, loss or partitions). Satellites are modelled by a restaurant-waiter analogy, with one permanent agent loss per run. | ✓ |
| V24 | P22 §3.1, §3.4 item 4, Fig. 1A | Star topology (followers talk only to the leader); the consensus logic "assumes instantaneous availability of data from all followers". | ✓ |
| V25 | R01 §3.3 (Figs. 4, 5, 9), §3.4 (Fig. 8) | Altitude change varies strongly between orbital planes of the same inclination. Only 30 of the 236 most affected satellites on 11 May were also among the most affected on 12 May. | ✓ |
| V26 | R02 (poster, method panel) | Launch decisions are framed as P(false go) against P(false no-go) from GOES integral proton flux. | ✓ |
| V27 | R03 §2, Eq. 2, Fig. 1 | Forecast value is given by a cost-loss analysis, V = 100 × (T_F − T_CL) / (T_CL − T_P). A perfect CME arrival-time forecast adds value only for 0.0015 < C/L < 0.0442. | ✓ |
| V28 | R05 p. 19, §6 | One operator avoided safe mode because "the loss of services would outweigh the risk of damage"; operators asked for more accurate, localised warnings. | ✓ |
| V29 | (optional) web search | The 2026-11-10 searches found no paper that coordinates protection modes across a decentralised constellation under per-spacecraft space-weather risk. The report states this as a fact about those searches only; a repeat search would refresh it. | ✓ |

## Part 3: bibliographic metadata

Check the title, authors, year and venue against the publisher or registry record (DOI, NTRS or arXiv). The values below are as recorded in `LITERATURE_REVIEW.md` and the per-item reports.

| Check | ID | Title as recorded | Authors | Venue, year | Outcome |
|---|---|---|---|---|---|
| M1 | P06 | Consensus-Based Decentralized Auctions for Robust Task Allocation | Choi, Brunet, How | *IEEE Trans. Robotics* 25(4):912–926, 2009; doi:10.1109/TRO.2009.2022423 | ✓ |
| M2 | P03 | On-Board Decentralized Observation Planning for LEO Satellite Constellations | Song, Chen, Yang, Zuo, Xu, Chen | *Algorithms* 16(2):114, 2023; doi:10.3390/a16020114 | ✓ |
| M3 | P09 | A Decentralized Framework for Resource-Constrained Task Redistribution | Reid, Reliford, Andy, Smith, Alfred, Phillips | AAAI SSS 2026, pp. 97–104; doi:10.1609/aaaiss.v8i1.42523 (not printed in the PDF) | ✓ |
| M4 | P19 | Decentralized, Decomposition-Based Observation Scheduling for a Large-Scale Satellite Constellation | Zilberstein, Rao, Salis, Chien | *JAIR* 82:169–208, 2025; doi:10.1613/jair.1.16997 | ✓ |
| M5 | P02 | same title as P19 | same authors as P19 | ICAPS 2024; doi:10.1609/icaps.v34i1.31535 | ✓ |
| M6 | P22 | Decoupling Global and Local Faults in Satellite Swarms Using Smart-Freeze Adaptation and Isolation-Priority Logic | Azadmanesh, Georgiev, Kolev, Todorov | *Aerospace* 13(2):176, 2026; doi:10.3390/aerospace13020176 | ✓ |
| M7 | P08 | Consensus and Cooperation in Networked Multi-Agent Systems | Olfati-Saber, Fax, Murray | *Proc. IEEE* 95(1):215–233, 2007; doi:10.1109/JPROC.2006.887293 | ✓ |
| M8 | P01S | Advancing Autonomy in Distributed Space Systems: Results from the Distributed Spacecraft Autonomy Experiment on Starling 1.0 (SSC24-WV-01) | Adams, Iatauro, Kempa, Levinson, Frank, Gridnev, Lassiter | SmallSat 2024; doi:10.26077/kdtp-6540 | ✓ |
| M9 | D10 | Starling CubeSat Swarm Technology Demonstration Flight Results (SSC24-I-06) | Miller, Adams, Alem, Cannon, Grashuis, Hendriks, Hwang, Iatauro, Pires, Kruger, D'Amico | SmallSat 2024; NTRS 20240006994 | ✓ |
| M10 | D11 | Results from NASA's Distributed Spacecraft Autonomy Project's Extended Mission on Starling (SSC26-RAII-07) | Adams, Iatauro, Kempa, Dalal, Gridnev, Ho, Lassiter | SmallSat 2026; NTRS 20260005696 | ✓ |
| M11 | D01 | What is Starling? | NASA (no byline) | NASA web page, revised 2026-03-19 | ✓ |
| M12 | D02 | What is NASA's Distributed Spacecraft Autonomy? | Tara Friesen | NASA web page, 2025-08-05 | ✓ |
| M13 | R01 | A Deep Dive into the Impact of Solar Storms on LEO Satellite Networks | Kang, Ramanathan, Abdu Jyothi | arXiv:2509.19647v1, 2025 (preprint) | ✓ |
| M14 | R02 | The Probability of False Go/No-Go Determined by GOES Proton Flux: Proposed Launch Constraints for Avoiding Damaging Solar Energetic Particle Events | DeStefano, Goodman, Suggs | NTRS 20180004195, 2018 (poster) | ✓ |
| M15 | R03 | The Value of CME Arrival Time Forecasts for Space Weather Mitigation | Owens, Lockwood, Barnard | *Space Weather* 18, e2020SW002507, 2020 (Commentary); doi:10.1029/2020SW002507 | ✓ |
| M16 | R04 | Optimizing Participant Selection for Fault-Tolerant Decision Making in Orbit Using Mixed Integer Linear Programming | Cowlishaw, Riccardi, Arulselvan | *IEEE JSTARS* 17:16961–16969, 2024; doi:10.1109/JSTARS.2024.3459630 | ✓ |
| M17 | R05 | Brace for Impact: A Review of Mitigation Decisions of Critical Infrastructure Operators During the 2024 Solar Maximum | LaNeve, Oughton, Rivera, Wilkerson, Weigel, Thomas, Gaunt | arXiv:2512.22424v1, 2025 (preprint) | ✓ |
| M18 | R06 | PAMELA's measurements of geomagnetic cutoff variations during solar energetic particle events | Bruno et al. (PAMELA collaboration) | arXiv:1511.00530v1, 2015 (preprint) | ✓ |
| M19 | R08 | Observations of geomagnetic cutoff variations during solar energetic particle events and implications for the radiation environment at the Space Station | Leske, Mewaldt, Stone, von Rosenvinge | *JGR* 106(A12):30011–30022, 2001; doi:10.1029/2000JA000212 | ✓ |
| M20 | R09 | Galactic Cosmic Radiation and Solar Energetic Particles (ch. 6) | Smart, Shea | *Handbook of Geophysics and the Space Environment*, ed. Jursa, AFGL, 1985 | ✓ |

## Discrepancies found while preparing this pack

1. **Starling: four CubeSats, but DSA on three.** REPORT §7 and `LITERATURE_REVIEW.md` Finding 1 say Starling 1.0 "flew four CubeSats coordinating dual-band GPS ionospheric observations … with distributed onboard planning". That follows D01. However, D10 (pp. 3, 7) and P01S (Table 1) say Starling-1 never joined the DSA network, so the coordination ran on three spacecraft. **Proposed wording:** "flew four CubeSats; its distributed onboard planning of dual-band GPS ionospheric observations ran on three of them". This does not change any result or the no-novelty conclusion. If V15 is confirmed, the fix is a dated correction to the released report.

## After verification

What follows from the outcomes is proposed in DL-132:

- A row whose Part 1 to 3 checks all pass is marked **key claims verified (owner, date)** in `LITERATURE_REVIEW.md`. Its "unverified" label is removed from REPORT §7, and its metadata may enter `references.bib`.
- **Any ✗ in Part 1** gets its own design entry. That entry says which results the value affects and whether they need a rerun.
- **Any ✗ in Parts 2 or 3** is fixed in the per-item report, the review table and REPORT §7, with a dated note.

# Literature Review Matrix

> **Owner:** Abdullah Muzher · **Status:** STARTED — metadata only; no paper has been reviewed yet · **Spec:** §15 · **Last updated:** 2026-11-03

## Rules

- A row's **bibliographic metadata** may be marked *verified* only when checked against the publisher/DOI registry. A DOI resolving is not proof that the paper has been read.
- Analysis columns (`problem` … `AstraMesh_overlap`) are filled **only from a full-text reading**, never from abstracts or memory. Empty means *not yet reviewed*.
- Only rows with verified metadata may be copied into `references.bib`.

## Status key

- `metadata: crossref` — title, authors, year, and venue retrieved from the Crossref API for the DOI on 2026-11-03.
- `metadata: pending` — not yet checked.
- `review: not started` / `in progress` / `complete`.

## Priority A — before algorithm design (spec §15.3)

| reference_id | verified_title | authors | year | doi/url | metadata | review | replication_priority |
|---|---|---|---:|---|---|---|---|
| P01 | Advancing Autonomy in Distributed Space Systems: Insights From On-Orbit Testing with the Starling 1.0 Mission *(title as listed in spec; unverified)* | — | 2024 | https://ntrs.nasa.gov/citations/20240004120 | pending (NTRS record, no DOI) | not started | — |
| D01 | What is Starling? *(NASA web page)* | NASA | — | https://www.nasa.gov/smallspacecraft/what-is-starling/ | pending | not started | — |
| D02 | What Is NASA's Distributed Spacecraft Autonomy? *(NASA web page)* | NASA | — | https://www.nasa.gov/centers-and-facilities/ames/what-is-nasas-distributed-spacecraft-autonomy/ | pending | not started | — |
| P06 | Consensus-Based Decentralized Auctions for Robust Task Allocation | Choi, Brunet, How | 2009 | https://doi.org/10.1109/TRO.2009.2022423 | crossref — *IEEE Transactions on Robotics* | not started | high (baseline B3) |
| P03 | On-Board Decentralized Observation Planning for LEO Satellite Constellations | Song, Chen, Yang, Zuo, Xu, Chen | 2023 | https://doi.org/10.3390/a16020114 | crossref — *Algorithms* | not started | — |
| P09 | A Decentralized Framework for Resource-Constrained Task Redistribution | Reid, Reliford, Andy, Smith, Alfred, Phillips | 2026 | https://doi.org/10.1609/aaaiss.v8i1.42523 | crossref — *Proceedings of the AAAI Symposium Series* | not started | — |
| P19 | Decentralized, Decomposition-Based Observation Scheduling for a Large-Scale Satellite Constellation | Zilberstein, Rao, Salis, Chien | 2025 | https://doi.org/10.1613/jair.1.16997 | crossref — *Journal of Artificial Intelligence Research* | not started | — |
| P21 | Decentralized Proof-of-Benefit mission negotiation method for satellite clusters | Ye, Dong | 2026 | https://doi.org/10.1016/j.asr.2026.05.020 | crossref — *Advances in Space Research* | not started | — |
| P22 | Decoupling Global and Local Faults in Satellite Swarms Using Smart-Freeze Adaptation and Isolation-Priority Logic | Azadmanesh, Georgiev, Kolev, Todorov | 2026 | https://doi.org/10.3390/aerospace13020176 | crossref — *Aerospace* | not started | — |
| P08 | Consensus and Cooperation in Networked Multi-Agent Systems | Olfati-Saber, Fax, Murray | 2007 | https://doi.org/10.1109/JPROC.2006.887293 | crossref — *Proceedings of the IEEE* | not started | — |

**Related-version note:** P02 (https://doi.org/10.1609/icaps.v34i1.31535, *ICAPS 2024*) has the same title and author list as P19 per Crossref. Spec §15.1 already flags that P19 must not be counted as an independent method without comparison to P02.

## Analysis columns (spec §15.3) — to be filled from full-text review

| reference_id | problem | agent_info | networking_assumptions | physics | fault_model | safety_model | method | baselines | metrics | scale | key_limitations | AstraMesh_overlap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P01 | | | | | | | | | | | | |
| P06 | | | | | | | | | | | | |
| P03 | | | | | | | | | | | | |
| P09 | | | | | | | | | | | | |
| P19 | | | | | | | | | | | | |
| P21 | | | | | | | | | | | | |
| P22 | | | | | | | | | | | | |
| P08 | | | | | | | | | | | | |

## Priorities B–D

Not yet entered. See spec §15.1–§15.3 for the full list (P02, P04, P05, P07, P10–P18, P20, P23, D03–D09).

# Dataset Registry

> **Owner:** Abdullah Muzher · **Status:** Phase 4: five bounded datasets downloaded and pinned (DS-02, DS-06, DS-07; forecast training data DS-08, DS-09); Phase 5: DS-10 (MSIS drivers); GloTEC and COSMIC-2 left out of Phase 4 (DL-071) · **Spec:** §8 · **Last updated:** 2026-11-10

## Rules (spec §8.2)

- One record per dataset. A dataset may not be used in an experiment until its record is complete for the fields that experiment depends on.
- **License/terms must be confirmed from the provider before download.** "UNVERIFIED" means not yet checked; do not assume government or open-access data is unrestricted.
- Raw data lives under `data/` (Git-ignored). Record retrieved file names and SHA-256 hashes here; never commit the files.
- Do **not** download the full ESA-ADB (spec §8.1, §8.2): start with a bounded OPS-SAT-AD sample after measured resource sizing.
- **Fetching (DL-063):** every downloaded file is listed in [`configs/data/sources.yaml`](../configs/data/sources.yaml) with its URL, size, the provider's MD5 (where published) and our SHA-256. `uv run python scripts/data/fetch_data.py` downloads into `data/raw/<id>/` and keeps a file only if all its pins match; `--verify-only` re-checks local copies without network. Experiments open files only through `require_pinned`.

## Summary

| ID | Dataset | License / terms | Downloaded | Phase |
|---|---|---|---|---|
| DS-01 | ESA Anomaly Dataset (ESA-ADB) | CC BY 3.0 IGO per the `LICENSE` file in `github.com/esa/anomaly-dataset`; Zenodo record 12528696 carries **no** license field — **confirm the license applies to the data files** | No — sized only (DL-062: 11.6 GB compressed, more than the 14 GB RAM available in WSL once unpacked) | 4 |
| DS-02 | ESA OPS-SAT-AD | CC BY 4.0 (Zenodo metadata) **and** MIT (the record's `LICENSE` file, © 2024 KP Labs); both permit use and require attribution — we meet both | **Yes** (19.5 MB, pinned 2026-11-04) | 4 |
| DS-03 | NOAA GloTEC | UNVERIFIED | No | Left out of Phase 4 (DL-071) |
| DS-04 | CelesTrak GP / OMM | UNVERIFIED | No | 1+ |
| DS-05 | UCAR COSMIC-2 | UNVERIFIED (check data-use / citation policy) | No | Left out of Phase 4 (DL-071) |
| DS-06 | NASA OMNI / SPDF | No restrictions stated; citation (DOI) and acknowledgement requested | **Yes** (May 2024 1-min, 13.4 MB, pinned 2026-11-04) | 4–5 |
| DS-07 | NOAA NCEI GOES-18 SEISS/SGPS L2 | File metadata: "These data may be redistributed and used without restriction." | **Yes** (8–15 May 2024, 5-min, 5.0 MB, pinned 2026-11-04) | 4–5 |
| DS-08 | NOAA NCEI GOES-18 SEISS/SGPS L2 (forecast training) | As DS-07 (same metadata statement in every file) | **Yes** (1 Jan 2023 – 30 Apr 2024, 5-min, 486 files, 293 MB, pinned 2026-11-05) | 4–5 |
| DS-09 | NASA OMNI / SPDF (forecast training) | As DS-06 | **Yes** (Jan 2023 – Apr 2024 1-min, 16 files, 210 MB, pinned 2026-11-05) | 4–5 |
| DS-10 | NASA OMNI2 hourly (F10.7, ap) | As DS-06 | **Yes** (2023 and 2024, 2 files, 5.8 MB, pinned 2026-11-10) | 5 |
| DS-11 | NOAA NCEI GOES-18 SEISS/SGPS L2 (held-out storms) | As DS-07 (same metadata statement in the files) | **Yes** (1 Jun 2024 – 31 Oct 2026, 5-min, 883 files, 419 MB, pinned 2026-11-13) | 6 |
| DS-12 | NASA OMNI / SPDF (held-out storms) | As DS-06 | **Yes** (Jun 2024 – Oct 2026 1-min, 29 files, 381 MB, pinned 2026-11-13) | 6 |

## Record template

```yaml
id: DS-XX
name:
owner_provider:
url:
doi:
version_or_date:
retrieved_utc:              # when downloaded
retrieved_files:            # [{name, sha256, bytes}]
license_terms:              # exact license name + URL, or terms page
license_verified_utc:
citation_required:          # exact citation text if the provider specifies one
sampling_interval:
units:
time_conventions:           # time scale, epoch, cadence
geospatial_conventions:     # frame, grid, coordinate system
missingness_quality_flags:
event_labels:
expected_storage_gb:
expected_ram_gb:
intended_experiment:
leakage_risks:
domain_transfer_caveats:
```

## Records

### DS-01 — ESA Anomaly Dataset (ESA-ADB)

```yaml
id: DS-01
name: ESA Anomaly Dataset
owner_provider: European Space Agency
url: https://github.com/esa/anomaly-dataset ; https://zenodo.org/records/12528696
doi: 10.5281/zenodo.12528696
version_or_date: "1.0 (Zenodo, published 2024-06-25)"
retrieved_utc: null
retrieved_files: null        # Zenodo lists ESA-Mission1.zip (~3.78 GB), ESA-Mission2.zip (~4.10 GB), ESA-Mission3.zip (~3.73 GB) — sizes from Zenodo metadata, not downloaded
license_terms: "CC BY 3.0 IGO per repository LICENSE file; Zenodo record has no license field — UNCONFIRMED for data files"
license_verified_utc: null
expected_storage_gb: ">11.6 compressed (Zenodo metadata); uncompressed size unknown"
intended_experiment: "Phase 4 telemetry anomaly detection (H-C), sampled subset only"
domain_transfer_caveats: "Separate real missions; not AstraMesh's four fictional spacecraft (spec §7.2, §8.2)"
```

### DS-02 — ESA OPS-SAT-AD

```yaml
# Recorded before download (2026-11-03); the measured record below supersedes
# retrieved_utc, license_terms and license_verified_utc.
id: DS-02
name: "OPSSAT-AD - anomaly detection dataset for satellite telemetry"
owner_provider: ESA OPS-SAT / dataset authors (see Zenodo record)
url: https://zenodo.org/records/15108715
doi: 10.5281/zenodo.15108715
version_or_date: "Zenodo publication date 2024-06-24 (no version string in metadata)"
retrieved_utc: null
license_terms: "CC BY 4.0 (Zenodo record metadata)"
license_verified_utc: "2026-11-03 (metadata only; confirm against the record's LICENSE file at download)"
intended_experiment: "Phase 4 initial local anomaly-detection experiments"
leakage_risks: "Use the benchmark's official splits; do not shuffle across time (spec §7.4)"
domain_transfer_caveats: "An anomaly label is not a confirmed failure (spec §8.1)"
```

Measured from the downloaded files (2026-11-04):

```yaml
retrieved_utc: "2026-11-04"
retrieved_files:   # sha256 and sizes pinned in configs/data/sources.yaml; provider md5 matched
  - segments.csv (18 987 091 B): 303 493 rows; columns channel, timestamp, value, label, sampling, anomaly, segment, train
  - dataset.csv (507 550 B): 2 123 segments x 18 engineered features + segment, anomaly, train, channel, sampling
  - LICENSE (1 091 B): MIT License for OPS-SAT Dataset, Copyright (c) 2024 KP Labs
license_terms: "CC BY 4.0 (Zenodo record metadata) and MIT (LICENSE file in the record). Comply with both: cite the dataset and paper (D05), keep the MIT notice with any redistributed copy (we redistribute nothing)."
license_verified_utc: "2026-11-04"
citation_required: "Ruszczak et al., The OPS-SAT benchmark for detecting anomalies in satellite telemetry, Scientific Data (2025), doi:10.1038/s41597-025-05035-3; dataset doi:10.5281/zenodo.15108715"
sampling_interval: "1 s (793 segments) or 5 s (1 330 segments); segment length 8-1 040 samples, median 70"
time_conventions: "ISO 8601 UTC timestamps, 2022-01-04 to 2022-06-02"
event_labels: "`anomaly` (0/1) per segment: 434 anomalous of 2 123 (20.4%). The `label` column is the string 'anomaly' on every row and is NOT the label."
channels: "9 channels CADC0872-CADC0894 (paper: 3 magnetometer, 6 photodiode). CADC0884 has no anomalous segments; CADC0886 and CADC0890 have 11 and 14 segments."
official_split: "train = 1 594 segments (321 anomalous), test = 529 (113 anomalous); stratified random, interleaved in time (train/test alternate 4-234 times per channel)"
leakage_risks: "The official split mixes time: neighbouring segments of the same channel fall on both sides. DL-062: report the official split (comparability) AND a per-channel time-ordered split; the gap is a possible leakage effect."
time_split: "DL-064 (astramesh.datasets.opssat.time_split): per channel, the earliest ceil(0.75 n) segments by first-sample time train. Train 1 596 (258 anomalous, 16 %), test 527 (176 anomalous, 33 %). Every test segment of a channel starts after all its training segments; segments do not overlap. Test anomalies per channel: CADC0872 52/136, CADC0873 56/148, CADC0874 35/48, CADC0884 0/39, CADC0886 1/2, CADC0888 15/63, CADC0890 3/3, CADC0892 6/52, CADC0894 8/36."
cross_validation: "Inside training only: 5 stratified random folds (official split) or 5 contiguous time blocks per channel (time split)."
feature_check: "The published len, duration, mean, var (population), std, kurtosis and skew (SciPy defaults) match values recomputed from segments.csv for all 2 123 segments (tests/integration/test_opssat_data.py)."
derived_files: "configs/data/opssat_score_sensor.json (DL-066): calibrated test-set anomaly probabilities of histogram gradient boosting (seed 0), by true label, for both splits, with the training anomaly rate. 527 + 529 numbers, no telemetry. Committed so CI and the simulation run without the raw data; regenerate with scripts/data/make_score_sensor.py. Attribution as for DS-02."
expected_storage_gb: 0.02
expected_ram_gb: "< 0.5"
```

### DS-06 — NASA OMNI high-resolution 1-min (May 2024)

```yaml
id: DS-06
name: "OMNI high-resolution (HRO) 1-min data, May 2024"
owner_provider: "NASA/GSFC Space Physics Data Facility (OMNIWeb)"
url: https://spdf.gsfc.nasa.gov/pub/data/omni/high_res_omni/monthly_1min/omni_min202405.asc
doi: "10.48322/45bb-8792"
version_or_date: "file dated 2025-11-24 on the SPDF server"
retrieved_utc: "2026-11-04"
retrieved_files: "omni_min202405.asc (13 392 000 B; sha256 pinned in configs/data/sources.yaml)"
license_terms: "No restrictions stated; citation and acknowledgement requested (https://omniweb.gsfc.nasa.gov/html/citing.html)"
license_verified_utc: "2026-11-04"
citation_required: "Papitashvili, N. E. and King, J. H. (2020), OMNI 1-min Data [Data set], NASA SPDF, doi:10.48322/45bb-8792 (with access date); acknowledge 'NASA/GSFC's Space Physics Data Facility's OMNIWeb service, and OMNI data'"
sampling_interval: "1 min; 44 640 rows = 31 days x 1 440"
units: "per the HRO format description (HROdocum.html); 46 whitespace-separated fields per row"
time_conventions: "year, day of year, hour, minute (UT); time-shifted to the bow-shock nose"
geospatial_conventions: "IMF Bz in GSM; solar-wind values at the bow-shock nose; AE and SYM/H are global geomagnetic indices (no position)"
missingness_quality_flags: "fill values are runs of 9s (e.g. 9999.99, 99999.9), field-specific"
event_labels: "none"
expected_storage_gb: 0.013
expected_ram_gb: "< 0.1 (four columns are kept)"
intended_experiment: "Phase 4 increment 4: May 2024 storm environment replay (S11)"
partitions: "Test only: the storm week 8-15 May 2024 is held out from all fitting, settings and feature choices (DL-068); training uses DS-09"
leakage_risks: "A forecast at time t may use only rows with time <= t minus the stated data latency"
domain_transfer_caveats: "Solar-wind values at the bow-shock nose and global geomagnetic indices: no position dependence. S11 applies them identically to all four spacecraft (DL-069), so they say nothing about differences in exposure between spacecraft"
```

### DS-07 — GOES-18 SEISS/SGPS L2 5-min averages (8–15 May 2024)

```yaml
id: DS-07
name: "L2 SEISS/SGPS 5-minute Flux Averages, GOES-18"
owner_provider: "NOAA NCEI"
url: https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes18/l2/data/sgps-l2-avg5m/2024/05/
doi: null
version_or_date: "v3-0-2; files created 2024-05-15 to 2024-05-22"
retrieved_utc: "2026-11-04"
retrieved_files: "8 daily netCDF-4 files, 594-643 kB each (sha256 pinned in configs/data/sources.yaml)"
license_terms: "Global attribute in every file: 'These data may be redistributed and used without restriction.'"
license_verified_utc: "2026-11-04"
citation_required: "None specified ('references: TBD'); acknowledge NOAA NCEI and GOES-R SEISS"
sampling_interval: "5 min (288 records per day); 2 sensor units (-X and +X look directions)"
units: "differential proton flux protons/(cm^2 sr keV s) in 13 channels from 1 to 500 MeV; integral flux protons/(cm^2 sr s) for >500 MeV only"
time_conventions: "seconds since 2000-01-01 12:00:00 UTC, start of each 5-min average (astramesh.datasets.goes checks the units string)"
geospatial_conventions: "GOES-18 at geostationary orbit (137.2 deg W); two sensor units looking -X and +X; no position-dependent use (one GEO proxy, DL-068)"
missingness_quality_flags: "per-average counts of valid 1-s samples and of dead-time, out-of-bounds and error DQFs; yaw-flip flag"
event_labels: "none; hazard = derived >= 10 MeV flux at or above the payload tolerance (DL-068)"
expected_storage_gb: 0.005
expected_ram_gb: "< 0.1"
intended_experiment: "Phase 4 increment 4: proton environment for the S11 radiation-risk replay"
partitions: "Test only, as DS-06: never used for fitting or settings"
caveats: "This product has no >10 MeV integral channel; a >=10 MeV flux must be integrated from the differential channels (method to be decided in increment 4). A 2025 NOAA/CIRES presentation reports a 2024 problem with SWPC proton integral fluxes; it concerns a different product but is recorded here. Temperature-corrected and observed fluxes are both provided."
leakage_risks: "Same rule as DS-06"
domain_transfer_caveats: "Geostationary orbit, not the AstraMesh LEO orbit: geomagnetic shielding differs, so GOES flux is an upper-bound proxy, not the dose at AstraMesh"
derived_files: "configs/data/s11_storm_series.json (DL-069): the >= 10 MeV flux of each 5-min record, five 1 h forecasts of its maximum, and OMNI SYM-H and AE (DS-06) on the same grid, 8-15 May 2024; 2 304 rows, about 130 kB. Committed so CI and the simulation run without the raw data; regenerate with scripts/data/make_storm_series.py. Attribution as for DS-06 and DS-07."
```

### DS-08 — GOES-18 SEISS/SGPS L2 5-min averages (Jan 2023 – Apr 2024; forecast training)

```yaml
id: DS-08
name: "L2 SEISS/SGPS 5-minute Flux Averages, GOES-18, 2023-01-01 to 2024-04-30"
owner_provider: "NOAA NCEI"
url: https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes18/l2/data/sgps-l2-avg5m/
doi: null
version_or_date: "v3-0-0 (to 2023-03-29), v3-0-1 and v3-0-2; the channel band edges changed with v3-0-1 and differ between the two sensor units"
retrieved_utc: "2026-11-05"
retrieved_files: "486 daily netCDF-4 files, one per day with no gaps (sha256 pinned in configs/data/sources.yaml)"
license_terms: "As DS-07: 'These data may be redistributed and used without restriction.'"
license_verified_utc: "2026-11-05"
citation_required: "As DS-07"
sampling_interval: "5 min; 139 968 records"
units: "as DS-07"
time_conventions: "as DS-07"
geospatial_conventions: "as DS-07"
event_labels: "as DS-07"
expected_storage_gb: 0.29
expected_ram_gb: "< 0.5 (files are read one at a time)"
missingness_quality_flags: "as DS-07; 0.06 % of records have no valid >= 10 MeV flux under the DL-068 validity rule. v3-0-0 files write the time units without 'UTC' (same epoch; every stamp falls on the 5-min grid)"
intended_experiment: "Phase 4 increment 4: training and calibration of the P-B and P-C radiation forecasts (DL-068). Never used to evaluate them"
partitions: "Everything here is training data; chronological folds inside it for calibration. The test event is the May 2024 storm week (DS-07), which starts 8 days after this period ends"
derived_quantity: ">= 10 MeV integral flux from the differential channels, astramesh.datasets.goes (DL-068): measured band integrals where a band lies wholly above 10 MeV, power laws matched to the neighbouring band averages elsewhere, plus the > 500 MeV channel; larger of the two units. Training period: 32 onsets of >= 100 pfu (78 h above), maximum 1 048 pfu (2024-03-23 18:20 UT)"
caveats: "The derived flux depends on the method: at the 10 May 2024 peak a flat-band sum gives 404 pfu and the DL-068 method 221 pfu, because the spectrum is steep (index about 5) across 10-12 MeV, where only interpolation is possible"
leakage_risks: "Same rule as DS-06; and no record from May 2024 or later may enter training or calibration"
domain_transfer_caveats: "As DS-07"
```

### DS-09 — NASA OMNI 1-min (Jan 2023 – Apr 2024; forecast training)

```yaml
id: DS-09
name: "OMNI high-resolution (HRO) 1-min data, January 2023 - April 2024"
owner_provider: "NASA/GSFC Space Physics Data Facility (OMNIWeb)"
url: https://spdf.gsfc.nasa.gov/pub/data/omni/high_res_omni/monthly_1min/
doi: "10.48322/45bb-8792"
version_or_date: "files as served on 2026-11-05"
retrieved_utc: "2026-11-05"
retrieved_files: "16 monthly files omni_min202301.asc ... omni_min202404.asc (sha256 pinned in configs/data/sources.yaml)"
license_terms: "As DS-06"
license_verified_utc: "2026-11-05"
citation_required: "As DS-06"
sampling_interval: "1 min; 699 840 rows, contiguous"
units: "as DS-06; columns used: Bz GSM, flow speed, AE, SYM/H (astramesh.datasets.omni)"
time_conventions: "as DS-06"
geospatial_conventions: "as DS-06"
missingness_quality_flags: "AE and SYM/H complete; Bz GSM 10 % missing; flow speed 29 % missing"
event_labels: "none"
expected_storage_gb: 0.21
expected_ram_gb: "< 0.5"
intended_experiment: "Phase 4 increment 4: forecast features (DL-068)"
partitions: "Training only, as DS-08"
leakage_risks: "As DS-08"
domain_transfer_caveats: "As DS-06"
```

### DS-10 — NASA OMNI2 hourly, 2023–2024 (F10.7 and ap for MSIS)

```yaml
id: DS-10
name: "OMNI2 low-resolution (hourly) data, 2023 and 2024"
owner_provider: "NASA/GSFC Space Physics Data Facility (OMNIWeb)"
url: https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/
doi: null
version_or_date: "files as served on 2026-11-10 (omni2_2024.dat last modified 2025-12-10)"
retrieved_utc: "2026-11-10"
retrieved_files: "omni2_2023.dat, omni2_2024.dat (sha256 pinned in configs/data/sources.yaml)"
license_terms: "As DS-06"
license_verified_utc: "2026-11-10"
citation_required: "As DS-06"
sampling_interval: "1 h; 8 760 + 8 784 rows, contiguous; format omni2.text (55 whitespace-separated words)"
units: "columns used: word 50 ap-index [nT] (3-hourly value repeated per hour), word 51 F10.7 [sfu] (daily value repeated per hour)"
time_conventions: "UT; year, day of year, hour"
geospatial_conventions: "none (global indices)"
missingness_quality_flags: "no fill values (999, 999.9) in words 50-51 in either file"
event_labels: "none"
expected_storage_gb: 0.006
expected_ram_gb: "< 0.1"
intended_experiment: "Phase 5 increment 2: storm-time density D2 (NRLMSIS 2.0 inputs: daily F10.7, 81-day average, ap history; DL-084)"
partitions: "Not a learning dataset; inputs only. For the forecast-tuning storm (2024 Q1) and the May 2024 test week the same file supplies the drivers."
leakage_risks: "The 81-day centred F10.7 average uses 40 days after the epoch. The simulator uses this density as truth only (agents never see it), so this is not forecast leakage; it must not be used as an agent input."
domain_transfer_caveats: "Global indices; MSIS is an empirical climatological model with its own uncertainty (DL-084)"
```

### DS-11 — GOES-18 SEISS/SGPS L2 5-min averages (Jun 2024 – Oct 2026; Phase 6 held-out storms)

```yaml
id: DS-11
name: "L2 SEISS/SGPS 5-minute Flux Averages, GOES-18, 2024-06-01 to 2026-10-31"
owner_provider: "NOAA NCEI"
url: https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes18/l2/data/sgps-l2-avg5m/
doi: null
version_or_date: "v3-0-2 to 2026-01-09, v3-0-3 from 2026-01-10 (algorithm version 3.3, dated 2025-09-04). Same variables and channel band edges in both (checked on 2026-01-09 and 2026-01-10). No NOAA release notes for v3-0-3 were found (searched 2026-11-13); the SGPS Full Maturity README says a temperature correction of the L2 averages was to follow, which may be what v3-0-3 contains (not confirmed)"
retrieved_utc: "2026-11-13"
retrieved_files: "883 daily netCDF-4 files, one per day with no gaps and no duplicate versions (sha256 pinned in configs/data/sources.yaml)"
license_terms: "As DS-07: 'These data may be redistributed and used without restriction.' (license attribute of the files, checked on one file of each version)"
license_verified_utc: "2026-11-13"
citation_required: "As DS-07"
sampling_interval: "5 min; 254 304 records"
units: "as DS-07"
time_conventions: "as DS-07"
geospatial_conventions: "as DS-07"
event_labels: "as DS-07"
expected_storage_gb: 0.42
expected_ram_gb: "< 0.5 (files are read one at a time)"
missingness_quality_flags: "as DS-07; 0.57 % of records have no valid >= 10 MeV flux under the DL-068 rule, mostly in August 2026 (12.9 %); every other month 0.04 - 0.5 %. Around the version change (90 days each side): 0.073 % and 0.085 % invalid; median quiet-day flux 0.426 and 0.419 pfu (configs/data/heldout_selection.json)"
intended_experiment: "Phase 6 increment 1: held-out evaluation of the frozen Phase 5 methods (DL-113). The frozen forecasts are applied, never fitted"
partitions: "Test only. Storm windows are chosen by the DL-113 rule; one third are reserved (never run) for a later fair test"
derived_quantity: ">= 10 MeV integral flux as DS-08 (DL-068). 8 episodes >= 100 pfu (48 h merge), 8 qualifying windows: 6 test storms (facts in heldout_selection.json) and 2 reserved, described by start date only"
caveats: "The 19 Jan 2026 test storm peaks at 39 231 pfu, far above the training maximum of 1 048 pfu; P-C cannot forecast above its training range (DL-071)"
leakage_risks: "None for training: the forecasts are frozen from DS-08 / DS-09. Reserved windows must not be inspected beyond their start dates"
domain_transfer_caveats: "As DS-07; v3-0-3 data are a processing version the forecasts never saw"
```

### DS-12 — NASA OMNI 1-min (Jun 2024 – Oct 2026; Phase 6 held-out storms)

```yaml
id: DS-12
name: "OMNI high-resolution (HRO) 1-min data, June 2024 - October 2026"
owner_provider: "NASA/GSFC Space Physics Data Facility (OMNIWeb)"
url: https://spdf.gsfc.nasa.gov/pub/data/omni/high_res_omni/monthly_1min/
doi: "10.48322/45bb-8792"
version_or_date: "files as served on 2026-11-13"
retrieved_utc: "2026-11-13"
retrieved_files: "29 monthly files omni_min202406.asc ... omni_min202610.asc (sha256 pinned in configs/data/sources.yaml)"
license_terms: "As DS-06"
license_verified_utc: "2026-11-13"
citation_required: "As DS-06"
sampling_interval: "1 min; 1 271 520 rows, contiguous"
units: "as DS-09"
time_conventions: "as DS-06"
geospatial_conventions: "as DS-06"
missingness_quality_flags: "SYM/H complete; AE complete except October 2026 (19.4 % missing); Bz GSM 3 - 28 % and flow speed 19 - 49 % missing per month (training: 10 % and 29 %). No test storm falls in October 2026"
event_labels: "none"
expected_storage_gb: 0.38
expected_ram_gb: "< 0.5"
intended_experiment: "Phase 6 increment 1: forecast features and the cutoff shift for the held-out storms (DL-113)"
partitions: "Test only, as DS-11"
leakage_risks: "As DS-11"
domain_transfer_caveats: "As DS-06"
```

### DS-03, DS-04, DS-05

Not yet started. GloTEC and COSMIC-2 are left out of Phase 4 (DL-071, approved 2026-11-09): GloTEC cannot cover May 2024 and the COSMIC-2 licence is unverified. Source URLs are listed in spec §8.1. Specific cautions recorded there:

- **GloTEC:** operational global product begins in 2025 (NCEI archive "2025-Feb to present"); it is an assimilated model product, not ground truth. Not usable as 2024 truth.
- **CelesTrak GP:** general-perturbations elements are not exact inertial truth; prefer OMM over TLE-only. CelesTrak links its own usage policy; read it before any download.
- **COSMIC-2:** multiple processing levels (podTc2 absolute TEC is level 1b; ionPrf electron density is level 2); suggested citation "UCAR COSMIC Program, 2019: COSMIC-2 Data Products, doi:10.5065/T353-C093"; no licence text found on the data page yet. Check dependency with GloTEC (which assimilates it).

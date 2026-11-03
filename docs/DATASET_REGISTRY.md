# Dataset Registry

> **Owner:** Abdullah Muzher · **Status:** STARTED — no dataset downloaded · **Spec:** §8 · **Last updated:** 2026-11-03

## Rules (spec §8.2)

- One record per dataset. A dataset may not be used in an experiment until its record is complete for the fields that experiment depends on.
- **License/terms must be confirmed from the provider before download.** "UNVERIFIED" means not yet checked; do not assume government or open-access data is unrestricted.
- Raw data lives under `data/` (Git-ignored). Record retrieved file names and SHA-256 hashes here; never commit the files.
- Do **not** download the full ESA-ADB (spec §8.1, §8.2): start with a bounded OPS-SAT-AD sample after measured resource sizing.

## Summary

| ID | Dataset | License / terms | Downloaded | Phase |
|---|---|---|---|---|
| DS-01 | ESA Anomaly Dataset (ESA-ADB) | CC BY 3.0 IGO per the `LICENSE` file in `github.com/esa/anomaly-dataset`; Zenodo record 12528696 carries **no** license field — **confirm the license applies to the data files** | No | 4 |
| DS-02 | ESA OPS-SAT-AD | CC BY 4.0 per Zenodo record 15108715 metadata (checked 2026-11-03) | No | 4 |
| DS-03 | NOAA GloTEC | UNVERIFIED | No | 4 |
| DS-04 | CelesTrak GP / OMM | UNVERIFIED | No | 1+ |
| DS-05 | UCAR COSMIC-2 | UNVERIFIED (check data-use / citation policy) | No | 4 |
| DS-06 | NASA OMNI / SPDF | UNVERIFIED | No | 4–5 |
| DS-07 | NOAA SWPC / NCEI space-weather products | UNVERIFIED | No | 4–5 |

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

### DS-03 … DS-07

Not yet started. Source URLs are listed in spec §8.1. Specific cautions recorded there:

- **GloTEC:** operational global product begins in 2025; it is an assimilated model product, not ground truth. Not usable as 2024 truth.
- **CelesTrak GP:** general-perturbations elements are not exact inertial truth; prefer OMM over TLE-only.
- **COSMIC-2:** multiple processing levels; check dependency with GloTEC (which assimilates it).
- **OMNI / SWPC:** prevent future-information leakage in forecasting experiments.

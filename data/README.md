# data/

Local working area for external datasets. **Everything in this directory except
this README is ignored by Git** — raw and processed data are never committed.

Before placing any dataset here, add or update its record in
[`docs/DATASET_REGISTRY.md`](../docs/DATASET_REGISTRY.md) (source, version,
license/terms, file hashes, expected size) per specification §8.2.

Downloaded files are pinned in [`configs/data/sources.yaml`](../configs/data/sources.yaml)
(size, provider MD5 where published, SHA-256). Fetch or re-verify them with:

```
uv run python scripts/data/fetch_data.py               # download missing files, verify all
uv run python scripts/data/fetch_data.py --verify-only # offline check of local copies
```

Files land in `data/raw/<dataset id>/`.

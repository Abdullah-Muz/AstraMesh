"""Fetch and verify the pinned external data files (DL-063).

Run:  uv run python scripts/data/fetch_data.py [--dataset DS-02 ...] [--verify-only]

Files are listed in ``configs/data/sources.yaml`` and written to ``data/raw/<id>/``
(Git-ignored). Prints one line per file with its size and sha256. Exit status 1 if any
file is missing (with ``--verify-only``) or fails a size or checksum check, or if any
file still has no pinned sha256 (record the printed value in sources.yaml).
"""

from __future__ import annotations

import argparse
import sys

from astramesh.datasets.sources import fetch, load_sources


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dataset", action="append", help="dataset id (repeatable; default all)")
    p.add_argument("--verify-only", action="store_true", help="check local files; no network")
    a = p.parse_args(argv)
    sources = load_sources()
    ids = a.dataset or sorted(sources)
    unknown = sorted(set(ids) - set(sources))
    if unknown:
        p.error(f"unknown dataset(s): {', '.join(unknown)}")
    bad = unpinned = 0
    for ds_id in ids:
        ds = sources[ds_id]
        print(f"{ds_id}  {ds.name}  [{ds.license}]")
        for f in ds.files:
            r = fetch(f, download=not a.verify_only)
            print(f"  {r.status:<10} {f.name}  bytes={r.bytes}  sha256={r.sha256}"
                  + (f"  ({r.detail})" if r.detail else ""))  # fmt: skip
            if r.status in ("missing", "mismatch"):
                bad += 1
            elif f.sha256 is None:
                unpinned += 1
    if unpinned:
        print(f"{unpinned} file(s) verified by size/md5 only: pin the sha256 values above")
    return 1 if bad or unpinned else 0


if __name__ == "__main__":
    sys.exit(main())

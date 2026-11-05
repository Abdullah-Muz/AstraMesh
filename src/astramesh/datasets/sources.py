"""Pinned external data files: load ``configs/data/sources.yaml``, fetch, verify (DL-063).

A file is accepted only if its size and every pinned checksum match. The provider's
``md5`` is checked when one is published. Our ``sha256`` is recorded at first download
(trust on first use, reported so it can be pinned) and is required before a file is used
in an experiment (``require_pinned``). Downloads go to a temporary name and are renamed
only after verification, so a failed or partial fetch never leaves a file that looks
valid.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "configs" / "data" / "sources.yaml"
RAW = ROOT / "data" / "raw"
USER_AGENT = "AstraMesh-data-fetch/1.0 (research simulation; bounded downloads)"
CHUNK = 1 << 20


@dataclass(frozen=True, slots=True)
class SourceFile:
    dataset: str
    name: str
    url: str
    bytes: int | None
    md5: str | None
    sha256: str | None

    def __post_init__(self) -> None:
        if not self.url.startswith(("https://", "file://")):
            raise ValueError(f"{self.dataset}/{self.name}: url must be https")
        if "/" in self.name or self.name in ("", ".", ".."):
            raise ValueError(f"{self.dataset}/{self.name}: name must be a plain file name")
        for label, value, n in (("md5", self.md5, 32), ("sha256", self.sha256, 64)):
            if value is not None and (len(value) != n or value.strip("0123456789abcdef")):
                raise ValueError(f"{self.dataset}/{self.name}: bad {label}")

    def path(self, raw: Path = RAW) -> Path:
        return raw / self.dataset / self.name


@dataclass(frozen=True, slots=True)
class Dataset:
    id: str
    name: str
    license: str
    files: tuple[SourceFile, ...]


def load_sources(path: Path = SOURCES) -> dict[str, Dataset]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[str, Dataset] = {}
    for ds_id, d in raw["datasets"].items():
        if not d.get("license"):
            raise ValueError(f"{ds_id}: license/terms must be recorded before download")
        files = tuple(
            SourceFile(ds_id, f["name"], f["url"], f.get("bytes"), f.get("md5"), f.get("sha256"))
            for f in d["files"]
        )
        if len({f.name for f in files}) != len(files):
            raise ValueError(f"{ds_id}: duplicate file names")
        out[ds_id] = Dataset(ds_id, d["name"], d["license"], files)
    return out


def digests(path: Path) -> tuple[int, str, str]:
    """Size, md5 and sha256 of a file, read in chunks."""
    md5, sha = hashlib.md5(usedforsecurity=False), hashlib.sha256()
    n = 0
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            n += len(chunk)
            md5.update(chunk)
            sha.update(chunk)
    return n, md5.hexdigest(), sha.hexdigest()


def check(f: SourceFile, path: Path) -> list[str]:
    """Mismatches between a local file and its pins (empty list = verified)."""
    n, md5, sha = digests(path)
    errs = []
    if f.bytes is not None and n != f.bytes:
        errs.append(f"size {n} != pinned {f.bytes}")
    if f.md5 is not None and md5 != f.md5:
        errs.append(f"md5 {md5} != provider {f.md5}")
    if f.sha256 is not None and sha != f.sha256:
        errs.append(f"sha256 {sha} != pinned {f.sha256}")
    return errs


@dataclass(frozen=True, slots=True)
class Result:
    file: SourceFile
    path: Path
    status: str  # "verified", "downloaded", "missing", "mismatch"
    bytes: int | None
    sha256: str | None
    detail: str = ""


def fetch(f: SourceFile, raw: Path = RAW, *, download: bool = True) -> Result:
    """Verify the local copy; download it first if absent (and ``download``)."""
    dest = f.path(raw)
    if dest.exists():
        errs = check(f, dest)
        n, _, sha = digests(dest)
        if errs:
            return Result(f, dest, "mismatch", n, sha, "; ".join(errs))
        return Result(f, dest, "verified", n, sha)
    if not download:
        return Result(f, dest, "missing", None, None)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(f.url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
            shutil.copyfileobj(resp, out, CHUNK)
        errs = check(f, tmp)
        n, _, sha = digests(tmp)
        if errs:
            return Result(f, dest, "mismatch", n, sha, "; ".join(errs) + " (download discarded)")
        os.replace(tmp, dest)
        return Result(f, dest, "downloaded", n, sha)
    finally:
        tmp.unlink(missing_ok=True)


def require_pinned(f: SourceFile, raw: Path = RAW) -> Path:
    """Path of a verified file whose sha256 is pinned; raise otherwise (use in experiments)."""
    if f.sha256 is None:
        raise ValueError(f"{f.dataset}/{f.name}: sha256 not pinned in sources.yaml")
    dest = f.path(raw)
    if not dest.exists():
        raise FileNotFoundError(f"{dest} missing; run scripts/data/fetch_data.py")
    errs = check(f, dest)
    if errs:
        raise ValueError(f"{dest}: " + "; ".join(errs))
    return dest

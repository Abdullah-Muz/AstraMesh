"""Pinned external data sources: schema, fetch and verification (DL-063).

The fetch tests use ``file://`` URLs in a temporary directory, so they need no network.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from astramesh.datasets.sources import (
    RAW,
    SourceFile,
    check,
    digests,
    fetch,
    load_sources,
    require_pinned,
)


def test_repo_sources_are_complete_and_pinned() -> None:
    sources = load_sources()
    assert {"DS-02", "DS-06", "DS-07"} <= set(sources)
    for ds in sources.values():
        assert ds.license
        for f in ds.files:
            assert f.url.startswith("https://")
            assert f.bytes is not None
            assert f.bytes > 0
            assert f.sha256 is not None  # every file used in an experiment is pinned


def _source(tmp: Path, payload: bytes, **pins: object) -> SourceFile:
    src = tmp / "upstream.bin"
    src.write_bytes(payload)
    return SourceFile("DS-XX", "file.bin", src.as_uri(), pins.get("bytes"),  # type: ignore[arg-type]
                      pins.get("md5"), pins.get("sha256"))  # type: ignore[arg-type]  # fmt: skip


def test_fetch_downloads_verifies_and_reverifies(tmp_path: Path) -> None:
    data = b"telemetry" * 1000
    sha = hashlib.sha256(data).hexdigest()
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    f = _source(tmp_path, data, bytes=len(data), md5=md5, sha256=sha)
    raw = tmp_path / "raw"
    r = fetch(f, raw)
    assert (r.status, r.bytes, r.sha256) == ("downloaded", len(data), sha)
    assert fetch(f, raw).status == "verified"
    assert require_pinned(f, raw) == raw / "DS-XX" / "file.bin"


def test_bad_download_is_discarded(tmp_path: Path) -> None:
    f = _source(tmp_path, b"abc", sha256="0" * 64)
    raw = tmp_path / "raw"
    r = fetch(f, raw)
    assert r.status == "mismatch"
    assert "discarded" in r.detail
    assert not (raw / "DS-XX").exists() or not any((raw / "DS-XX").iterdir())  # no partial


def test_local_tampering_is_detected(tmp_path: Path) -> None:
    data = b"x" * 10
    f = _source(tmp_path, data, bytes=10, sha256=hashlib.sha256(data).hexdigest())
    raw = tmp_path / "raw"
    fetch(f, raw)
    f.path(raw).write_bytes(b"y" * 10)
    assert fetch(f, raw).status == "mismatch"
    with pytest.raises(ValueError, match="sha256"):
        require_pinned(f, raw)


def test_unpinned_or_missing_files_are_refused(tmp_path: Path) -> None:
    f = _source(tmp_path, b"abc")
    with pytest.raises(ValueError, match="not pinned"):
        require_pinned(f, tmp_path)
    g = _source(tmp_path, b"abc", sha256=hashlib.sha256(b"abc").hexdigest())
    with pytest.raises(FileNotFoundError):
        require_pinned(g, tmp_path / "empty")
    assert fetch(g, tmp_path / "empty", download=False).status == "missing"


@pytest.mark.parametrize(
    ("name", "url", "md5", "sha"),
    [("../x", "https://a.b/x", None, None), ("x", "http://a.b/x", None, None),
     ("x", "https://a.b/x", "zz", None), ("x", "https://a.b/x", None, "A" * 64)],
)  # fmt: skip
def test_source_file_validation(name: str, url: str, md5: str | None, sha: str | None) -> None:
    with pytest.raises(ValueError, match=r"name|url|md5|sha256"):
        SourceFile("DS-XX", name, url, None, md5, sha)


def test_local_copies_match_pins_when_present() -> None:
    """Checks the developer's downloaded copies; skipped where data/ is empty (CI)."""
    files = [f for ds in load_sources().values() for f in ds.files if f.path(RAW).exists()]
    if not files:
        pytest.skip("no local data downloaded")
    for f in files:
        assert check(f, f.path(RAW)) == [], f.name
        assert digests(f.path(RAW))[0] == f.bytes

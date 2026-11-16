"""Gate P6 traceability checks (DL-128): every recorded result names a clean commit, every
relative link in the report, the Gate P6 page and the README resolves, and the report cites
every results page."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "docs/results"
LINKED_DOCS = ("docs/REPORT.md", "docs/results/GATE_P6.md", "README.md")
# [text](target) and ![alt](target); the target ends at whitespace or ")"
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def _recorded() -> list[Path]:
    extra = ("storm_diagnostics.json", "demo_trace.json")
    return [*sorted(RESULTS.glob("*_meta.json")), *(RESULTS / n for n in extra)]


@pytest.mark.parametrize("path", _recorded(), ids=lambda p: p.name)
def test_recorded_result_names_a_clean_commit(path: Path) -> None:
    meta = json.loads(path.read_text())
    assert re.fullmatch(r"[0-9a-f]{40}", meta["git_commit"])
    assert meta["git_dirty"] is False


def _relative_links(doc: Path) -> list[str]:
    out = []
    for target in LINK.findall(doc.read_text()):
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue  # external URL or same-page anchor
        out.append(unquote(target.split("#", 1)[0]))
    return out


@pytest.mark.parametrize("rel", LINKED_DOCS)
def test_relative_links_resolve(rel: str) -> None:
    doc = ROOT / rel
    links = _relative_links(doc)
    assert links, f"{rel} has no relative links"
    missing = [t for t in links if not (doc.parent / t).exists()]
    assert not missing, f"{rel}: {missing}"


def test_report_cites_every_results_page() -> None:
    cited = {(ROOT / "docs" / t).resolve() for t in _relative_links(ROOT / "docs/REPORT.md")}
    pages = {p.resolve() for p in RESULTS.glob("*.md")}
    missing = sorted(p.name for p in pages - cited)
    assert not missing, f"REPORT.md does not cite {missing}"

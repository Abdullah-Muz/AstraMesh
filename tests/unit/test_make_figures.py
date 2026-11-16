"""Report figures (DL-125): every figure draws from committed files into a temporary folder,
with a generated README, and reads only docs/results and configs/data."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _mod() -> ModuleType:
    path = ROOT / "scripts/figures/make_figures.py"
    spec = importlib.util.spec_from_file_location("make_figures", path)
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m  # dataclasses look their module up while the class is built
    spec.loader.exec_module(m)
    return m


def test_sources_exist_and_are_committed_result_or_series_files() -> None:
    m = _mod()
    assert len(m.FIGURES) == 9
    for f in m.FIGURES:
        assert f.sources
        for s in f.sources:
            assert not Path(s).is_absolute()
            assert s.startswith(("docs/results/", "configs/data/")), s
            assert (ROOT / s).is_file(), s


def test_names_unique_and_captions_label_data() -> None:
    m = _mod()
    names = [f.name for f in m.FIGURES]
    assert len(names) == len(set(names))
    assert all(n.endswith(".png") for n in names)
    for f in m.FIGURES:  # spec §19: say what is simulated and what is measured
        assert "simulated" in f.caption.lower() or "measured" in f.caption.lower(), f.name


def test_main_writes_every_figure_and_readme(tmp_path: Path) -> None:
    m = _mod()
    m.main(["--out", str(tmp_path)])
    for f in m.FIGURES:
        png = tmp_path / f.name
        assert png.is_file()
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    readme = (tmp_path / "README.md").read_text()
    assert "uv run python scripts/figures/make_figures.py" in readme
    for f in m.FIGURES:
        assert f"]({f.name})" in readme
        for s in f.sources:
            assert f"`{s}`" in readme

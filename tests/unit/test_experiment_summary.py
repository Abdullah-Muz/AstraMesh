"""Statistics of the S00 loss-comparison script (scripts/experiments)."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/experiments/s00_loss_comparison.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("s00_loss_comparison", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(method: str, loss: float, utility: float, dup: int = 0) -> dict[str, float | str]:
    base: dict[str, float | str] = dict.fromkeys(_module().METRICS, 0.0)
    base.update({"method": method, "loss": loss, "utility": utility, "n_duplicates": dup})
    return base


def test_mean_sd_and_t_interval() -> None:
    rows = [_row("static_b0", 0.1, u, d) for u, d in ((10, 0), (12, 1), (14, 0))]
    (rec,) = _module().summarize(rows)
    assert rec["n_runs"] == 3
    assert rec["utility_mean"] == 12.0
    assert rec["utility_sd"] == 2.0
    half = 4.302652729911275 * 2.0 / math.sqrt(3)  # t(0.975, 2)
    assert rec["utility_ci95_lo"] == pytest.approx(12.0 - half, abs=1e-6)
    assert rec["utility_ci95_hi"] == pytest.approx(12.0 + half, abs=1e-6)
    assert rec["runs_with_duplicates"] == 1


def test_single_run_has_zero_width_interval() -> None:
    (rec,) = _module().summarize([_row("cbba_b3", 0.3, 7)])
    assert (rec["utility_sd"], rec["utility_ci95_lo"], rec["utility_ci95_hi"]) == (0.0, 7.0, 7.0)

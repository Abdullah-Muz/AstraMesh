"""B4 re-sync comparison (DL-122, DL-123): every B4 run reuses a recorded configuration,
the re-sync variant differs only in ``agents.ownership_sync``, the test storms are the
reserved windows, and the R1 - R6 rules on synthetic pairs."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from astramesh.core.config import parse_scenario

ROOT = Path(__file__).resolve().parents[2]


def _mod() -> ModuleType:
    path = ROOT / "scripts/experiments/resync_comparison.py"
    spec = importlib.util.spec_from_file_location("resync_comparison", path)
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_jobs_and_recorded_b4_configurations() -> None:
    m = _mod()
    jobs = m.jobs()
    n_test = len(m.reserved_storms())
    assert n_test == 2
    assert len(jobs) == len(set(jobs)) == 2 * n_test + 2 * 69 + 2 * n_test * 6 * 3
    assert all(j[3] == "b3" for j in jobs[: 2 * n_test])  # the long B3 runs first
    recorded = json.loads((ROOT / "docs/results/negative_results_meta.json").read_text())
    hashes = recorded["config_hashes"]
    n = 0
    for job in jobs:
        g, storm, arm, variant, _ = job
        if g == "test" or variant != "b4":
            continue
        assert parse_scenario(m.config(job)).config_hash() == hashes[f"{g}/{storm}/{arm}"]
        n += 1
    assert n == 69


def test_resync_differs_only_in_the_switch() -> None:
    m = _mod()
    for job in (("heldout", "20241007", "no_lookahead", "b4", 1),
                ("test", sorted(m.reserved_storms())[0], "shorter", "b4", 2)):  # fmt: skip
        b4 = m.config(job)
        rs = m.config((*job[:3], "b4_resync", job[4]))
        assert rs["agents"].pop("ownership_sync") == m.SYNC
        assert rs == b4


def test_test_storms_use_the_reserved_series() -> None:
    m = _mod()
    sel = json.loads(m.RESERVED.read_text())
    held = json.loads((ROOT / "configs/data/heldout_selection.json").read_text())
    assert sorted(s["window_start_utc"] for s in sel["test_storms"]) == sorted(
        held["reserved_window_starts_utc"])  # fmt: skip
    for name, s in m.reserved_storms().items():
        raw = m.config(("test", name, "baseline", "b4", 1))
        rp = raw["environment"]["replay"]
        assert rp["series_sha256"] == s["series_sha256"]
        assert raw["time"]["epoch_utc"] == s["epoch_utc"]
        assert m.config(("test", name, "baseline", "b3", 1))["operations"]["algorithm"] == m.B3


def _pair(arm: str, **kw: Any) -> dict[str, Any]:
    base = {"group": "test", "storm": "x", "arm": arm, "seed": 1, "b4_utility": 900,
            "resync_utility": 950, "resync_lost_available_split": 0, "resync_duplicates": 0,
            "protection_identical": True, "bytes_ratio": 1.1}  # fmt: skip
    if arm == "quiet":
        base["resync_utility"] = base["b4_utility"]
    return base | kw


def test_expectation_rules() -> None:
    m = _mod()
    ok = [_pair("quiet"), _pair("baseline"), _pair("shorter", group="phase5")]
    exp = m.expectations(ok)
    assert all(v["held"] for scope in exp.values() for v in scope.values())
    bad = [_pair("quiet", resync_utility=901), _pair("baseline", resync_utility=899),
           _pair("shorter", resync_lost_available_split=1, resync_duplicates=1,
                 protection_identical=False, bytes_ratio=1.25)]  # fmt: skip
    t = m.expectations(bad)["test"]
    assert not any(v["held"] for v in t.values())
    assert t["R2_utility_not_below_b4"]["failures"] == ["x/baseline/seed1"]
    assert m.expectations(bad)["development"]["R1_no_split_task_lost_while_available"]["held"]


def test_pairs_compute_losses_against_b4_quiet() -> None:
    m = _mod()

    def row(arm: str, v: str, util: int, done: list[str], avail: list[str],
            split: list[str]) -> dict[str, Any]:  # fmt: skip
        return {"group": "test", "storm": "x", "arm": arm, "variant": v, "seed": 1,
                "utility": util, "completed": done, "not_done_available": avail,
                "split": split, "n_duplicates": 0, "bytes_sent": 100 if v == "b4" else 110,
                "protection_digest": "d"}  # fmt: skip

    rows = [row("quiet", "b4", 1000, ["A", "B", "C"], [], []),
            row("quiet", "b4_resync", 1000, ["A", "B", "C"], [], []),
            row("baseline", "b4", 800, ["A"], ["B", "C", "Z"], ["B"]),
            row("baseline", "b4_resync", 900, ["A", "B"], ["C"], [])]  # fmt: skip
    prs = {p["arm"]: p for p in m.pairs(rows)}
    p = prs["baseline"]
    assert (p["b4_lost_available"], p["b4_lost_available_split"]) == (2, 1)  # Z not in QUIET
    assert (p["resync_lost_available"], p["resync_lost_available_split"]) == (1, 0)
    assert p["retention_change"] == 0.1
    assert p["bytes_ratio"] == 1.1
    assert p["protection_identical"]

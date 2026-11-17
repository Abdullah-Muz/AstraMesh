"""Compute-cost script (DL-134, DL-135): the jobs, the recorded configurations and the
behaviour check. No simulation is run here."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from astramesh.core.config import NominalOperationsScenario, parse_scenario

ROOT = Path(__file__).resolve().parents[2]


def _mod() -> ModuleType:
    path = ROOT / "scripts/experiments/compute_cost.py"
    spec = importlib.util.spec_from_file_location("compute_cost", path)
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CC = _mod()


def test_jobs() -> None:
    jobs = CC.cases(3)
    assert len(jobs) == len(set(jobs)) == 3 * (6 + 2 + 2 + 6) + 2
    assert [j for j in jobs if j[0] == CC.LONG] == [(CC.LONG, m, 1) for m in CC.PAIR]


def test_every_measured_configuration_parses_and_hashes_as_recorded() -> None:
    rec = CC._recorded()
    assert len(rec) == 6 + 2 + 2 + 4 + 2  # B3 + timeout and B4 at 30 % loss are unrecorded
    for case, method in {(c, m) for c, m, _ in CC.cases(1)}:
        cfg = parse_scenario(CC.build(case, method))
        assert isinstance(cfg, NominalOperationsScenario)
        assert cfg.operations.algorithm == method
        want = rec.get((case, method), {})
        if "config_hash" in want:
            assert cfg.config_hash() == want["config_hash"], (case, method)


def _row(**kw: Any) -> dict[str, Any]:
    base = {"case": "S00 30% loss", "method": "rule_b4", "repeat": 1, "utility": 144,
            "n_completed": 43, "messages_sent": 1, "bytes_sent": 2, "config_hash": "h"}  # fmt: skip
    return {**base, **kw}


def test_check_flags_a_changed_run_and_disagreeing_repeats() -> None:
    rec = CC._recorded()
    case, method = "S00 1% loss", "static_b0"
    good = {k: (v if k == "config_hash" else int(v)) for k, v in rec[(case, method)].items()}
    ok = _row(case=case, method=method, **good)
    assert CC.check([ok]) == []
    assert CC.check([{**ok, "utility": good["utility"] - 1}])
    assert CC.check([_row(), _row(repeat=2)]) == []
    assert CC.check([_row(), _row(repeat=2, bytes_sent=3)])


def test_phase2_bytes_are_adjusted_for_the_phase3_status_fields() -> None:
    # B0 sends only status messages, and loss does not change what is sent, so the
    # adjusted Phase 2 value at 30 % loss equals the Phase 3 value at 1 % loss.
    rec = CC._recorded()
    assert (
        rec[("S00 30% loss", "static_b0")]["bytes_sent"]
        == rec[("S00 1% loss", "static_b0")]["bytes_sent"]
    )
    assert "config_hash" not in rec[("S00 30% loss", "static_b0")]

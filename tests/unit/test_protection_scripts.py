"""Shorter-protection tuning and comparison scripts (DL-101): baselines identical to the
recorded DL-096 and DL-100 runs, arms change only the protection setting, and the
selection rule."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from astramesh.core.config import NominalOperationsScenario, parse_scenario

ROOT = Path(__file__).resolve().parents[2]


def _mod(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/experiments/{name}.py")
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _parse(raw: dict[str, Any]) -> NominalOperationsScenario:
    cfg = parse_scenario(raw)
    assert isinstance(cfg, NominalOperationsScenario)
    return cfg


def test_tuning_baseline_and_quiet_are_the_recorded_dl096_runs() -> None:
    m = _mod("protection_tuning")
    sha = hashlib.sha256(m.SERIES.read_bytes()).hexdigest()
    recorded = json.loads((ROOT / "docs/results/handover_tuning_meta.json").read_text())
    for arm in ("quiet", "baseline"):
        for seed in m.SEEDS:
            got = _parse(m.config(arm, seed, sha)).config_hash()
            assert got == recorded["config_hashes"][f"{arm}/seed{seed}"]


def test_comparison_baseline_and_quiet_are_the_recorded_dl100_runs() -> None:
    m = _mod("protection_comparison")
    recorded = json.loads((ROOT / "docs/results/multi_storm_meta.json").read_text())
    for storm in m.STORMS:
        for planner in m.PLANNERS:
            for arm in ("baseline", "quiet"):
                for seed in m.SEEDS:
                    key = f"{storm}/{planner}/{arm}/seed{seed}"
                    got = _parse(m.config(storm, planner, arm, seed)).config_hash()
                    assert got == recorded["config_hashes"][key]


def test_tuning_arms_change_only_the_protection_setting() -> None:
    m = _mod("protection_tuning")
    sha = hashlib.sha256(m.SERIES.read_bytes()).hexdigest()
    base = _parse(m.config("baseline", 1, sha))
    assert base.environment is not None
    assert base.environment.replay is not None
    assert base.environment.replay.access is not None
    assert base.environment.replay.access.horizon_s == 3600.0
    assert base.supervisor.release_dwell_s == 1800.0
    assert base.supervisor.protect_exposure_ratio == 1.0
    assert base.environment.replay.forecast == "P-B/q50"
    assert len(m.ARMS) == 2 + 18
    for arm in m.ARMS[2:]:
        st = m.setting_of(arm)
        cfg = _parse(m.config(arm, 1, sha))
        assert cfg.environment is not None
        rp = cfg.environment.replay
        assert rp is not None
        assert rp.access is not None
        assert rp.access.horizon_s == st["horizon_s"]
        assert cfg.supervisor.release_dwell_s == st["release_dwell_s"]
        assert cfg.supervisor.protect_exposure_ratio == (
            0.9 if st["margin"] == "ratio_0.9" else 1.0
        )
        assert rp.forecast == ("P-B/q90" if st["margin"] == "q90" else "P-B/q50")
        same = {"horizon_s": 3600.0, "release_dwell_s": 1800.0, "margin": "none"}
        reverted = m.apply_protection(m.config(arm, 1, sha), same)
        reverted["environment"]["replay"]["forecast"] = "P-B/q50"
        reverted["supervisor"]["protect_exposure_ratio"] = 1.0
        reverted["scenario_id"] = base.scenario_id
        reverted_cfg = _parse(reverted)
        assert reverted_cfg.model_dump(exclude={"supervisor"}) == base.model_dump(
            exclude={"supervisor"}
        )
        assert reverted_cfg.supervisor == base.supervisor


def test_unknown_margin_rejected() -> None:
    m = _mod("protection_tuning")
    sha = hashlib.sha256(m.SERIES.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="unknown margin"):
        m.apply_protection(
            m.config("baseline", 1, sha),
            {"horizon_s": 600.0, "release_dwell_s": 300.0, "margin": "q95"},
        )


def test_extra_unprotected_is_the_worst_spacecraft() -> None:
    m = _mod("protection_tuning")
    arm = {"unprotected_hazard_s": json.dumps({"sc00": 900.0, "sc01": 100.0})}
    base = {"unprotected_hazard_s": json.dumps({"sc00": 0.0, "sc01": 300.0})}
    assert m.extra_unprotected_s(arm, base) == 900.0
    with pytest.raises(ValueError, match="spacecraft sets differ"):
        m.extra_unprotected_s(arm, {"unprotected_hazard_s": json.dumps({"sc00": 0.0})})


def _row(arm: str, ret: float, extra: float) -> dict[str, Any]:
    return {"arm": arm, "mean_retention": ret, "max_extra_unprotected_s": extra,
            "eligible": arm == "baseline" or extra <= 600.0}  # fmt: skip


def test_selection_rule() -> None:
    m = _mod("protection_tuning")
    base = _row("baseline", 0.93, 0.0)
    # the best arm breaks the safety limit: the next best eligible one wins
    s = [base, _row("pt:300:300:none", 0.98, 750.0), _row("pt:600:300:none", 0.96, 370.0),
         _row("pt:1200:600:none", 0.95, 0.0)]  # fmt: skip
    assert m.choose(s) == "pt:600:300:none"
    # ties: longer H, then longer D, then the more conservative margin
    s = [base, _row("pt:300:600:q90", 0.96, 0.0), _row("pt:600:300:none", 0.96, 0.0)]
    assert m.choose(s) == "pt:600:300:none"
    s = [base, _row("pt:600:300:q90", 0.96, 0.0), _row("pt:600:600:none", 0.96, 0.0)]
    assert m.choose(s) == "pt:600:600:none"
    s = [base, _row("pt:600:600:none", 0.96, 0.0), _row("pt:600:600:ratio_0.9", 0.96, 0.0)]
    assert m.choose(s) == "pt:600:600:ratio_0.9"
    # nothing eligible, or nothing better than the baseline
    assert m.choose([base, _row("pt:300:300:none", 0.98, 601.0)]) is None
    assert m.choose([base, _row("pt:300:300:none", 0.93, 0.0)]) is None


def test_comparison_needs_a_frozen_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _mod("protection_comparison")
    assert m.FROZEN is None or set(m.FROZEN) == {"horizon_s", "release_dwell_s", "margin"}
    if m.FROZEN is None:
        with pytest.raises(ValueError, match="FROZEN"):
            m.config("mar23_2024", "rule_b4", "candidate", 1)
    monkeypatch.setattr(
        m, "FROZEN", {"horizon_s": 600.0, "release_dwell_s": 300.0, "margin": "q90"}
    )
    cfg = _parse(m.config("mar23_2024", "rule_b4", "candidate", 1))
    assert cfg.environment is not None
    assert cfg.environment.replay is not None
    assert cfg.environment.replay.forecast == "P-B/q90"
    assert cfg.supervisor.release_dwell_s == 300.0

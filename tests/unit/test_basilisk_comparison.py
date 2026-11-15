"""Basilisk cross-check (DL-116, DL-117): the case file, the matched AstraMesh models, the
measures and tolerances on synthetic trajectories, and the separate environment."""

from __future__ import annotations

import importlib.util
import json
import math
import tomllib
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from astramesh.dynamics.constants import (
    C20_NORMALIZED_EGM2008,
    GM_EARTH_M3PS2,
    J2_EARTH,
    OMEGA_EARTH_RADPS,
    R_EARTH_EQ_M,
)
from astramesh.dynamics.drag import density

ROOT = Path(__file__).resolve().parents[2]


def _mod() -> ModuleType:
    path = ROOT / "scripts/experiments/basilisk_comparison.py"
    spec = importlib.util.spec_from_file_location("basilisk_comparison", path)
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _y0() -> np.ndarray:
    a = R_EARTH_EQ_M + 525e3
    v = math.sqrt(GM_EARTH_M3PS2 / a)
    i = math.radians(97.5)
    s1 = 20e3 / a
    return np.array([[a, 0.0, 0.0, 0.0, v * math.cos(i), v * math.sin(i)],
                     [a * math.cos(s1), -a * math.sin(s1) * math.cos(i),
                      -a * math.sin(s1) * math.sin(i), v * math.sin(s1),
                      v * math.cos(s1) * math.cos(i), v * math.cos(s1) * math.sin(i)]])  # fmt: skip


def test_density_table_samples_astramesh_density_finely() -> None:
    m = _mod()
    t = m.density_table()
    h, rho = np.array(t["alt_m"]), np.array(t["rho_kgpm3"])
    assert h[0] == 480e3
    assert h[-1] == 700e3
    assert np.all(np.diff(h) == 100.0)
    np.testing.assert_array_equal(rho, density(h))
    mid = 0.5 * (h[:-1] + h[1:])  # Basilisk interpolates rho linearly between nodes
    rel = np.abs(0.5 * (rho[:-1] + rho[1:]) / density(mid) - 1.0)
    assert rel.max() < 1e-6


def test_case_file_uses_astramesh_constants_and_the_design_cases() -> None:
    m = _mod()
    doc = json.loads(json.dumps(m.case_doc(_y0(), duration_s=600)))
    c = doc["constants"]
    assert (c["mu"], c["r_ref_m"], c["omega_radps"]) == (GM_EARTH_M3PS2, R_EARTH_EQ_M,
                                                         OMEGA_EARTH_RADPS)  # fmt: skip
    assert c["c20_normalized"] == C20_NORMALIZED_EGM2008
    assert c["j2"] == pytest.approx(-math.sqrt(5.0) * c["c20_normalized"], rel=1e-15)
    assert (doc["step_s"], doc["n_steps"]) == (10, 60)
    cases = {k["name"]: k for k in doc["cases"]}
    assert list(cases) == ["K1", "K2", "K3", "K4", "K2_rkf78", "K3_rkf78"]
    assert [(k["gravity"], k["drag"], k["integrator"]) for k in cases.values()] == [
        ("point_mass", False, "rk4"), ("j2", False, "rk4"), ("j2", True, "rk4"),
        ("j2", True, "rk4"), ("j2", False, "rkf78"), ("j2", True, "rkf78")]  # fmt: skip
    k4 = cases["K4"]["spacecraft"]
    assert [s["ballistic_m2pkg"] for s in k4] == [0.0092, pytest.approx(1.2 * 0.0092)]
    assert k4[1]["r_m"] == _y0()[1, :3].tolist()
    assert all(len(k["spacecraft"]) == 1 for n, k in cases.items() if n != "K4")


def test_matched_models_use_the_z_pole_and_spherical_altitude() -> None:
    m = _mod()
    fm = m.force_model("j2", True, (0.0092,))
    assert fm.pole == (0.0, 0.0, 1.0)
    assert fm.j2 == J2_EARTH
    assert fm.drag is not None
    assert fm.drag.corotating
    assert fm.drag.omega_radps == OMEGA_EARTH_RADPS
    r = np.array([[0.0, 0.0, R_EARTH_EQ_M + 530e3]])  # over the pole: spherical, not WGS 84
    assert m.spherical_density(r, 0.0)[0] == density(np.array([530e3]))[0]
    assert m.force_model("point_mass", False, (0.0092,)).j2 == 0.0


def test_astramesh_runs_on_a_short_case_file() -> None:
    from datetime import UTC, datetime

    m = _mod()
    doc = m.case_doc(_y0(), duration_s=600)
    runs = m.astramesh_runs(doc, datetime(2025, 6, 1, tzinfo=UTC))
    assert set(runs) == {"K1", "K2", "K3", "K4", "K1_kepler"}
    assert runs["K4"].shape == (61, 2, 6)
    assert runs["K1"].shape == runs["K1_kepler"].shape == (61, 1, 6)
    assert m.max_diff(runs["K1"], runs["K1_kepler"])[0] < 1e-3  # RK4 over 10 min
    assert 0 < m.max_diff(runs["K3"], runs["K2"])[0] < 1.0  # drag acts, slowly


def _synthetic(m: ModuleType, offset: float) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    n = 11
    t = np.arange(n, dtype=float)
    base = np.zeros((n, 1, 6))
    base[:, 0, 0] = 7e6
    k3 = base.copy()
    k3[:, 0, 1] = 100.0 * t  # drag effect grows to 1 km
    k4 = np.zeros((n, 2, 6))
    k4[:, 1, 0] = 20e3 - 100.0 * t  # spacing shrinks by 1 km
    am = {"K1": base, "K2": base, "K3": k3, "K4": k4, "K1_kepler": base,
          "production": np.concatenate([k3, k3], axis=1)}  # fmt: skip
    shift = np.zeros(6)
    shift[2] = offset
    bsk = {"K1": base + shift, "K2": base, "K3": k3 + shift, "K4": k4 + shift,
           "K2_rkf78": base, "K3_rkf78": k3}  # fmt: skip
    bsk["K4"] = k4.copy()
    bsk["K4"][:, 1, 0] += offset
    return am, bsk


def test_measures_and_tolerances_on_synthetic_trajectories() -> None:
    m = _mod()
    am, bsk = _synthetic(m, 0.5)
    rows = {(r["case"], r["quantity"]): r for r in m.measures(am, bsk)}
    k1 = rows[("K1", "max |dr| AstraMesh - Basilisk [m]")]
    assert (k1["value"], k1["test"], k1["passed"]) == (0.5, "T1", True)
    assert rows[("K3", "drag effect max |r_K3 - r_K2| (AstraMesh) [m]")]["value"] == 1000.0
    t2 = rows[("K3", "max |dr| / drag effect")]
    assert (t2["value"], t2["passed"]) == (0.0005, True)
    t3 = rows[("K4", "max |d spacing| / spacing change")]
    assert (t3["value"], t3["passed"]) == (0.0005, True)
    assert rows[("K1", "max |dr| AstraMesh - Kepler [m]")]["passed"] is None
    am, bsk = _synthetic(m, 6.0)  # 6 m: fails T1 and T2 (0.6 %) and T3 (0.6 %)
    failed = {(r["test"], r["case"]) for r in m.measures(am, bsk) if r["passed"] is False}
    assert failed == {("T1", "K1"), ("T2", "K3"), ("T3", "K4")}


def test_daily_rows_and_spacing() -> None:
    m = _mod()
    am, bsk = _synthetic(m, 0.5)
    rows = m.daily(am, bsk, steps_per_day=5)
    assert [r["day"] for r in rows] == [0, 1, 2]
    assert rows[2]["K3_drag_effect_m"] == 1000.0
    assert rows[1]["K4_d_spacing_m"] == pytest.approx(-0.5)
    np.testing.assert_allclose(m.spacing(am["K4"])[[0, -1]], [20e3, 19e3])


def test_basilisk_lives_in_its_own_environment() -> None:
    tools = tomllib.loads((ROOT / "tools/basilisk/pyproject.toml").read_text())
    assert tools["project"]["dependencies"] == ["bsk==2.12.2"]
    assert (ROOT / "tools/basilisk/uv.lock").exists()
    assert 'name = "bsk"' not in (ROOT / "uv.lock").read_text()  # main lock untouched
    main = tomllib.loads((ROOT / "pyproject.toml").read_text())
    groups = json.dumps([main["project"]["dependencies"], main.get("dependency-groups", {})])
    assert "bsk" not in groups

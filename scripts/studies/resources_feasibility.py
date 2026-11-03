"""Study for increment 6b: energy balance by orbit timing, and propulsion feasibility.

Run:  uv run python scripts/studies/resources_feasibility.py [--out r.json]

Recorded in docs/NUMERICAL_MISSION_DESIGN.md §B.8 (Part A questions 4 and 5).

  R1  The mission-geometry baseline re-run with the ascending node at local
      times 06:00, 07:25 (baseline), 10:30 and 12:00 on 2025-06-01: eclipse
      fraction and, for the bus-only and payload-in-every-window profiles,
      worst eclipse discharge, minimum charge, deficit, and the daily energy
      balance. Configured spacecraft values (DL-035/036).
  R2  Analytic break-even continuous load (orbit average, charging losses):
      P_max = G (1 - f) eta / ((1 - f) eta + f); checked by 3-day simulations
      just below and above it at LTAN 12:00 (worst case f = 0.375).
  R3  Propulsion: propellant, thrust time and thruster energy for the 5 m/s
      budget (Tsiolkovsky, exact for constant Isp) vs an independent numerical
      integration of dm/dt = -F / (Isp g0), dv/dt = F / m (RK4, 1 s); and the
      constant-mass approximation in spec §3.3 (33.3 h).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from astramesh.core.config import MissionGeometryScenario, load_scenario
from astramesh.core.events import EventLog
from astramesh.dynamics.earth_frames import earth_pole_gcrs
from astramesh.dynamics.forces import equatorial_basis
from astramesh.dynamics.sun import sun_direction_gcrs
from astramesh.resources.ledgers import G0_MPS2, PropulsionBudget, simulate_energy
from astramesh.scenarios.mission_geometry import run_mission_geometry

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "mission_geometry_24h.yaml"


def raan_for_ltan(config: MissionGeometryScenario, ltan_h: float) -> float:
    epoch = config.time.epoch_utc
    s = equatorial_basis(earth_pole_gcrs(epoch)) @ sun_direction_gcrs(epoch, [0])[0]
    sun_ra = math.degrees(math.atan2(s[1], s[0]))
    return (sun_ra + 15.0 * (ltan_h - 12.0)) % 360.0


def with_changes(config: MissionGeometryScenario, **changes: Any) -> MissionGeometryScenario:
    raw = config.canonical_dict()
    for path, value in changes.items():
        node = raw
        *parents, leaf = path.split("__")
        for key in parents:
            node = node[key]
        node[leaf] = value
    out = MissionGeometryScenario.model_validate(raw)
    return out


def r1(config: MissionGeometryScenario) -> dict[str, Any]:
    out = {}
    for ltan in (6.0, 7.41, 10.5, 12.0):
        cfg = with_changes(config, reference_orbit__raan_deg=raan_for_ltan(config, ltan))
        run = run_mission_geometry(cfg, EventLog())
        s = run.summary
        res = s["resources"]
        row: dict[str, Any] = {
            "ltan_h": s["orbit_orientation_at_epoch"]["ltan_h"],
            "beta_deg": s["orbit_orientation_at_epoch"]["beta_angle_deg"],
            "eclipse_fraction_sc00": s["illumination"]["eclipse_fraction"]["sc00"],
            "n_opportunities": s["science"]["n_opportunities"],
        }
        for prof in ("energy_bus_only", "energy_payload_all_eligible"):
            worst = max(res[prof].values(), key=lambda e: e["max_drawdown_wh"])
            row[prof] = {
                k: worst[k]
                for k in ("max_drawdown_wh", "min_fraction", "deficit_wh", "curtailed_wh",
                          "generated_wh", "consumed_wh", "final_wh")
            }  # fmt: skip
        out[f"ltan_{ltan:g}h"] = row
    return out


def breakeven_w(gen_w: float, f: float, eta: float) -> float:
    return gen_w * (1 - f) * eta / ((1 - f) * eta + f)


def r2(config: MissionGeometryScenario) -> dict[str, Any]:
    sc = config.spacecraft
    cfg = with_changes(
        config,
        reference_orbit__raan_deg=raan_for_ltan(config, 12.0),
        time__duration_s=3 * 86_400,
        output__trajectory_sample_interval_s=60,
    )
    run = run_mission_geometry(cfg, EventLog())
    sunlit = run.sunlit[:, 0]
    f = float(np.count_nonzero(~sunlit) / len(sunlit))
    pmax = breakeven_w(sc.solar_generation_w, f, sc.charge_efficiency_fraction)
    sims = {}
    for load in (pmax - 0.5, pmax + 0.5):
        r = simulate_energy(
            sunlit=sunlit, payload_on=np.zeros_like(sunlit), step_s=cfg.time.time_step_s,
            capacity_wh=sc.battery_capacity_wh, initial_fraction=1.0,
            charge_efficiency=sc.charge_efficiency_fraction,
            generation_w=sc.solar_generation_w, bus_w=load, payload_w=0.0,
        )  # fmt: skip
        sims[f"{load:.2f}_w"] = {
            "final_wh": r.final_wh,
            "min_wh": r.min_wh,
            "deficit_wh": r.deficit_wh,
            "curtailed_wh": r.curtailed_wh,
        }
    return {"eclipse_fraction_ltan12": f, "breakeven_continuous_load_w": pmax, "sims_3day": sims}


def r3(config: MissionGeometryScenario) -> dict[str, Any]:
    sc = config.spacecraft
    prop = PropulsionBudget(
        mass_kg=sc.mass_kg, thrust_n=sc.thrust_mn * 1e-3,
        specific_impulse_s=sc.specific_impulse_s, budget_mps=sc.delta_v_budget_mps,
    )  # fmt: skip
    t_exact = prop.burn_time_s(sc.delta_v_budget_mps)
    # Independent: integrate m' = -F/ve, v' = F/m with RK4 at 1 s until v reaches the budget.
    ve = sc.specific_impulse_s * G0_MPS2
    thrust = sc.thrust_mn * 1e-3
    m, v, t, h = sc.mass_kg, 0.0, 0.0, 1.0

    def deriv(mm: float) -> tuple[float, float]:
        return -thrust / ve, thrust / mm

    while True:
        k1 = deriv(m)
        k2 = deriv(m + 0.5 * h * k1[0])
        k3 = deriv(m + 0.5 * h * k2[0])
        k4 = deriv(m + h * k3[0])
        dm = h / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        dv = h / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        if v + dv >= sc.delta_v_budget_mps:
            frac = (sc.delta_v_budget_mps - v) / dv  # final partial step (linear)
            t += frac * h
            m += frac * dm
            break
        m, v, t = m + dm, v + dv, t + h
    return {
        "propellant_kg": prop.propellant_kg(sc.delta_v_budget_mps),
        "propellant_numerical_kg": sc.mass_kg - m,
        "thrust_time_h": t_exact / 3600,
        "thrust_time_numerical_h": t / 3600,
        "rel_diff_time": (t_exact - t) / t,
        "constant_mass_thrust_time_h": sc.mass_kg * sc.delta_v_budget_mps / thrust / 3600,
        "thruster_energy_wh": sc.thruster_power_w * t_exact / 3600,
        "acceleration_mps2": thrust / sc.mass_kg,
        "sunlit_thrust_load_w": sc.bus_power_w + sc.thruster_power_w,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    config = load_scenario(CONFIG)
    assert isinstance(config, MissionGeometryScenario)
    result = {
        "R1_energy_by_ltan": r1(config),
        "R2_breakeven": r2(config),
        "R3_propulsion": r3(config),
    }
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

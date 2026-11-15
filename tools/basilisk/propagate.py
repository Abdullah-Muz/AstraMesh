"""Propagate the DL-116 cases with Basilisk (bsk 2.12.2) for comparison with AstraMesh.

Run in this directory's own environment (it never imports astramesh):

    uv run --locked --project tools/basilisk python tools/basilisk/propagate.py <dir>

Reads ``<dir>/cases.json`` (written by ``scripts/experiments/basilisk_comparison.py
cases``) and writes ``<dir>/basilisk.npz`` (one array per case, shape (n_steps + 1,
n_spacecraft, 6): GCRS position [m] and velocity [m/s] at every step) and
``<dir>/basilisk_meta.json``. No Basilisk support data is used: the J2 field comes from a
coefficients file written here from the case constants, and the density table is passed
in, so nothing is downloaded.

Setup per case (DL-116): Earth at the origin with an identity orientation (the J2 axis is
GCRS z); mu and the reference radius set explicitly (``createEarth`` has its own
defaults); C-bar(2,0) normalized as Basilisk's files expect. Drag: ``tabularAtmosphere``
on the spherical altitude |r| - R, ``zeroWindModel`` (co-rotation at omega about z), and
``dragDynamicEffector`` with C_D A / m equal to the case's ballistic coefficient.
Basilisk holds the density and wind messages over each task step.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
from Basilisk.architecture import messaging
from Basilisk.simulation import (
    dragDynamicEffector,
    spacecraft,
    svIntegrators,
    tabularAtmosphere,
    zeroWindModel,
)
from Basilisk.utilities import SimulationBaseClass, macros, simIncludeGravBody

HERE = Path(__file__).resolve().parent
MASS_KG = 100.0
DRAG_COEFF = 2.2


def _coefficients_file(c: dict[str, float], folder: Path) -> Path:
    """Degree-2 zonal field in Basilisk's file format (normalized coefficients)."""
    path = folder / "j2_field.txt"
    rows = [(0, 0, 1.0), (1, 0, 0.0), (1, 1, 0.0), (2, 0, c["c20_normalized"]),
            (2, 1, 0.0), (2, 2, 0.0)]  # fmt: skip
    text = f"{c['r_ref_m']:.16E}, {c['mu']:.16E}, {c['omega_radps']:.16E}, 2, 2, 1, 0.0, 0.0\n"
    text += "".join(f"{n}, {m}, {v:.16E}, 0.0, 0.0, 0.0\n" for n, m, v in rows)
    path.write_text(text)
    return path


def run_case(case: dict[str, Any], doc: dict[str, Any], folder: Path) -> np.ndarray:
    c = doc["constants"]
    dt_ns = macros.sec2nano(doc["step_s"])
    sim = SimulationBaseClass.SimBaseClass()
    proc = sim.CreateNewProcess("proc")
    proc.addTask(sim.CreateNewTask("task", dt_ns))

    grav = simIncludeGravBody.gravBodyFactory()
    earth = grav.createEarth()
    earth.isCentralBody = True
    if case["gravity"] == "j2":
        earth.useSphericalHarmonicsGravityModel(str(_coefficients_file(c, folder)), 2)
    elif case["gravity"] != "point_mass":
        raise ValueError(f"unknown gravity {case['gravity']!r}")
    earth.mu = c["mu"]
    earth.radEquator = c["r_ref_m"]

    crafts, recorders = [], []
    for k, s in enumerate(case["spacecraft"]):
        sc = spacecraft.Spacecraft()
        sc.ModelTag = f"sc{k}"
        sc.hub.mHub = MASS_KG
        sc.hub.r_CN_NInit = list(s["r_m"])
        sc.hub.v_CN_NInit = list(s["v_mps"])
        if case["integrator"] == "rk4":
            integ = svIntegrators.svIntegratorRK4(sc)
        elif case["integrator"] == "rkf78":
            integ = svIntegrators.svIntegratorRKF78(sc)
            integ.relTol = doc["rkf78"]["rel_tol"]
            integ.absTol = doc["rkf78"]["abs_tol"]
        else:
            raise ValueError(f"unknown integrator {case['integrator']!r}")
        sc.setIntegrator(integ)
        grav.addBodiesTo(sc)
        sim.AddModelToTask("task", sc)
        crafts.append((sc, integ))

    if case["drag"]:
        planet = messaging.SpicePlanetStateMsgPayload()
        planet.PositionVector = [0.0, 0.0, 0.0]
        planet.J20002Pfix = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        planet_msg = messaging.SpicePlanetStateMsg().write(planet)
        atmo = tabularAtmosphere.TabularAtmosphere()
        atmo.ModelTag = "atmosphere"
        vec = tabularAtmosphere.DoubleVector
        table = doc["density_table"]
        atmo.altList = vec([float(x) for x in table["alt_m"]])
        atmo.rhoList = vec([float(x) for x in table["rho_kgpm3"]])
        atmo.tempList = vec([1000.0] * len(table["alt_m"]))  # unused by drag
        atmo.planetRadius = c["r_ref_m"]
        wind = zeroWindModel.ZeroWindModel()
        wind.ModelTag = "wind"
        wind.planetPosInMsg.subscribeTo(planet_msg)
        wind.setPlanetOmega_N([0.0, 0.0, c["omega_radps"]])
        effectors = []
        for k, (sc, _) in enumerate(crafts):
            atmo.addSpacecraftToModel(sc.scStateOutMsg)
            wind.addSpacecraftToModel(sc.scStateOutMsg)
            drag = dragDynamicEffector.DragDynamicEffector()
            drag.ModelTag = f"drag{k}"
            b = case["spacecraft"][k]["ballistic_m2pkg"]
            drag.coreParams.dragCoeff = DRAG_COEFF
            drag.coreParams.projectedArea = b * MASS_KG / DRAG_COEFF
            drag.atmoDensInMsg.subscribeTo(atmo.envOutMsgs[k])
            drag.windVelInMsg.subscribeTo(wind.envOutMsgs[k])
            sc.addDynamicEffector(drag)
            effectors.append(drag)
        sim.AddModelToTask("task", atmo)
        sim.AddModelToTask("task", wind)
        for d in effectors:
            sim.AddModelToTask("task", d)

    for sc, _ in crafts:
        rec = sc.scStateOutMsg.recorder(dt_ns)
        sim.AddModelToTask("task", rec)
        recorders.append(rec)
    sim.InitializeSimulation()
    sim.ConfigureStopTime(macros.sec2nano(doc["duration_s"]))
    sim.ExecuteSimulation()
    n = doc["n_steps"] + 1
    out = np.empty((n, len(crafts), 6))
    for k, rec in enumerate(recorders):
        r, v = np.array(rec.r_BN_N), np.array(rec.v_BN_N)
        if len(r) != n:
            raise ValueError(f"{case['name']}: {len(r)} records, expected {n}")
        out[:, k, :3], out[:, k, 3:] = r, v
    return out


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    folder = Path(sys.argv[1])
    raw = (folder / "cases.json").read_bytes()
    doc = json.loads(raw)
    arrays, walls = {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        for case in doc["cases"]:
            t0 = time.perf_counter()
            arrays[case["name"]] = run_case(case, doc, Path(tmp))
            walls[case["name"]] = round(time.perf_counter() - t0, 2)
            print(case["name"], walls[case["name"]], "s", flush=True)
    np.savez(folder / "basilisk.npz", **arrays)
    meta = {
        "bsk_version": version("bsk"),
        "numpy_version": np.__version__,
        "python": sys.version.split()[0],
        "tools_lockfile_sha256": hashlib.sha256((HERE / "uv.lock").read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256(raw).hexdigest(),
        "mass_kg": MASS_KG,
        "drag_coeff": DRAG_COEFF,
        "wall_s": walls,
    }
    (folder / "basilisk_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

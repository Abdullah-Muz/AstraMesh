"""GOES >= 10 MeV integration and the OMNI 1-min parser on synthetic inputs (DL-068)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from astramesh.datasets import omni
from astramesh.datasets.goes import integral_above

# SGPS proton bands reaching above 10 MeV (P4 ... P10), keV
LO = np.array([5840, 11640, 25500, 41000, 80900, 96300, 114880, 153300, 267000.0])
HI = np.array([11000, 23270, 38400, 77000, 97600, 118400, 138400, 229300, 390000.0])


def _band_averages(g: float, scale: float = 1e20) -> np.ndarray:
    if g == 1.0:
        avg = np.log(HI / LO) / (HI - LO)
    else:
        avg = (HI ** (1 - g) - LO ** (1 - g)) / ((1 - g) * (HI - LO))
    return scale * avg[None, :]


def _exact(g: float, scale: float = 1e20, a: float = 1e4, b: float = 5e5) -> float:
    return scale * (np.log(b / a) if g == 1.0 else (b ** (1 - g) - a ** (1 - g)) / (1 - g))


@given(st.floats(0.5, 6.0))
def test_a_pure_power_law_is_integrated_almost_exactly(g: float) -> None:
    got = integral_above(LO, HI, _band_averages(g))[0]
    assert got == pytest.approx(_exact(g), rel=2e-3)  # only the band overlaps are approximate


def test_gamma_one_and_steep_spectra() -> None:
    assert integral_above(LO, HI, _band_averages(1.0))[0] == pytest.approx(_exact(1.0), rel=2e-3)
    assert integral_above(LO, HI, _band_averages(9.0))[0] == pytest.approx(_exact(9.0), rel=1e-3)


def test_measured_bands_are_used_as_measured() -> None:
    j = _band_averages(3.0)
    bumped = j.copy()
    bumped[0, 1] *= 2  # P5 lies wholly above 10 MeV: its band integral enters as measured
    delta = integral_above(LO, HI, bumped)[0] - integral_above(LO, HI, j)[0]
    assert delta > j[0, 1] * (HI[1] - LO[1])  # plus the neighbouring fitted pieces
    assert delta < 2 * j[0, 1] * (HI[1] - LO[1])


def test_non_positive_quiet_fluxes_never_give_negative_flux() -> None:
    j = np.array([[0.0, -1e-6, 2e-5, 0.0, -3e-7, 1e-7, 0.0, 2e-8, -1e-9]])
    v = integral_above(LO, HI, j)[0]
    assert np.isfinite(v)
    assert v >= 0.0


def test_rows_are_independent() -> None:
    j = np.vstack([_band_averages(2.0), _band_averages(4.0)])
    both = integral_above(LO, HI, j)
    assert both[0] == integral_above(LO, HI, j[:1])[0]
    assert both[1] == integral_above(LO, HI, j[1:])[0]


def test_bad_band_layout_is_refused() -> None:
    with pytest.raises(ValueError, match="bands"):
        integral_above(LO[::-1], HI[::-1], _band_averages(2.0)[:, ::-1])


def _omni_row(doy: int, minute: int, bz: float, symh: int, ae: int) -> str:
    v = [2024, doy, minute // 60, minute % 60] + [0.0] * 42
    v[18], v[21], v[37], v[41] = bz, 99999.9, ae, symh
    return " ".join(str(x) for x in v)


def test_omni_parser_times_and_fill_values(tmp_path: Path) -> None:
    p = tmp_path / "omni_min.asc"
    rows = [_omni_row(132, 134, -12.5, -518, 4000), _omni_row(132, 135, 9999.99, 99999, 99999)]
    p.write_text("\n".join(rows) + "\n")
    s = omni.read_file(p)
    assert s.t_ns[0] == np.datetime64("2024-05-11T02:14", "ns").astype(np.int64)
    assert s.t_ns[1] - s.t_ns[0] == omni.MINUTE_NS
    assert s.values["sym_h_nt"][0] == -518
    assert s.values["bz_gsm_nt"][0] == -12.5
    assert np.isnan(s.values["flow_speed_km_s"]).all()
    assert all(np.isnan(s.values[k][1]) for k in ("bz_gsm_nt", "sym_h_nt", "ae_nt"))


def test_omni_parser_refuses_gaps(tmp_path: Path) -> None:
    p = tmp_path / "omni_min.asc"
    p.write_text(_omni_row(132, 0, 1, 1, 1) + "\n" + _omni_row(132, 2, 1, 1, 1) + "\n")
    with pytest.raises(ValueError, match="consecutive"):
        omni.read_file(p)

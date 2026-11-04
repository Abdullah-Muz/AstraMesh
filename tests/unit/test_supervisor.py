"""Five-mode protection supervisor (DL-054, DL-056) and Gate P3 properties: SAFE always
overrides, invalid forecasts are not zero risk, no mode chatter under brief noise."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.supervisor import (
    MODES,
    NOMINAL,
    PROTECTIVE,
    RECOVERY,
    SAFE,
    SCIENCE_MODES,
    STORM_WATCH,
    Supervisor,
    SupervisorSettings,
)

S = 10**9
STEP = 10 * S


def _sup() -> Supervisor:
    return Supervisor(SupervisorSettings())


def _risks(
    rad: float | None = 0.1, nav: float | None = 0.1, orb: float | None = 0.1
) -> dict[str, float | None]:
    return {"radiation": rad, "navcomms": nav, "orbital": orb}


def _feed(sup: Supervisor, t: int, *, batt: float = 0.8, flags: tuple[str, ...] = (),
          risks: dict[str, float | None] | None = None, enabled: bool = True,
          checks: bool = True) -> str:  # fmt: skip
    sup.update(t, battery_fraction=batt, critical_flags=flags,
               risks=_risks() if risks is None else risks, forecast_enabled=enabled,
               recovery_checks_ok=checks)  # fmt: skip
    return sup.mode


def _run(sup: Supervisor, t0: int, n: int, **kw: object) -> int:
    """Feed ``n`` steps from ``t0`` with the same inputs; return the next time."""
    for k in range(n):
        _feed(sup, t0 + k * STEP, **kw)  # type: ignore[arg-type]
    return t0 + n * STEP


def test_watch_entry_on_any_dimension_without_protection() -> None:
    for dim in ("navcomms", "orbital"):
        s = _sup()
        r = _risks(**{"nav" if dim == "navcomms" else "orb": 0.9})
        assert _feed(s, 0, risks=r) == STORM_WATCH
        assert _feed(s, STEP, risks={**r, dim: 5.0}) == STORM_WATCH  # never PROTECTIVE
        assert s.history[0][3] == f"risk>=watch:{dim}"


def test_full_protective_cycle_with_chain_recovery_and_checks() -> None:
    s = _sup()
    assert _feed(s, 0, risks=_risks(rad=1.2)) == PROTECTIVE
    assert [h[2] for h in s.history] == [STORM_WATCH, PROTECTIVE]  # chained, both logged
    t = _run(s, STEP, 180, risks=_risks(rad=0.5))  # 30 min below release (incl. first sample)
    assert s.mode == PROTECTIVE
    assert _feed(s, t, risks=_risks(rad=0.5)) == RECOVERY
    t += STEP
    t = _run(s, t, 29, risks=_risks(rad=0.5), checks=True)  # < 5 min in RECOVERY
    assert s.mode == RECOVERY
    assert _feed(s, t, risks=_risks(rad=0.5), checks=False) == RECOVERY  # checks fail: wait
    assert _feed(s, t + STEP, risks=_risks(rad=0.5), checks=True) == NOMINAL


def test_hazard_returning_during_recovery_goes_back_to_protective() -> None:
    s = _sup()
    _feed(s, 0, risks=_risks(rad=1.5))
    t = _run(s, STEP, 181, risks=_risks(rad=0.5))
    assert s.mode == RECOVERY
    assert _feed(s, t, risks=_risks(rad=1.1)) == PROTECTIVE


def test_watch_release_needs_all_valid_and_calm_for_dwell() -> None:
    s = _sup()
    _feed(s, 0, risks=_risks(nav=0.7))
    t = _run(s, STEP, 170, risks=_risks(nav=0.4))
    _feed(s, t, risks=_risks(nav=None))  # invalid: dwell restarts
    t += STEP
    t = _run(s, t, 180, risks=_risks(nav=0.4))
    assert s.mode == STORM_WATCH
    assert _feed(s, t, risks=_risks(nav=0.4)) == NOMINAL


def test_invalid_forecast_policy() -> None:
    s = _sup()
    t = _run(s, 0, 61, risks=_risks(rad=None))  # exactly 600 s invalid: still NOMINAL
    assert s.mode == NOMINAL
    assert _feed(s, t, risks=_risks(rad=None)) == STORM_WATCH  # > 10 min: uncertainty
    assert s.history[-1][3] == "forecast_invalid>600s"
    t = _run(s, t + STEP, 500, risks=_risks(rad=None))
    assert s.mode == STORM_WATCH  # invalid alone never triggers PROTECTIVE nor releases
    assert [n for _, n in s.notes] == ["forecast_invalid:radiation"]  # once per episode


def test_invalid_never_releases_protective() -> None:
    s = _sup()
    _feed(s, 0, risks=_risks(rad=2.0))
    _run(s, STEP, 1000, risks=_risks(rad=None))
    assert s.mode == PROTECTIVE


@pytest.mark.parametrize("start", [_risks(), _risks(nav=0.7), _risks(rad=1.5)])
def test_safe_overrides_from_any_mode_and_exits_to_recovery(start: dict[str, float | None]) -> None:
    s = _sup()
    _feed(s, 0, risks=start)
    assert _feed(s, STEP, flags=("F1",), risks=start) == SAFE
    t = _run(s, 2 * STEP, 50, flags=("F1",), risks=_risks(rad=0.0))  # good forecast: no exit
    assert s.mode == SAFE
    t = _run(s, t, 60, batt=0.6, risks=_risks(rad=0.0))  # 10 min clear + battery >= 50%
    assert s.mode == SAFE
    assert _feed(s, t, batt=0.6, risks=_risks(rad=0.0)) == RECOVERY
    s2 = _sup()
    _feed(s2, 0, risks=start)
    assert _feed(s2, STEP, batt=0.10, risks=start) == SAFE  # battery_low


def test_no_forecast_service_means_no_environmental_input() -> None:
    s = _sup()
    _run(s, 0, 100, risks={}, enabled=False)
    assert s.mode == NOMINAL
    assert s.notes == []


def test_brief_noise_does_not_chatter() -> None:
    """Radiation jittering across every threshold each step for 3 h."""
    s = _sup()
    for k in range(1080):
        _feed(s, k * STEP, risks=_risks(rad=(1.01, 0.79, 0.59, 0.49)[k % 4]))
    assert [h[2] for h in s.history] == [STORM_WATCH, PROTECTIVE]


inputs = st.lists(
    st.tuples(
        st.one_of(st.none(), st.floats(0.0, 1.0)),
        st.lists(st.sampled_from(["F1", "F2"]), max_size=2, unique=True),
        st.tuples(*(st.one_of(st.none(), st.floats(0.0, 3.0)) for _ in range(3))),
        st.booleans(),
        st.booleans(),
    ),
    max_size=400,
)


@settings(max_examples=200)
@given(inputs)
def test_properties(
    seq: list[tuple[float | None, list[str], tuple[float | None, ...], bool, bool]],
) -> None:
    s = _sup()
    for k, (batt, flags, (rad, nav, orb), enabled, checks) in enumerate(seq):
        s.update(k * STEP, battery_fraction=batt, critical_flags=tuple(flags),
                 risks=_risks(rad, nav, orb), forecast_enabled=enabled,
                 recovery_checks_ok=checks)  # fmt: skip
        assert s.mode in MODES
        assert s.allows_payload() == (s.mode in SCIENCE_MODES)
        if flags or (batt is not None and batt <= 0.10):
            assert s.mode == SAFE  # SAFE always overrides
    for t, old, new, _ in s.history:
        assert not (old == SAFE and new != RECOVERY)  # SAFE only exits through RECOVERY
        assert not (old == PROTECTIVE and new == NOMINAL)  # PROTECTIVE exits via RECOVERY
        assert not (new == PROTECTIVE and old == NOMINAL)  # always via STORM_WATCH
        assert t >= 0


@pytest.mark.parametrize(
    "kw",
    [{"safe_battery_fraction": 0.6}, {"release_ratio": 1.0}, {"watch_ratio": 1.2},
     {"watch_release_ratio": 0.7}, {"recovery_min_dwell_ns": -1}],
)  # fmt: skip
def test_settings_validated(kw: dict[str, float]) -> None:
    with pytest.raises(ValueError, match=r"need|dwell"):
        SupervisorSettings(**kw)  # type: ignore[arg-type]

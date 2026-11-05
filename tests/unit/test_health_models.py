"""H-B silence model, H-C payload filter, score sensor and config wiring (DL-066)."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st

from astramesh.agents.agent import AgentSettings, SpacecraftAgent
from astramesh.agents.health import (
    HEALTHY,
    LOST,
    SUSPECTED,
    BayesSettings,
    HealthSettings,
    HealthTracker,
    PayloadBelief,
    PayloadSettings,
    p_unavailable,
)
from astramesh.agents.packets import PayloadCheck
from astramesh.anomaly.adapter import ScoreSensor
from astramesh.core.config import parse_scenario
from astramesh.core.rng import RandomStreams

S = 10**9
ROOT = Path(__file__).resolve().parents[2]
SENSOR = "configs/data/opssat_score_sensor.json"
SENSOR_SHA = hashlib.sha256((ROOT / SENSOR).read_bytes()).hexdigest()
BAYES = BayesSettings(status_interval_ns=30 * S, mtbf_ns=30 * 86400 * S)
PAYLOAD = PayloadSettings(interval_ns=300 * S, mtbf_ns=30 * 86400 * S, repair_ns=86400 * S,
                          train_prior=0.16)  # fmt: skip


# -- H-B -------------------------------------------------------------------------------
@given(st.integers(0, 3600), st.floats(0.5, 50), st.floats(5, 5000))
def test_p_unavailable_is_a_probability_and_grows_with_silence(s: int, a: float, b: float) -> None:
    p0, p1 = p_unavailable(s * S, a, b, BAYES), p_unavailable((s + 30) * S, a, b, BAYES)
    assert 0.0 <= p0 <= p1 <= 1.0


def test_learned_low_loss_detects_sooner() -> None:
    # same silence: the more reliable the link has proved, the likelier a real outage
    assert p_unavailable(90 * S, 1, 30, BAYES) < p_unavailable(90 * S, 1, 3000, BAYES)
    assert p_unavailable(0, 1, 30, BAYES) == 0.0


def _bayes_tracker() -> HealthTracker:
    return HealthTracker(HealthSettings(90 * S, 300 * S, 2, bayes=BAYES), ("a",))


def test_bayes_tracker_suspects_then_loses_before_the_timeout() -> None:
    h = _bayes_tracker()
    for k in range(200):  # 100 min of status every 30 s, none lost
        h.heard("a", k * 30 * S, status=True, degraded=False)
    last = 199 * 30 * S
    assert h.belief("a") == HEALTHY
    beliefs = {}
    for dt in range(10, 310, 10):
        h.tick(last + dt * S)
        beliefs[dt] = h.belief("a")
    first_lost = min(dt for dt, b in beliefs.items() if b == LOST)
    assert first_lost <= 120  # sooner than H-A's 300 s timer
    assert set(beliefs.values()) == {HEALTHY, LOST}  # learned link: no SUSPECTED phase


def test_bayes_tracker_suspects_first_while_the_link_is_unproven() -> None:
    h = _bayes_tracker()  # prior Beta(1, 30): nothing learned yet
    h.heard("a", 0, status=True, degraded=False)
    h.tick(120 * S)
    assert h.belief("a") == SUSPECTED
    h.tick(150 * S)
    assert h.belief("a") == SUSPECTED  # P = 0.9495, just below lost_p
    h.tick(180 * S)
    assert h.belief("a") == LOST


def test_loss_rate_is_learned_only_while_believed_up() -> None:
    h = _bayes_tracker()
    h.heard("a", 0, status=True, degraded=False)
    h.heard("a", 90 * S, status=True, degraded=False)  # two status messages missed
    peer = h._p["a"]
    assert (peer.loss_a, peer.loss_b) == (3.0, 31.0)
    h.tick(2000 * S)  # long silence: LOST
    assert h.belief("a") == LOST
    h.heard("a", 2010 * S, status=True, degraded=False)  # the outage is not counted as loss
    assert (peer.loss_a, peer.loss_b) == (3.0, 31.0)


def test_bayes_settings_validation() -> None:
    with pytest.raises(ValueError, match="suspect_p"):
        BayesSettings(30 * S, S, suspect_p=0.9, lost_p=0.5)
    with pytest.raises(ValueError, match="Beta"):
        BayesSettings(30 * S, S, loss_a=0)


# -- H-C payload filter -------------------------------------------------------------------
def test_payload_filter_needs_repeated_evidence_and_has_hysteresis() -> None:
    b = PayloadBelief(PAYLOAD)
    assert not b.update(300 * S, 0.99)  # one alarming check is not enough
    assert b.update(600 * S, 0.99)  # the second is
    assert b.degraded
    assert not b.update(900 * S, 0.5)  # ambiguous: stays degraded (hysteresis)
    changed = [b.update((1200 + 300 * k) * S, 0.01) for k in range(5)]
    assert any(changed)
    assert not b.degraded


def test_payload_filter_ignores_healthy_scores() -> None:
    b = PayloadBelief(PAYLOAD)
    for k in range(1, 289):
        b.update(300 * k * S, 0.16)  # exactly the training base rate: no evidence
    assert not b.degraded
    h, r = 1 / (30 * 288), 1 / 288  # per-check onset and repair rates
    assert 0.0 < b.p < h / (h + r)  # rising towards the stationary prior (~0.032), no further


# -- adapter ------------------------------------------------------------------------------
def test_score_sensor_checks_its_pin_and_draws_by_state() -> None:
    with pytest.raises(ValueError, match="sha256"):
        ScoreSensor.load(SENSOR, "0" * 64, "time")
    s = ScoreSensor.load(SENSOR, SENSOR_SHA, "time")
    assert len(s.nominal) == 351
    assert len(s.anomalous) == 176
    assert s.train_prior == pytest.approx(258 / 1596, abs=1e-6)
    rng = np.random.default_rng(0)
    nom = [s.draw(rng, False) for _ in range(500)]
    bad = [s.draw(rng, True) for _ in range(500)]
    assert set(nom) <= set(s.nominal)
    assert set(bad) <= set(s.anomalous)
    assert np.mean(bad) > np.mean(nom) + 0.5
    shifted = ScoreSensor(s.nominal, s.anomalous, s.train_prior, nominal_contamination=0.5)
    mixed = [shifted.draw(rng, False) for _ in range(500)]
    assert np.mean(mixed) > np.mean(nom) + 0.2


def test_substream_does_not_advance_the_parent_stream() -> None:
    a, b = RandomStreams(3), RandomStreams(3)
    a.substream("sensors", "payload_check").random(10)
    assert a["sensors"].random() == b["sensors"].random()
    x = RandomStreams(3).substream("sensors", "payload_check").random()
    assert x == RandomStreams(3).substream("sensors", "payload_check").random()
    assert x != RandomStreams(3).substream("sensors", "other").random()


# -- agent ----------------------------------------------------------------------------------
def _agent(payload: PayloadSettings | None) -> SpacecraftAgent:
    st_ = AgentSettings(status_interval_ns=30 * S, status_lifetime_ns=60 * S,
                        payload_check=payload)  # fmt: skip
    return SpacecraftAgent("sc00", ("sc01",), st_)


def test_agent_reports_its_payload_only_under_h_c() -> None:
    plain = _agent(None)
    plain.observe(PayloadCheck(300 * S, 0.99))
    assert not plain.payload_degraded
    assert "payload" not in plain.step(0)[0].payload  # H-A / H-B messages unchanged
    hc = _agent(PAYLOAD)
    assert hc.step(0)[0].payload["payload"] == "ok"
    hc.observe(PayloadCheck(300 * S, 0.99))
    hc.observe(PayloadCheck(600 * S, 0.99))
    assert hc.payload_degraded
    status = [m for m in hc.step(30 * S) if m.payload.get("payload")]
    assert status[0].payload["payload"] == "degraded"
    kinds = [e["kind"] for e in hc.drain_log()]
    assert "payload_belief_changed" in kinds


# -- config ----------------------------------------------------------------------------------
def _cfg() -> dict[str, object]:
    raw = yaml.safe_load((ROOT / "configs/experiments/nominal_ops_b0_24h.yaml").read_text())
    return copy.deepcopy(raw)


def test_absent_health_block_keeps_the_config_hash() -> None:
    base = parse_scenario(_cfg())
    assert "health" not in base.canonical_dict()["agents"]
    raw = _cfg()
    raw["agents"]["health"] = {"model": "timeout"}  # type: ignore[index]
    explicit = parse_scenario(raw)
    assert explicit.config_hash() != base.config_hash()  # recorded when given


def test_payload_check_config_validation() -> None:
    raw = _cfg()
    check = {"sensor_sha256": SENSOR_SHA, "interval_s": 25}
    raw["agents"]["health"] = {"model": "bayes", "payload_check": check}  # type: ignore[index]
    with pytest.raises(ValueError, match=r"payload_check\.interval_s"):
        parse_scenario(raw)
    raw["agents"]["health"]["payload_check"]["interval_s"] = 300  # type: ignore[index]
    raw["agents"]["health"]["payload_check"]["clear_probability"] = 0.95  # type: ignore[index]
    with pytest.raises(ValueError, match="clear_probability"):
        parse_scenario(raw)

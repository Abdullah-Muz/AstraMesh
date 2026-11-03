from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from astramesh.core.events import EventLog, canonical_json

json_scalars = st.none() | st.booleans() | st.integers(-(2**53), 2**53) | st.text(max_size=20)
json_values = st.recursive(
    json_scalars,
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=12,
)


def test_record_assigns_sequential_ids() -> None:
    log = EventLog()
    for i in range(3):
        event = log.record(tick=i, time_ns=i * 10, source="sim", kind="k")
        assert event.seq == i
    assert len(log) == 3


def test_time_must_not_decrease() -> None:
    log = EventLog()
    log.record(tick=2, time_ns=20, source="sim", kind="k")
    log.record(tick=2, time_ns=20, source="sim", kind="same_time_ok")
    with pytest.raises(ValueError, match="non-decreasing"):
        log.record(tick=1, time_ns=10, source="sim", kind="k")


@pytest.mark.parametrize("data", [{"x": float("nan")}, {"x": object()}, {"x": float("inf")}])
def test_rejects_non_json_payload(data: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="not JSON-serializable"):
        EventLog().record(tick=0, time_ns=0, source="sim", kind="k", data=data)


def test_payload_is_detached_from_caller() -> None:
    payload: dict[str, object] = {"items": [1, 2]}
    log = EventLog()
    event = log.record(tick=0, time_ns=0, source="sim", kind="k", data=payload)
    payload["items"].append(3)  # type: ignore[attr-defined]
    assert event.data["items"] == [1, 2]


def test_jsonl_is_canonical_and_lf_terminated(tmp_path: Path) -> None:
    log = EventLog()
    log.record(tick=0, time_ns=0, source="sim", kind="k", data={"b": 1, "a": 2})
    path = tmp_path / "events.jsonl"
    digest = log.write_jsonl(path)
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert raw.index(b'"a"') < raw.index(b'"b"')  # sorted keys
    assert digest == log.sha256()


@given(data=st.dictionaries(st.text(max_size=8), json_values, max_size=5))
def test_serialization_round_trips(data: dict[str, object]) -> None:
    log = EventLog()
    event = log.record(tick=0, time_ns=0, source="sim", kind="k", data=data)
    decoded = json.loads(event.to_json_line())
    assert decoded["data"] == json.loads(canonical_json(data))
    assert decoded["t_ns"] == 0

"""Fast paths in message freezing, size accounting and CBBA payload checks (DL-074) must
give exactly what the general paths give: same frozen data, same errors, same bytes."""

from __future__ import annotations

import enum
import math
from collections import OrderedDict
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astramesh.agents.cbba import CbbaState
from astramesh.communications.messages import (
    Message,
    MessageError,
    MessageType,
    freeze,
    thaw,
)
from astramesh.core.events import canonical_json

scalars = st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=5)
json_like = st.recursive(
    scalars,
    lambda c: st.lists(c, max_size=4) | st.tuples(c, c)
    | st.dictionaries(st.text(max_size=4), c, max_size=4),
    max_leaves=25,
)  # fmt: skip


def _tagged(value: Any) -> Any:
    """Exact structure: type names all the way down, so True / 1 / 1.0, -0.0 / 0.0 and
    tuple / list / mapping are told apart (``==`` after ``thaw`` cannot)."""
    if isinstance(value, Mapping):
        return (type(value).__name__, tuple((k, _tagged(v)) for k, v in value.items()))
    if isinstance(value, tuple | list):
        return (type(value).__name__, tuple(_tagged(v) for v in value))
    return (type(value).__name__, repr(value))


def _freeze_old(value: Any, *, path: str = "payload") -> Any:
    """``freeze`` as it was before DL-074 (commit 9c458af), kept here verbatim as the
    reference, so the oracle cannot change together with the module under test."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MessageError(f"{path} contains a non-finite float")
        return value
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise MessageError(f"{path} has a non-string key {k!r}")
            out[k] = _freeze_old(v, path=f"{path}.{k}")
        return MappingProxyType(out)
    if isinstance(value, list | tuple):
        return tuple(_freeze_old(v, path=f"{path}[{i}]") for i, v in enumerate(value))
    raise MessageError(f"{path} has unsupported type {type(value).__name__}")


def _general(value: Any) -> tuple[str, Any]:
    try:
        return "ok", _freeze_old(value)
    except MessageError as e:
        return "error", str(e)


@settings(max_examples=300, deadline=None)
@given(json_like)
def test_fast_freeze_equals_the_old_freeze(value: Any) -> None:
    try:
        got: tuple[str, Any] = ("ok", freeze(value))
    except MessageError as e:
        got = ("error", str(e))
    want = _general(value)
    assert got[0] == want[0]
    if got[0] == "ok":
        assert _tagged(got[1]) == _tagged(want[1])
    else:
        assert got[1] == want[1]


class Level(enum.IntEnum):
    HIGH = 2


def test_unusual_types_freeze_as_before() -> None:
    value = {"a": Level.HIGH, "b": OrderedDict(x=[1, (2.5, "s")]), "c": True}
    assert _tagged(freeze(value)) == _tagged(_freeze_old(value))
    with pytest.raises(MessageError, match=r"payload\.b\.x\[1\] contains a non-finite"):
        freeze({"b": {"x": [1, float("inf")]}})
    with pytest.raises(MessageError, match="non-string key 3"):
        freeze({"ok": {3: 1}})
    with pytest.raises(MessageError, match=r"payload\.s has unsupported type set"):
        freeze({"s": {1, 2}})


@settings(max_examples=200, deadline=None)
@given(st.dictionaries(st.text(max_size=6), json_like, max_size=6))
def test_size_is_the_canonical_json_length_of_to_dict(payload: dict[str, Any]) -> None:
    try:
        m = Message("sc00", 1, 0, 10, MessageType.PLAN_SYNC, 0, payload)
    except MessageError:
        return
    assert m.size_bytes == len(canonical_json(m.to_dict()).encode("ascii"))


def _valid_general(p: dict[str, Any]) -> bool:
    y, z, s = p["y"], p["z"], p["s"]
    if set(y) != set(z):
        return False
    return (all(isinstance(v, int | float) and not isinstance(v, bool) and v >= 0
                for v in y.values())
            and all(isinstance(v, str) for v in z.values())
            and all(isinstance(v, int) and not isinstance(v, bool)
                    for v in s.values()))  # fmt: skip


values = st.booleans() | st.integers(-3, 3) | st.floats(-3, 3) | st.text(max_size=2) | st.none()


stamps = values | st.just(Level.HIGH)


@settings(max_examples=300, deadline=None)
@given(st.dictionaries(st.sampled_from("abc"), values, max_size=3),
       st.dictionaries(st.sampled_from("abc"), values, max_size=3),
       st.dictionaries(st.sampled_from("wxyz"), stamps, max_size=3))  # fmt: skip
def test_cbba_payload_check_is_unchanged(y: dict[str, Any], z: dict[str, Any],
                                         s: dict[str, Any]) -> None:  # fmt: skip
    p = {"y": y, "z": z, "s": s}
    frozen = freeze(p)
    assert CbbaState.valid_payload(frozen) == _valid_general(p)  # type: ignore[arg-type]


class Mode(enum.StrEnum):
    SAFE = "safe"


class Key(str):
    pass


def test_unusual_values_give_the_same_size_as_before() -> None:
    unusual: list[Mapping[str, Any]] = [
        {"lvl": Level.HIGH, "mode": Mode.SAFE, "flag": True, "z": -0.0, "big": 10**30},
        {Key("k"): [Key("v"), (1, 2.5)]},
        OrderedDict(b=1, a={"y": [None, "s"]}),
        MappingProxyType({"m": MappingProxyType({"n": (1,)})}),
    ]
    for payload in unusual:
        m = Message("sc00", 1, 0, 10, MessageType.PLAN_SYNC, 0, payload)
        assert m.size_bytes == len(canonical_json(m.to_dict()).encode("ascii"))
        again = Message("sc00", 2, 0, 10, MessageType.PLAN_SYNC, 0, thaw(m.payload))
        assert again.size_bytes == m.size_bytes


@settings(max_examples=100, deadline=None)
@given(json_like, st.sampled_from(["payload", "payload.y", "x[3]"]))
def test_errors_name_the_path_and_carry_no_internal_context(value: Any, path: str) -> None:
    err: MessageError | None = None
    try:
        got: tuple[str, Any] = ("ok", _tagged(freeze(value, path=path)))
    except MessageError as e:
        err, got = e, ("error", str(e))
    if err is not None:  # no trace of the fast path's internal exception
        assert err.__context__ is None
        assert err.__cause__ is None
    try:
        want: tuple[str, Any] = ("ok", _tagged(_freeze_old(value, path=path)))
    except MessageError as e:
        want = ("error", str(e))
    assert got == want


# Unusual types buried anywhere inside otherwise plain data: the fast path must give up
# and the general path must give exactly the old result, from any depth.
odd_leaves = (
    scalars
    | st.just(Level.HIGH)
    | st.just(Mode.SAFE)
    | st.builds(Key, st.text(max_size=3))
    | st.just({1, 2})
    | st.just(float("nan"))
)
odd_data = st.recursive(
    odd_leaves,
    lambda c: st.lists(c, max_size=3) | st.tuples(c, c)
    | st.dictionaries(st.text(max_size=3), c, max_size=3)
    | st.dictionaries(st.text(max_size=3), c, max_size=3).map(OrderedDict)
    | st.dictionaries(st.text(max_size=3), c, max_size=3).map(MappingProxyType)
    | st.dictionaries(st.builds(Key, st.text(max_size=3)), c, max_size=2)
    | st.dictionaries(st.integers(0, 3), c, max_size=2),
    max_leaves=25,
)  # fmt: skip


@settings(max_examples=300, deadline=None)
@given(st.dictionaries(st.text(max_size=4), odd_data, max_size=4))
def test_deeply_buried_unusual_types_give_old_values_errors_and_sizes(
    payload: dict[str, Any],
) -> None:
    try:
        got: tuple[str, Any] = ("ok", _tagged(freeze(payload)))
    except MessageError as e:
        got = ("error", str(e))
    try:
        want: tuple[str, Any] = ("ok", _tagged(_freeze_old(payload)))
    except MessageError as e:
        want = ("error", str(e))
    assert got == want
    if got[0] == "ok":
        m = Message("sc00", 1, 0, 10, MessageType.PLAN_SYNC, 0, payload)
        assert m.size_bytes == len(canonical_json(m.to_dict()).encode("ascii"))

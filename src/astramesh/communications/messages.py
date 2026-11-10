"""Message schema (spec §5.3).

Every message carries sender ID, sequence ID, creation time, expiry, message
type, plan version, and a payload. Messages are immutable: the payload is
deep-frozen into read-only mappings and tuples of JSON scalars, so a receiver
cannot modify what another agent sent (and nothing can alias an agent's
private state through a message).

Times are integer nanoseconds since the scenario epoch (CONVENTIONS §2).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

Frozen = None | bool | int | float | str | tuple[Any, ...] | Mapping[str, Any]


class MessageType(StrEnum):
    """Application message types. Agents must reject types they do not handle."""

    STATUS = "status"  # periodic own-state / plan-version report (spec §5.3: every 30 s)
    TASK_BID = "task_bid"  # reserved for the allocation increments; not handled yet
    TASK_AWARD = "task_award"  # reserved
    PLAN_SYNC = "plan_sync"  # reserved


class MessageError(ValueError):
    """Raised when a message would violate the schema."""


class _Invalid(Exception):
    """Internal: ``_freeze_fast`` met data that ``freeze`` must reject."""


def _freeze_fast(value: Any) -> Frozen:
    """``freeze`` without building error paths; raises ``_Invalid`` on bad data."""
    t = type(value)
    if t is str or t is int or t is bool or value is None:
        return value  # type: ignore[no-any-return]
    if t is float:
        if not math.isfinite(value):
            raise _Invalid
        return value  # type: ignore[no-any-return]
    if t is dict:
        out: dict[str, Any] = {}
        for k, v in value.items():
            if type(k) is not str:
                raise _Invalid
            out[k] = _freeze_fast(v)
        return MappingProxyType(out)
    if t is list or t is tuple:
        return tuple(_freeze_fast(v) for v in value)
    raise _Invalid  # anything else (subclasses, other mappings): the general path decides


def freeze(value: Any, *, path: str = "payload") -> Frozen:
    """Deep-freeze JSON-like data: dict -> read-only mapping, list/tuple -> tuple.

    Only str keys and None/bool/int/finite float/str leaves are allowed. Plain
    dicts, lists and scalars take a fast path; anything else, and any error, goes
    through the general recursion, which names the offending path.
    """
    if path == "payload":
        try:
            return _freeze_fast(value)
        except _Invalid:
            pass
    return _freeze_general(value, path=path)


def _freeze_general(value: Any, *, path: str) -> Frozen:
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
            out[k] = _freeze_general(v, path=f"{path}.{k}")
        return MappingProxyType(out)
    if isinstance(value, list | tuple):
        return tuple(_freeze_general(v, path=f"{path}[{i}]") for i, v in enumerate(value))
    raise MessageError(f"{path} has unsupported type {type(value).__name__}")


def thaw(value: Any) -> Any:
    """JSON-ready copy of frozen data (mappings -> dict, tuples -> list)."""
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [thaw(v) for v in value]
    return value


@dataclass(frozen=True, slots=True)
class Message:
    sender: str
    seq: int
    created_ns: int
    expires_ns: int
    msg_type: MessageType
    plan_version: int
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.sender, str) or not self.sender:
            raise MessageError("sender must be a non-empty string")
        for name in ("seq", "created_ns", "expires_ns", "plan_version"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise MessageError(f"{name} must be a non-negative int, got {v!r}")
        if self.expires_ns <= self.created_ns:
            raise MessageError("expires_ns must be after created_ns")
        if not isinstance(self.msg_type, MessageType):
            raise MessageError(f"msg_type must be a MessageType, got {self.msg_type!r}")
        frozen = freeze(self.payload)
        if not isinstance(frozen, Mapping):
            raise MessageError("payload must be a mapping")
        object.__setattr__(self, "payload", frozen)

    @property
    def key(self) -> tuple[str, int]:
        """Unique message identity (sender, sequence ID), used for duplicate detection."""
        return (self.sender, self.seq)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender": self.sender,
            "seq": self.seq,
            "created_ns": self.created_ns,
            "expires_ns": self.expires_ns,
            "type": str(self.msg_type),
            "plan_version": self.plan_version,
            "payload": thaw(self.payload),
        }

    @property
    def size_bytes(self) -> int:
        """Encoded size (canonical JSON, as ``canonical_json(self.to_dict())``), used for
        packet/byte accounting. The frozen payload is encoded directly: the encoder
        writes tuples as lists and turns read-only mappings into dicts as it meets
        them, which gives the same text without first copying the whole payload."""
        d = self._to_dict_frozen()
        return len(_ENCODER.encode(d).encode("ascii"))

    def _to_dict_frozen(self) -> dict[str, Any]:
        """``to_dict`` with the payload left frozen (for encoding only)."""
        return {
            "sender": self.sender,
            "seq": self.seq,
            "created_ns": self.created_ns,
            "expires_ns": self.expires_ns,
            "type": str(self.msg_type),
            "plan_version": self.plan_version,
            "payload": self.payload,
        }


def _mapping_as_dict(o: Any) -> dict[str, Any]:
    if isinstance(o, Mapping):
        return dict(o)
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


# Same settings as ``core.events.canonical_json``, plus frozen mappings.
_ENCODER = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                            allow_nan=False, default=_mapping_as_dict)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Delivery:
    """A message as handed to one receiver by the network."""

    message: Message
    receiver: str
    delivered_ns: int

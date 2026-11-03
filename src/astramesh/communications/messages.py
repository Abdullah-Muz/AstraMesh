"""Message schema (spec §5.3).

Every message carries sender ID, sequence ID, creation time, expiry, message
type, plan version, and a payload. Messages are immutable: the payload is
deep-frozen into read-only mappings and tuples of JSON scalars, so a receiver
cannot modify what another agent sent (and nothing can alias an agent's
private state through a message).

Times are integer nanoseconds since the scenario epoch (CONVENTIONS §2).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from astramesh.core.events import canonical_json

Frozen = None | bool | int | float | str | tuple[Any, ...] | Mapping[str, Any]


class MessageType(StrEnum):
    """Application message types. Agents must reject types they do not handle."""

    STATUS = "status"  # periodic own-state / plan-version report (spec §5.3: every 30 s)
    TASK_BID = "task_bid"  # reserved for the allocation increments; not handled yet
    TASK_AWARD = "task_award"  # reserved
    PLAN_SYNC = "plan_sync"  # reserved


class MessageError(ValueError):
    """Raised when a message would violate the schema."""


def freeze(value: Any, *, path: str = "payload") -> Frozen:
    """Deep-freeze JSON-like data: dict -> read-only mapping, list/tuple -> tuple.

    Only str keys and None/bool/int/finite float/str leaves are allowed.
    """
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
            out[k] = freeze(v, path=f"{path}.{k}")
        return MappingProxyType(out)
    if isinstance(value, list | tuple):
        return tuple(freeze(v, path=f"{path}[{i}]") for i, v in enumerate(value))
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
        """Encoded size (canonical JSON), used for packet/byte accounting."""
        return len(canonical_json(self.to_dict()).encode("ascii"))


@dataclass(frozen=True, slots=True)
class Delivery:
    """A message as handed to one receiver by the network."""

    message: Message
    receiver: str
    delivered_ns: int

"""Append-only, replayable simulation event log.

Events are serialized as canonical JSON Lines (sorted keys, compact separators,
ASCII only, no NaN/Infinity, ``\\n`` line endings) so that two runs of the same
configuration produce byte-identical logs, and the log's SHA-256 can be used to
check replay. Events contain simulation time only, never wall-clock time.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astramesh.core.clock import NS_PER_S

EVENT_SCHEMA_VERSION = 1


def canonical_json(obj: Any) -> str:
    """Deterministic JSON encoding used for events, manifests, and hashes."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


@dataclass(frozen=True, slots=True)
class Event:
    """A single logged event.

    Attributes:
        seq: 0-based position in the log.
        tick: Clock tick at which the event occurred.
        time_ns: Elapsed simulation nanoseconds since epoch (authoritative time).
        source: Emitting component, e.g. ``"sim"`` or a node/agent ID.
        kind: Event type, e.g. ``"heartbeat_sent"``.
        data: JSON-compatible payload (deep-copied on record).
    """

    seq: int
    tick: int
    time_ns: int
    source: str
    kind: str
    data: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "tick": self.tick,
            "t_ns": self.time_ns,
            "t_s": self.time_ns / NS_PER_S,
            "source": self.source,
            "kind": self.kind,
            "data": dict(self.data),
        }

    def to_json_line(self) -> str:
        return canonical_json(self.to_dict())


class EventLog:
    """Ordered collection of :class:`Event` records with non-decreasing time."""

    __slots__ = ("_events",)

    def __init__(self) -> None:
        self._events: list[Event] = []

    def record(
        self,
        *,
        tick: int,
        time_ns: int,
        source: str,
        kind: str,
        data: Mapping[str, Any] | None = None,
    ) -> Event:
        if not source or not kind:
            raise ValueError("event source and kind must be non-empty strings")
        if tick < 0 or time_ns < 0:
            raise ValueError("event tick and time must be non-negative")
        if self._events:
            last = self._events[-1]
            if time_ns < last.time_ns or tick < last.tick:
                raise ValueError(
                    f"event time must be non-decreasing: got tick={tick}, t_ns={time_ns} "
                    f"after tick={last.tick}, t_ns={last.time_ns}"
                )
        payload = dict(data or {})
        try:
            # Round-trip through canonical JSON: validates the payload and detaches
            # it from caller-owned mutable objects.
            frozen = json.loads(canonical_json(payload))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"event data for {kind!r} is not JSON-serializable: {exc}") from exc
        event = Event(
            seq=len(self._events),
            tick=tick,
            time_ns=time_ns,
            source=source,
            kind=kind,
            data=frozen,
        )
        self._events.append(event)
        return event

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[Event]:
        return iter(self._events)

    def to_jsonl(self) -> str:
        return "".join(e.to_json_line() + "\n" for e in self._events)

    def sha256(self) -> str:
        return hashlib.sha256(self.to_jsonl().encode("ascii")).hexdigest()

    def write_jsonl(self, path: Path) -> str:
        """Write the log to ``path`` and return its SHA-256 hex digest."""
        text = self.to_jsonl()
        with path.open("w", encoding="ascii", newline="\n") as fh:
            fh.write(text)
        return hashlib.sha256(text.encode("ascii")).hexdigest()

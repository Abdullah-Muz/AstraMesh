"""Deterministic simulation clock.

Simulation time is an integer count of nanoseconds elapsed since the scenario
epoch. Time points are computed as ``tick * step_ns`` (never by accumulating
floating-point increments), so the same configuration always produces exactly
the same sequence of time points on every platform.

Elapsed time is measured in SI seconds. Converting an elapsed time back to a
calendar UTC timestamp requires a leap-second table and is deliberately *not*
provided here; it belongs to the Phase 1 time/frame layer (Astropy). See
``docs/CONVENTIONS.md``.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

NS_PER_S = 1_000_000_000


def seconds_to_ns(value_s: float, *, name: str = "value") -> int:
    """Convert a duration in seconds to an exact integer number of nanoseconds.

    The decimal representation of ``value_s`` must be an exact multiple of 1 ns
    (e.g. ``10``, ``0.5``, ``1e-9``). Values that are not representable, not
    finite, or negative raise :class:`ValueError` rather than being rounded.
    """
    if isinstance(value_s, bool) or not isinstance(value_s, int | float):
        raise TypeError(f"{name} must be a number of seconds, got {type(value_s).__name__}")
    if not math.isfinite(value_s):
        raise ValueError(f"{name} must be finite, got {value_s!r}")
    if value_s < 0:
        raise ValueError(f"{name} must be non-negative, got {value_s!r}")
    try:
        ns = Decimal(repr(value_s)) * NS_PER_S
    except InvalidOperation as exc:  # pragma: no cover - repr of a finite float is always valid
        raise ValueError(f"{name} is not a valid number: {value_s!r}") from exc
    if ns != ns.to_integral_value():
        raise ValueError(f"{name} must be a whole number of nanoseconds, got {value_s!r} s")
    return int(ns)


def require_utc(epoch: datetime, *, name: str = "epoch") -> datetime:
    """Return ``epoch`` normalized to UTC, rejecting naive or non-UTC datetimes."""
    if epoch.tzinfo is None or epoch.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC (e.g. '2025-06-01T00:00:00Z')")
    if epoch.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must have a UTC offset of zero, got {epoch.isoformat()}")
    return epoch.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ClockSpec:
    """Immutable description of a simulation time grid.

    Attributes:
        epoch_utc: Scenario epoch (time point ``tick == 0``), timezone-aware UTC.
        step_ns: Fixed time step in nanoseconds (> 0).
        duration_ns: Scenario duration in nanoseconds (>= 0, multiple of ``step_ns``).
    """

    epoch_utc: datetime
    step_ns: int
    duration_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "epoch_utc", require_utc(self.epoch_utc, name="epoch_utc"))
        for attr in ("step_ns", "duration_ns"):
            value = getattr(self, attr)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{attr} must be an int, got {type(value).__name__}")
        if self.step_ns <= 0:
            raise ValueError(f"step_ns must be positive, got {self.step_ns}")
        if self.duration_ns < 0:
            raise ValueError(f"duration_ns must be non-negative, got {self.duration_ns}")
        if self.duration_ns % self.step_ns != 0:
            raise ValueError(
                f"duration ({self.duration_ns} ns) must be an integer multiple of the "
                f"time step ({self.step_ns} ns)"
            )

    @classmethod
    def from_seconds(cls, epoch_utc: datetime, step_s: float, duration_s: float) -> ClockSpec:
        return cls(
            epoch_utc=epoch_utc,
            step_ns=seconds_to_ns(step_s, name="time_step_s"),
            duration_ns=seconds_to_ns(duration_s, name="duration_s"),
        )

    @property
    def n_steps(self) -> int:
        """Number of steps; the grid has ``n_steps + 1`` time points (both ends included)."""
        return self.duration_ns // self.step_ns

    def time_ns(self, tick: int) -> int:
        """Elapsed nanoseconds since epoch at ``tick``."""
        if not 0 <= tick <= self.n_steps:
            raise ValueError(f"tick {tick} outside grid [0, {self.n_steps}]")
        return tick * self.step_ns


@dataclass(slots=True)
class SimulationClock:
    """Forward-only clock over a :class:`ClockSpec` time grid."""

    spec: ClockSpec
    _tick: int = field(default=0, init=False)

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def time_ns(self) -> int:
        return self._tick * self.spec.step_ns

    @property
    def time_s(self) -> float:
        """Elapsed seconds (derived from the exact integer time; for display/output only)."""
        return self.time_ns / NS_PER_S

    @property
    def at_end(self) -> bool:
        return self._tick >= self.spec.n_steps

    def advance(self) -> None:
        """Move to the next time point. Advancing past the final time point is an error."""
        if self.at_end:
            raise RuntimeError("clock is already at the final time point")
        self._tick += 1

    def ticks(self) -> Iterator[int]:
        """Yield every remaining tick from the current one to the end, advancing the clock."""
        while True:
            yield self._tick
            if self.at_end:
                return
            self.advance()

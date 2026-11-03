"""Frame-tagged Cartesian states and input validation.

Every state carries its frame and its time (scenario epoch + integer
nanoseconds), per ``docs/CONVENTIONS.md`` §3. Arrays are copied, checked for
shape and finiteness, and made read-only, so a state cannot be silently
modified or built from NaN/Inf.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import numpy as np
from numpy.typing import ArrayLike, NDArray

from astramesh.core.clock import require_utc

Vector3 = NDArray[np.float64]


class Frame(StrEnum):
    """Reference frames (``docs/CONVENTIONS.md`` §3)."""

    GCRS = "GCRS"  # inertial (ECI)
    ITRS = "ITRS"  # Earth-fixed (see astramesh.dynamics.earth_frames)
    RIC = "RIC"  # local orbital frame of a chief spacecraft; states are relative


class NonPhysicalStateError(ValueError):
    """Raised for NaN/Inf, malformed, or physically impossible states/parameters."""


class FrameError(ValueError):
    """Raised when states in incompatible frames or at different times are combined."""


def as_vector3(value: ArrayLike, *, name: str) -> Vector3:
    """Return a read-only float64 copy of a finite 3-vector, or raise."""
    arr = np.array(value, dtype=np.float64, copy=True)
    if arr.shape != (3,):
        raise NonPhysicalStateError(f"{name} must have shape (3,), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise NonPhysicalStateError(f"{name} must be finite, got {arr.tolist()}")
    arr.setflags(write=False)
    return arr


def norm3(v: NDArray[np.float64]) -> NDArray[np.float64]:
    """Euclidean norm over the last axis (length 3), with a fixed evaluation order.

    Written out explicitly instead of ``np.linalg.norm`` so the result does not
    depend on BLAS or pairwise-summation choices (bit-for-bit replay, PA-09).
    """
    return np.sqrt(v[..., 0] * v[..., 0] + v[..., 1] * v[..., 1] + v[..., 2] * v[..., 2])


def cross3(a: NDArray[np.float64], b: NDArray[np.float64]) -> NDArray[np.float64]:
    """Cross product over the last axis with a fixed evaluation order."""
    return np.stack(
        (
            a[..., 1] * b[..., 2] - a[..., 2] * b[..., 1],
            a[..., 2] * b[..., 0] - a[..., 0] * b[..., 2],
            a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0],
        ),
        axis=-1,
    )


def dot3(a: NDArray[np.float64], b: NDArray[np.float64]) -> NDArray[np.float64]:
    """Dot product over the last axis with a fixed evaluation order."""
    return a[..., 0] * b[..., 0] + a[..., 1] * b[..., 1] + a[..., 2] * b[..., 2]


@dataclass(frozen=True, slots=True, eq=False)
class CartesianState:
    """Position and velocity in a named frame at a scenario time.

    Attributes:
        frame: Frame the vectors are expressed in. For :attr:`Frame.RIC` the
            vectors are *relative* to a chief spacecraft.
        epoch_utc: Scenario epoch (UTC).
        t_ns: Elapsed SI nanoseconds since ``epoch_utc``.
        r_m: Position [m].
        v_mps: Velocity [m/s].
    """

    frame: Frame
    epoch_utc: datetime
    t_ns: int
    r_m: Vector3
    v_mps: Vector3

    def __init__(
        self,
        frame: Frame,
        epoch_utc: datetime,
        t_ns: int,
        r_m: ArrayLike,
        v_mps: ArrayLike,
    ) -> None:
        if not isinstance(frame, Frame):
            raise TypeError(f"frame must be a Frame, got {type(frame).__name__}")
        if isinstance(t_ns, bool) or not isinstance(t_ns, int):
            raise TypeError(f"t_ns must be an int, got {type(t_ns).__name__}")
        object.__setattr__(self, "frame", frame)
        object.__setattr__(self, "epoch_utc", require_utc(epoch_utc, name="epoch_utc"))
        object.__setattr__(self, "t_ns", t_ns)
        object.__setattr__(self, "r_m", as_vector3(r_m, name="r_m"))
        object.__setattr__(self, "v_mps", as_vector3(v_mps, name="v_mps"))

    def require_same_time(self, other: CartesianState) -> None:
        if self.epoch_utc != other.epoch_utc or self.t_ns != other.t_ns:
            raise FrameError(
                f"states are at different times: ({self.epoch_utc.isoformat()}, {self.t_ns} ns) "
                f"vs ({other.epoch_utc.isoformat()}, {other.t_ns} ns)"
            )

    def require_frame(self, frame: Frame) -> None:
        if self.frame is not frame:
            raise FrameError(f"expected a state in {frame}, got {self.frame}")

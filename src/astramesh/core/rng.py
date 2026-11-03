"""Named, independent random-number streams.

The specification (§10.3) requires separate seeds for task generation,
communication, sensor noise, fault injection, and algorithm stochasticity, so
that, for example, the fault schedule can be varied while the communication
noise is held fixed.

Each stream is a NumPy ``PCG64`` generator seeded from
``SeedSequence(entropy=<stream seed>, spawn_key=(<stable stream key>,))``. The
stream key is derived from the stream *name* with SHA-256, so it is stable
across processes and platforms (Python's built-in ``hash`` is not) and does not
depend on the order in which streams are created.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Final, Literal, get_args

import numpy as np

StreamName = Literal["tasks", "comms", "sensors", "faults", "algorithm"]
STREAM_NAMES: Final[tuple[StreamName, ...]] = get_args(StreamName)


def stream_key(name: str) -> int:
    """Stable 64-bit key for a stream name."""
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big")


def _check_seed(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an int, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{label} must be non-negative, got {value}")
    return value


class RandomStreams:
    """Container of the project's named random streams.

    Args:
        seed: Root seed used by every stream unless overridden.
        stream_seeds: Optional per-stream seed overrides, e.g. ``{"faults": 7}``.
    """

    __slots__ = ("_effective_seeds", "_generators")

    def __init__(
        self,
        seed: int,
        stream_seeds: Mapping[StreamName, int] | Mapping[str, int] | None = None,
    ) -> None:
        root = _check_seed(seed, "seed")
        overrides = dict(stream_seeds or {})
        unknown = sorted(set(overrides) - set(STREAM_NAMES))
        if unknown:
            raise ValueError(f"unknown random stream(s) {unknown}; valid: {list(STREAM_NAMES)}")
        self._effective_seeds: dict[str, int] = {
            name: _check_seed(overrides.get(name, root), f"stream_seeds[{name!r}]")
            for name in STREAM_NAMES
        }
        self._generators: dict[str, np.random.Generator] = {
            name: np.random.Generator(
                np.random.PCG64(np.random.SeedSequence(entropy=s, spawn_key=(stream_key(name),)))
            )
            for name, s in self._effective_seeds.items()
        }

    def __getitem__(self, name: StreamName) -> np.random.Generator:
        try:
            return self._generators[name]
        except KeyError:
            raise KeyError(f"unknown random stream {name!r}; valid: {list(STREAM_NAMES)}") from None

    @property
    def effective_seeds(self) -> dict[str, int]:
        """Seed actually used by each stream (for the provenance manifest)."""
        return dict(self._effective_seeds)

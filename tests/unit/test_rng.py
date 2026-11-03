from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from astramesh.core.rng import STREAM_NAMES, RandomStreams, stream_key


def _draws(streams: RandomStreams, name: str, n: int = 16) -> np.ndarray:
    return streams[name].random(n)  # type: ignore[index]


def test_stream_names_match_specification() -> None:
    assert set(STREAM_NAMES) == {"tasks", "comms", "sensors", "faults", "algorithm"}


@given(seed=st.integers(0, 2**63 - 1))
def test_same_seed_same_draws(seed: int) -> None:
    a, b = RandomStreams(seed), RandomStreams(seed)
    for name in STREAM_NAMES:
        np.testing.assert_array_equal(_draws(a, name), _draws(b, name))


def test_streams_are_distinct_under_one_seed() -> None:
    s = RandomStreams(1)
    draws = {name: tuple(_draws(s, name)) for name in STREAM_NAMES}
    assert len(set(draws.values())) == len(STREAM_NAMES)


def test_override_changes_only_that_stream() -> None:
    base = RandomStreams(1)
    varied = RandomStreams(1, {"faults": 7})
    for name in STREAM_NAMES:
        same = np.array_equal(_draws(base, name), _draws(varied, name))
        assert same is (name != "faults"), name
    assert varied.effective_seeds["faults"] == 7
    assert varied.effective_seeds["comms"] == 1


def test_stream_independent_of_consumption_of_other_streams() -> None:
    a, b = RandomStreams(3), RandomStreams(3)
    a["tasks"].random(1000)  # consuming one stream must not shift another
    np.testing.assert_array_equal(_draws(a, "comms"), _draws(b, "comms"))


def test_stream_key_is_stable() -> None:
    # Pinned values guard against accidental changes to stream derivation, which
    # would silently change every experiment's random draws.
    assert stream_key("comms") == 14711413765983604226
    assert stream_key("comms") != stream_key("faults")


def test_first_draw_is_pinned() -> None:
    # Depends on NumPy's PCG64 bit stream, which uv.lock pins. If a NumPy upgrade
    # changes this, treat it as a reproducibility-breaking change and record it.
    assert RandomStreams(1)["comms"].random() == 0.787074512841741


@pytest.mark.parametrize("bad", [-1, True, 1.0])
def test_rejects_bad_seed(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        RandomStreams(bad)  # type: ignore[arg-type]


def test_rejects_unknown_stream_override() -> None:
    with pytest.raises(ValueError, match="unknown random stream"):
        RandomStreams(1, {"weather": 2})


def test_unknown_stream_lookup() -> None:
    with pytest.raises(KeyError):
        RandomStreams(1)["weather"]  # type: ignore[index]

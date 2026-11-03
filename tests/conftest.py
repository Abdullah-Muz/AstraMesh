from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, settings

# "dev": random exploration, no deadline (Windows/OneDrive timing is noisy).
# "ci":  derandomized so CI failures are reproducible.
settings.register_profile("dev", deadline=None)
settings.register_profile(
    "ci", deadline=None, derandomize=True, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

REPO_ROOT = Path(__file__).resolve().parents[1]
TOY_CONFIG = REPO_ROOT / "configs" / "experiments" / "toy_heartbeat.yaml"


@pytest.fixture
def toy_config_path() -> Path:
    return TOY_CONFIG


@pytest.fixture
def toy_config_dict() -> dict[str, Any]:
    data = yaml.safe_load(TOY_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data

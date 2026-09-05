"""Shared fixtures.

The test suite is the composition root for Stage 0.1. Nothing in the kernel
imports an adapter, so something outside it has to assemble the two, and
until Stage 0.3 builds the real control plane that job belongs here. If the
kernel could not be assembled from outside, the seam would not be real.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from kultrun.adapters.persistence import file_store
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.persistence import Store
from kultrun.kernel.registry import AdapterRegistry

FIXED_INSTANT = dt.datetime(2026, 9, 5, 6, 30, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED_INSTANT)


@pytest.fixture
def store_root(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def stores() -> AdapterRegistry[Store]:
    """A registry with the file store registered, as the composition root would."""
    registry: AdapterRegistry[Store] = AdapterRegistry("kernel.persistence.Store")
    registry.register("file", file_store.build)
    return registry


@pytest.fixture
def store(
    stores: AdapterRegistry[Store], store_root: Path
) -> file_store.FileStore:
    built = stores.create("file", store_root)
    assert isinstance(built, file_store.FileStore)
    return built

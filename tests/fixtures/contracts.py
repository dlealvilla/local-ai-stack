"""Contracts used only by tests.

Defined once, in one module, because contract registration is global: two
test modules each declaring the same kind would collide. They live outside
the ``kultrun.`` module prefix, so they never enter the committed schema
fingerprint.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, JsonValue, contract, meaning
from kultrun.kernel.unresolved import Maybe


class ProbeId(EntityId):
    prefix = "probe"


class Outcome(StrEnum):
    SUCCESS = "success"
    CLASSIFIED_FAILURE = "classified_failure"
    INCONCLUSIVE = "inconclusive"


@contract(kind="test.leaf", version=1)
@dataclass(frozen=True, slots=True)
class Leaf(Contract):
    label: str = meaning("a human-readable label")


@contract(kind="test.probe", version=1)
@dataclass(frozen=True, slots=True)
class Probe(Contract):
    """Exercises every field shape the codec claims to support."""

    probe_id: ProbeId = meaning("minted identity of this probe")
    logical_name: Name = meaning("client-facing name, distinct from the identity")
    outcome: Outcome = meaning("how the probe ended")
    started_at: dt.datetime = meaning("when it began, UTC")
    requested_bytes: int = meaning("size requested, in bytes")
    ratio: float = meaning("fraction of the pool consumed")
    verified: bool = meaning("whether the result was confirmed")
    leaf: Leaf = meaning("a nested contract")
    tags: list[str] = meaning("free-form operator tags")
    attempts: tuple[int, ...] = meaning("byte sizes attempted, in order")
    annotations: dict[str, JsonValue] = meaning("opaque operator annotations")
    detail: JsonValue = meaning("provider-specific body, shape not owned here")
    observed_bytes: Maybe[int] = meaning("measured size, or why it is not known")
    note: str | None = meaning("optional free text", default=None)
    ceiling_bytes: Maybe[int] | None = meaning(
        "upper bound: a value, not applicable, or not known", default=None
    )


@contract(kind="test.settings", version=1)
@dataclass(frozen=True, slots=True)
class Settings(Contract):
    """A configuration section."""

    root: str = meaning("filesystem path the store owns", default="/var/lib/kultrun")
    retention_days: int = meaning("how long records are kept", default=7)


@contract(kind="test.required_settings", version=1)
@dataclass(frozen=True, slots=True)
class RequiredSettings(Contract):
    """A configuration section with no defaults."""

    endpoint: str = meaning("where to reach the service")

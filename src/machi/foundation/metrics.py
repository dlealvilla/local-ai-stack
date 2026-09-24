"""Normalized foundation metrics. Not a warehouse and not a model log."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning

_TOKEN_MAX = 80
_REASON_MAX = 240
_MAX_METRICS = 16


class MetricAvailability(StrEnum):
    """Whether a normalized figure was actually observed."""

    OBSERVED = "observed"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    HIDDEN_INTERNAL = "hidden_internal"
    NOT_EXPOSED = "not_exposed"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    UNRESOLVED = "unresolved"


@contract(kind="foundation.metric", version=1)
@dataclass(frozen=True, slots=True)
class FoundationMetric(Contract):
    """One normalized figure. Later blocks can reuse this shape."""

    name: str = meaning("stable metric name")
    value: str = meaning("figure as text; unresolved when unknown")
    availability: MetricAvailability = meaning("how this figure was obtained")
    unit: str = meaning("text, seconds, bytes, or count")
    source: str = meaning("provider fact this figure came from")
    privacy: str = meaning("operational; request text is not stored here")

    def __post_init__(self) -> None:
        _bounded(self.name, what="metric", maximum=_TOKEN_MAX)
        _bounded(self.value, what="metric value", maximum=_REASON_MAX)
        _bounded(self.unit, what="unit", maximum=16)
        _bounded(self.source, what="source", maximum=_TOKEN_MAX)
        if self.unit not in {"text", "seconds", "bytes", "count"}:
            raise ValidationError("metric unit is not supported")
        if self.privacy != "operational":
            raise ValidationError("foundation metrics are operational only")


@contract(kind="foundation.metric_set", version=1)
@dataclass(frozen=True, slots=True)
class FoundationMetricSet(Contract):
    """Ordered foundation metrics. Raw provider text stays separate."""

    metrics: tuple[FoundationMetric, ...] = meaning("ordered foundation metrics")

    def __post_init__(self) -> None:
        if not self.metrics or len(self.metrics) > _MAX_METRICS:
            raise ValidationError("foundation metric set size is not supported")


def _bounded(value: str, *, what: str, maximum: int) -> None:
    if not value or len(value) > maximum:
        raise ValidationError(
            f"{what} must be a non-empty bounded string",
            maximum=maximum,
        )

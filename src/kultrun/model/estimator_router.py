"""Route one estimate through an ordered provider chain.

Planning never sees this module. Composition builds the chain; this
classifies typed estimator failure and, in auto mode only, asks the
fallback. A valid over-capacity or underutilized estimate is success.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field, replace

from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import (
    EstimatorFailureReason,
    MemoryPlacement,
    ModelEstimationRequest,
    ModelRequirement,
)
from kultrun.model.ports import ModelRequirementEstimator

_LOG = logging.getLogger("kultrun.model.estimator")

_FAILED_METHODS = frozenset({"unsupported", "provider-unavailable"})
_METHOD_TO_FAILURE = {
    "provider-unavailable": EstimatorFailureReason.PROVIDER_UNAVAILABLE,
    "unsupported": EstimatorFailureReason.UNSUPPORTED_CONFIGURATION,
}


@dataclass
class EstimatorDiagnostics:
    """In-process counters. Not an analytics platform."""

    attempts: int = 0
    successes: int = 0
    fallbacks: int = 0
    failures_by_reason: Counter[str] = field(default_factory=Counter)
    last_latency_ms: float | None = None
    last_effective: str | None = None


class EstimatorRouter:
    """Ordered ModelRequirementEstimator attempts. One effective result."""

    def __init__(
        self,
        *,
        mode: str,
        providers: tuple[ModelRequirementEstimator, ...],
        allow_fallback: bool,
    ) -> None:
        if not providers:
            raise ValueError("an estimator router needs at least one provider")
        self._mode = mode
        self._providers = providers
        self._allow_fallback = allow_fallback and len(providers) > 1
        self.diagnostics = EstimatorDiagnostics()

    @property
    def identity(self) -> Name:
        return Name(self._mode)

    @property
    def version(self) -> str:
        return self._providers[0].version

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def allow_fallback(self) -> bool:
        return self._allow_fallback

    @property
    def requested_primary(self) -> str:
        return self._providers[0].identity.value

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        primary = self._providers[0]
        started = time.perf_counter()
        self.diagnostics.attempts += 1
        first = primary.estimate(request)
        usable, failure = classify(first, request)
        if usable:
            self.diagnostics.successes += 1
            self.diagnostics.last_effective = primary.identity.value
            self.diagnostics.last_latency_ms = (time.perf_counter() - started) * 1000
            return annotate(
                first,
                mode=self._mode,
                requested_primary=primary.identity.value,
                fallback_used=False,
                fallback_reason=None,
            )
        self.diagnostics.failures_by_reason[
            (failure or EstimatorFailureReason.UNRESOLVED_ESTIMATE).value
        ] += 1
        if not self._allow_fallback:
            self.diagnostics.last_effective = primary.identity.value
            self.diagnostics.last_latency_ms = (time.perf_counter() - started) * 1000
            return annotate(
                first,
                mode=self._mode,
                requested_primary=primary.identity.value,
                fallback_used=False,
                fallback_reason=None,
            )
        fallback = self._providers[1]
        reason = failure or EstimatorFailureReason.UNRESOLVED_ESTIMATE
        _LOG.info(
            "estimator primary failed; trying fallback",
            extra={
                "estimator_mode": self._mode,
                "requested_primary": primary.identity.value,
                "fallback_provider": fallback.identity.value,
                "fallback_reason": reason.value,
            },
        )
        second = fallback.estimate(request)
        self.diagnostics.fallbacks += 1
        usable_fallback, _ = classify(second, request)
        if usable_fallback:
            self.diagnostics.successes += 1
        self.diagnostics.last_effective = fallback.identity.value
        self.diagnostics.last_latency_ms = (time.perf_counter() - started) * 1000
        return annotate(
            second,
            mode=self._mode,
            requested_primary=primary.identity.value,
            fallback_used=True,
            fallback_reason=reason,
        )


def classify(
    requirement: ModelRequirement, request: ModelEstimationRequest
) -> tuple[bool, EstimatorFailureReason | None]:
    """Usable evidence for this request, or a typed failure.

    Planning's utilization class is not consulted. Unknown is never zero.
    """
    if is_resolved(requirement.estimator_failure):
        try:
            reason = EstimatorFailureReason(requirement.estimator_failure)
        except ValueError:
            reason = EstimatorFailureReason.UNRESOLVED_ESTIMATE
        return False, reason
    method = requirement.estimation_method
    if is_resolved(method) and method in _FAILED_METHODS:
        return False, _METHOD_TO_FAILURE[method]
    if not _load_bearing_resolved(requirement, request.placement):
        return False, EstimatorFailureReason.MISSING_LOAD_BEARING_REQUIREMENT
    return True, None


def annotate(
    requirement: ModelRequirement,
    *,
    mode: str,
    requested_primary: str,
    fallback_used: bool,
    fallback_reason: EstimatorFailureReason | None,
) -> ModelRequirement:
    """Attach router provenance. Does not change memory figures."""
    return replace(
        requirement,
        estimator_mode=mode,
        requested_primary=requested_primary,
        fallback_used=fallback_used,
        fallback_reason=(
            fallback_reason.value if fallback_reason is not None else NOT_PROVIDED
        ),
    )


def _load_bearing_resolved(
    requirement: ModelRequirement, placement: MemoryPlacement
) -> bool:
    if placement is MemoryPlacement.CPU_ONLY:
        return is_resolved(requirement.ram_bytes)
    if placement is MemoryPlacement.UNIFIED_MEMORY:
        return is_resolved(requirement.unified_memory_bytes)
    return is_resolved(requirement.estimated_vram_bytes)

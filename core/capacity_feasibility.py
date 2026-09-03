"""Does a candidate model fit the characterized safe host capacity?

AI_DEPLOYMENT_CAPACITY_FEASIBILITY

    CapacityEnvelope + ModelRequirement -> FeasibilityResult

One question only. This module does not rank, select, iterate a
catalogue, characterize the host, probe storage or estimate anything:
every figure it reports is copied from the envelope (C1/C2), the
requirement (C4) or a storage characterization result. It is pure
comparison, which is what keeps the later selection objective free to
change without touching it.

Not to be confused with `core.model_feasibility`, the Phase-8 evaluator
that works from hardware and resource safety directly and still serves
the existing `/capacity/models/feasibility` route.

Three verdicts, never a boolean, because "we cannot determine this" is
a common and honest answer. RAM has no estimator anywhere in the
source, so a candidate passing everything else is conditionally
compatible rather than compatible. Unknown is never zero and never a
pass.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.capacity_contracts import CapacityEnvelope
from core.model_requirement import ModelRequirement


CAPACITY_FEASIBILITY_SCHEMA_VERSION = 1


VERDICT_COMPATIBLE = "compatible"
VERDICT_CONDITIONALLY_COMPATIBLE = (
    "conditionally_compatible"
)
VERDICT_UNSUPPORTED = "unsupported"


CHECK_PASS = "pass"
CHECK_FAIL = "fail"
CHECK_UNRESOLVED = "unresolved"


#
# Evaluated and reported in this fixed order, which is what makes
# `limiting_factor` deterministic.
#
RESOURCE_RUNTIME = "runtime"
RESOURCE_PRIMARY_INFERENCE_MEMORY = (
    "primary_inference_memory"
)
RESOURCE_RAM = "ram"
RESOURCE_STORAGE = "storage"

RESOURCE_ORDER = (
    RESOURCE_RUNTIME,
    RESOURCE_PRIMARY_INFERENCE_MEMORY,
    RESOURCE_RAM,
    RESOURCE_STORAGE,
)


@dataclass(frozen=True)
class ResourceCheck:
    """One hard constraint, evaluated.

    `available_bytes` is always a safe or proven figure. Headroom and
    utilization appear only when both sides are known, so a missing
    figure cannot masquerade as a comfortable fit.
    """

    resource: str
    pool_id: str | None
    status: str
    required_bytes: int | None
    available_bytes: int | None
    remaining_bytes: int | None
    utilization: float | None
    confidence: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeasibilityResult:
    schema_version: int
    model_id: str | None
    runtime: str | None
    quantization: str | None
    verdict: str
    checks: tuple[ResourceCheck, ...]
    limiting_factor: str | None
    unresolved_resources: tuple[str, ...]
    reasons: tuple[str, ...]

    def check(
        self,
        resource: str,
    ) -> ResourceCheck | None:
        for entry in self.checks:
            if entry.resource == resource:
                return entry

        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "runtime": self.runtime,
            "quantization": self.quantization,
            "verdict": self.verdict,
            "checks": [
                entry.to_dict()
                for entry in self.checks
            ],
            "limiting_factor": self.limiting_factor,
            "unresolved_resources": list(
                self.unresolved_resources
            ),
            "reasons": list(self.reasons),
        }


def _headroom(required_bytes, available_bytes):
    remaining = available_bytes - required_bytes

    utilization = None

    if available_bytes > 0:
        utilization = (
            required_bytes / available_bytes
        )

    return remaining, utilization


def _memory_pool(
    envelope: CapacityEnvelope,
    memory_type: str,
):
    """The most capacious pool of a type, or None.

    Conservative, matching the existing compatibility logic: one pool
    must satisfy the requirement alone. Pooled accelerator memory and
    tensor parallelism are not assumed, so capacity is not summed
    across devices.
    """

    candidates = [
        pool
        for pool in envelope.memory_pools
        if pool.memory_type == memory_type
    ]

    if not candidates:
        return None

    def ranking(pool):
        figure = (
            pool.safe_available_for_additional_workload_bytes
        )

        if figure is None:
            figure = (
                pool.observed_safe_available_bytes or 0
            )

        return figure

    return max(candidates, key=ranking)


def _memory_check(
    *,
    resource: str,
    requirement_memory,
    envelope: CapacityEnvelope,
) -> ResourceCheck:
    pool = _memory_pool(
        envelope,
        requirement_memory.memory_type,
    )

    required = requirement_memory.required_bytes
    confidence = requirement_memory.confidence

    if pool is None:
        #
        # A required pool that does not exist on this host is a
        # definite failure, not an unknown.
        #
        return ResourceCheck(
            resource=resource,
            pool_id=None,
            status=CHECK_FAIL,
            required_bytes=required,
            available_bytes=None,
            remaining_bytes=None,
            utilization=None,
            confidence=confidence,
            reason=(
                "no "
                + requirement_memory.memory_type
                + " pool exists on this host"
            ),
        )

    available = (
        pool.safe_available_for_additional_workload_bytes
    )

    if required is None:
        return ResourceCheck(
            resource=resource,
            pool_id=pool.pool_id,
            status=CHECK_UNRESOLVED,
            required_bytes=None,
            available_bytes=available,
            remaining_bytes=None,
            utilization=None,
            confidence=confidence,
            reason=(
                "required bytes are unresolved ("
                + str(requirement_memory.basis)
                + ")"
            ),
        )

    if available is None:
        #
        # The envelope reports reservation state as unknown rather
        # than zero when no ledger snapshot was supplied. Treating the
        # observed figure as available would silently assume nothing
        # else is reserved.
        #
        return ResourceCheck(
            resource=resource,
            pool_id=pool.pool_id,
            status=CHECK_UNRESOLVED,
            required_bytes=required,
            available_bytes=None,
            remaining_bytes=None,
            utilization=None,
            confidence=confidence,
            reason=(
                "safe available bytes for an additional "
                "workload are unknown because managed "
                "reservation state was not supplied"
            ),
        )

    remaining, utilization = _headroom(
        required,
        available,
    )

    if required > available:
        return ResourceCheck(
            resource=resource,
            pool_id=pool.pool_id,
            status=CHECK_FAIL,
            required_bytes=required,
            available_bytes=available,
            remaining_bytes=remaining,
            utilization=utilization,
            confidence=confidence,
            reason=(
                "required bytes exceed safe available bytes"
            ),
        )

    return ResourceCheck(
        resource=resource,
        pool_id=pool.pool_id,
        status=CHECK_PASS,
        required_bytes=required,
        available_bytes=available,
        remaining_bytes=remaining,
        utilization=utilization,
        confidence=confidence,
        reason="fits within safe available bytes",
    )


def _storage_check(
    *,
    requirement: ModelRequirement,
    storage_characterization: Mapping[str, Any] | None,
) -> ResourceCheck:
    """Compare acquisition storage against characterized evidence.

    Bound semantics matter here. `L` is the largest proven successful
    probe and `U` the smallest classified capacity failure:

        required <= L                 pass, proven to fit
        required > L, U unknown       UNRESOLVED, not a failure
        required >= U                 fail, proven not to fit

    Exceeding the proven lower bound is an absence of evidence, not
    evidence of absence. Raw filesystem free space is never consulted.
    """

    storage = requirement.storage

    #
    # C4's installed/absent semantics decide this. Running an
    # already-installed model does not require its acquisition peak a
    # second time.
    #
    if storage.installed_bytes is not None:
        return ResourceCheck(
            resource=RESOURCE_STORAGE,
            pool_id=storage.target_pool_id,
            status=CHECK_PASS,
            required_bytes=None,
            available_bytes=None,
            remaining_bytes=None,
            utilization=None,
            confidence=storage.confidence,
            reason=(
                "model artifact is already installed; no "
                "acquisition storage is required"
            ),
        )

    required = storage.acquisition_peak_bytes

    if required is None:
        return ResourceCheck(
            resource=RESOURCE_STORAGE,
            pool_id=storage.target_pool_id,
            status=CHECK_UNRESOLVED,
            required_bytes=None,
            available_bytes=None,
            remaining_bytes=None,
            utilization=None,
            confidence=storage.confidence,
            reason=(
                "acquisition peak storage is unresolved ("
                + str(storage.basis)
                + ")"
            ),
        )

    if storage_characterization is None:
        return ResourceCheck(
            resource=RESOURCE_STORAGE,
            pool_id=storage.target_pool_id,
            status=CHECK_UNRESOLVED,
            required_bytes=required,
            available_bytes=None,
            remaining_bytes=None,
            utilization=None,
            confidence=storage.confidence,
            reason=(
                "no storage characterization was supplied"
            ),
        )

    lower_bound = (
        storage_characterization.get(
            "verified_lower_bound_bytes"
        )
    )

    upper_bound = (
        storage_characterization.get(
            "capacity_failure_upper_bound_bytes"
        )
    )

    if (
        lower_bound is not None
        and required <= lower_bound
    ):
        remaining, utilization = _headroom(
            required,
            lower_bound,
        )

        return ResourceCheck(
            resource=RESOURCE_STORAGE,
            pool_id=storage.target_pool_id,
            status=CHECK_PASS,
            required_bytes=required,
            available_bytes=lower_bound,
            remaining_bytes=remaining,
            utilization=utilization,
            confidence=storage.confidence,
            reason=(
                "within the proven storage lower bound"
            ),
        )

    if (
        upper_bound is not None
        and required >= upper_bound
    ):
        return ResourceCheck(
            resource=RESOURCE_STORAGE,
            pool_id=storage.target_pool_id,
            status=CHECK_FAIL,
            required_bytes=required,
            available_bytes=lower_bound,
            remaining_bytes=None,
            utilization=None,
            confidence=storage.confidence,
            reason=(
                "at or above a proven storage capacity "
                "failure"
            ),
        )

    return ResourceCheck(
        resource=RESOURCE_STORAGE,
        pool_id=storage.target_pool_id,
        status=CHECK_UNRESOLVED,
        required_bytes=required,
        available_bytes=lower_bound,
        remaining_bytes=None,
        utilization=None,
        confidence=storage.confidence,
        reason=(
            "exceeds the proven storage lower bound and no "
            "capacity failure proves it cannot fit"
        ),
    )


def _runtime_check(
    requirement: ModelRequirement,
) -> tuple[ResourceCheck, list[str]]:
    compatibility = requirement.runtime_compatibility

    reasons: list[str] = []

    if compatibility.status is None:
        return (
            ResourceCheck(
                resource=RESOURCE_RUNTIME,
                pool_id=None,
                status=CHECK_UNRESOLVED,
                required_bytes=None,
                available_bytes=None,
                remaining_bytes=None,
                utilization=None,
                confidence=compatibility.confidence,
                reason=(
                    "runtime compatibility has not been "
                    "evaluated"
                ),
            ),
            reasons,
        )

    if compatibility.status in {
        "unsupported",
        "not_supported",
    }:
        return (
            ResourceCheck(
                resource=RESOURCE_RUNTIME,
                pool_id=None,
                status=CHECK_FAIL,
                required_bytes=None,
                available_bytes=None,
                remaining_bytes=None,
                utilization=None,
                confidence=compatibility.confidence,
                reason=(
                    "no validated runtime for this model "
                    "on this host"
                ),
            ),
            reasons,
        )

    #
    # A "conditionally_compatible" static verdict passes here: this
    # layer consumes the normalized result and must not re-judge
    # compatibility. The qualification is surfaced as a reason.
    #
    if compatibility.status != "compatible":
        reasons.append(
            "static runtime compatibility is "
            + str(compatibility.status)
        )

    return (
        ResourceCheck(
            resource=RESOURCE_RUNTIME,
            pool_id=None,
            status=CHECK_PASS,
            required_bytes=None,
            available_bytes=None,
            remaining_bytes=None,
            utilization=None,
            confidence=compatibility.confidence,
            reason=(
                "runtime compatibility is "
                + str(compatibility.status)
            ),
        ),
        reasons,
    )


def evaluate_capacity_feasibility(
    *,
    requirement: ModelRequirement,
    envelope: CapacityEnvelope,
    storage_characterization=None,
) -> FeasibilityResult:
    """Compare one requirement against one envelope and one storage bound.

        unsupported                any hard constraint definitely
                                   fails; one definite failure
                                   dominates every unresolved
                                   dimension.

        conditionally_compatible   nothing definitely fails, but at
                                   least one hard constraint is
                                   unresolved.

        compatible                 every applicable hard constraint is
                                   resolved and passes.

    A known figure of low confidence is used and its confidence
    reported unchanged. Low confidence does not by itself force a
    conditional verdict: a known value is usable, and only a
    missing value is uncertainty.
    """

    if not isinstance(requirement, ModelRequirement):
        raise TypeError(
            "requirement must be a ModelRequirement"
        )

    if not isinstance(envelope, CapacityEnvelope):
        raise TypeError(
            "envelope must be a CapacityEnvelope"
        )

    if storage_characterization is not None and not isinstance(
        storage_characterization,
        Mapping,
    ):
        raise TypeError(
            "storage_characterization must be a mapping"
        )

    runtime_check, reasons = _runtime_check(
        requirement
    )

    by_resource = {
        RESOURCE_RUNTIME: runtime_check,

        RESOURCE_PRIMARY_INFERENCE_MEMORY: (
            _memory_check(
                resource=(
                    RESOURCE_PRIMARY_INFERENCE_MEMORY
                ),
                requirement_memory=(
                    requirement.primary_inference_memory
                ),
                envelope=envelope,
            )
        ),

        RESOURCE_RAM: _memory_check(
            resource=RESOURCE_RAM,
            requirement_memory=requirement.ram,
            envelope=envelope,
        ),

        RESOURCE_STORAGE: _storage_check(
            requirement=requirement,
            storage_characterization=(
                storage_characterization
            ),
        ),
    }

    ordered = tuple(
        by_resource[resource]
        for resource in RESOURCE_ORDER
    )

    failures = [
        entry
        for entry in ordered
        if entry.status == CHECK_FAIL
    ]

    unresolved = tuple(
        entry.resource
        for entry in ordered
        if entry.status == CHECK_UNRESOLVED
    )

    if failures:
        verdict = VERDICT_UNSUPPORTED
        limiting_factor = failures[0].resource

    elif unresolved:
        verdict = VERDICT_CONDITIONALLY_COMPATIBLE
        limiting_factor = None

    else:
        verdict = VERDICT_COMPATIBLE
        limiting_factor = None

    for status in (CHECK_FAIL, CHECK_UNRESOLVED):
        for entry in ordered:
            if entry.status == status:
                reasons.append(
                    entry.resource
                    + ": "
                    + entry.reason
                )

    return FeasibilityResult(
        schema_version=(
            CAPACITY_FEASIBILITY_SCHEMA_VERSION
        ),
        model_id=requirement.model_id,
        runtime=requirement.runtime,
        quantization=requirement.quantization,
        verdict=verdict,
        checks=ordered,
        limiting_factor=limiting_factor,
        unresolved_resources=unresolved,
        reasons=tuple(reasons),
    )

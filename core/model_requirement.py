"""One coherent ModelRequirement contract.

AI_DEPLOYMENT_MODEL_REQUIREMENT_C4

See docs/CAPACITY_ARCHITECTURE.md section 30.

The platform already estimates what a model needs, but the answers are
scattered across several layers with different shapes, different
confidence vocabularies and different notions of "size". This module
states them once, coherently, so the next step can do:

    CapacityEnvelope + ModelRequirement -> FeasibilityResult

Existing owners, reused and never reimplemented:

    core.model_storage_requirements   acquisition/install storage
    core.model_inventory             installed artifact bytes
    core.requirements                model resource envelope and
                                     exact local weight measurement
    core.model_feasibility           the provisional runtime memory
                                     estimate
    core.model_compatibility         runtime and architecture
                                     compatibility

Not to be confused with its neighbours: `core.model_storage_requirements`
estimates storage for one operation, `core.requirements` owns the
resource envelope and the legacy planner estimator. This module
normalizes their outputs and computes nothing itself.

Two honest gaps are represented rather than papered over:

- RAM has no estimator anywhere in the source. `build_model_resource_
  requirements` leaves `system_ram_bytes` as None, and
  `STATIC_RAM_WEIGHT_BUDGET` is a compatibility gate on weight size,
  not a requirement figure. So RAM is reported unresolved.
- The only model-derived inference-memory figure is the explicitly
  provisional `weights + max(1 GiB, 25%)` estimate, carried through
  with its own low confidence intact rather than being dressed up.

Normalization receives already-established evidence. Nothing here reads
the filesystem, NVML or configuration, so the contract stays pure and
testable. No caller consumes it yet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.capacity_contracts import (
    PLATFORM_DATA_STORAGE_POOL_ID,
)


MODEL_REQUIREMENT_SCHEMA_VERSION = 1


#
# Memory-type vocabulary is shared with core.resource_capacity and the
# C1 capacity contracts, so a requirement can be matched against an
# envelope pool without translation.
#
SYSTEM_RAM = "system_ram"
DEDICATED_VRAM = "dedicated_vram"


#
# Why a figure is missing. These are decision-relevant: C5 must be able
# to distinguish "needs nothing" from "we do not know".
#
BASIS_UNRESOLVED_NO_ESTIMATOR = (
    "no_estimator_in_source"
)
BASIS_UNRESOLVED_MISSING_INPUT = (
    "estimator_output_not_supplied"
)
BASIS_NOT_IMPLEMENTED = "not_implemented"


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        return None

    value = int(value)

    if value < 0:
        return None

    return value


@dataclass(frozen=True)
class StorageRequirement:
    """What the model needs from one storage pool.

    `installed_bytes` is what an already-stored artifact occupies.
    `acquisition_peak_bytes` is the transient peak while installing,
    which is the figure storage admission cares about and is larger
    than the artifact itself. They are not interchangeable.
    """

    target_pool_id: str
    installed_bytes: int | None
    acquisition_peak_bytes: int | None
    artifact_bytes: int | None
    overhead_bytes: int | None
    confidence: str | None
    basis: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryRequirement:
    """What the model needs from one memory pool.

    `memory_type` matches the capacity-envelope vocabulary so a
    requirement can be compared against the corresponding pool
    directly.
    """

    memory_type: str
    required_bytes: int | None
    confidence: str | None
    basis: str | None

    @property
    def resolved(self) -> bool:
        return self.required_bytes is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeCompatibility:
    """Whether this host can run the model at all, and with what."""

    status: str | None
    confidence: str | None
    candidate_runtimes: tuple[str, ...]
    weight_formats: tuple[str, ...]
    architecture: str | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RequirementAssumptions:
    """The serving assumptions the figures above depend on.

    A memory requirement is meaningless without them: the same model
    needs very different memory at 4k context and one request than at
    128k context and thirty. Each is reported only where the source
    actually provides it.
    """

    context_length: int | None
    concurrency: int | None
    offload: str | None
    basis: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelRequirement:
    schema_version: int
    model_id: str | None
    revision: str | None
    runtime: str | None
    quantization: str | None
    storage: StorageRequirement
    ram: MemoryRequirement
    primary_inference_memory: MemoryRequirement
    runtime_compatibility: RuntimeCompatibility
    assumptions: RequirementAssumptions
    unresolved_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "revision": self.revision,
            "runtime": self.runtime,
            "quantization": self.quantization,
            "storage": self.storage.to_dict(),
            "ram": self.ram.to_dict(),
            "primary_inference_memory": (
                self.primary_inference_memory.to_dict()
            ),
            "runtime_compatibility": (
                self.runtime_compatibility.to_dict()
            ),
            "assumptions": self.assumptions.to_dict(),
            "unresolved_fields": list(
                self.unresolved_fields
            ),
        }

    def memory_requirement(
        self,
        memory_type: str,
    ) -> MemoryRequirement | None:
        for requirement in (
            self.ram,
            self.primary_inference_memory,
        ):
            if requirement.memory_type == memory_type:
                return requirement

        return None


def _require_mapping(
    value: Any,
    *,
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")

    return value


#
# The platform has two model record shapes, and a requirement must be
# derivable from either: candidates are evaluated before acquisition,
# installed models after it.
#
#   candidate  core.model_metadata.normalize_local_model /
#              normalize_huggingface_model, as consumed by the
#              catalogue, compatibility and storage estimators. Flat:
#              quantization, context_length, architecture, size,
#              format, runtime, requirements at the top level.
#
#   inventory  core.model_inventory.list_model_inventory.
#              Nested: artifact, deployment, metadata, source.
#
SHAPE_CANDIDATE = "candidate"
SHAPE_INVENTORY = "inventory"


def _detect_shape(
    model: Mapping[str, Any],
) -> str:
    if "artifact" in model or "metadata" in model:
        return SHAPE_INVENTORY

    return SHAPE_CANDIDATE


def _model_identity(
    model: Mapping[str, Any],
    shape: str,
):
    model_id = (
        model.get("model_id")
        or model.get("name")
        or model.get("catalog_id")
        or model.get("id")
    )

    source = model.get("source") or {}

    revision = source.get("revision")

    if shape == SHAPE_INVENTORY:
        metadata = model.get("metadata") or {}

    else:
        #
        # Present the flat candidate fields through the same keys so
        # everything downstream reads one shape.
        #
        metadata = {
            "architecture": model.get(
                "architecture"
            ),
            "quantization": model.get(
                "quantization"
            ),
            "context_length": model.get(
                "context_length"
            ),
            "family": model.get("family"),
        }

    deployment = model.get("deployment") or {}

    runtime = deployment.get("runtime")

    if runtime is None and isinstance(
        model.get("runtime"),
        str,
    ):
        runtime = model.get("runtime")

    return (
        model_id,
        revision,
        runtime,
        metadata,
    )


def _installed_bytes(
    model: Mapping[str, Any],
    shape: str,
) -> int | None:
    if shape == SHAPE_INVENTORY:
        artifact = model.get("artifact") or {}

        return _int_or_none(
            artifact.get("disk_usage_bytes")
        )

    size = model.get("size") or {}

    return _int_or_none(
        size.get("installed_bytes")
    )


def _weight_formats(
    model: Mapping[str, Any],
    shape: str,
) -> tuple[str, ...]:
    if shape == SHAPE_INVENTORY:
        artifact = model.get("artifact") or {}

        return tuple(
            str(value)
            for value in (
                artifact.get("weight_formats") or []
            )
        )

    weights = (
        model.get("format") or {}
    ).get("weights")

    return (str(weights),) if weights else ()


def _build_storage_requirement(
    *,
    model: Mapping[str, Any],
    shape: str,
    install_storage: Mapping[str, Any] | None,
    target_pool_id: str,
) -> StorageRequirement:
    installed_bytes = _installed_bytes(
        model,
        shape,
    )

    if install_storage is None:
        return StorageRequirement(
            target_pool_id=target_pool_id,
            installed_bytes=installed_bytes,
            acquisition_peak_bytes=None,
            artifact_bytes=None,
            overhead_bytes=None,
            confidence=None,
            basis=BASIS_UNRESOLVED_MISSING_INPUT,
        )

    install_storage = _require_mapping(
        install_storage,
        name="install_storage",
    )

    estimated_artifact = (
        install_storage.get("artifact") or {}
    )

    return StorageRequirement(
        target_pool_id=target_pool_id,
        installed_bytes=installed_bytes,
        acquisition_peak_bytes=_int_or_none(
            install_storage.get(
                "peak_additional_bytes"
            )
        ),
        artifact_bytes=_int_or_none(
            estimated_artifact.get("bytes")
        ),
        overhead_bytes=_int_or_none(
            install_storage.get("overhead_bytes")
        ),
        confidence=install_storage.get(
            "confidence"
        ),
        basis=(
            "model_storage_requirements."
            + str(
                install_storage.get(
                    "operation",
                    "install",
                )
            )
        ),
    )


def _build_primary_inference_memory(
    *,
    model: Mapping[str, Any],
    feasibility: Mapping[str, Any] | None,
    memory_type: str,
) -> MemoryRequirement:
    if feasibility is None:
        #
        # Fall back to a figure declared on the record itself, which
        # is where a future runtime-specific estimator would publish
        # one. Nothing populates it today.
        #
        declared = _int_or_none(
            (model.get("requirements") or {}).get(
                "vram_bytes"
            )
        )

        return MemoryRequirement(
            memory_type=memory_type,
            required_bytes=declared,
            confidence=(
                "declared"
                if declared is not None
                else None
            ),
            basis=(
                "model_record.requirements.vram_bytes"
                if declared is not None
                else BASIS_UNRESOLVED_MISSING_INPUT
            ),
        )

    estimate = (
        (
            (
                feasibility.get("dimensions")
                or {}
            ).get("memory")
            or {}
        ).get("provisional_estimate")
        or {}
    )

    #
    # Carried through with the estimator's own confidence. It is
    # deliberately "low": the figure is weights plus a flat margin,
    # not a runtime prediction.
    #
    return MemoryRequirement(
        memory_type=memory_type,
        required_bytes=_int_or_none(
            estimate.get(
                "estimated_runtime_target_bytes"
            )
        ),
        confidence=estimate.get("confidence"),
        basis=(
            "model_feasibility.provisional_estimate"
            if estimate
            else BASIS_UNRESOLVED_MISSING_INPUT
        ),
    )


def _build_runtime_compatibility(
    *,
    model: Mapping[str, Any],
    shape: str,
    compatibility: Mapping[str, Any] | None,
    metadata: Mapping[str, Any],
) -> RuntimeCompatibility:
    weight_formats = _weight_formats(
        model,
        shape,
    )

    architecture = metadata.get("architecture")

    if compatibility is None:
        return RuntimeCompatibility(
            status=None,
            confidence=None,
            candidate_runtimes=(),
            weight_formats=weight_formats,
            architecture=architecture,
            reasons=(),
        )

    #
    # evaluate_model_compatibility returns the ENRICHED MODEL, with
    # its verdict under "compatibility" and the supported runtimes
    # under "runtime". Reading it any other way silently loses both.
    #
    compatibility = _require_mapping(
        compatibility,
        name="compatibility",
    )

    verdict = compatibility.get("compatibility") or {}

    runtime_section = (
        compatibility.get("runtime") or {}
    )

    return RuntimeCompatibility(
        status=verdict.get("status"),
        confidence=verdict.get("confidence"),
        candidate_runtimes=tuple(
            str(value)
            for value in (
                runtime_section.get("supported") or []
            )
        ),
        weight_formats=weight_formats,
        architecture=architecture,
        reasons=tuple(
            str(value)
            for value in (
                verdict.get("reasons") or []
            )
        ),
    )


def build_model_requirement(
    *,
    model,
    feasibility=None,
    install_storage=None,
    compatibility=None,
    concurrency=None,
    target_storage_pool_id=PLATFORM_DATA_STORAGE_POOL_ID,
    primary_inference_memory_type=DEDICATED_VRAM,
) -> ModelRequirement:
    """Normalize what the existing estimators already know.

    `model` is an inventory or catalogue record. `feasibility`,
    `install_storage` and `compatibility` are the outputs of
    `evaluate_model_feasibility`, `estimate_model_install_storage` and
    `evaluate_model_compatibility`. Each is optional: an absent input
    yields an explicitly unresolved figure, never a guessed one.

    `concurrency` is supplied by the caller because it is a serving
    decision held in configuration, and this layer does not read
    configuration.
    """

    model = _require_mapping(model, name="model")

    shape = _detect_shape(model)

    (
        model_id,
        revision,
        runtime,
        metadata,
    ) = _model_identity(model, shape)

    if feasibility is not None:
        feasibility = _require_mapping(
            feasibility,
            name="feasibility",
        )

    storage = _build_storage_requirement(
        model=model,
        shape=shape,
        install_storage=install_storage,
        target_pool_id=target_storage_pool_id,
    )

    #
    # The candidate record reserves a slot for a RAM figure, which is
    # where a future estimator would publish one. Today nothing fills
    # it and there is no RAM estimator anywhere in the source, so this
    # reports unresolved rather than approximating from weight size.
    # C5 must be able to see that the figure is unknown.
    #
    declared = model.get("requirements") or {}

    declared_ram = _int_or_none(
        declared.get("ram_bytes")
    )

    ram = MemoryRequirement(
        memory_type=SYSTEM_RAM,
        required_bytes=declared_ram,
        confidence=(
            "declared"
            if declared_ram is not None
            else None
        ),
        basis=(
            "model_record.requirements.ram_bytes"
            if declared_ram is not None
            else BASIS_UNRESOLVED_NO_ESTIMATOR
        ),
    )

    primary_inference_memory = (
        _build_primary_inference_memory(
            model=model,
            feasibility=feasibility,
            memory_type=(
                primary_inference_memory_type
            ),
        )
    )

    runtime_compatibility = (
        _build_runtime_compatibility(
            model=model,
            shape=shape,
            compatibility=compatibility,
            metadata=metadata,
        )
    )

    context_length = _int_or_none(
        metadata.get("context_length")
    )

    assumptions = RequirementAssumptions(
        context_length=context_length,
        concurrency=_int_or_none(concurrency),
        offload=None,
        basis={
            "context_length": (
                "model_metadata"
                if context_length is not None
                else BASIS_UNRESOLVED_MISSING_INPUT
            ),
            "concurrency": (
                "caller_supplied"
                if _int_or_none(concurrency)
                is not None
                else BASIS_UNRESOLVED_MISSING_INPUT
            ),
            "offload": BASIS_NOT_IMPLEMENTED,
        },
    )

    unresolved = []

    if storage.acquisition_peak_bytes is None:
        unresolved.append(
            "storage.acquisition_peak_bytes"
        )

    if storage.installed_bytes is None:
        unresolved.append(
            "storage.installed_bytes"
        )

    if not ram.resolved:
        unresolved.append("ram.required_bytes")

    if not primary_inference_memory.resolved:
        unresolved.append(
            "primary_inference_memory.required_bytes"
        )

    if runtime_compatibility.status is None:
        unresolved.append(
            "runtime_compatibility.status"
        )

    if assumptions.context_length is None:
        unresolved.append(
            "assumptions.context_length"
        )

    if assumptions.concurrency is None:
        unresolved.append(
            "assumptions.concurrency"
        )

    unresolved.append("assumptions.offload")

    return ModelRequirement(
        schema_version=(
            MODEL_REQUIREMENT_SCHEMA_VERSION
        ),
        model_id=model_id,
        revision=revision,
        runtime=runtime,
        quantization=metadata.get("quantization"),
        storage=storage,
        ram=ram,
        primary_inference_memory=(
            primary_inference_memory
        ),
        runtime_compatibility=(
            runtime_compatibility
        ),
        assumptions=assumptions,
        unresolved_fields=tuple(unresolved),
    )

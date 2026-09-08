"""Runtime-aware model eligibility. Compatibility, not capacity.

Consumes the selected foundation, a matching installation, and a fresh
VERIFIED RuntimeCapabilityProfile. Does not import model, planning,
resource, inference, execution, or subprocess. Does not acquire, delete,
or rank. Unknown is never eligible.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.clock import Clock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.runtime.contracts import (
    EligibilityReasonCode,
    EligibleModelView,
    EligibleModelViewId,
    EligibleViewStatus,
    FoundationSelection,
    FoundationSelectionMode,
    InstallationStatus,
    RuntimeCapabilityProfile,
    RuntimeEligibilityStatus,
    RuntimeEligibleModelCandidate,
    RuntimeInstallation,
    RuntimePolicy,
    RuntimeSupportDescriptor,
    VerificationStatus,
)
from kultrun.runtime.pins import ELIGIBILITY_SCHEMA
from kultrun.runtime.provision import ProvisioningService
from kultrun.runtime.resolve import ExecutorCapabilityView
from kultrun.runtime.selection import FoundationSelectionService
from kultrun.runtime.verify import VerificationService

PLANNING_COMPATIBLE = "compatible"
PLANNING_UNSUPPORTED = "unsupported"
PLANNING_UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ModelEligibilityFacts:
    """Catalog facts the evaluator may consume. Not ModelMetadata."""

    model_id: str
    logical_name: str
    architecture: Maybe[str] = NOT_PROVIDED
    family: Maybe[str] = NOT_PROVIDED
    quantization: Maybe[str] = NOT_PROVIDED
    supported_runtimes: tuple[str, ...] = ()
    artifact_format: Maybe[str] = NOT_PROVIDED
    modality: Maybe[str] = NOT_PROVIDED


@dataclass(frozen=True, slots=True)
class CompatibilityDecision:
    """One model's runtime compatibility. Not a capacity verdict."""

    status: RuntimeEligibilityStatus
    reason_codes: tuple[EligibilityReasonCode, ...]
    reasons: tuple[str, ...]


@runtime_checkable
class RuntimeModelCompatibility(Protocol):
    """Runtime-specific interpretation. Core owns the status vocabulary."""

    @property
    def runtime(self) -> Name:
        """Runtime family this interpreter applies to."""
        ...

    def evaluate(
        self,
        model: ModelEligibilityFacts,
        descriptor: RuntimeSupportDescriptor,
        profile: RuntimeCapabilityProfile,
    ) -> CompatibilityDecision:
        """Judge one model. Must not consult RAM, VRAM, or reservations."""
        ...


def fingerprint_view_id(
    host_id: str,
    selected_candidate_id: str,
    profile_id: str,
    generation: int,
) -> EligibleModelViewId:
    """Derived view identity. Not a persisted catalog row."""
    material = (
        f"{ELIGIBILITY_SCHEMA}|{host_id}|{selected_candidate_id}|"
        f"{profile_id}|{generation}"
    )
    digest = hashlib.sha256(material.encode()).hexdigest()
    return EligibleModelViewId(f"emv_{digest[:16]}")


def _token(value: object) -> str | None:
    if not is_resolved(value) or not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text or None


def _codes(
    *items: EligibilityReasonCode,
) -> tuple[EligibilityReasonCode, ...]:
    seen: list[EligibilityReasonCode] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return tuple(seen)


def declared_compatibility(
    model: ModelEligibilityFacts,
    descriptor: RuntimeSupportDescriptor,
    profile: RuntimeCapabilityProfile | None = None,
) -> CompatibilityDecision:
    """Generic declared-support matching. Adapters add runtime-specific rules."""
    codes: list[EligibilityReasonCode] = []
    notes: list[str] = []
    blocked = False
    unresolved = False
    runtime_name = descriptor.runtime.value.strip().lower()

    declared = tuple(
        item.strip().lower() for item in model.supported_runtimes if item.strip()
    )
    if not declared:
        unresolved = True
        codes.append(EligibilityReasonCode.REQUIRED_MODEL_METADATA_MISSING)
        notes.append("supported_runtimes unstated")
    elif runtime_name not in declared:
        blocked = True
        codes.append(EligibilityReasonCode.UNSUPPORTED_RUNTIME)
        notes.append(f"{descriptor.runtime.value} is not a declared runtime")

    known_arch = tuple(
        item.strip().lower() for item in descriptor.known_model_architectures
    )
    architecture = _token(model.architecture)
    if known_arch:
        if architecture is None:
            unresolved = True
            codes.append(EligibilityReasonCode.REQUIRED_MODEL_METADATA_MISSING)
            notes.append("architecture unstated")
        elif architecture not in known_arch:
            blocked = True
            codes.append(EligibilityReasonCode.UNSUPPORTED_ARCHITECTURE)
            notes.append(f"architecture {architecture} is not declared")

    known_quant = tuple(
        item.strip().lower() for item in descriptor.known_quantizations
    )
    quantization = _token(model.quantization)
    if known_quant:
        if quantization is None:
            unresolved = True
            codes.append(EligibilityReasonCode.REQUIRED_MODEL_METADATA_MISSING)
            notes.append("quantization unstated")
        elif quantization not in known_quant:
            blocked = True
            codes.append(EligibilityReasonCode.UNSUPPORTED_QUANTIZATION)
            notes.append(f"quantization {quantization} is not declared")

    known_formats = tuple(item.strip().lower() for item in descriptor.known_formats)
    artifact_format = _token(model.artifact_format)
    if (
        artifact_format is not None
        and known_formats
        and artifact_format not in known_formats
    ):
        blocked = True
        codes.append(EligibilityReasonCode.UNSUPPORTED_ARTIFACT_FORMAT)
        notes.append(f"format {artifact_format} is not declared")

    known_modalities = tuple(
        item.strip().lower() for item in descriptor.known_modalities
    )
    modality = _token(model.modality)
    if known_modalities:
        if modality is None:
            unresolved = True
            codes.append(EligibilityReasonCode.REQUIRED_MODEL_METADATA_MISSING)
            notes.append("modality unstated")
        elif modality not in known_modalities:
            blocked = True
            codes.append(EligibilityReasonCode.UNSUPPORTED_MODALITY)
            notes.append(f"modality {modality} is not declared")

    preferred = _token(descriptor.preferred_version)
    if profile is not None and preferred is not None:
        observed = profile.runtime_version.strip().lower()
        if observed and observed != preferred:
            blocked = True
            codes.append(EligibilityReasonCode.RUNTIME_VERSION_UNSUPPORTED)
            notes.append(
                f"runtime {profile.runtime_version} is not "
                f"{descriptor.preferred_version}"
            )

    if blocked:
        return CompatibilityDecision(
            RuntimeEligibilityStatus.BLOCKED, _codes(*codes), tuple(notes)
        )
    if unresolved:
        if not codes:
            codes.append(EligibilityReasonCode.COMPATIBILITY_UNRESOLVED)
        return CompatibilityDecision(
            RuntimeEligibilityStatus.UNRESOLVED, _codes(*codes), tuple(notes)
        )
    return CompatibilityDecision(RuntimeEligibilityStatus.ELIGIBLE, (), ())


class DeclaredSupportCompatibility:
    """Fallback interpreter: descriptor lists only. Not a scoring engine."""

    def __init__(self, runtime: Name) -> None:
        self._runtime = runtime

    @property
    def runtime(self) -> Name:
        return self._runtime

    def evaluate(
        self,
        model: ModelEligibilityFacts,
        descriptor: RuntimeSupportDescriptor,
        profile: RuntimeCapabilityProfile,
    ) -> CompatibilityDecision:
        return declared_compatibility(model, descriptor, profile)


def planning_compatibility(
    view: EligibleModelView, model_ids: Sequence[str]
) -> dict[str, str]:
    """Map eligibility into planning CompatibilityVerdict values.

    Planning cannot import this module. Composition copies these tokens.
    A view that is not CURRENT never yields compatible.
    """
    if view.status is not EligibleViewStatus.CURRENT:
        return dict.fromkeys(model_ids, PLANNING_UNRESOLVED)
    by_id = {item.model_id: item.status for item in view.candidates}
    mapping: dict[str, str] = {}
    for ident in model_ids:
        status = by_id.get(ident)
        if status is RuntimeEligibilityStatus.ELIGIBLE:
            mapping[ident] = PLANNING_COMPATIBLE
        elif status is RuntimeEligibilityStatus.BLOCKED:
            mapping[ident] = PLANNING_UNSUPPORTED
        else:
            mapping[ident] = PLANNING_UNRESOLVED
    return mapping


def view_payload(view: EligibleModelView) -> dict[str, object]:
    """API-shaped derived view. GET callers must not treat this as a mutation."""
    return {
        "view": view,
        "status": view.status.value,
        "selection_mode": (
            view.selection_mode if isinstance(view.selection_mode, str) else None
        ),
        "recommended_candidate_id": (
            view.recommended_candidate_id
            if isinstance(view.recommended_candidate_id, str)
            else None
        ),
        "selected_candidate_id": (
            view.selected_candidate_id
            if isinstance(view.selected_candidate_id, str)
            else None
        ),
        "runtime": view.runtime if isinstance(view.runtime, str) else None,
        "runtime_version": (
            view.runtime_version if isinstance(view.runtime_version, str) else None
        ),
        "executor": view.executor if isinstance(view.executor, str) else None,
        "installation_id": (
            view.installation_id if isinstance(view.installation_id, str) else None
        ),
        "profile_id": view.profile_id if isinstance(view.profile_id, str) else None,
        "profile_status": (
            view.profile_status if isinstance(view.profile_status, str) else None
        ),
        "foundation_stale": view.foundation_stale,
        "authoritative": view.status is EligibleViewStatus.CURRENT,
        "reason_codes": [item.value for item in view.reason_codes],
        "eligible_count": view.eligible_count,
        "blocked_count": view.blocked_count,
        "unresolved_count": view.unresolved_count,
        "candidates": list(view.candidates),
        "mutations": False,
        "acquire": False,
        "capacity": False,
        "inventory": False,
    }


class ModelEligibilityService:
    """Read-only eligible model view for the selected verified foundation."""

    def __init__(
        self,
        clock: Clock,
        foundation: FoundationSelectionService,
        provisioning: ProvisioningService,
        verification: VerificationService,
        interpreters: Sequence[RuntimeModelCompatibility] = (),
    ) -> None:
        self._clock = clock
        self._foundation = foundation
        self._provisioning = provisioning
        self._verification = verification
        self._interpreters = {item.runtime.value: item for item in interpreters}

    def evaluate(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        models: Sequence[ModelEligibilityFacts],
        policy: RuntimePolicy | None = None,
        *,
        components: Mapping[str, str] | None = None,
    ) -> EligibleModelView:
        """Recompute the derived view. GET must not persist, provision, or probe."""
        overview = self._foundation.view(
            host, executors, descriptors, policy, components=components
        )
        selection = overview.selection
        selected = selection.selected_candidate_id
        selected_token = selected if isinstance(selected, str) else ""
        installation = (
            self._installation_for(selected_token) if selected_token else None
        )
        profile = None
        if installation is not None:
            profile = self._verification.profile_for(
                installation.installation_id, host, executors
            )
        descriptor = _descriptor_for(descriptors, installation, profile, selected_token)
        status, reasons = _view_status(selection, installation, profile)
        evaluated: tuple[RuntimeEligibleModelCandidate, ...] = ()
        if (
            status is not EligibleViewStatus.UNAVAILABLE
            and descriptor is not None
            and profile is not None
            and installation is not None
        ):
            interpreter = self._interpreter_for(descriptor.runtime.value)
            evaluated = tuple(
                _candidate_from(
                    model,
                    interpreter.evaluate(model, descriptor, profile),
                )
                for model in models
            )
        return _build_view(
            host.host_id,
            selection,
            installation,
            profile,
            status,
            reasons,
            evaluated,
            self._clock.now(),
        )

    def _installation_for(self, candidate_id: str) -> RuntimeInstallation | None:
        matches = [
            item
            for item in self._provisioning.installations()
            if item.candidate_id.value == candidate_id
        ]
        if not matches:
            return None
        installed = [
            item for item in matches if item.status is InstallationStatus.INSTALLED
        ]
        return installed[-1] if installed else matches[-1]

    def _interpreter_for(self, runtime: str) -> RuntimeModelCompatibility:
        found = self._interpreters.get(runtime)
        if found is not None:
            return found
        return DeclaredSupportCompatibility(Name(runtime))


def _descriptor_for(
    descriptors: Sequence[RuntimeSupportDescriptor],
    installation: RuntimeInstallation | None,
    profile: RuntimeCapabilityProfile | None,
    selected_candidate_id: str,
) -> RuntimeSupportDescriptor | None:
    del selected_candidate_id
    runtime = None
    if installation is not None:
        runtime = installation.runtime.value
    elif profile is not None:
        runtime = profile.runtime.value
    if runtime is None:
        return None
    for descriptor in descriptors:
        if descriptor.runtime.value == runtime:
            return descriptor
    return None


def _view_status(
    selection: FoundationSelection,
    installation: RuntimeInstallation | None,
    profile: RuntimeCapabilityProfile | None,
) -> tuple[EligibleViewStatus, tuple[EligibilityReasonCode, ...]]:
    selected = selection.selected_candidate_id
    if not isinstance(selected, str):
        return (
            EligibleViewStatus.UNAVAILABLE,
            (EligibilityReasonCode.SELECTED_FOUNDATION_MISSING,),
        )
    if installation is None:
        return (
            EligibleViewStatus.UNAVAILABLE,
            (EligibilityReasonCode.SELECTED_FOUNDATION_MISSING,),
        )
    if profile is None:
        return (
            EligibleViewStatus.UNAVAILABLE,
            (EligibilityReasonCode.RUNTIME_CAPABILITY_UNVERIFIED,),
        )
    if profile.installation_id.value != installation.installation_id.value:
        return (
            EligibleViewStatus.UNAVAILABLE,
            (EligibilityReasonCode.PROFILE_INSTALLATION_MISMATCH,),
        )
    if profile.candidate_id.value != selected:
        return (
            EligibleViewStatus.UNAVAILABLE,
            (EligibilityReasonCode.PROFILE_INSTALLATION_MISMATCH,),
        )
    if profile.status is VerificationStatus.STALE:
        return (
            EligibleViewStatus.STALE,
            (EligibilityReasonCode.RUNTIME_CAPABILITY_STALE,),
        )
    if profile.status is VerificationStatus.FAILED:
        return (
            EligibleViewStatus.UNAVAILABLE,
            (EligibilityReasonCode.RUNTIME_CAPABILITY_UNVERIFIED,),
        )
    if profile.status is not VerificationStatus.VERIFIED:
        return (
            EligibleViewStatus.UNAVAILABLE,
            (EligibilityReasonCode.RUNTIME_CAPABILITY_UNVERIFIED,),
        )
    if selection.selection_mode is FoundationSelectionMode.AUTO:
        recommended = selection.recommended_candidate_id
        if isinstance(recommended, str) and recommended != selected:
            return (
                EligibleViewStatus.STALE,
                (EligibilityReasonCode.FOUNDATION_STALE,),
            )
    return EligibleViewStatus.CURRENT, ()


def _candidate_from(
    model: ModelEligibilityFacts, decision: CompatibilityDecision
) -> RuntimeEligibleModelCandidate:
    return RuntimeEligibleModelCandidate(
        model_id=model.model_id,
        logical_name=model.logical_name,
        status=decision.status,
        reason_codes=decision.reason_codes,
        reasons=decision.reasons,
        architecture=model.architecture,
        quantization=model.quantization,
        family=model.family,
    )


def _build_view(
    host_id: HostId,
    selection: FoundationSelection,
    installation: RuntimeInstallation | None,
    profile: RuntimeCapabilityProfile | None,
    status: EligibleViewStatus,
    reasons: tuple[EligibilityReasonCode, ...],
    candidates: tuple[RuntimeEligibleModelCandidate, ...],
    when: dt.datetime,
) -> EligibleModelView:
    ordered = tuple(
        sorted(candidates, key=lambda item: (item.logical_name, item.model_id))
    )
    selected = selection.selected_candidate_id
    selected_token = selected if isinstance(selected, str) else ""
    profile_token = profile.profile_id.value if profile is not None else ""
    eligible = sum(
        1 for item in ordered if item.status is RuntimeEligibilityStatus.ELIGIBLE
    )
    blocked = sum(
        1 for item in ordered if item.status is RuntimeEligibilityStatus.BLOCKED
    )
    unresolved = sum(
        1 for item in ordered if item.status is RuntimeEligibilityStatus.UNRESOLVED
    )
    shown = ordered if status is not EligibleViewStatus.UNAVAILABLE else ()
    if status is EligibleViewStatus.UNAVAILABLE:
        eligible = 0
        blocked = 0
        unresolved = 0
    return EligibleModelView(
        view_id=fingerprint_view_id(
            host_id.value,
            selected_token,
            profile_token,
            selection.generation,
        ),
        host_id=selection.host_id,
        status=status,
        evaluated_at=when,
        selection_mode=selection.selection_mode.value,
        recommended_candidate_id=selection.recommended_candidate_id,
        selected_candidate_id=selection.selected_candidate_id,
        runtime=(
            installation.runtime.value
            if installation is not None
            else (profile.runtime.value if profile is not None else NOT_PROVIDED)
        ),
        runtime_version=(
            installation.runtime_version
            if installation is not None
            else (profile.runtime_version if profile is not None else NOT_PROVIDED)
        ),
        executor=(
            installation.executor.value
            if installation is not None
            else (profile.executor.value if profile is not None else NOT_PROVIDED)
        ),
        installation_id=(
            installation.installation_id.value
            if installation is not None
            else NOT_PROVIDED
        ),
        profile_id=profile.profile_id.value if profile is not None else NOT_PROVIDED,
        profile_status=profile.status.value if profile is not None else NOT_PROVIDED,
        foundation_stale=selection.downstream_stale,
        reason_codes=reasons,
        eligible_count=eligible,
        blocked_count=blocked,
        unresolved_count=unresolved,
        candidates=shown,
    )

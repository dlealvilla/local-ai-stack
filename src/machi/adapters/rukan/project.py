"""Project stored Stage-1 records into a Rukan admin view and snapshot.

The projection does not discover hardware, admit, or serve.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypeVar

from machi.adapters.journal.jsonl import JOURNAL_FILENAME
from machi.adapters.rukan.read import load_errors, load_records
from machi.admit.contracts import ReservationRelease, ResourceReservation
from machi.capacity.contracts import CapacityEnvelope
from machi.discover.contracts import (
    AcceleratorObservation,
    MemoryObservation,
    OSArchitectureObservation,
)
from machi.discover.mount_contracts import MountObservation
from machi.foundation.contracts import FoundationSelection
from machi.install.contracts import InstallRecord
from machi.kernel.build import BuildIdentity
from machi.kernel.errors import UnknownKindError, UnknownVersionError, ValidationError
from machi.kernel.events import EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, from_dict, to_dict
from machi.kernel.snapshot import (
    NOT_RECORDED,
    SNAPSHOT_SCHEMA,
    SupportEvent,
    SupportSnapshot,
    snapshot_id_for,
)
from machi.kernel.unresolved import Unresolved, is_resolved
from machi.kernel.witness import WitnessFacts, compose_witness
from machi.model.contracts import ModelArtifact
from machi.model.provider_qualification import OllamaQualificationEvidence
from machi.model.qualification import QualificationEvidence
from machi.plan.contracts import DeploymentConfiguration
from machi.plan.provider import ProviderDeploymentConfiguration
from machi.serve.contracts import InferenceProof, ServeTransition, ServingInstance
from machi.serve.provider import ProviderInferenceProof, ProviderServingInstance

PHYSICAL_REGISTER = "product qualification register; not a live host status"
PENDING_COVERAGE = "AMD native/vLLM; macOS/Ollama; NVIDIA Ampere/N1"
_READY = "ready"
_MAX_EVENTS = 32
_WITNESS_CLOCK = "1970-01-01T00:00:00+00:00"
ContractT = TypeVar("ContractT", bound=Contract)


@dataclass(frozen=True, slots=True)
class ChainView:
    """One cited journey. latest_stored is not a live claim."""

    basis: str
    macropath: str
    generation_id: str
    model_identity: str
    model_identity_kind: str
    qualification_id: str
    qualification_outcome: str
    plan_id: str
    reservation_id: str
    reservation_state: str
    release_id: str
    instance_id: str
    instance_state: str
    instance_health: str
    proof_id: str
    proof_outcome: str
    contradictory: bool


@dataclass(frozen=True, slots=True)
class AdminProjection:
    """Read model for Rukan Admin. Authority stays in the stored records."""

    install_id: str
    install_created_at: str
    version: str
    build_id: str
    source_commit: str
    os_family: str
    architecture: str
    memory_summary: str
    accelerator_summary: str
    mount_summary: str
    safe_host_bytes: str
    safe_accelerator_bytes: str
    capacity_evidence_id: str
    capacity_observed_at: str
    chain: ChainView
    witness_id: str
    witness_verdict: str
    witness_reason: str
    models: tuple[dict[str, str], ...]
    unreadable: int


def project_admin(
    store_root: Path,
    build: BuildIdentity,
    *,
    journal_dir: Path | None = None,
) -> AdminProjection:
    """Compose the admin view from whatever the store currently holds."""
    root = Path(store_root)
    installs = _typed(root, InstallRecord)
    envelopes = _typed(root, CapacityEnvelope)
    observations = _typed(root, OSArchitectureObservation)
    memories = _typed(root, MemoryObservation)
    accelerators = _typed(root, AcceleratorObservation)
    mounts = _typed(root, MountObservation)
    selections = _typed(root, FoundationSelection)
    native_plans = _typed(root, DeploymentConfiguration)
    provider_plans = _typed(root, ProviderDeploymentConfiguration)
    reservations = _typed(root, ResourceReservation)
    releases = _typed(root, ReservationRelease)
    steps = _typed(root, ServeTransition)
    native_instances = _overlay_native(_typed(root, ServingInstance), steps)
    provider_instances = _overlay_provider(
        _typed(root, ProviderServingInstance), steps
    )
    native_proofs = _typed(root, InferenceProof)
    provider_proofs = _typed(root, ProviderInferenceProof)
    artifacts = _typed(root, ModelArtifact)
    native_quals = _typed(root, QualificationEvidence)
    provider_quals = _typed(root, OllamaQualificationEvidence)
    envelope = _newest(envelopes)
    observation = _newest(observations)
    memory = _newest(memories)
    accelerator = _newest(accelerators)
    mount = _newest(mounts)
    install = installs[0] if len(installs) == 1 else None
    chain = _chain(
        selections=selections,
        native_plans=native_plans,
        provider_plans=provider_plans,
        reservations=reservations,
        releases=releases,
        native_instances=native_instances,
        provider_instances=provider_instances,
        native_proofs=native_proofs,
        provider_proofs=provider_proofs,
        native_quals=native_quals,
        provider_quals=provider_quals,
        envelope=envelope,
    )
    selection_id = _selection_id(selections, chain.generation_id)
    witness = compose_witness(
        _facts(install, envelope, chain, selection_id, build.built_at)
    )
    unreadable = sum(
        load_errors(root, kind)
        for kind in (
            InstallRecord,
            CapacityEnvelope,
            ServingInstance,
            ProviderServingInstance,
        )
    )
    return AdminProjection(
        install_id=str(install.install_id) if install is not None else NOT_RECORDED,
        install_created_at=_time(install, "created_at"),
        version=build.version,
        build_id=build.build_id or NOT_RECORDED,
        source_commit=build.source_commit or NOT_RECORDED,
        os_family=_maybe(observation, "os_family"),
        architecture=_maybe(observation, "architecture"),
        memory_summary=_memory_summary(memory),
        accelerator_summary=_accelerator_summary(accelerator),
        mount_summary=_mount_summary(mount),
        safe_host_bytes=_safe_host(envelope),
        safe_accelerator_bytes=_safe_accelerator(envelope),
        capacity_evidence_id=envelope.evidence_id if envelope else NOT_RECORDED,
        capacity_observed_at=_time(envelope, "observed_at"),
        chain=chain,
        witness_id=witness.witness_id,
        witness_verdict=witness.verdict,
        witness_reason=witness.reason,
        models=_models(artifacts, provider_quals),
        unreadable=unreadable,
    )


def export_snapshot(
    view: AdminProjection,
    *,
    exported_at: str,
    journal_dir: Path | None = None,
) -> SupportSnapshot:
    """Build a non-content snapshot. Payloads and paths stay out."""
    events = _support_events(journal_dir)
    chain = view.chain
    fields = (
        exported_at,
        view.install_id,
        view.install_created_at,
        view.version,
        view.build_id,
        view.source_commit,
        view.os_family,
        view.architecture,
        view.accelerator_summary,
        view.safe_host_bytes,
        view.safe_accelerator_bytes,
        view.capacity_observed_at,
        chain.macropath,
        chain.generation_id,
        chain.model_identity,
        chain.model_identity_kind,
        chain.qualification_id,
        chain.qualification_outcome,
        chain.plan_id,
        chain.reservation_id,
        chain.reservation_state,
        chain.instance_id,
        chain.instance_state,
        view.witness_verdict,
        view.witness_reason,
        PHYSICAL_REGISTER,
        PENDING_COVERAGE,
        "|".join(item.event_type + item.occurred_at for item in events),
    )
    return SupportSnapshot(
        snapshot_id=snapshot_id_for("\n".join(fields)),
        schema_name=SNAPSHOT_SCHEMA,
        exported_at=exported_at,
        install_id=view.install_id,
        install_created_at=view.install_created_at,
        product_name="Rukan",
        package_name="machi",
        version=view.version,
        build_id=view.build_id,
        source_commit=view.source_commit,
        os_family=view.os_family,
        architecture=view.architecture,
        accelerator_summary=view.accelerator_summary,
        safe_host_bytes=view.safe_host_bytes,
        safe_accelerator_bytes=view.safe_accelerator_bytes,
        capacity_observed_at=view.capacity_observed_at,
        macropath=chain.macropath,
        foundation_generation_id=chain.generation_id,
        model_identity=chain.model_identity,
        model_identity_kind=chain.model_identity_kind,
        qualification_id=chain.qualification_id,
        qualification_outcome=chain.qualification_outcome,
        plan_id=chain.plan_id,
        reservation_id=chain.reservation_id,
        reservation_state=chain.reservation_state,
        instance_id=chain.instance_id,
        instance_state=chain.instance_state,
        witness_verdict=view.witness_verdict,
        witness_reason=view.witness_reason,
        physical_register=PHYSICAL_REGISTER,
        pending_coverage=PENDING_COVERAGE,
        support_events=events,
    )


def projection_document(view: AdminProjection) -> dict[str, object]:
    """JSON-ready admin document. No prompts and no filesystem paths."""
    chain = view.chain
    return {
        "product_name": "Rukan",
        "package_name": "machi",
        "version": view.version,
        "build_id": view.build_id,
        "source_commit": view.source_commit,
        "install_id": view.install_id,
        "install_created_at": view.install_created_at,
        "witness": {
            "witness_id": view.witness_id,
            "verdict": view.witness_verdict,
            "reason": view.witness_reason,
        },
        "chain": {
            "basis": chain.basis,
            "macropath": chain.macropath,
            "foundation_generation_id": chain.generation_id,
            "model_identity": chain.model_identity,
            "model_identity_kind": chain.model_identity_kind,
            "qualification_id": chain.qualification_id,
            "qualification_outcome": chain.qualification_outcome,
            "plan_id": chain.plan_id,
            "reservation_id": chain.reservation_id,
            "reservation_state": chain.reservation_state,
            "release_id": chain.release_id,
            "instance_id": chain.instance_id,
            "instance_state": chain.instance_state,
            "instance_health": chain.instance_health,
            "proof_id": chain.proof_id,
            "proof_outcome": chain.proof_outcome,
            "contradictory": chain.contradictory,
        },
        "host": {
            "os_family": view.os_family,
            "architecture": view.architecture,
            "memory_summary": view.memory_summary,
            "accelerator_summary": view.accelerator_summary,
            "mount_summary": view.mount_summary,
            "safe_host_bytes": view.safe_host_bytes,
            "safe_accelerator_bytes": view.safe_accelerator_bytes,
            "capacity_evidence_id": view.capacity_evidence_id,
            "capacity_observed_at": view.capacity_observed_at,
        },
        "models": list(view.models),
        "physical_register": PHYSICAL_REGISTER,
        "pending_coverage": PENDING_COVERAGE,
        "unreadable_records": view.unreadable,
        "live_claim": False,
    }


def _chain(
    *,
    selections: tuple[FoundationSelection, ...],
    native_plans: tuple[DeploymentConfiguration, ...],
    provider_plans: tuple[ProviderDeploymentConfiguration, ...],
    reservations: tuple[ResourceReservation, ...],
    releases: tuple[ReservationRelease, ...],
    native_instances: tuple[ServingInstance, ...],
    provider_instances: tuple[ProviderServingInstance, ...],
    native_proofs: tuple[InferenceProof, ...],
    provider_proofs: tuple[ProviderInferenceProof, ...],
    native_quals: tuple[QualificationEvidence, ...],
    provider_quals: tuple[OllamaQualificationEvidence, ...],
    envelope: CapacityEnvelope | None,
) -> ChainView:
    ready: list[tuple[str, ServingInstance | ProviderServingInstance]] = [
        ("native", item) for item in native_instances if item.state.value == _READY
    ]
    ready.extend(
        ("provider", item)
        for item in provider_instances
        if item.state.value == _READY
    )
    if len(ready) > 1:
        return _empty(contradictory=True, basis="contradictory_ready_instances")
    if len(ready) == 1:
        _kind, chosen = ready[0]
        return _from_instance(
            _kind,
            chosen,
            basis="authorised_ready_instance",
            selections=selections,
            native_plans=native_plans,
            provider_plans=provider_plans,
            reservations=reservations,
            releases=releases,
            native_proofs=native_proofs,
            provider_proofs=provider_proofs,
            native_quals=native_quals,
            provider_quals=provider_quals,
            envelope=envelope,
        )
    latest = _latest_instance(
        native_instances, provider_instances, releases
    )
    if latest is None:
        return _empty(contradictory=False, basis="no_instance")
    kind, instance = latest
    return _from_instance(
        kind,
        instance,
        basis="latest_stored_not_live",
        selections=selections,
        native_plans=native_plans,
        provider_plans=provider_plans,
        reservations=reservations,
        releases=releases,
        native_proofs=native_proofs,
        provider_proofs=provider_proofs,
        native_quals=native_quals,
        provider_quals=provider_quals,
        envelope=envelope,
    )


def _from_instance(
    kind: str,
    instance: ServingInstance | ProviderServingInstance,
    *,
    basis: str,
    selections: tuple[FoundationSelection, ...],
    native_plans: tuple[DeploymentConfiguration, ...],
    provider_plans: tuple[ProviderDeploymentConfiguration, ...],
    reservations: tuple[ResourceReservation, ...],
    releases: tuple[ReservationRelease, ...],
    native_proofs: tuple[InferenceProof, ...],
    provider_proofs: tuple[ProviderInferenceProof, ...],
    native_quals: tuple[QualificationEvidence, ...],
    provider_quals: tuple[OllamaQualificationEvidence, ...],
    envelope: CapacityEnvelope | None,
) -> ChainView:
    del selections, envelope
    release = next(
        (item for item in releases if item.reservation_id == instance.reservation_id),
        None,
    )
    reservation = next(
        (
            item
            for item in reservations
            if item.reservation_id == instance.reservation_id
        ),
        None,
    )
    if kind == "native" and isinstance(instance, ServingInstance):
        plan = next(
            (item for item in native_plans if item.plan_id == instance.plan_id),
            None,
        )
        proof = next(
            (
                item
                for item in native_proofs
                if item.instance_id == instance.instance_id
            ),
            None,
        )
        qual = next(
            (
                item
                for item in native_quals
                if item.artifact_id == instance.artifact_id
                and item.generation_id == instance.generation_id
            ),
            None,
        )
        return ChainView(
            basis=basis,
            macropath=plan.provider if plan is not None else "vllm",
            generation_id=instance.generation_id,
            model_identity=instance.artifact_id,
            model_identity_kind="warehouse_artifact",
            qualification_id=qual.qualification_id if qual else NOT_RECORDED,
            qualification_outcome=qual.outcome.value if qual else NOT_RECORDED,
            plan_id=instance.plan_id,
            reservation_id=instance.reservation_id,
            reservation_state=_reservation_state(reservation, release),
            release_id=release.release_id if release else NOT_RECORDED,
            instance_id=instance.instance_id,
            instance_state=instance.state.value,
            instance_health=instance.health.value,
            proof_id=proof.proof_id if proof else NOT_RECORDED,
            proof_outcome=_native_proof(proof),
            contradictory=False,
        )
    assert isinstance(instance, ProviderServingInstance)
    plan_p = next(
        (item for item in provider_plans if item.plan_id == instance.plan_id),
        None,
    )
    proof_p = next(
        (
            item
            for item in provider_proofs
            if item.instance_id == instance.instance_id
        ),
        None,
    )
    qual_p = next(
        (
            item
            for item in provider_quals
            if item.digest == instance.digest
            and item.generation_id == instance.generation_id
        ),
        None,
    )
    return ChainView(
        basis=basis,
        macropath=plan_p.provider if plan_p is not None else instance.serve_provider,
        generation_id=instance.generation_id,
        model_identity=instance.digest,
        model_identity_kind="provider_digest",
        qualification_id=qual_p.qualification_id if qual_p else NOT_RECORDED,
        qualification_outcome=qual_p.outcome.value if qual_p else NOT_RECORDED,
        plan_id=instance.plan_id,
        reservation_id=instance.reservation_id,
        reservation_state=_reservation_state(reservation, release),
        release_id=release.release_id if release else NOT_RECORDED,
        instance_id=instance.instance_id,
        instance_state=instance.state.value,
        instance_health=instance.health.value,
        proof_id=proof_p.proof_id if proof_p else NOT_RECORDED,
        proof_outcome=_provider_proof(proof_p),
        contradictory=False,
    )


def _facts(
    install: InstallRecord | None,
    envelope: CapacityEnvelope | None,
    chain: ChainView,
    selection_id: str,
    observed_at: str | None,
) -> WitnessFacts:
    clock = observed_at if observed_at else _WITNESS_CLOCK
    return WitnessFacts(
        install_id=str(install.install_id) if install is not None else NOT_RECORDED,
        foundation_selection_id=selection_id,
        capacity_evidence_id=envelope.evidence_id if envelope else NOT_RECORDED,
        foundation_generation_id=chain.generation_id,
        model_identity=chain.model_identity,
        model_identity_kind=chain.model_identity_kind,
        qualification_id=chain.qualification_id,
        plan_id=chain.plan_id,
        plan_generation_id=chain.generation_id,
        reservation_id=chain.reservation_id,
        reservation_plan_id=chain.plan_id,
        reservation_state=chain.reservation_state
        if chain.reservation_state in {"reserved", "released"}
        else NOT_RECORDED,
        instance_id=chain.instance_id,
        instance_plan_id=chain.plan_id,
        instance_reservation_id=chain.reservation_id,
        instance_generation_id=chain.generation_id,
        instance_state=chain.instance_state,
        proof_id=chain.proof_id,
        proof_outcome=chain.proof_outcome
        if chain.proof_outcome in {"proven", "failed"}
        else NOT_RECORDED,
        proof_plan_id=chain.plan_id,
        proof_reservation_id=chain.reservation_id,
        release_id=chain.release_id,
        observed_at=clock,
    )


def _selection_id(
    selections: tuple[FoundationSelection, ...], generation_id: str
) -> str:
    if generation_id in ("", NOT_RECORDED):
        return NOT_RECORDED
    for item in selections:
        if is_resolved(item.generation_id) and item.generation_id == generation_id:
            return item.selection_id
    return NOT_RECORDED


def _empty(*, contradictory: bool, basis: str) -> ChainView:
    return ChainView(
        basis=basis,
        macropath=NOT_RECORDED,
        generation_id=NOT_RECORDED,
        model_identity=NOT_RECORDED,
        model_identity_kind=NOT_RECORDED,
        qualification_id=NOT_RECORDED,
        qualification_outcome=NOT_RECORDED,
        plan_id=NOT_RECORDED,
        reservation_id=NOT_RECORDED,
        reservation_state=NOT_RECORDED,
        release_id=NOT_RECORDED,
        instance_id=NOT_RECORDED,
        instance_state=NOT_RECORDED,
        instance_health=NOT_RECORDED,
        proof_id=NOT_RECORDED,
        proof_outcome=NOT_RECORDED,
        contradictory=contradictory,
    )


def _models(
    artifacts: tuple[ModelArtifact, ...],
    quals: tuple[OllamaQualificationEvidence, ...],
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for item in artifacts:
        rows.append(
            {
                "identity": item.artifact_id,
                "kind": "warehouse_artifact",
                "revision": item.immutable_revision,
                "lifecycle": item.lifecycle.value,
            }
        )
    seen: set[str] = set()
    for qual in quals:
        if qual.digest in seen:
            continue
        seen.add(qual.digest)
        rows.append(
            {
                "identity": qual.digest,
                "kind": "provider_digest",
                "revision": NOT_RECORDED,
                "lifecycle": qual.outcome.value,
            }
        )
    return tuple(rows)


def _support_events(journal_dir: Path | None) -> tuple[SupportEvent, ...]:
    if journal_dir is None:
        return ()
    path = Path(journal_dir) / JOURNAL_FILENAME
    if not path.is_file():
        return ()
    chosen: list[SupportEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            document = json.loads(line)
            event = from_dict(document)
        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ValidationError,
            UnknownKindError,
            UnknownVersionError,
        ):
            continue
        if not isinstance(event, EventRecord):
            continue
        if event.privacy not in {PrivacyClass.PUBLIC_OPS, PrivacyClass.OPERATIONAL}:
            continue
        chosen.append(
            SupportEvent(
                event_type=str(event.event_type),
                outcome=str(event.outcome.value),
                occurred_at=event.occurred_at.isoformat(),
                privacy=event.privacy.value,
            )
        )
    return tuple(chosen[-_MAX_EVENTS:])


def _latest_step(
    instance_id: str, steps: tuple[ServeTransition, ...]
) -> ServeTransition | None:
    latest: ServeTransition | None = None
    for step in steps:
        if step.instance_id != instance_id:
            continue
        if latest is None or step.sequence >= latest.sequence:
            latest = step
    return latest


def _overlay_native(
    instances: tuple[ServingInstance, ...], steps: tuple[ServeTransition, ...]
) -> tuple[ServingInstance, ...]:
    visible: list[ServingInstance] = []
    for item in instances:
        latest = _latest_step(item.instance_id, steps)
        if latest is None:
            visible.append(item)
        else:
            visible.append(replace(item, state=latest.state, health=latest.health))
    return tuple(visible)


def _overlay_provider(
    instances: tuple[ProviderServingInstance, ...],
    steps: tuple[ServeTransition, ...],
) -> tuple[ProviderServingInstance, ...]:
    visible: list[ProviderServingInstance] = []
    for item in instances:
        latest = _latest_step(item.instance_id, steps)
        if latest is None:
            visible.append(item)
        else:
            visible.append(replace(item, state=latest.state, health=latest.health))
    return tuple(visible)


def _typed(root: Path, contract_type: type[ContractT]) -> tuple[ContractT, ...]:
    found: list[ContractT] = []
    for record in load_records(root, contract_type):
        if isinstance(record, contract_type):
            found.append(record)
    return tuple(found)


def _newest(records: tuple[ContractT, ...]) -> ContractT | None:
    if not records:
        return None
    return max(records, key=_observed_at)


def _observed_at(item: Contract) -> dt.datetime:
    value = item.__getattribute__("observed_at")
    if not isinstance(value, dt.datetime):
        raise ValidationError("record has no observation time")
    return value


def _latest_instance(
    native: tuple[ServingInstance, ...],
    provider: tuple[ProviderServingInstance, ...],
    releases: tuple[ReservationRelease, ...] = (),
) -> tuple[str, ServingInstance | ProviderServingInstance] | None:
    """Prefer a hold that is still reserved over a higher instance id."""
    released = {item.reservation_id for item in releases}
    rows: list[tuple[str, str, ServingInstance | ProviderServingInstance]] = [
        ("native", item.instance_id, item) for item in native
    ]
    rows.extend(("provider", item.instance_id, item) for item in provider)
    held = [item for item in rows if item[2].reservation_id not in released]
    pool = held or rows
    if not pool:
        return None
    kind, _identity, instance = max(pool, key=lambda item: item[1])
    return kind, instance


def _reservation_state(
    reservation: ResourceReservation | None,
    release: ReservationRelease | None,
) -> str:
    if release is not None:
        return "released"
    if reservation is None:
        return NOT_RECORDED
    return reservation.state.value


def _native_proof(proof: InferenceProof | None) -> str:
    if proof is None:
        return NOT_RECORDED
    if proof.structurally_valid and proof.failure.value == "none":
        return "proven"
    return "failed"


def _provider_proof(proof: ProviderInferenceProof | None) -> str:
    if proof is None:
        return NOT_RECORDED
    if proof.failure.value == "none":
        return "proven"
    return "failed"


def _safe_host(envelope: CapacityEnvelope | None) -> str:
    if envelope is None or not is_resolved(envelope.memory.safe_bytes):
        return NOT_RECORDED
    return str(envelope.memory.safe_bytes)


def _safe_accelerator(envelope: CapacityEnvelope | None) -> str:
    if envelope is None or not envelope.accelerators:
        return NOT_RECORDED
    safe = envelope.accelerators[0].safe_bytes
    if not is_resolved(safe):
        return NOT_RECORDED
    return str(safe)


def _memory_summary(observation: MemoryObservation | None) -> str:
    if observation is None:
        return NOT_RECORDED
    total = observation.physical_total_bytes
    if isinstance(total, Unresolved) or not isinstance(total, int):
        return "unresolved"
    return f"physical_bytes {total}"


def _accelerator_summary(observation: AcceleratorObservation | None) -> str:
    if observation is None or not observation.devices:
        return NOT_RECORDED
    parts: list[str] = []
    for device in observation.devices:
        vendor = device.vendor.value if is_resolved(device.vendor) else "unresolved"
        model = device.model_name if "/" not in device.model_name else "redacted"
        parts.append(f"{vendor} {model}".strip())
    summary = "; ".join(parts)
    return summary[:240]


def _mount_summary(observation: MountObservation | None) -> str:
    if observation is None:
        return NOT_RECORDED
    return f"entries {len(observation.entries)}"


def _maybe(record: object | None, field: str) -> str:
    if record is None:
        return NOT_RECORDED
    value = getattr(record, field)
    if isinstance(value, Unresolved):
        return "unresolved"
    if isinstance(value, str):
        return value or NOT_RECORDED
    value_of = getattr(value, "value", None)
    if isinstance(value_of, str):
        return value_of
    return NOT_RECORDED


def _time(record: object | None, field: str) -> str:
    if record is None:
        return NOT_RECORDED
    value = getattr(record, field)
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return NOT_RECORDED


def snapshot_document(snapshot: SupportSnapshot) -> dict[str, object]:
    """Serialize a snapshot for export. Validation already rejected content."""
    return to_dict(snapshot)

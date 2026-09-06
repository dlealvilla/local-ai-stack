"""The Stage 0.2 contract set: it serializes, and it keeps its distinctions.

Round-tripping every contract is the least interesting half. The tests that
matter are the ones asserting that specific distinctions survive — the ones
the previous attempt either collapsed or was explicitly warned not to.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from kultrun.analytics.contracts import UsageEvent, UsageId
from kultrun.audit.contracts import AuditDecision, AuditEvent, AuditId, AuditOutcome
from kultrun.capacity.contracts import CapacityEvidence, EvidenceType
from kultrun.entitlement.contracts import Entitlement, EntitlementKind
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.execution import contracts as _execution_contracts  # noqa: F401
from kultrun.host.contracts import (
    Accelerator,
    AcceleratorVendor,
    Architecture,
    CpuFacts,
    ExecutionCapabilities,
    HostCapabilities,
    HostId,
    MemoryFacts,
    MountFacts,
    NetworkFacts,
    OperatingEnvironment,
)
from kultrun.identity.contracts import (
    AccessContext,
    PrincipalKind,
    Subject,
    SubjectId,
    TeamId,
)
from kultrun.inference.contracts import (
    HealthState,
    InferenceEndpoint,
    InferenceInstance,
    InstanceId,
    LifecycleState,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import (
    Contract,
    from_dict,
    registered_contracts,
    to_dict,
    unresolved_fields,
    validate_registry,
)
from kultrun.kernel.unresolved import (
    NOT_MEASURED,
    NOT_PROVIDED,
    Unresolved,
    is_resolved,
)
from kultrun.knowledge.contracts import (
    IndexingState,
    KnowledgeItem,
    KnowledgeItemId,
    KnowledgeSource,
    KnowledgeSourceId,
)
from kultrun.model.contracts import (
    ArtifactId,
    DerivationType,
    InventoryState,
    ModelArtifact,
    ModelId,
    ModelInventoryRecord,
    ModelMetadata,
    ModelRequirement,
)
from kultrun.policy.contracts import PolicyRef
from kultrun.resource.contracts import (
    ReservationId,
    ReservationState,
    ResourceReservation,
    Workload,
    WorkloadId,
    WorkloadProfile,
    WorkloadType,
)
from kultrun.runtime import contracts as _runtime_contracts  # noqa: F401
from kultrun.storage.contracts import ProviderClass, StoragePool, StoragePoolId
from kultrun.training.contracts import (
    DatasetSnapshot,
    DatasetSnapshotId,
    DerivedModel,
    DerivedModelId,
    PromotionState,
)

INSTANT = dt.datetime(2026, 9, 5, 6, 30, tzinfo=dt.UTC)
HOST = HostId.generate()
MODEL = ModelId.generate()


def provenance() -> Provenance:
    return Provenance(
        producer=Name("internal.estimator"),
        producer_version="1",
        observed_at=INSTANT,
        policy_version=NOT_PROVIDED,
    )


def host_capabilities() -> HostCapabilities:
    return HostCapabilities(
        host_id=HOST,
        fingerprint="abc123",
        detected_at=INSTANT,
        operating_environment=OperatingEnvironment(
            os_name="linux",
            os_version="6.8.0",
            architecture=Architecture.X86_64,
            kernel_version=NOT_MEASURED,
            virtualized=True,
        ),
        cpu=CpuFacts(
            vendor="AuthenticAMD",
            model_name=NOT_MEASURED,
            physical_cores=32,
            logical_cores=64,
        ),
        memory=MemoryFacts(
            total_bytes=274_877_906_944,
            available_bytes=NOT_MEASURED,
            unified_with_accelerator=False,
        ),
        execution=ExecutionCapabilities(
            native_process=True, docker=True, podman=NOT_MEASURED
        ),
        network=NetworkFacts(
            hostname="reference", loopback_address="127.0.0.1", occupied_ports=(22,)
        ),
        accelerators=(
            Accelerator(
                index=0,
                vendor=AcceleratorVendor.NVIDIA,
                model_name="L40S",
                memory_total_bytes=48_305_799_168,
                driver_version="550.90.07",
                unified_memory=False,
            ),
        ),
        mounts=(
            MountFacts(
                mount_point="/",
                device=NOT_MEASURED,
                filesystem_type="ext4",
                total_bytes=1_000_000_000_000,
                free_bytes=900_000_000_000,
            ),
        ),
    )


def storage_pool() -> StoragePool:
    return StoragePool(
        pool_id=StoragePoolId.generate(),
        host_id=HOST,
        mount_point="/",
        provider_class=ProviderClass.LOCAL_DISK,
        fingerprint="pool-abc",
        generation=1,
        filesystem_type="ext4",
        quota_identity=NOT_PROVIDED,
    )


def subject() -> Subject:
    return Subject(
        subject_id=SubjectId.generate(),
        principal_kind=PrincipalKind.USER,
        display_name="Ada",
    )


EVERY_CONTRACT = [
    provenance,
    lambda: LayeredBytes(
        reported_bytes=100,
        effective_bytes=90,
        safe_bytes=80,
        confidence=Confidence.MEDIUM,
        provenance=provenance(),
    ),
    lambda: PolicyRef(
        policy_id=Name("capacity.headroom"), version=1, effective_at=INSTANT
    ),
    subject,
    lambda: AccessContext(subject=subject(), team_ids=(TeamId.generate(),)),
    lambda: Entitlement(
        claim=Name("hosts"), entitlement_kind=EntitlementKind.CAPACITY, limit=4
    ),
    lambda: AuditEvent(
        audit_id=AuditId.generate(),
        occurred_at=INSTANT,
        actor_id=SubjectId.generate(),
        action=Name("model.install"),
        target_kind=Name("model"),
        target_id=str(MODEL),
        decision=AuditDecision.ALLOWED,
        outcome=AuditOutcome.SUCCEEDED,
    ),
    host_capabilities,
    storage_pool,
    lambda: CapacityEvidence(
        evidence_type=EvidenceType.THEORETICAL,
        model_ref=str(MODEL),
        host_fingerprint="abc123",
        confidence=Confidence.LOW,
        provenance=provenance(),
        runtime=Name("vllm"),
        runtime_version=NOT_PROVIDED,
        weights_bytes=16_000_000_000,
        kv_cache_bytes_per_token=NOT_MEASURED,
        activation_bytes=NOT_MEASURED,
        runtime_overhead_bytes=NOT_MEASURED,
        total_memory_bytes=NOT_MEASURED,
        host_memory_bytes=NOT_MEASURED,
        max_context_tokens=NOT_MEASURED,
    ),
    lambda: ModelMetadata(
        model_id=MODEL,
        logical_name=Name("qwen3-8b-awq"),
        source=Name("huggingface"),
        source_ref="Qwen/Qwen3-8B-AWQ",
        source_revision="a1b2c3",
        family=NOT_PROVIDED,
        parameter_count=8_000_000_000,
        context_length_tokens=NOT_PROVIDED,
        quantization="awq",
        license_id=NOT_PROVIDED,
        commercial_use_restricted=NOT_PROVIDED,
    ),
    lambda: ModelArtifact(
        artifact_id=ArtifactId.generate(), model_id=MODEL, revision="a1b2c3"
    ),
    lambda: ModelRequirement(
        model_id=MODEL,
        confidence=Confidence.LOW,
        storage_bytes=6_000_000_000,
        peak_additional_bytes=12_000_000_000,
        vram_weights_bytes=NOT_MEASURED,
        vram_kv_bytes_per_token=NOT_MEASURED,
        vram_overhead_bytes=NOT_MEASURED,
        ram_bytes=NOT_MEASURED,
    ),
    lambda: ModelInventoryRecord(
        model_id=MODEL, host_id=HOST, state=InventoryState.STORED
    ),
    lambda: Workload(
        workload_id=WorkloadId.generate(),
        host_id=HOST,
        workload_type=WorkloadType.INFERENCE,
        created_at=INSTANT,
        model_id=MODEL,
    ),
    lambda: WorkloadProfile(
        average_input_tokens=512,
        average_output_tokens=256,
        maximum_input_tokens=NOT_MEASURED,
        maximum_output_tokens=NOT_MEASURED,
        requests_per_second=NOT_MEASURED,
        expected_concurrency=NOT_MEASURED,
        streaming=True,
        target_ttft_seconds=NOT_MEASURED,
    ),
    lambda: ResourceReservation(
        reservation_id=ReservationId.generate(),
        workload_id=WorkloadId.generate(),
        host_id=HOST,
        state=ReservationState.ADMITTED,
        created_at=INSTANT,
        admitted_vram_bytes=20_000_000_000,
        admitted_ram_bytes=8_000_000_000,
        admitted_storage_bytes=NOT_MEASURED,
        accelerator_index=0,
    ),
    lambda: InferenceEndpoint(scheme="http", address="127.0.0.1", port=8000),
    lambda: InferenceInstance(
        instance_id=InstanceId.generate(),
        host_id=HOST,
        model_id=MODEL,
        runtime=Name("vllm"),
        executor=Name("native-process"),
        lifecycle_state=LifecycleState.RUNNING,
        health=HealthState.HEALTHY,
        configuration_version=1,
        model_revision="a1b2c3",
        reachable=True,
        endpoint=InferenceEndpoint(scheme="http", address="127.0.0.1", port=8000),
    ),
    lambda: UsageEvent(
        usage_id=UsageId.generate(),
        occurred_at=INSTANT,
        logical_name=Name("local-llm"),
        provider=Name("vllm"),
        service_id=Name("inference"),
        route_reason=Name("default-model"),
    ),
    lambda: DatasetSnapshot(
        snapshot_id=DatasetSnapshotId.generate(),
        created_at=INSTANT,
        training_authorized=True,
    ),
    lambda: DerivedModel(
        derived_id=DerivedModelId.generate(),
        parent_model_id=MODEL,
        derivation_type=DerivationType.LORA,
        promotion_state=PromotionState.DRAFT,
        created_at=INSTANT,
    ),
]


@pytest.mark.parametrize("build", EVERY_CONTRACT)
def test_every_contract_survives_the_wire(build: Callable[[], Contract]) -> None:
    record = build()
    assert from_dict(to_dict(record)) == record


def test_the_whole_registry_is_well_formed() -> None:
    validate_registry(module_prefix="kultrun.")


def test_knowledge_contracts_round_trip() -> None:
    source = KnowledgeSource(
        source_id=KnowledgeSourceId.generate(),
        display_name="Finance share",
        connector=Name("smb"),
        indexing_state=IndexingState.INDEXED,
        capabilities=(Name("per-item-permissions"),),
    )
    item = KnowledgeItem(
        item_id=KnowledgeItemId.generate(),
        source_id=source.source_id,
        external_id="\\\\share\\finance\\q3.xlsx",
        indexing_state=IndexingState.INDEXED,
        modified_at=INSTANT,
    )
    assert from_dict(to_dict(source)) == source
    assert from_dict(to_dict(item)) == item


class TestDistinctionsThatMustSurvive:
    """Each of these is a conflation the previous attempt made or was warned about."""

    def test_a_usage_event_keeps_five_identities_apart(self) -> None:
        event = UsageEvent(
            usage_id=UsageId.generate(),
            occurred_at=INSTANT,
            logical_name=Name("local-llm"),
            provider=Name("vllm"),
            service_id=Name("inference"),
            route_reason=Name("fallback"),
            requested_model=Name("qwen3-32b"),
            actual_model=Name("qwen3-8b-awq"),
        )
        document = to_dict(event)
        assert document["logical_name"] != document["actual_model"]
        assert document["requested_model"] != document["actual_model"]
        assert {
            "logical_name",
            "provider",
            "service_id",
            "route_reason",
            "requested_model",
            "actual_model",
        } <= set(document)

    def test_only_the_safe_layer_authorizes(self) -> None:
        layered = LayeredBytes(
            reported_bytes=256_060_514_304,
            effective_bytes=240_000_000_000,
            safe_bytes=200_000_000_000,
            confidence=Confidence.MEDIUM,
            provenance=provenance(),
        )
        assert layered.authorizing_bytes == layered.safe_bytes
        assert layered.authorizing_bytes != layered.reported_bytes

    def test_an_unknown_safe_layer_authorizes_nothing(self) -> None:
        """Unknown capacity must be unusable, not read as unlimited or zero."""
        layered = LayeredBytes(
            reported_bytes=256_060_514_304,
            effective_bytes=NOT_MEASURED,
            safe_bytes=NOT_MEASURED,
            confidence=Confidence.UNKNOWN,
            provenance=provenance(),
        )
        assert not is_resolved(layered.authorizing_bytes)

    def test_audit_separates_permission_from_outcome(self) -> None:
        """A permitted action can still fail; one field cannot say both."""
        event = AuditEvent(
            audit_id=AuditId.generate(),
            occurred_at=INSTANT,
            actor_id=SubjectId.generate(),
            action=Name("model.install"),
            target_kind=Name("model"),
            target_id=str(MODEL),
            decision=AuditDecision.ALLOWED,
            outcome=AuditOutcome.CANCELLED,
            reason="operator cancelled during transfer",
        )
        assert event.decision is AuditDecision.ALLOWED
        assert event.outcome is not AuditOutcome.SUCCEEDED

    def test_a_reservation_records_what_was_admitted_not_what_was_asked(self) -> None:
        reservation = ResourceReservation(
            reservation_id=ReservationId.generate(),
            workload_id=WorkloadId.generate(),
            host_id=HOST,
            state=ReservationState.ADMITTED,
            created_at=INSTANT,
            admitted_vram_bytes=20_000_000_000,
            admitted_ram_bytes=NOT_MEASURED,
            admitted_storage_bytes=NOT_MEASURED,
            accelerator_index=0,
        )
        names = set(to_dict(reservation))
        assert "admitted_vram_bytes" in names
        assert not any(name.startswith("requested_") for name in names)
        assert not any(name.startswith("observed_") for name in names)

    def test_an_instance_separates_reachability_from_health(self) -> None:
        """A bound port that cannot serve is reachable and unhealthy."""
        instance = InferenceInstance(
            instance_id=InstanceId.generate(),
            host_id=HOST,
            model_id=MODEL,
            runtime=Name("vllm"),
            executor=Name("native-process"),
            lifecycle_state=LifecycleState.DEGRADED,
            health=HealthState.UNHEALTHY,
            configuration_version=1,
            reachable=True,
        )
        assert instance.reachable is True
        assert instance.health is HealthState.UNHEALTHY

    def test_a_requirement_names_no_host(self) -> None:
        """What a model needs is a property of the model, not of a machine."""
        names = set(
            to_dict(
                ModelRequirement(
                    model_id=MODEL,
                    confidence=Confidence.LOW,
                    storage_bytes=NOT_MEASURED,
                    peak_additional_bytes=NOT_MEASURED,
                    vram_weights_bytes=NOT_MEASURED,
                    vram_kv_bytes_per_token=NOT_MEASURED,
                    vram_overhead_bytes=NOT_MEASURED,
                    ram_bytes=NOT_MEASURED,
                )
            )
        )
        assert "host_id" not in names
        assert "host_fingerprint" not in names

    def test_peak_additional_storage_is_separate_from_installed_size(self) -> None:
        """Admission is against the peak, not the result."""
        requirement = ModelRequirement(
            model_id=MODEL,
            confidence=Confidence.LOW,
            storage_bytes=6_000_000_000,
            peak_additional_bytes=13_000_000_000,
            vram_weights_bytes=NOT_MEASURED,
            vram_kv_bytes_per_token=NOT_MEASURED,
            vram_overhead_bytes=NOT_MEASURED,
            ram_bytes=NOT_MEASURED,
        )
        assert requirement.peak_additional_bytes != requirement.storage_bytes

    def test_training_authorization_is_not_inferred_from_access(self) -> None:
        """Permission to retrieve is not permission to train."""
        snapshot = DatasetSnapshot(
            snapshot_id=DatasetSnapshotId.generate(),
            created_at=INSTANT,
            training_authorized=False,
        )
        assert snapshot.training_authorized is False
        assert "training_authorized" in to_dict(snapshot)

    def test_accelerators_and_mounts_are_plural_on_a_single_device_host(self) -> None:
        """Milestone 14 is an extension only if this is already true."""
        capabilities = host_capabilities()
        assert isinstance(capabilities.accelerators, tuple)
        assert isinstance(capabilities.mounts, tuple)
        assert len(capabilities.accelerators) == 1


class TestUnknownIsRepresentable:
    def test_absent_upstream_metadata_is_unresolved_not_zero(self) -> None:
        """The previous attempt's catalogue carried nulls for exactly these."""
        metadata = ModelMetadata(
            model_id=MODEL,
            logical_name=Name("qwen3-8b-awq"),
            source=Name("huggingface"),
            source_ref="Qwen/Qwen3-8B-AWQ",
            source_revision=NOT_PROVIDED,
            family=NOT_PROVIDED,
            parameter_count=NOT_PROVIDED,
            context_length_tokens=NOT_PROVIDED,
            quantization=NOT_PROVIDED,
            license_id=NOT_PROVIDED,
            commercial_use_restricted=NOT_PROVIDED,
        )
        assert "context_length_tokens" in unresolved_fields(metadata)
        assert "download_bytes" not in unresolved_fields(metadata)

    def test_an_inventory_record_tolerates_unknown_managed_storage(self) -> None:
        """This exact shape crashed capacity observation in the previous attempt."""
        record = ModelInventoryRecord(
            model_id=MODEL, host_id=HOST, state=InventoryState.STORED
        )
        assert isinstance(record.managed_bytes, Unresolved)
        assert from_dict(to_dict(record)) == record

    def test_unresolved_fields_reports_nested_paths(self) -> None:
        capabilities = host_capabilities()
        reported = unresolved_fields(capabilities)
        assert "cpu.model_name" in reported
        assert "memory.available_bytes" in reported
        assert "mounts[0].device" in reported


def test_the_registry_and_the_committed_fingerprint_agree() -> None:
    """Every registered contract is in the committed record, and vice versa.

    A magic number would drift; tying the two mechanisms together means an
    accidental registration shows up as a fingerprint diff, which is the
    review surface that already exists.
    """
    registered = {
        f"{kind}@{version}"
        for (kind, version), cls in registered_contracts().items()
        if cls.__module__.startswith("kultrun.")
    }
    committed = set(
        json.loads(
            (Path(__file__).resolve().parent / "golden" / "schema_fingerprint.json")
            .read_text(encoding="utf-8")
        )
    )
    assert registered == committed

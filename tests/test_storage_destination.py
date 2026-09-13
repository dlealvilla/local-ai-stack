"""Consume paths must name a StoragePool. Unique-SAFE is diagnostic only."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.capacity.contracts import (
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.acquisition import safe_storage
from kultrun.model.contracts import AcquisitionFailureReason
from kultrun.model.inventory import ModelInventory
from kultrun.model.store import ModelArtifactStore
from kultrun.planning.evaluate import deployment_capacity
from kultrun.platform.capacity_snapshot import bind_current_capacity
from kultrun.platform.managed_usage import PlatformManagedUsage
from kultrun.resource.contracts import (
    LedgerHealth,
    PoolResourceSummary,
    ResourceSummary,
)
from kultrun.runtime.contracts import InstallationStatus, RuntimePolicy
from kultrun.storage.topology import mount_for_path
from tests.test_capacity import GIB, INSTANT, mount
from tests.test_contracts import host_capabilities
from tests.test_model_acquisition import _request
from tests.test_model_acquisition import _service as acquire_service
from tests.test_runtime_provisioning import _candidate, _service
from tests.test_runtime_resolution import _native
from tests.test_storage_recompute import _layered


def _two_safe() -> CapacityEnvelope:
    return CapacityEnvelope(
        host_id=HostId.generate(),
        host_fingerprint="test",
        computed_at=INSTANT,
        policy_version="t",
        memory=_layered(48 * GIB),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        pools=(
            PoolCapacity(
                mount_point="/",
                space=_layered(24 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
            ),
            PoolCapacity(
                mount_point="/workspace",
                space=_layered(27 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
            ),
        ),
    )


def _workspace_host(tmp_path: Path) -> tuple[Path, HostCapabilities]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    base = host_capabilities()
    subject = replace(
        base,
        mounts=(
            *base.mounts,
            mount(str(workspace), "fuse.moosefs", free=80 * GIB, total=180 * GIB),
        ),
    )
    return workspace, subject


def test_two_resolved_pools_unnamed_safe_storage_is_unresolved() -> None:
    envelope = _two_safe()
    mount_point, safe = safe_storage(envelope, None)
    assert mount_point is None
    assert not is_resolved(safe)
    named, value = safe_storage(envelope, "/workspace")
    assert named == "/workspace"
    assert value == 27 * GIB


def test_deployment_capacity_two_resolved_pools_requires_named_mount() -> None:
    envelope = _two_safe()
    unnamed = deployment_capacity(envelope)
    assert not is_resolved(unnamed.safe_storage_bytes)
    named = deployment_capacity(envelope, storage_mount="/workspace")
    assert named.safe_storage_bytes == 27 * GIB


def test_available_models_capacity_uses_named_pool_when_two_are_safe() -> None:
    envelope = _two_safe()
    snapshot = ResourceSummary(
        host_id=envelope.host_id,
        host_fingerprint=envelope.host_fingerprint,
        health=LedgerHealth.WITHIN_CAPACITY,
        policy_version="t",
        capacity_policy_version="t",
        safe_ram_bytes=envelope.memory.safe_bytes,
        reserved_ram_bytes=0,
        available_ram_bytes=envelope.memory.safe_bytes,
        pools=(
            PoolResourceSummary(
                mount_point="/",
                reserved_bytes=0,
                safe_bytes=24 * GIB,
                available_bytes=24 * GIB,
            ),
            PoolResourceSummary(
                mount_point="/workspace",
                reserved_bytes=0,
                safe_bytes=27 * GIB,
                available_bytes=27 * GIB,
            ),
        ),
    )
    unnamed = bind_current_capacity(envelope, snapshot)
    assert not is_resolved(unnamed.safe_storage_bytes)
    named = bind_current_capacity(
        envelope, snapshot, storage_mount="/workspace"
    )
    assert named.safe_storage_bytes == 27 * GIB
    assert named.available_storage_bytes == 27 * GIB


def test_named_acquire_succeeds_when_two_pools_are_safe(tmp_path: Path) -> None:
    service, inventory, _, host_id = acquire_service(tmp_path)
    envelope = _two_safe()
    request = _request(expected_peak_bytes=1000, expected_storage_bytes=1000)
    with pytest.raises(PreconditionFailedError) as error:
        service.acquire(request, envelope, host_id)
    assert error.value.context["reason"] == (
        AcquisitionFailureReason.UNRESOLVED_STORAGE_REQUIREMENT.value
    )
    receipt = service.acquire(
        request, envelope, host_id, destination_mount="/workspace"
    )
    assert receipt.outcome == "stored"
    artifact = inventory.get(receipt.artifact_id)
    assert artifact is not None
    assert artifact.storage_mount == "/workspace"


def test_create_plan_records_state_root_destination(tmp_path: Path) -> None:
    workspace, subject = _workspace_host(tmp_path)
    native = _native(subject)
    service = _service(workspace / "state")
    candidate, _ = _candidate(subject, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        subject,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    assert plan.storage_mount == str(workspace)


def test_backfill_fills_unresolved_plan_destination(tmp_path: Path) -> None:
    workspace, subject = _workspace_host(tmp_path)
    native = _native(subject)
    service = _service(workspace / "state")
    candidate, _ = _candidate(subject, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        subject,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    stripped = replace(plan, storage_mount=NOT_PROVIDED)
    service._store.put(stripped.plan_id.value, stripped)
    filled = service.create_plan(
        candidate.candidate_id.value,
        subject,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    assert filled.plan_id == plan.plan_id
    assert filled.storage_mount == str(workspace)


def test_runtime_install_bytes_reduce_named_pool_remaining(tmp_path: Path) -> None:
    workspace, subject = _workspace_host(tmp_path)
    native = _native(subject)
    state = workspace / "state"
    service = _service(state)
    candidate, _ = _candidate(subject, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        subject,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    installed = service.provision(
        plan.plan_id,
        subject,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    assert installed.status is InstallationStatus.INSTALLED
    counted = replace(installed, installed_bytes=7 * GIB)
    service._store.put(counted.installation_id.value, counted)
    inventory = ModelInventory(service._store, ModelArtifactStore(state))
    usage = PlatformManagedUsage(service._store, inventory, state)
    found = usage.bytes_by_mount(subject.host_id)
    assert found[str(workspace)] == 7 * GIB
    assert found.get("/") != 7 * GIB


def test_model_destination_follows_state_root_not_unique_safe(tmp_path: Path) -> None:
    workspace, subject = _workspace_host(tmp_path)
    state = workspace / "kultrun"
    assert mount_for_path(state / "models", subject) == str(workspace)
    assert mount_for_path(state / "runtimes", subject) == str(workspace)

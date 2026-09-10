"""Capacity-first ordering: storage excludes a runtime before realize."""

from __future__ import annotations

from pathlib import Path

import pytest

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.provisioning.fixture import FixtureRuntimeProvisioner
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.adapters.verification.fixture import (
    FixtureProbeRunner,
    FixtureRuntimeVerifier,
)
from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.runtime.contracts import RuntimePolicy
from kultrun.runtime.lock import ProvisioningLock, SelectionLock, VerificationLock
from kultrun.runtime.provision import ProvisioningService
from kultrun.runtime.selection import FoundationSelectionService
from kultrun.runtime.verify import VerificationService
from kultrun.storage.contracts import StorageCapacityEvidence, StorageEvidenceStatus
from kultrun.storage.limits import POLICY_VERSION
from tests.test_contracts import host_capabilities
from tests.test_runtime_resolution import _native

GIB = 1024**3


def _services(
    tmp_path: Path,
) -> tuple[FoundationSelectionService, FixtureRuntimeProvisioner]:
    records = FileStore(tmp_path / "records")
    clock = FixedClock(now_utc())
    state = tmp_path / "state"
    provisioner = FixtureRuntimeProvisioner()
    provisioning = ProvisioningService(
        records,
        clock,
        provisioner,
        state,
        ProvisioningLock(state),
    )
    verification = VerificationService(
        records,
        clock,
        FixtureRuntimeVerifier(),
        FixtureProbeRunner(),
        state,
        VerificationLock(state),
    )
    foundation = FoundationSelectionService(
        records,
        clock,
        provisioning,
        verification,
        SelectionLock(state),
    )
    return foundation, provisioner


def _evidence(host_id: HostId, available: Maybe[int]) -> StorageCapacityEvidence:
    status = (
        StorageEvidenceStatus.UNRESOLVED
        if not is_resolved(available)
        else StorageEvidenceStatus.PROBED
    )
    return StorageCapacityEvidence(
        host_id=host_id,
        mount_point="/",
        quota_identity=NOT_PROVIDED,
        pool_fingerprint="test",
        observed_at=now_utc(),
        status=status,
        confidence=Confidence.MEDIUM,
        provenance=Provenance(
            producer=Name("test"),
            producer_version=NOT_PROVIDED,
            observed_at=now_utc(),
            policy_version=POLICY_VERSION,
        ),
        operational_available_bytes=available,
        authorizing_available_bytes=available,
        selected_reason="test",
    )


def test_insufficient_storage_excludes_runtime_before_realize(
    tmp_path: Path,
) -> None:
    foundation, _provisioner = _services(tmp_path)
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(),)
    evidence = {"/": _evidence(host.host_id, 1 * GIB)}
    overview = foundation.view(
        host,
        (native,),
        descriptors,
        RuntimePolicy(),
        components={"vllm": "missing"},
        storage_evidence=evidence,
        require_storage=True,
    )
    assert overview.provisionable_ids == ()
    with pytest.raises(PreconditionFailedError):
        foundation.realize_selected(
            host,
            (native,),
            descriptors,
            components={"vllm": "missing"},
            storage_evidence=evidence,
            require_storage=True,
        )


def test_sufficient_storage_allows_selection(tmp_path: Path) -> None:
    foundation, _provisioner = _services(tmp_path)
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(),)
    evidence = {"/": _evidence(host.host_id, 80 * GIB)}
    overview = foundation.select_auto(
        host,
        (native,),
        descriptors,
        components={"vllm": "missing"},
        storage_evidence=evidence,
        require_storage=True,
    )
    assert isinstance(overview.selection.selected_candidate_id, str)
    assert overview.provisionable_ids


def test_realize_never_calls_installer_when_storage_infeasible(
    tmp_path: Path,
) -> None:
    from kultrun.adapters.persistence.file_store import FileStore
    from kultrun.capacity.envelope import CapacityService
    from kultrun.platform.foundation_realize import FoundationRealizeService
    from kultrun.resource.lock import AdmissionLock
    from kultrun.resource.manager import ResourceManager
    from kultrun.storage.characterize import StorageCharacterizationService
    from kultrun.storage.index import StorageEvidenceIndex
    from kultrun.storage.probes import ProbeRegistry

    foundation, provisioner = _services(tmp_path)
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(),)
    evidence = {"/": _evidence(host.host_id, 1 * GIB)}
    records = FileStore(tmp_path / "rm")
    clock = FixedClock(now_utc())
    service = FoundationRealizeService(
        foundation,
        StorageCharacterizationService(clock, ProbeRegistry(())),
        ResourceManager(records, clock, AdmissionLock(tmp_path / "lock")),
        CapacityService(clock=clock),
        tmp_path / "state",
        StorageEvidenceIndex(records),
        allow_empirical=False,
    )
    with pytest.raises(PreconditionFailedError):
        service.realize(
            host,
            (native,),
            descriptors,
            components={"vllm": "missing"},
            storage_evidence=evidence,
        )
    assert provisioner.install_calls == 0


def test_sufficient_storage_admits_then_installs(tmp_path: Path) -> None:
    from kultrun.adapters.persistence.file_store import FileStore
    from kultrun.capacity.envelope import CapacityService
    from kultrun.platform.foundation_realize import FoundationRealizeService
    from kultrun.resource.lock import AdmissionLock
    from kultrun.resource.manager import ResourceManager
    from kultrun.storage.characterize import StorageCharacterizationService
    from kultrun.storage.index import StorageEvidenceIndex
    from kultrun.storage.probes import ProbeRegistry

    foundation, provisioner = _services(tmp_path)
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(),)
    evidence = {"/": _evidence(host.host_id, 80 * GIB)}
    records = FileStore(tmp_path / "rm")
    clock = FixedClock(now_utc())
    service = FoundationRealizeService(
        foundation,
        StorageCharacterizationService(clock, ProbeRegistry(())),
        ResourceManager(records, clock, AdmissionLock(tmp_path / "lock")),
        CapacityService(clock=clock),
        tmp_path / "state",
        StorageEvidenceIndex(records),
        allow_empirical=False,
    )
    foundation.select_auto(
        host,
        (native,),
        descriptors,
        components={"vllm": "missing"},
        storage_evidence=evidence,
        require_storage=True,
    )
    installation = service.realize(
        host,
        (native,),
        descriptors,
        components={"vllm": "missing"},
        storage_evidence=evidence,
    )
    assert provisioner.install_calls == 1
    assert installation.status.value in {"installed", "failed"}

"""Minimum feasibility, reclaimable occupancy, and occupancy-conditional Sonar."""

from __future__ import annotations

from pathlib import Path

import pytest

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.runtime.llama_cpp import LlamaCppRuntimeSupport
from kultrun.adapters.runtime.mlx import MlxRuntimeSupport
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.capacity.contracts import EvidenceRequirement, PoolCapacity
from kultrun.capacity.envelope import storage_safe_bytes
from kultrun.capacity.policy import default_policy
from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.platform.contracts import (
    HostPossibility,
    MinimumFeasibilityVerdict,
    OperationalOutcome,
    OperationalStage,
)
from kultrun.platform.minimum import (
    assess_minimum,
    destination_pool,
    foundation_possibilities,
)
from kultrun.platform.observation import OperationalJournal
from kultrun.platform.report import compose_deployment_report, format_deployment_report
from kultrun.platform.runs import DeploymentRunStore
from kultrun.storage.contracts import (
    EmpiricalProbeEvidence,
    ManagedOccupancyClass,
    ManagedOccupancyItem,
    ManagedResourceType,
    OwnershipId,
)
from kultrun.storage.inventory import (
    classify_occupancy,
    totals_by_pool,
    unique_occupancy,
)
from kultrun.storage.limits import POLICY_VERSION
from kultrun.storage.ownership import OwnershipService
from kultrun.storage.recharacterize import should_recharacterize
from kultrun.storage.reclaim import execute_reclaim, plan_reclaim
from kultrun.storage.topology import pools_from_host
from kultrun.vendor.sanitize import sanitize_fact
from tests.test_capacity import GIB, INSTANT, accelerator, host, mount
from tests.test_capacity_first_storage import _evidence
from tests.test_deployment_report import _base_envelope, _layered

CLOCK = FixedClock(INSTANT)


def _linux_nvidia(*mounts):
    return host(
        memory_total=64 * GIB,
        accelerators=(accelerator(memory=32 * GIB),),
        mounts=mounts,
    )


def _descriptors():
    return (
        VllmRuntimeSupport().support(),
        LlamaCppRuntimeSupport().support(),
        MlxRuntimeSupport().support(),
    )


def _item(
    *,
    occupancy: ManagedOccupancyClass,
    occupied: int,
    mount_point: str,
    quota: object,
    fingerprint: object,
    resource: ManagedResourceType = ManagedResourceType.MODEL_ARTIFACT,
    root: str = "/workspace/prior/state/models",
) -> ManagedOccupancyItem:
    return ManagedOccupancyItem(
        ownership_id=OwnershipId.generate(),
        resource_type=resource,
        occupancy_class=occupancy,
        managed_root=root,
        occupied_bytes=occupied,
        mount_point=mount_point,
        quota_identity=quota,
        pool_fingerprint=fingerprint,
        reason="test",
    )


def _capacity(host_id: HostId, mount_point: str, available: int, hard=NOT_PROVIDED):
    evidence = _evidence(host_id, available)
    from dataclasses import replace

    return replace(
        evidence,
        mount_point=mount_point,
        hard_maximum_bytes=hard,
        pool_fingerprint="fp-dest",
        quota_identity="quota-dest",
    )


def test_same_domain_reclaimable_adds_to_potential_gross() -> None:
    subject = _linux_nvidia(
        mount(point="/workspace", filesystem="ext4", free=25 * GIB),
    )
    dest = destination_pool(Path("/workspace/app/state"), pools_from_host(subject))
    assert dest is not None
    items = (
        _item(
            occupancy=ManagedOccupancyClass.RECLAIMABLE,
            occupied=25 * GIB,
            mount_point=dest.mount_point,
            quota=dest.quota_identity,
            fingerprint=dest.fingerprint,
        ),
    )
    assessment = assess_minimum(
        subject,
        destination=dest,
        evidence=_capacity(subject.host_id, dest.mount_point, 25 * GIB),
        items=items,
        descriptors=_descriptors(),
        ram_safe_bytes=32 * GIB,
    )
    assert assessment.verdict is MinimumFeasibilityVerdict.PASS
    assert assessment.current_authorizing_bytes == 25 * GIB
    assert assessment.reclaimable_bytes == 25 * GIB
    assert assessment.potential_authorizing_bytes == 50 * GIB
    assert assessment.potential_safe_bytes == storage_safe_bytes(
        50 * GIB, default_policy()
    )
    assert assessment.requires_reclamation is True


def test_reclaimable_on_different_pool_is_not_added() -> None:
    subject = _linux_nvidia(
        mount(point="/", filesystem="overlay", free=25 * GIB),
        mount(point="/workspace", filesystem="ext4", free=25 * GIB),
    )
    dest = destination_pool(Path("/workspace/app/state"), pools_from_host(subject))
    assert dest is not None
    other = next(pool for pool in pools_from_host(subject) if pool.mount_point == "/")
    items = (
        _item(
            occupancy=ManagedOccupancyClass.RECLAIMABLE,
            occupied=25 * GIB,
            mount_point=other.mount_point,
            quota=other.quota_identity,
            fingerprint=other.fingerprint,
            root="/old-root/state/models",
        ),
    )
    assessment = assess_minimum(
        subject,
        destination=dest,
        evidence=_capacity(subject.host_id, dest.mount_point, 25 * GIB),
        items=items,
        descriptors=_descriptors(),
        ram_safe_bytes=32 * GIB,
    )
    assert assessment.reclaimable_bytes == 0
    assert assessment.potential_authorizing_bytes == 25 * GIB


def test_hard_quota_caps_free_plus_reclaimable() -> None:
    subject = _linux_nvidia(
        mount(point="/workspace", filesystem="ext4", free=25 * GIB),
    )
    dest = destination_pool(Path("/workspace/app/state"), pools_from_host(subject))
    assert dest is not None
    items = (
        _item(
            occupancy=ManagedOccupancyClass.RECLAIMABLE,
            occupied=25 * GIB,
            mount_point=dest.mount_point,
            quota=dest.quota_identity,
            fingerprint=dest.fingerprint,
        ),
    )
    assessment = assess_minimum(
        subject,
        destination=dest,
        evidence=_capacity(subject.host_id, dest.mount_point, 25 * GIB, hard=30 * GIB),
        items=items,
        descriptors=_descriptors(),
        ram_safe_bytes=32 * GIB,
    )
    assert assessment.potential_authorizing_bytes == 30 * GIB
    assert assessment.hard_maximum_bytes == 30 * GIB


def test_reusable_reduces_requirement_and_is_not_capacity() -> None:
    subject = _linux_nvidia(
        mount(point="/workspace", filesystem="ext4", free=25 * GIB),
    )
    dest = destination_pool(Path("/workspace/app/state"), pools_from_host(subject))
    assert dest is not None
    items = (
        _item(
            occupancy=ManagedOccupancyClass.REUSABLE,
            occupied=10 * GIB,
            mount_point=dest.mount_point,
            quota=dest.quota_identity,
            fingerprint=dest.fingerprint,
            resource=ManagedResourceType.RUNTIME_FINAL,
            root="/workspace/app/state/runtimes",
        ),
        _item(
            occupancy=ManagedOccupancyClass.RECLAIMABLE,
            occupied=15 * GIB,
            mount_point=dest.mount_point,
            quota=dest.quota_identity,
            fingerprint=dest.fingerprint,
            root="/workspace/prior/state/models",
        ),
    )
    assessment = assess_minimum(
        subject,
        destination=dest,
        evidence=_capacity(subject.host_id, dest.mount_point, 25 * GIB),
        items=items,
        descriptors=_descriptors(),
        ram_safe_bytes=32 * GIB,
    )
    assert assessment.reusable_bytes == 10 * GIB
    assert assessment.reclaimable_bytes == 15 * GIB
    assert assessment.potential_authorizing_bytes == 40 * GIB
    assert assessment.net_new_bytes == max(0, assessment.required_peak_bytes - 10 * GIB)
    assert assessment.reusable_bytes != assessment.reclaimable_bytes


def test_active_and_protected_are_not_reclaimable(tmp_path: Path) -> None:
    current = tmp_path / "current" / "state"
    prior = tmp_path / "prior" / "state" / "models"
    live = tmp_path / "prior" / "state" / "runtimes"
    protected = tmp_path / "prior" / "state" / "rollback"
    unlabeled = tmp_path / "customer-files"
    current.mkdir(parents=True)
    prior.mkdir(parents=True)
    live.mkdir(parents=True)
    protected.mkdir(parents=True)
    unlabeled.mkdir()
    (prior / "weights.bin").write_bytes(b"x" * 64)
    (live / "venv").mkdir()
    (protected / "keep").write_bytes(b"y" * 32)
    (unlabeled / "notes.txt").write_text("not kultrun")
    subject = _linux_nvidia(mount(point="/", filesystem="ext4", free=80 * GIB))
    pools = pools_from_host(subject)
    service = OwnershipService(FileStore(tmp_path / "records"), CLOCK, current)
    reclaimable = service.assert_owned(
        prior,
        subject.host_id,
        ManagedResourceType.MODEL_ARTIFACT,
        protected=True,
        allowed_roots=(tmp_path,),
    )
    active = service.assert_owned(
        live,
        subject.host_id,
        ManagedResourceType.RUNTIME_FINAL,
        protected=True,
        allowed_roots=(tmp_path,),
    )
    held = service.assert_owned(
        protected,
        subject.host_id,
        ManagedResourceType.RUNTIME_FINAL,
        rollback_protected=True,
        allowed_roots=(tmp_path,),
    )
    items = classify_occupancy(
        (reclaimable, active, held),
        pools,
        current_state_root=current,
        live_roots=(live,),
        reusable_roots=(),
    )
    by_root = {item.managed_root: item.occupancy_class for item in items}
    assert by_root[str(prior.resolve())] is ManagedOccupancyClass.RECLAIMABLE
    assert by_root[str(live.resolve())] is ManagedOccupancyClass.ACTIVE
    assert by_root[str(protected.resolve())] is ManagedOccupancyClass.PROTECTED
    assert str(unlabeled.resolve()) not in by_root


def test_classify_never_marks_the_same_root_reusable_and_reclaimable(
    tmp_path: Path,
) -> None:
    current = tmp_path / "state"
    runtime = current / "runtimes"
    runtime.mkdir(parents=True)
    subject = _linux_nvidia(mount(point="/", filesystem="ext4", free=80 * GIB))
    service = OwnershipService(FileStore(tmp_path / "records"), CLOCK, current)
    record = service.assert_owned(
        runtime,
        subject.host_id,
        ManagedResourceType.RUNTIME_FINAL,
        protected=True,
    )
    items = classify_occupancy(
        (record,),
        pools_from_host(subject),
        current_state_root=current,
        live_roots=(),
        reusable_roots=(runtime,),
    )
    assert len(items) == 1
    assert items[0].occupancy_class is ManagedOccupancyClass.REUSABLE


def test_reclaim_expected_versus_actual(tmp_path: Path) -> None:
    current = tmp_path / "current" / "state"
    prior = tmp_path / "prior" / "state" / "models"
    current.mkdir(parents=True)
    service = OwnershipService(FileStore(tmp_path / "records"), CLOCK, current)
    record = service.assert_owned(
        prior,
        subject_host := HostId.generate(),
        ManagedResourceType.MODEL_ARTIFACT,
        protected=True,
        allowed_roots=(tmp_path,),
    )
    (prior / "blob").write_bytes(b"a" * 2048)
    subject = _linux_nvidia(mount(point="/", filesystem="ext4", free=80 * GIB))
    items = classify_occupancy(
        (record,),
        pools_from_host(subject),
        current_state_root=current,
    )
    dest = destination_pool(current, pools_from_host(subject))
    assert dest is not None
    plan = plan_reclaim(items, mount_point=dest.mount_point)
    (prior / "blob").write_bytes(b"b" * 100)
    result = execute_reclaim(
        plan, (record,), service, allowed_roots=(tmp_path / "prior" / "state",)
    )
    assert result.expected_bytes != result.actual_bytes
    assert result.actual_bytes > 0
    assert not prior.exists()
    del subject_host


def test_should_recharacterize_only_when_occupancy_dropped() -> None:
    host_id = HostId.generate()
    empirical = EmpiricalProbeEvidence(
        host_id=host_id,
        mount_point="/workspace",
        target_path="/workspace",
        max_probe_bytes=32 * GIB,
        bytes_physically_written=0,
        search_granularity_bytes=1,
        probe_ceiling_reached=False,
        confidence=Confidence.MEDIUM,
        provenance=Provenance(
            producer=Name("test"),
            producer_version=NOT_PROVIDED,
            observed_at=INSTANT,
            policy_version=POLICY_VERSION,
        ),
        cleanup_success=True,
        verified_lower_bound_bytes=24 * GIB,
        observed_failure_upper_bytes=32 * GIB,
    )
    held = _capacity(host_id, "/workspace", 24 * GIB)
    from dataclasses import replace

    held = replace(held, accounted_managed_bytes=17 * GIB)
    assert (
        should_recharacterize(
            empirical,
            held,
            managed_now=0,
            reclaimable_bytes=17 * GIB,
            current_safe_blocks=True,
        )
        is True
    )
    assert (
        should_recharacterize(
            empirical,
            held,
            managed_now=17 * GIB,
            reclaimable_bytes=17 * GIB,
            current_safe_blocks=True,
        )
        is False
    )
    assert (
        should_recharacterize(
            empirical,
            held,
            managed_now=17 * GIB,
            reclaimable_bytes=0,
            current_safe_blocks=False,
        )
        is False
    )


def test_minimum_fail_and_pass_with_reclamation_condition() -> None:
    subject = _linux_nvidia(
        mount(point="/workspace", filesystem="ext4", free=8 * GIB),
    )
    dest = destination_pool(Path("/workspace/app/state"), pools_from_host(subject))
    assert dest is not None
    failed = assess_minimum(
        subject,
        destination=dest,
        evidence=_capacity(subject.host_id, dest.mount_point, 8 * GIB),
        items=(),
        descriptors=_descriptors(),
        ram_safe_bytes=32 * GIB,
    )
    assert failed.verdict is MinimumFeasibilityVerdict.FAIL
    assert failed.reason_code == "minimum_storage"
    assert failed.requires_reclamation is False
    passed = assess_minimum(
        subject,
        destination=dest,
        evidence=_capacity(subject.host_id, dest.mount_point, 80 * GIB),
        items=(),
        descriptors=_descriptors(),
        ram_safe_bytes=32 * GIB,
    )
    assert passed.verdict is MinimumFeasibilityVerdict.PASS
    assert passed.requires_reclamation is False


def test_foundation_possibilities_are_coarse() -> None:
    linux = _linux_nvidia(mount(point="/", filesystem="ext4", free=80 * GIB))
    rows = {
        item.family: item for item in foundation_possibilities(linux, _descriptors())
    }
    assert rows["vllm"].host_possibility is HostPossibility.PLAUSIBLE
    assert rows["vllm"].support_tier == "product"
    assert rows["llama.cpp"].host_possibility is HostPossibility.PLAUSIBLE
    assert rows["llama.cpp"].support_tier == "future"
    assert rows["mlx"].host_possibility is HostPossibility.NOT_PLAUSIBLE
    assert rows["mlx"].support_tier == "future"


def test_deployment_failed_renders_failed_layer() -> None:
    from kultrun.platform.contracts import OperationalFact, OperationalFactId
    from kultrun.platform.observation import attr
    from tests.test_capacity import INSTANT as WHEN

    subject = _linux_nvidia(mount(point="/workspace", filesystem="ext4", free=8 * GIB))
    envelope = _base_envelope(
        subject,
        (
            PoolCapacity(
                mount_point="/workspace",
                space=_layered(8 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="ext4",
            ),
        ),
    )
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=WHEN,
        stage=OperationalStage.FEASIBILITY,
        event_type=Name("deployment.failed"),
        outcome=OperationalOutcome.FAIL,
        summary="potential post-reclaim SAFE is below net new peak",
        reason_code="minimum_storage",
        attributes=(attr("profile", "minimum-host-v1"),),
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=WHEN,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
        candidates=(),
        recommended_candidate_id=None,
        selection=None,
        installations=(),
        provisioning_plans=(),
        profiles={},
        available=None,
        model_selection=None,
        deployment_plan=None,
        instances=(),
        executions=(),
        facts=(fact,),
    )
    assert report.verdict.value == "fail"
    text = format_deployment_report(report)
    assert "OVERALL: FAIL" in text
    assert "FAILED LAYER:" in text
    assert "Minimum Feasibility" in text


def test_realize_emits_deployment_failed_and_marks_run(tmp_path: Path) -> None:
    from kultrun.adapters.provisioning.fixture import FixtureRuntimeProvisioner
    from kultrun.adapters.verification.fixture import (
        FixtureProbeRunner,
        FixtureRuntimeVerifier,
    )
    from kultrun.capacity.envelope import CapacityService
    from kultrun.platform.foundation_realize import FoundationRealizeService
    from kultrun.resource.lock import AdmissionLock
    from kultrun.resource.manager import ResourceManager
    from kultrun.runtime.lock import ProvisioningLock, SelectionLock, VerificationLock
    from kultrun.runtime.provision import ProvisioningService
    from kultrun.runtime.selection import FoundationSelectionService
    from kultrun.runtime.verify import VerificationService
    from kultrun.storage.characterize import StorageCharacterizationService
    from kultrun.storage.index import StorageEvidenceIndex
    from kultrun.storage.probes import ProbeRegistry
    from tests.test_runtime_resolution import _native

    records = FileStore(tmp_path / "records")
    state = tmp_path / "state"
    journal = OperationalJournal(records, CLOCK)
    runs = DeploymentRunStore(records, CLOCK)
    host_caps = _linux_nvidia(mount(point="/", filesystem="ext4", free=80 * GIB))
    runs.ensure(host_caps.host_id, "test")
    provisioner = FixtureRuntimeProvisioner()
    provisioning = ProvisioningService(
        records, CLOCK, provisioner, state, ProvisioningLock(state)
    )
    verification = VerificationService(
        records,
        CLOCK,
        FixtureRuntimeVerifier(),
        FixtureProbeRunner(),
        state,
        VerificationLock(state),
    )
    foundation = FoundationSelectionService(
        records, CLOCK, provisioning, verification, SelectionLock(state)
    )
    service = FoundationRealizeService(
        foundation,
        StorageCharacterizationService(CLOCK, ProbeRegistry(())),
        ResourceManager(records, CLOCK, AdmissionLock(tmp_path / "lock")),
        CapacityService(clock=CLOCK),
        state,
        StorageEvidenceIndex(records),
        allow_empirical=False,
        journal=journal,
        runs=runs,
    )
    with pytest.raises(PreconditionFailedError):
        service.realize(
            host_caps,
            (_native(host_caps),),
            (VllmRuntimeSupport().support(),),
            storage_evidence={"/": _evidence(host_caps.host_id, 1 * GIB)},
        )
    facts = journal.facts(host_caps.host_id)
    assert any(item.event_type.value == "deployment.failed" for item in facts)
    current = runs.current()
    assert current is not None
    assert current.status.value == "failed"


def test_sanitize_keeps_bands_and_drops_paths() -> None:
    from kultrun.kernel.schema import to_dict
    from kultrun.platform.contracts import OperationalFact, OperationalFactId
    from kultrun.platform.observation import attr

    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=INSTANT,
        stage=OperationalStage.FEASIBILITY,
        event_type=Name("minimum.feasibility_completed"),
        outcome=OperationalOutcome.PASS,
        summary="MINIMUM FEASIBILITY PASS",
        attributes=(
            attr("profile", "minimum-host-v1"),
            attr("requires_reclamation", True),
            attr("byte_band", "<=48GiB"),
            attr("possibility", "plausible"),
            attr("support_tier", "product"),
            attr("mount", "/workspace/customer/models"),
            attr("ownership", "own_secret"),
        ),
    )
    record = sanitize_fact(fact)
    encoded = str(to_dict(record))
    assert record.profile == "minimum-host-v1"
    assert record.requires_reclamation == "True"
    assert record.byte_band == "<=48GiB"
    assert "customer" not in encoded
    assert "own_secret" not in encoded
    assert "mount" not in encoded


def _stub_characterization(evidence: dict):
    from kultrun.storage.characterize import Characterization
    from kultrun.storage.topology import pools_from_host

    class Stub:
        def characterize(self, host, **kwargs):
            del kwargs
            return Characterization(
                pools=pools_from_host(host),
                evidence=evidence,
                cleanup=None,
                low_space=(),
                empirical_ran=(),
                empirical_evidence={},
            )

    return Stub()


def _realize_for_reclaim(
    tmp_path: Path, host_caps, ownership, occupancy, characterization
):
    from kultrun.adapters.provisioning.fixture import FixtureRuntimeProvisioner
    from kultrun.adapters.verification.fixture import (
        FixtureProbeRunner,
        FixtureRuntimeVerifier,
    )
    from kultrun.capacity.envelope import CapacityService
    from kultrun.platform.foundation_realize import FoundationRealizeService
    from kultrun.resource.lock import AdmissionLock
    from kultrun.resource.manager import ResourceManager
    from kultrun.runtime.lock import ProvisioningLock, SelectionLock, VerificationLock
    from kultrun.runtime.provision import ProvisioningService
    from kultrun.runtime.selection import FoundationSelectionService
    from kultrun.runtime.verify import VerificationService
    from kultrun.storage.index import StorageEvidenceIndex

    records = FileStore(tmp_path / "records")
    state = tmp_path / "current" / "state"
    journal = OperationalJournal(records, CLOCK)
    runs = DeploymentRunStore(records, CLOCK)
    runs.ensure(host_caps.host_id, "test")
    provisioner = FixtureRuntimeProvisioner()
    provisioning = ProvisioningService(
        records, CLOCK, provisioner, state, ProvisioningLock(state)
    )
    verification = VerificationService(
        records,
        CLOCK,
        FixtureRuntimeVerifier(),
        FixtureProbeRunner(),
        state,
        VerificationLock(state),
    )
    foundation = FoundationSelectionService(
        records, CLOCK, provisioning, verification, SelectionLock(state)
    )
    return (
        FoundationRealizeService(
            foundation,
            characterization,
            ResourceManager(records, CLOCK, AdmissionLock(tmp_path / "lock")),
            CapacityService(clock=CLOCK),
            state,
            StorageEvidenceIndex(records),
            allow_empirical=False,
            journal=journal,
            ownership=ownership,
            runs=runs,
            occupancy_records=occupancy,
        ),
        journal,
        runs,
        state,
    )


def test_reclaim_required_without_ownership_fails(tmp_path: Path) -> None:
    from unittest.mock import patch

    current = tmp_path / "current" / "state"
    prior = tmp_path / "prior" / "state" / "models"
    current.mkdir(parents=True)
    prior.mkdir(parents=True)
    (prior / "blob").write_bytes(b"x" * 2048)
    host_caps = _linux_nvidia(mount(point="/", filesystem="ext4", free=80 * GIB))
    ownership = OwnershipService(FileStore(tmp_path / "own"), CLOCK, current)
    record = ownership.assert_owned(
        prior,
        host_caps.host_id,
        ManagedResourceType.MODEL_ARTIFACT,
        allowed_roots=(tmp_path,),
    )
    dest = destination_pool(current, pools_from_host(host_caps))
    assert dest is not None
    service, _journal, _runs, _state = _realize_for_reclaim(
        tmp_path,
        host_caps,
        None,
        lambda _host: ((record,), (), ()),
        _stub_characterization({}),
    )
    with (
        patch("kultrun.storage.inventory.tree_bytes", return_value=10 * GIB),
        pytest.raises(PreconditionFailedError, match="cannot be executed safely"),
    ):
        service._apply_minimum_and_reclaim(
            host_caps,
            _descriptors(),
            {
                dest.mount_point: _capacity(
                    host_caps.host_id, dest.mount_point, 20 * GIB
                )
            },
            None,
        )


def test_reclaim_then_capacity_pass_continues(tmp_path: Path) -> None:
    from unittest.mock import patch

    current = tmp_path / "current" / "state"
    prior = tmp_path / "prior" / "state" / "models"
    current.mkdir(parents=True)
    prior.mkdir(parents=True)
    (prior / "blob").write_bytes(b"x" * 4096)
    host_caps = _linux_nvidia(mount(point="/", filesystem="ext4", free=80 * GIB))
    dest = destination_pool(current, pools_from_host(host_caps))
    assert dest is not None
    ownership = OwnershipService(FileStore(tmp_path / "own"), CLOCK, current)
    ownership.assert_owned(
        prior,
        host_caps.host_id,
        ManagedResourceType.MODEL_ARTIFACT,
        allowed_roots=(tmp_path,),
    )
    after = {dest.mount_point: _capacity(host_caps.host_id, dest.mount_point, 80 * GIB)}
    service, journal, _runs, _state = _realize_for_reclaim(
        tmp_path,
        host_caps,
        ownership,
        lambda _host: (tuple(ownership.records()), (), ()),
        _stub_characterization(after),
    )
    with patch("kultrun.storage.inventory.tree_bytes", return_value=10 * GIB):
        updated = service._apply_minimum_and_reclaim(
            host_caps,
            _descriptors(),
            {
                dest.mount_point: _capacity(
                    host_caps.host_id, dest.mount_point, 20 * GIB
                )
            },
            None,
        )
    assert updated[dest.mount_point].authorizing_available_bytes == 80 * GIB
    assert not prior.exists()
    facts = journal.facts(host_caps.host_id)
    assert any(item.event_type.value == "storage.reclaim_completed" for item in facts)
    assert not any(item.event_type.value == "storage.recharacterized" for item in facts)
    completed = [
        item
        for item in facts
        if item.event_type.value == "minimum.feasibility_completed"
    ]
    assert len(completed) == 1
    assert any(
        item.outcome is OperationalOutcome.PASS
        and "requires_reclamation=False" in " ".join(item.attributes)
        for item in completed
    )


def test_reclaim_insufficient_blocks(tmp_path: Path) -> None:
    from unittest.mock import patch

    current = tmp_path / "current" / "state"
    prior = tmp_path / "prior" / "state" / "models"
    current.mkdir(parents=True)
    prior.mkdir(parents=True)
    (prior / "blob").write_bytes(b"x" * 4096)
    host_caps = _linux_nvidia(mount(point="/", filesystem="ext4", free=80 * GIB))
    dest = destination_pool(current, pools_from_host(host_caps))
    assert dest is not None
    ownership = OwnershipService(FileStore(tmp_path / "own"), CLOCK, current)
    ownership.assert_owned(
        prior,
        host_caps.host_id,
        ManagedResourceType.MODEL_ARTIFACT,
        allowed_roots=(tmp_path,),
    )
    after = {dest.mount_point: _capacity(host_caps.host_id, dest.mount_point, 8 * GIB)}
    service, _journal, runs, _state = _realize_for_reclaim(
        tmp_path,
        host_caps,
        ownership,
        lambda _host: (tuple(ownership.records()), (), ()),
        _stub_characterization(after),
    )
    with (
        patch("kultrun.storage.inventory.tree_bytes", return_value=10 * GIB),
        pytest.raises(PreconditionFailedError),
    ):
        service._apply_minimum_and_reclaim(
            host_caps,
            _descriptors(),
            {
                dest.mount_point: _capacity(
                    host_caps.host_id, dest.mount_point, 20 * GIB
                )
            },
            None,
        )
    # _apply_minimum_and_reclaim does not mark the run; realize() does.
    assert runs.current() is not None
    assert runs.current().status.value == "in_progress"


def test_layer_two_renders_reclaimable_capacity() -> None:
    subject = _linux_nvidia(
        mount(point="/workspace", filesystem="ext4", free=25 * GIB),
    )
    dest = destination_pool(Path("/workspace/app/state"), pools_from_host(subject))
    assert dest is not None
    items = (
        _item(
            occupancy=ManagedOccupancyClass.RECLAIMABLE,
            occupied=15 * GIB,
            mount_point=dest.mount_point,
            quota=dest.quota_identity,
            fingerprint=dest.fingerprint,
        ),
    )
    assessment = assess_minimum(
        subject,
        destination=dest,
        evidence=_capacity(subject.host_id, dest.mount_point, 20 * GIB),
        items=items,
        descriptors=_descriptors(),
        ram_safe_bytes=32 * GIB,
    )
    assert assessment.requires_reclamation is True
    envelope = _base_envelope(
        subject,
        (
            PoolCapacity(
                mount_point=dest.mount_point,
                space=_layered(25 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="ext4",
            ),
        ),
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
        candidates=(),
        recommended_candidate_id=None,
        selection=None,
        installations=(),
        provisioning_plans=(),
        profiles={},
        available=None,
        model_selection=None,
        deployment_plan=None,
        instances=(),
        executions=(),
        facts=(),
        intended_storage_pool=dest.mount_point,
        minimum=assessment,
    )
    text = format_deployment_report(report)
    assert "Purpose:" in text
    assert "PASS  (requires reclamation)" in text
    assert "Reclaimable" in text
    assert "vllm" in text
    assert "llama.cpp" in text
    assert "mlx" in text
    assert "- selected" not in text
    assert "Intended destination  /workspace" in text
    assert "LAYER 3 — MINIMUM FEASIBILITY" in text
    assert "Foundation Possibilities" in text


def test_cleanup_happens_despite_sufficient_capacity(tmp_path: Path) -> None:
    from unittest.mock import patch

    current = tmp_path / "current" / "state"
    prior = tmp_path / "prior" / "state" / "models"
    current.mkdir(parents=True)
    prior.mkdir(parents=True)
    (prior / "blob").write_bytes(b"x" * 4096)
    host_caps = _linux_nvidia(mount(point="/", filesystem="ext4", free=80 * GIB))
    dest = destination_pool(current, pools_from_host(host_caps))
    assert dest is not None
    ownership = OwnershipService(FileStore(tmp_path / "own"), CLOCK, current)
    ownership.assert_owned(
        prior,
        host_caps.host_id,
        ManagedResourceType.MODEL_ARTIFACT,
        allowed_roots=(tmp_path,),
    )
    after = {dest.mount_point: _capacity(host_caps.host_id, dest.mount_point, 40 * GIB)}
    service, journal, _runs, _state = _realize_for_reclaim(
        tmp_path,
        host_caps,
        ownership,
        lambda _host: (tuple(ownership.records()), (), ()),
        _stub_characterization(after),
    )
    with patch("kultrun.storage.inventory.tree_bytes", return_value=17 * GIB):
        updated = service._apply_minimum_and_reclaim(
            host_caps,
            _descriptors(),
            {
                dest.mount_point: _capacity(
                    host_caps.host_id, dest.mount_point, 40 * GIB
                )
            },
            None,
        )
    assert updated[dest.mount_point].authorizing_available_bytes == 40 * GIB
    assert not prior.exists()
    facts = journal.facts(host_caps.host_id)
    planned = next(
        item for item in facts if item.event_type.value == "storage.reclaim_planned"
    )
    assert "cleanup_lifecycle=True" in " ".join(planned.attributes)
    assert "cleanup_capacity=False" in " ".join(planned.attributes)
    assert any(item.event_type.value == "storage.reclaim_completed" for item in facts)
    completed = [
        item
        for item in facts
        if item.event_type.value == "minimum.feasibility_completed"
    ]
    assert len(completed) == 1
    assert completed[0].outcome is OperationalOutcome.PASS


def test_unique_occupancy_keeps_stronger_class_and_nested_bytes_once() -> None:
    parent = _item(
        occupancy=ManagedOccupancyClass.RECLAIMABLE,
        occupied=10 * GIB,
        mount_point="/",
        quota=NOT_PROVIDED,
        fingerprint=NOT_PROVIDED,
        root="/workspace/prior",
    )
    child = _item(
        occupancy=ManagedOccupancyClass.UNKNOWN,
        occupied=10 * GIB,
        mount_point="/",
        quota=NOT_PROVIDED,
        fingerprint=NOT_PROVIDED,
        root="/workspace/prior/models",
    )
    unique = unique_occupancy((parent, child))
    assert len(unique) == 1
    assert unique[0].occupancy_class is ManagedOccupancyClass.RECLAIMABLE
    same = unique_occupancy(
        (
            _item(
                occupancy=ManagedOccupancyClass.UNKNOWN,
                occupied=4 * GIB,
                mount_point="/",
                quota=NOT_PROVIDED,
                fingerprint=NOT_PROVIDED,
                root="/workspace/prior",
            ),
            _item(
                occupancy=ManagedOccupancyClass.REUSABLE,
                occupied=4 * GIB,
                mount_point="/",
                quota=NOT_PROVIDED,
                fingerprint=NOT_PROVIDED,
                root="/workspace/prior",
            ),
        )
    )
    assert len(same) == 1
    assert same[0].occupancy_class is ManagedOccupancyClass.REUSABLE


def test_unknown_parent_does_not_hide_reclaimable_sibling_artifacts() -> None:
    """Physical leftover layout: UNKNOWN state root wrapping owned models."""
    parent = _item(
        occupancy=ManagedOccupancyClass.UNKNOWN,
        occupied=19 * GIB,
        mount_point="/workspace",
        quota=NOT_PROVIDED,
        fingerprint=NOT_PROVIDED,
        resource=ManagedResourceType.STATE_ROOT,
        root="/workspace/prior/state",
    )
    models = _item(
        occupancy=ManagedOccupancyClass.RECLAIMABLE,
        occupied=6 * GIB,
        mount_point="/workspace",
        quota=NOT_PROVIDED,
        fingerprint=NOT_PROVIDED,
        resource=ManagedResourceType.MODEL_ARTIFACT,
        root="/workspace/prior/state/models",
    )
    runtimes = _item(
        occupancy=ManagedOccupancyClass.RECLAIMABLE,
        occupied=8 * GIB,
        mount_point="/workspace",
        quota=NOT_PROVIDED,
        fingerprint=NOT_PROVIDED,
        resource=ManagedResourceType.RUNTIME_FINAL,
        root="/workspace/prior/state/runtimes",
    )
    logs = _item(
        occupancy=ManagedOccupancyClass.UNKNOWN,
        occupied=1,
        mount_point="/workspace",
        quota=NOT_PROVIDED,
        fingerprint=NOT_PROVIDED,
        resource=ManagedResourceType.LOGS,
        root="/workspace/prior/state/logs",
    )
    unique = unique_occupancy((parent, models, runtimes, logs))
    reclaimable = [
        item
        for item in unique
        if item.occupancy_class is ManagedOccupancyClass.RECLAIMABLE
    ]
    unknown = [
        item
        for item in unique
        if item.occupancy_class is ManagedOccupancyClass.UNKNOWN
    ]
    assert {item.managed_root for item in reclaimable} == {
        "/workspace/prior/state/models",
        "/workspace/prior/state/runtimes",
    }
    assert "/workspace/prior/state" not in {item.managed_root for item in unique}
    assert {item.managed_root for item in unknown} == {
        "/workspace/prior/state/logs"
    }
    totals = totals_by_pool((parent, models, runtimes, logs))["/workspace"]
    assert totals.reclaimable_bytes == 14 * GIB
    assert totals.unknown_bytes == 1
    plan = plan_reclaim(
        (parent, models, runtimes, logs),
        mount_point="/workspace",
        capacity_required=False,
    )
    assert plan.cleanup_required_by_lifecycle is True
    assert plan.cleanup_required_for_capacity is False
    assert plan.expected_bytes == 14 * GIB

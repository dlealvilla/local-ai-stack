"""Reported → effective → safe.

Stage 1.2's whole job is refusing to confuse those three, so most of these
tests are about what capacity *declines* to claim.

Three are worth naming. `test_a_network_pool_reporting_petabytes_is_bounded`
is the case the stage exists for. `test_a_container_limit_beats_the_machines_memory`
is the same error in a different resource, found on the real host after the
accelerator version of it was found at Stage 1.1. And
`test_unified_memory_unresolved_asserts_no_accelerator_budget` is the one
that has no hardware to exercise it yet, which is exactly why it is written
now.
"""

from __future__ import annotations

import datetime as dt

import pytest

from kultrun.capacity.contracts import CapacityEnvelope, EvidenceRequirement
from kultrun.capacity.envelope import CapacityService
from kultrun.capacity.policy import default_policy
from kultrun.evidence.contracts import Confidence
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
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.schema import from_dict, to_dict
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, Maybe, is_resolved

INSTANT = dt.datetime(2026, 9, 5, 12, 0, tzinfo=dt.UTC)
GIB = 1024**3
TIB = 1024**4
PIB = 1024**5


def service() -> CapacityService:
    return CapacityService(clock=FixedClock(INSTANT))


def host(
    *,
    memory_total: Maybe[int] = 64 * GIB,
    memory_limit: Maybe[int] = NOT_PROVIDED,
    unified: Maybe[bool] = False,
    accelerators: tuple[Accelerator, ...] = (),
    mounts: tuple[MountFacts, ...] = (),
) -> HostCapabilities:
    """A host with only the facts a capacity test needs."""
    return HostCapabilities(
        host_id=HostId.generate(),
        fingerprint="test-fingerprint",
        detected_at=INSTANT,
        operating_environment=OperatingEnvironment(
            os_name="linux",
            os_version="24.04",
            architecture=Architecture.X86_64,
            kernel_version=NOT_PROVIDED,
            virtualized=NOT_PROVIDED,
        ),
        cpu=CpuFacts(
            vendor=NOT_PROVIDED,
            model_name=NOT_PROVIDED,
            physical_cores=NOT_PROVIDED,
            logical_cores=NOT_PROVIDED,
        ),
        memory=MemoryFacts(
            total_bytes=memory_total,
            available_bytes=NOT_PROVIDED,
            unified_with_accelerator=unified,
            limit_bytes=memory_limit,
        ),
        execution=ExecutionCapabilities(
            native_process=True, docker=NOT_PROVIDED, podman=NOT_PROVIDED
        ),
        network=NetworkFacts(
            hostname=NOT_PROVIDED, loopback_address=NOT_PROVIDED, occupied_ports=()
        ),
        accelerators=accelerators,
        mounts=mounts,
    )


def accelerator(
    index: int = 0,
    memory: Maybe[int] = 32 * GIB,
    unified: Maybe[bool] = False,
) -> Accelerator:
    return Accelerator(
        index=index,
        vendor=AcceleratorVendor.NVIDIA,
        model_name="Test Accelerator",
        memory_total_bytes=memory,
        driver_version=NOT_PROVIDED,
        unified_memory=unified,
    )


def mount(
    point: str = "/data",
    filesystem: Maybe[str] = "ext4",
    free: Maybe[int] = 500 * GIB,
    total: Maybe[int] = 1000 * GIB,
) -> MountFacts:
    return MountFacts(
        mount_point=point,
        device=NOT_PROVIDED,
        filesystem_type=filesystem,
        total_bytes=total,
        free_bytes=free,
    )


class TestTheThreeLayersStayDistinct:
    def test_reported_is_preserved_exactly(self) -> None:
        """Reported may be displayed, so it must not be quietly adjusted."""
        envelope = service().compute(host(memory_total=64 * GIB))
        assert envelope.memory.reported_bytes == 64 * GIB

    def test_safe_is_below_effective_by_the_reserve(self) -> None:
        envelope = service().compute(host(memory_total=64 * GIB))
        policy = default_policy()
        expected = 64 * GIB - int(64 * GIB * policy.memory_reserve_fraction)
        assert envelope.memory.effective_bytes == 64 * GIB
        assert envelope.memory.safe_bytes == expected

    def test_only_safe_is_offered_as_authorizing(self) -> None:
        """The type names the one layer allowed to authorize."""
        envelope = service().compute(host())
        assert envelope.memory.authorizing_bytes == envelope.memory.safe_bytes

    def test_a_floor_protects_a_small_resource(self) -> None:
        """A fraction alone protects nothing when the resource is small."""
        policy = default_policy()
        envelope = service().compute(host(memory_total=4 * GIB))
        assert envelope.memory.safe_bytes == 4 * GIB - policy.memory_reserve_floor_bytes

    def test_a_fraction_protects_a_large_resource(self) -> None:
        """A floor alone protects nothing when the resource is large."""
        envelope = service().compute(host(memory_total=1000 * GIB))
        reserve = int(1000 * GIB * default_policy().memory_reserve_fraction)
        assert envelope.memory.safe_bytes == 1000 * GIB - reserve
        assert reserve > default_policy().memory_reserve_floor_bytes

    def test_a_resource_smaller_than_its_reserve_is_unresolved_not_zero(self) -> None:
        """Zero reads as a measured absence; this is "too small to use".

        Different facts, and admission must not read either as permission.
        """
        envelope = service().compute(host(memory_total=1 * GIB))
        assert not is_resolved(envelope.memory.safe_bytes)
        assert envelope.memory.safe_bytes is not 0  # noqa: F632 - identity is the point
        assert any("no safe memory remains" in d for d in envelope.defects)


class TestSystemMemory:
    def test_a_container_limit_beats_the_machines_memory(self) -> None:
        """Measured on the reference host, and it is a 4.4x error.

        The machine reports 251.5 GiB; the container may use 57.7 GiB.
        Admitting against the machine gets workloads OOM-killed — the same
        class of error as counting accelerators nobody assigned.
        """
        envelope = service().compute(
            host(memory_total=270_055_956_480, memory_limit=61_999_996_928)
        )
        assert envelope.memory.reported_bytes == 270_055_956_480
        assert envelope.memory.effective_bytes == 61_999_996_928
        assert envelope.memory_requirement is EvidenceRequirement.RESTRICTED
        assert isinstance(envelope.memory.safe_bytes, int)
        assert envelope.memory.safe_bytes < 61_999_996_928
        assert envelope.memory_note is not None
        assert "restricts" in envelope.memory_note

    def test_a_limit_above_the_machine_is_not_a_restriction(self) -> None:
        envelope = service().compute(
            host(memory_total=64 * GIB, memory_limit=128 * GIB)
        )
        assert envelope.memory.effective_bytes == 64 * GIB

    def test_unresolved_memory_yields_no_safe_figure(self) -> None:
        envelope = service().compute(host(memory_total=NOT_PROVIDED))
        assert not is_resolved(envelope.memory.safe_bytes)
        assert not is_resolved(envelope.memory.effective_bytes)
        assert envelope.memory.confidence is Confidence.UNKNOWN
        assert envelope.memory_requirement is EvidenceRequirement.UNKNOWN
        assert envelope.defects

    def test_capacity_is_not_utilization(self) -> None:
        """Available memory must not become capacity.

        A busy machine is not a small one, and a workload admitted against
        a momentary dip would be refused for no structural reason.
        """
        envelope = service().compute(host(memory_total=64 * GIB))
        assert envelope.memory.reported_bytes == 64 * GIB


class TestAccelerators:
    def test_only_assigned_accelerators_appear(self) -> None:
        """Host discovery reconciled four visible devices to one assigned.

        An envelope covering four would claim ~128 GiB that does not exist.
        Capacity consumes that reconciliation and never re-counts the bus.
        """
        envelope = service().compute(host(accelerators=(accelerator(),)))
        assert len(envelope.accelerators) == 1
        assert envelope.accelerators[0].index == 0

    def test_several_accelerators_are_each_layered_separately(self) -> None:
        """Never aggregated: one 32 GiB device is not half of a 64 GiB one."""
        envelope = service().compute(
            host(
                accelerators=(
                    accelerator(0, 32 * GIB),
                    accelerator(1, 16 * GIB),
                )
            )
        )
        assert [entry.index for entry in envelope.accelerators] == [0, 1]
        assert envelope.accelerators[0].memory.reported_bytes == 32 * GIB
        assert envelope.accelerators[1].memory.reported_bytes == 16 * GIB
        assert envelope.accelerators[0].memory.safe_bytes != (
            envelope.accelerators[1].memory.safe_bytes
        )

    def test_no_accelerator_is_a_fact_not_a_failure(self) -> None:
        """A CPU-only host must still produce a coherent envelope."""
        envelope = service().compute(host(accelerators=()))
        assert envelope.accelerators == ()
        assert any("no accelerator is assigned" in d for d in envelope.defects)
        assert is_resolved(envelope.memory.safe_bytes)

    def test_a_device_reporting_no_memory_yields_no_safe_figure(self) -> None:
        envelope = service().compute(
            host(accelerators=(accelerator(memory=NOT_PROVIDED),))
        )
        entry = envelope.accelerators[0]
        assert not is_resolved(entry.memory.safe_bytes)
        assert entry.requirement is EvidenceRequirement.UNKNOWN

    def test_unified_memory_unresolved_asserts_no_accelerator_budget(self) -> None:
        """Fails closed rather than assuming the two pools are independent.

        No unified-memory host has been observed, so this branch has no
        hardware to exercise it — which is precisely why it is written now.
        Assuming independence on Apple Silicon would double-count a model's
        memory and admit something that cannot fit.
        """
        envelope = service().compute(
            host(
                unified=NOT_PROVIDED,
                accelerators=(accelerator(unified=NOT_PROVIDED),),
            )
        )
        entry = envelope.accelerators[0]
        assert entry.memory.reported_bytes == 32 * GIB
        assert not is_resolved(entry.memory.effective_bytes)
        assert not is_resolved(entry.memory.safe_bytes)
        assert any(
            "shared with system memory is unknown" in d for d in envelope.defects
        )

    def test_unified_memory_true_defers_rather_than_double_counting(self) -> None:
        envelope = service().compute(
            host(unified=True, accelerators=(accelerator(unified=True),))
        )
        entry = envelope.accelerators[0]
        assert not is_resolved(entry.memory.safe_bytes)
        assert any("DC-01" in d for d in envelope.defects)

    def test_a_host_level_answer_settles_a_silent_device(self) -> None:
        """Either source resolving it is enough; they need not both."""
        envelope = service().compute(
            host(unified=False, accelerators=(accelerator(unified=NOT_PROVIDED),))
        )
        assert is_resolved(envelope.accelerators[0].memory.safe_bytes)


class TestStorage:
    def test_a_network_pool_reporting_petabytes_is_bounded(self) -> None:
        """The case Stage 1.2 exists for.

        The reference host mounts a network filesystem advertising 2.15 PB.
        The previous attempt met the same shape as "239 TB free" and then
        could not complete a 6.70 GiB install. Reported is kept intact;
        effective is bounded because nothing has verified anything.
        """
        policy = default_policy()
        envelope = service().compute(
            host(mounts=(mount("/workspace", "fuse", free=500 * TIB, total=2 * PIB),))
        )
        pool = envelope.pools[0]
        assert pool.space.reported_bytes == 500 * TIB
        assert pool.space.effective_bytes == policy.unverified_pool_ceiling_bytes
        assert pool.requirement is EvidenceRequirement.EMPIRICAL_EVIDENCE_NEEDED
        assert pool.space.confidence is Confidence.LOW
        assert isinstance(pool.space.safe_bytes, int)
        assert pool.space.safe_bytes < policy.unverified_pool_ceiling_bytes
        assert pool.note is not None
        assert "Stage 2.2" in pool.note

    def test_the_bound_is_explained_as_a_defect(self) -> None:
        """An administrator is told, not left to infer it from a number."""
        envelope = service().compute(
            host(mounts=(mount("/workspace", "fuse", free=500 * TIB),))
        )
        assert any("only" in d and "/workspace" in d for d in envelope.defects)

    def test_a_local_filesystem_is_believed(self) -> None:
        envelope = service().compute(
            host(mounts=(mount("/", "ext4", free=500 * GIB),))
        )
        pool = envelope.pools[0]
        assert pool.space.effective_bytes == 500 * GIB
        assert pool.requirement is EvidenceRequirement.SUFFICIENT
        assert pool.space.confidence is Confidence.HIGH

    def test_a_small_local_pool_is_not_inflated_by_the_ceiling(self) -> None:
        """The ceiling bounds; it never raises."""
        envelope = service().compute(host(mounts=(mount("/", "ext4", free=10 * GIB),)))
        assert envelope.pools[0].space.effective_bytes == 10 * GIB

    def test_an_unknown_filesystem_family_is_not_believed(self) -> None:
        """Unrecognised is not the same as fine."""
        policy = default_policy()
        envelope = service().compute(
            host(mounts=(mount("/odd", "somethingnew", free=900 * TIB),))
        )
        pool = envelope.pools[0]
        assert pool.space.effective_bytes == policy.unverified_pool_ceiling_bytes
        assert pool.requirement is EvidenceRequirement.UNKNOWN

    def test_memory_backed_storage_is_not_a_pool(self) -> None:
        """It is RAM. Counting it as storage counts the same bytes twice."""
        envelope = service().compute(
            host(mounts=(mount("/", "ext4"), mount("/scratch", "tmpfs")))
        )
        assert [pool.mount_point for pool in envelope.pools] == ["/"]

    def test_a_pool_with_no_free_figure_yields_nothing_safe(self) -> None:
        envelope = service().compute(
            host(mounts=(mount("/", "ext4", free=NOT_PROVIDED),))
        )
        pool = envelope.pools[0]
        assert not is_resolved(pool.space.safe_bytes)
        assert pool.requirement is EvidenceRequirement.UNKNOWN

    def test_reported_total_is_kept_for_explanation_only(self) -> None:
        envelope = service().compute(
            host(mounts=(mount("/workspace", "fuse", free=500 * TIB, total=2 * PIB),))
        )
        pool = envelope.pools[0]
        assert pool.reported_total_bytes == 2 * PIB
        assert pool.space.authorizing_bytes != pool.reported_total_bytes

    @pytest.mark.parametrize(
        "family", ["fuse", "nfs", "nfs4", "cifs", "ceph", "glusterfs", "9p", "s3fs"]
    )
    def test_every_network_family_requires_evidence(self, family: str) -> None:
        envelope = service().compute(
            host(mounts=(mount("/net", family, free=100 * TIB),))
        )
        assert envelope.pools[0].requirement is (
            EvidenceRequirement.EMPIRICAL_EVIDENCE_NEEDED
        )


class TestTheEnvelopeItself:
    def test_it_is_scoped_to_the_host_that_produced_it(self) -> None:
        """Capacity is not portable; another machine's envelope is invalid."""
        subject = host()
        envelope = service().compute(subject)
        assert envelope.host_id == subject.host_id
        assert envelope.host_fingerprint == subject.fingerprint

    def test_recomputation_is_deterministic(self) -> None:
        """Same facts and same policy give the same answer, every time."""
        subject = host(
            memory_total=64 * GIB,
            accelerators=(accelerator(),),
            mounts=(mount(), mount("/workspace", "fuse", free=500 * TIB)),
        )
        first = to_dict(service().compute(subject))
        second = to_dict(service().compute(subject))
        assert first == second

    def test_it_names_the_policy_that_produced_it(self) -> None:
        """So an old decision stays explicable after the policy changes."""
        envelope = service().compute(host())
        assert envelope.policy_version == default_policy().policy_version
        assert envelope.memory.provenance.policy_version == envelope.policy_version

    def test_it_survives_the_wire(self) -> None:
        envelope = service().compute(
            host(accelerators=(accelerator(),), mounts=(mount(),))
        )
        assert from_dict(to_dict(envelope)) == envelope

    def test_a_host_with_nothing_known_admits_nothing(self) -> None:
        """And says so, rather than reporting zero or unlimited."""
        envelope = service().compute(
            host(memory_total=NOT_PROVIDED, accelerators=(), mounts=())
        )
        assert envelope.admits_anything is False
        assert envelope.defects

    def test_a_usable_host_admits_something(self) -> None:
        envelope = service().compute(host(accelerators=(accelerator(),)))
        assert envelope.admits_anything is True

    def test_no_safe_layer_is_ever_silently_zero(self) -> None:
        """The invariant behind every test above.

        A safe figure of zero would read as "measured: no capacity" and
        could be compared against a request. Too-small-to-use and
        not-known are different facts and both stay unresolved. A
        *reported* zero is allowed through, because a full filesystem
        reporting zero free is a genuine measurement.
        """
        subjects = [
            host(),
            host(memory_total=NOT_PROVIDED),
            host(memory_total=1 * GIB),
            host(accelerators=(accelerator(memory=NOT_PROVIDED),)),
            host(accelerators=(accelerator(memory=1),)),
            host(mounts=(mount(free=0),)),
            host(mounts=(mount("/workspace", "fuse", free=1 * PIB),)),
        ]
        for subject in subjects:
            envelope = service().compute(subject)
            for value in _every_safe_layer(envelope):
                assert value != 0, "a safe layer resolved to zero"


def _every_safe_layer(envelope: CapacityEnvelope) -> list[object]:
    values: list[object] = [envelope.memory.safe_bytes]
    values += [entry.memory.safe_bytes for entry in envelope.accelerators]
    values += [pool.space.safe_bytes for pool in envelope.pools]
    return [value for value in values if is_resolved(value)]


def test_the_reserve_never_produces_a_negative_figure() -> None:
    """A reserve larger than the resource yields unresolved, never a negative."""
    envelope = service().compute(
        host(memory_total=1, accelerators=(accelerator(index=0, memory=1),))
    )
    assert envelope.memory.safe_bytes is NOT_MEASURED
    assert not is_resolved(envelope.accelerators[0].memory.safe_bytes)

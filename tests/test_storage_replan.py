"""Bounded control-plane storage replan: 10% ceilings, real candidates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.capacity.contracts import (
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.model.contracts import MemoryPlacement
from kultrun.model.discovery import DiscoveryQuery, DiscoveryResult
from kultrun.planning.contracts import (
    AvailableModelMember,
    AvailableModelView,
    AvailableModelViewId,
    AvailableViewStatus,
    ModelSelectionMode,
)
from kultrun.planning.evaluate import deployment_capacity
from kultrun.platform.available_models import FunnelPass
from kultrun.platform.storage_replan import (
    ReplanOutcome,
    ReplanStage,
    StorageReplanService,
    member_footprint,
)
from kultrun.resource.contracts import (
    AdmissionVerdict,
    RequestId,
    ResourceRequest,
    WorkloadType,
)
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.contracts import (
    EligibleModelView,
    EligibleModelViewId,
    EligibleViewStatus,
    FoundationSelectionMode,
    InstallationStatus,
)
from kultrun.runtime.selection import ROLE_BLOCKED
from kultrun.storage.characterize import Characterization
from kultrun.storage.contracts import LowSpaceGuidance
from kultrun.storage.limits import LOW_SPACE_THRESHOLD_BYTES
from kultrun.storage.reduction import peak_cap_bytes
from tests.test_capacity import INSTANT
from tests.test_contracts import host_capabilities

GIB = 1024**3

A, B, C, D, E = 40 * GIB, 35 * GIB, 31 * GIB, 26 * GIB, 20 * GIB
ORIGINAL = {"A": A, "B": B, "C": C, "D": D, "E": E}


def _layered(safe: Maybe[int]) -> LayeredBytes:
    return LayeredBytes(
        reported_bytes=100 * GIB if isinstance(safe, int) else NOT_PROVIDED,
        effective_bytes=safe if isinstance(safe, int) else NOT_PROVIDED,
        safe_bytes=safe,
        confidence=Confidence.HIGH,
        provenance=Provenance(
            producer=Name("test"),
            producer_version="t",
            observed_at=INSTANT,
            policy_version="t",
        ),
    )


def _envelope(host: HostCapabilities, safe: int) -> CapacityEnvelope:
    return CapacityEnvelope(
        host_id=host.host_id,
        host_fingerprint=host.fingerprint,
        computed_at=INSTANT,
        policy_version="t",
        memory=_layered(48 * GIB),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        pools=(
            PoolCapacity(
                mount_point="/",
                space=_layered(safe),
                requirement=EvidenceRequirement.SUFFICIENT,
            ),
        ),
    )


def _member(ident: str, peak: int) -> AvailableModelMember:
    return AvailableModelMember(
        model_id=ident,
        logical_name=ident.lower(),
        source_ref=f"org/{ident}",
        source_revision=NOT_PROVIDED,
        runtime="vllm",
        runtime_version="0.1",
        quantization=NOT_PROVIDED,
        requested_context_tokens=NOT_PROVIDED,
        required_vram_bytes=NOT_PROVIDED,
        available_vram_bytes=NOT_PROVIDED,
        required_ram_bytes=NOT_PROVIDED,
        available_ram_bytes=NOT_PROVIDED,
        incremental_storage_bytes=peak,
        available_storage_bytes=100 * GIB,
        requirement_provider="test",
        requirement_confidence="low",
        requirement_basis=f"basis-{ident}-{peak}",
    )


def _available(
    host: HostCapabilities, members: tuple[AvailableModelMember, ...], snapshot: str
) -> AvailableModelView:
    return AvailableModelView(
        view_id=AvailableModelViewId.generate(),
        host_id=host.host_id,
        status=AvailableViewStatus.CURRENT,
        evaluated_at=now_utc(),
        view_basis=f"view-{snapshot}",
        snapshot_basis=snapshot,
        host_fingerprint=host.fingerprint,
        eligible_view_id="emv_test",
        runtime="vllm",
        runtime_version="0.1",
        requested_context_tokens=NOT_PROVIDED,
        universe_count=len(members),
        discovered_count=len(members),
        compatibility_count=len(members),
        cheap_reject_count=0,
        deep_analyzed_count=len(members),
        available_count=len(members),
        excluded_count=0,
        estimator_invocations=0,
        members=members,
    )


def _eligible(host: HostCapabilities) -> EligibleModelView:
    return EligibleModelView(
        view_id=EligibleModelViewId.generate(),
        host_id=host.host_id,
        status=EligibleViewStatus.CURRENT,
        evaluated_at=now_utc(),
        selected_candidate_id="cand",
        runtime="vllm",
        runtime_version="0.1",
        executor="native-process",
        profile_id="prof",
        eligible_count=0,
    )


def _funnel(
    host: HostCapabilities,
    members: tuple[AvailableModelMember, ...],
    snapshot: str,
    safe: int,
) -> FunnelPass:
    envelope = _envelope(host, safe)
    return FunnelPass(
        eligible=_eligible(host),
        envelope=envelope,
        capacity=deployment_capacity(envelope, storage_mount="/"),
        assessments=(),
        available=_available(host, members, snapshot),
        discovery=DiscoveryResult(
            universe_count=len(members),
            discovered_count=len(members),
            criteria=DiscoveryQuery(),
            catalog_entries=(),
        ),
    )


@dataclass
class FakeStored:
    selection_mode: ModelSelectionMode = ModelSelectionMode.AUTO


@dataclass
class FakeSelection:
    selected_model_id: str | None = None
    selected_candidate_id: str | None = "vllm"


@dataclass
class FakeOverview:
    selection: FakeSelection
    candidates: tuple[object, ...] = ()


@dataclass
class FakeInstall:
    status: InstallationStatus


@dataclass
class FakePlan:
    plan_id: str
    plan_basis: str


@dataclass
class FakePlanOverview:
    plan: FakePlan


class FakeModels:
    def __init__(self, mode: ModelSelectionMode = ModelSelectionMode.AUTO) -> None:
        self.mode = mode
        self.auto_calls = 0
        self.selected: list[str] = []

    def stored(self, host: HostCapabilities) -> FakeStored:
        del host
        return FakeStored(self.mode)

    def select_auto(
        self,
        host: HostCapabilities,
        eligible: object,
        envelope: object,
        assessments: object,
        available: AvailableModelView | None = None,
    ) -> FakeOverview:
        del host, eligible, envelope, assessments
        self.auto_calls += 1
        members = available.members if available is not None else ()
        winner = max(
            members, key=lambda item: member_footprint(item) or 0, default=None
        )
        ident = winner.model_id if winner is not None else None
        if ident is not None:
            self.selected.append(ident)
        return FakeOverview(FakeSelection(selected_model_id=ident))


class FakePlans:
    def __init__(self) -> None:
        self.bases: list[str] = []
        self.n = 0

    def refresh(
        self,
        host: HostCapabilities,
        eligible: object,
        envelope: object,
        assessments: object,
        overview: object,
        foundation: object,
    ) -> FakePlanOverview:
        del host, eligible, envelope, assessments, overview, foundation
        self.n += 1
        plan = FakePlan(plan_id="dplan_hoststable0001", plan_basis=f"basis-{self.n}")
        self.bases.append(plan.plan_basis)
        return FakePlanOverview(plan)


class FakeCapacity:
    def __init__(self, host: HostCapabilities, safe: int) -> None:
        self.host = host
        self.safe = safe
        self.computes = 0

    def compute(
        self,
        host: HostCapabilities,
        sanity: object,
        storage_evidence: object = None,
    ) -> CapacityEnvelope:
        del sanity, storage_evidence
        self.computes += 1
        return _envelope(host, self.safe)


class FakeChar:
    def __init__(self, host: HostCapabilities) -> None:
        self.host = host
        self.calls: list[dict[str, object]] = []
        self.low_space: tuple[LowSpaceGuidance, ...] = ()
        self.empirical = False

    def characterize(
        self,
        host: HostCapabilities,
        *,
        run_cleanup: bool = True,
        run_empirical: bool = True,
        probe_workspace: Path | None = None,
    ) -> Characterization:
        del probe_workspace
        self.calls.append({"run_cleanup": run_cleanup, "run_empirical": run_empirical})
        self.empirical = run_empirical
        return Characterization(
            pools=(),
            evidence={},
            cleanup=None,
            low_space=self.low_space,
            empirical_ran=("/workspace",) if run_empirical else (),
        )


class FakeFoundation:
    def __init__(
        self,
        *,
        mode: FoundationSelectionMode = FoundationSelectionMode.AUTO,
        installed: bool = False,
        blocked: bool = False,
        candidate: str = "vllm",
    ) -> None:
        self.mode = mode
        self.installed = installed
        self.blocked = blocked
        self.candidate = candidate
        self.select_auto_calls = 0
        self.realize_calls = 0

    def stored(self, host: HostCapabilities) -> FakeStored:
        del host
        return FakeStored(cast(ModelSelectionMode, self.mode))

    def view(
        self, host: HostCapabilities, *args: object, **kwargs: object
    ) -> FakeOverview:
        del host, args, kwargs
        role = ROLE_BLOCKED if self.blocked else "recommended"
        classified = type("C", (), {"candidate_id": self.candidate, "role": role})()
        return FakeOverview(
            FakeSelection(selected_candidate_id=self.candidate),
            candidates=(classified,),
        )

    def installation_for(self, candidate_id: str) -> object | None:
        del candidate_id
        if not self.installed:
            return None
        return FakeInstall(status=InstallationStatus.INSTALLED)

    def select_auto(
        self, host: HostCapabilities, *args: object, **kwargs: object
    ) -> FakeOverview:
        del args, kwargs
        self.select_auto_calls += 1
        return self.view(host)

    def realize_selected(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.realize_calls += 1


def _members(
    names: tuple[str, ...] = ("A", "B", "C", "D", "E"),
) -> tuple[AvailableModelMember, ...]:
    return tuple(_member(name, ORIGINAL[name]) for name in names)


class World:
    def __init__(
        self,
        tmp_path: Path,
        *,
        safe: int = 80 * GIB,
        names: tuple[str, ...] = ("A", "B", "C", "D", "E"),
        mode: ModelSelectionMode = ModelSelectionMode.AUTO,
        installed: bool = False,
        blocked: bool = False,
    ) -> None:
        self.host = host_capabilities()
        self.safe = safe
        self.names = names
        self.funnel_calls = 0
        self.snapshots: list[str] = []
        self.char = FakeChar(self.host)
        self.models = FakeModels(mode)
        self.plans = FakePlans()
        self.capacity = FakeCapacity(self.host, safe)
        self.foundation = FakeFoundation(installed=installed, blocked=blocked)
        self.resources = ResourceManager(
            FileStore(tmp_path / "records"),
            FixedClock(INSTANT),
            AdmissionLock(tmp_path / "lock"),
        )
        self.service = StorageReplanService(
            characterization=cast(object, self.char),  # type: ignore[arg-type]
            funnel=self.funnel,
            model_selection=cast(object, self.models),  # type: ignore[arg-type]
            plans=cast(object, self.plans),  # type: ignore[arg-type]
            resources=self.resources,
            capacity=cast(object, self.capacity),  # type: ignore[arg-type]
            stored_sanity=lambda _host: {},
            foundation=cast(object, self.foundation),  # type: ignore[arg-type]
            foundation_inputs=lambda _host: ((), (), None),
            index=None,
            state_root=tmp_path / "state",
            allow_empirical=False,
        )

    def funnel(self, host: HostCapabilities) -> FunnelPass:
        self.funnel_calls += 1
        snapshot = f"snap-{self.funnel_calls}-safe-{self.capacity.safe}"
        self.snapshots.append(snapshot)
        return _funnel(host, _members(self.names), snapshot, self.capacity.safe)


def test_policy_math_on_40gib_original() -> None:
    assert peak_cap_bytes(A, 0) == A
    assert peak_cap_bytes(A, 1) == A * 9 // 10
    assert peak_cap_bytes(A, 1) == 36 * GIB
    assert B <= peak_cap_bytes(A, 1) < A
    assert C <= peak_cap_bytes(A, 2) < B
    assert D <= peak_cap_bytes(A, 3) < C


def test_auto_reselects_real_candidates_without_scaling_requirements(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    report = world.service.handle(
        world.host,
        failure_code="insufficient_safe_storage",
        original_identity="A",
        original_footprint=A,
    )
    assert report.outcome is ReplanOutcome.SUCCEEDED
    assert report.attempts[0].candidate == "A"
    assert report.attempts[0].candidate_footprint_bytes == A
    retry = report.attempts[1]
    assert retry.footprint_ceiling_bytes == peak_cap_bytes(A, 1)
    assert retry.candidate == "B"
    assert retry.candidate_footprint_bytes == B
    assert retry.candidate_footprint_bytes != int(A * 0.90)
    assert retry.plan_basis == "basis-1"
    assert retry.admission == AdmissionVerdict.ADMITTED.value
    assert retry.request_id is not None
    assert world.models.auto_calls == 1
    assert member_footprint(_member("B", B)) == B


def test_three_reductions_then_terminal(tmp_path: Path) -> None:
    world = World(tmp_path, safe=1 * GIB)
    report = world.service.handle(
        world.host,
        failure_code="insufficient_safe_storage",
        original_identity="A",
        original_footprint=A,
    )
    assert report.outcome is ReplanOutcome.TERMINAL
    assert [item.attempt for item in report.attempts] == [0, 1, 2, 3]
    assert all(item.result != "admitted" for item in report.attempts)
    assert report.payload()["fourth_retry"] is False
    assert world.funnel_calls == 3


def test_each_retry_recomputes_derived_state(tmp_path: Path) -> None:
    world = World(tmp_path, safe=1 * GIB)
    report = world.service.handle(
        world.host,
        failure_code="insufficient_safe_storage",
        original_identity="A",
        original_footprint=A,
    )
    retries = [item for item in report.attempts if item.attempt > 0]
    assert len(retries) == 3
    assert world.funnel_calls == 3
    assert world.capacity.computes == 3
    assert world.models.auto_calls == 3
    assert world.plans.bases == ["basis-1", "basis-2", "basis-3"]
    snapshots = [item.snapshot_basis for item in retries]
    expected = [f"snap-{n}-safe-{1 * GIB}" for n in (1, 2, 3)]
    assert snapshots == expected
    assert len({item.request_id for item in retries}) == 3
    assert {item.plan_id for item in retries} == {"dplan_hoststable0001"}


def test_edquot_rediscovers_before_reducing_and_does_not_reuse_old_safe(
    tmp_path: Path,
) -> None:

    world = World(tmp_path, safe=50 * GIB)

    def funnel(host: HostCapabilities) -> FunnelPass:
        world.funnel_calls += 1
        if world.char.calls:
            world.capacity.safe = 28 * GIB
            world.names = ("C", "D", "E")
        snapshot = f"snap-{world.funnel_calls}-safe-{world.capacity.safe}"
        world.snapshots.append(snapshot)
        return _funnel(host, _members(world.names), snapshot, world.capacity.safe)

    world.service._funnel = funnel
    stale = _envelope(world.host, 50 * GIB)
    stale_admit = world.resources.admit(
        ResourceRequest(
            request_id=RequestId.generate(),
            host_id=world.host.host_id,
            plan_fingerprint="stale-A",
            placement=MemoryPlacement.CPU_ONLY,
            ram_bytes=NOT_PROVIDED,
            accelerator_bytes=NOT_PROVIDED,
            unified_bytes=NOT_PROVIDED,
            incremental_storage_bytes=A,
            storage_pool_mount="/",
            workload_type=WorkloadType.MODEL_ACQUISITION,
        ),
        stale,
    )
    assert stale_admit.verdict is AdmissionVerdict.ADMITTED
    if stale_admit.reservation is not None:
        world.resources.release(stale_admit.reservation.reservation_id)

    report = world.service.handle(
        world.host,
        failure_code="storage_quota_exceeded",
        original_identity="A",
        original_footprint=A,
    )
    assert world.char.calls
    assert world.char.calls[0]["run_cleanup"] is True
    assert world.capacity.safe == 28 * GIB
    fresh = world.capacity.compute(world.host, {})
    assert stale.pools[0].space.safe_bytes == 50 * GIB
    assert fresh.pools[0].space.safe_bytes == 28 * GIB
    rejected = world.resources.admit(
        ResourceRequest(
            request_id=RequestId.generate(),
            host_id=world.host.host_id,
            plan_fingerprint="old-A",
            placement=MemoryPlacement.CPU_ONLY,
            ram_bytes=NOT_PROVIDED,
            accelerator_bytes=NOT_PROVIDED,
            unified_bytes=NOT_PROVIDED,
            incremental_storage_bytes=A,
            storage_pool_mount="/",
            workload_type=WorkloadType.MODEL_ACQUISITION,
        ),
        fresh,
    )
    assert rejected.verdict is AdmissionVerdict.REJECTED
    assert report.outcome is ReplanOutcome.SUCCEEDED
    chosen = next(item for item in report.attempts if item.result == "admitted")
    assert chosen.candidate == "D"
    assert chosen.candidate_footprint_bytes == D
    assert chosen.snapshot_basis == f"snap-3-safe-{28 * GIB}"
    assert chosen.attempt == 3


def test_low_space_does_not_reduce(tmp_path: Path) -> None:
    world = World(tmp_path, safe=4 * GIB)
    world.char.low_space = (
        LowSpaceGuidance(
            host_id=world.host.host_id,
            mount_point="/",
            quota_identity=NOT_PROVIDED,
            authorizing_available_bytes=4 * GIB,
            threshold_bytes=LOW_SPACE_THRESHOLD_BYTES,
            cleaned_bytes=0,
            message="clear space before deploying",
            rediscovery_required=True,
        ),
    )
    report = world.service.handle(
        world.host,
        failure_code="storage_low_space",
        original_identity="A",
        original_footprint=A,
    )
    assert report.outcome is ReplanOutcome.LOW_SPACE
    assert world.funnel_calls == 0
    assert world.models.auto_calls == 0
    assert len(report.attempts) == 1
    assert report.low_space[0].rediscovery_required is True

    world.char.low_space = ()
    world.capacity.safe = 80 * GIB
    resumed = world.service.handle(
        world.host,
        failure_code="insufficient_safe_storage",
        original_identity="A",
        original_footprint=A,
    )
    assert resumed.outcome is ReplanOutcome.SUCCEEDED
    assert resumed.attempts[1].candidate == "B"


def test_manual_is_not_silently_converted_to_auto(tmp_path: Path) -> None:
    world = World(tmp_path, mode=ModelSelectionMode.MANUAL)
    report = world.service.handle(
        world.host,
        failure_code="insufficient_safe_storage",
        original_identity="A",
        original_footprint=A,
    )
    assert report.outcome is ReplanOutcome.MANUAL_BLOCKED
    assert report.outcome.value == "selected_configuration_no_longer_feasible"
    assert world.models.auto_calls == 0
    assert "B" in {ident for ident, _peak in report.alternatives}
    assert all(peak in ORIGINAL.values() for _ident, peak in report.alternatives)


def test_non_capacity_failures_do_not_reduce(tmp_path: Path) -> None:
    world = World(tmp_path)
    for code in (
        "artifact_integrity",
        "unsupported_architecture",
        "policy_denial",
        "authentication_failed",
        "runtime_crash",
    ):
        report = world.service.handle(
            world.host,
            failure_code=code,
            original_identity="A",
            original_footprint=A,
        )
        assert report.outcome is ReplanOutcome.NOT_RETRYABLE, code
        assert world.funnel_calls == 0
        assert world.char.calls == []


def test_valid_runtime_is_not_reprovisioned_on_model_reduction(
    tmp_path: Path,
) -> None:
    world = World(tmp_path, installed=True, blocked=False)
    report = world.service.handle(
        world.host,
        failure_code="insufficient_safe_storage",
        original_identity="A",
        original_footprint=A,
    )
    assert report.outcome is ReplanOutcome.SUCCEEDED
    assert report.runtime_reprovision is False
    assert world.foundation.realize_calls == 0


def test_infeasible_runtime_is_not_treated_as_installed(tmp_path: Path) -> None:
    world = World(tmp_path, installed=True, blocked=True)
    report = world.service.handle(
        world.host,
        failure_code="insufficient_safe_storage",
        original_identity="A",
        original_footprint=A,
    )
    assert report.outcome is ReplanOutcome.SUCCEEDED
    assert report.runtime_reprovision is True


def test_sonar_is_not_rerun_when_empirical_is_disabled(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.service.handle(
        world.host,
        failure_code="storage_quota_exceeded",
        original_identity="A",
        original_footprint=A,
    )
    assert world.char.calls
    assert world.char.calls[0]["run_empirical"] is False


def test_runtime_stage_manual_is_blocked(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.foundation.mode = FoundationSelectionMode.MANUAL
    report = world.service.handle(
        world.host,
        failure_code="runtime_storage_infeasible",
        original_identity="vllm",
        original_footprint=24 * GIB,
        stage=ReplanStage.RUNTIME,
    )
    assert report.outcome is ReplanOutcome.MANUAL_BLOCKED
    assert world.foundation.select_auto_calls == 0


def test_requirement_bytes_on_members_never_change() -> None:
    members = _members()
    before = {item.model_id: member_footprint(item) for item in members}
    cap = peak_cap_bytes(A, 1)
    kept = tuple(item for item in members if (member_footprint(item) or 0) <= cap)
    after = {item.model_id: member_footprint(item) for item in kept}
    assert before["B"] == B
    assert after["B"] == B
    assert "A" not in after

"""Stage 1.5B — InferenceInstance lifecycle, mobility, and reconciliation."""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from dataclasses import fields
from pathlib import Path

import pytest

from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.host import fixtures
from kultrun.adapters.http.console import asset_root
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.api.contracts import ApiRequest, ApiResponse, Method
from kultrun.capacity.contracts import (
    AcceleratorCapacity,
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import HostId
from kultrun.inference.contracts import (
    DesiredState,
    InferenceInstance,
    InstanceId,
    ObservedState,
)
from kultrun.inference.service import InstanceService
from kultrun.kernel.clock import FixedClock, SystemClock
from kultrun.kernel.errors import (
    ConflictError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.main import Platform, build, config_schema, main
from kultrun.model.contracts import (
    ArtifactId,
    ArtifactState,
    MemoryPlacement,
    ModelArtifact,
    ModelId,
)
from kultrun.model.inventory import ModelInventory
from kultrun.model.store import ModelArtifactStore
from kultrun.resource.contracts import (
    LedgerHealth,
    RequestId,
    ReservationState,
    ResourceRequest,
    ResourceReservation,
    ResourceSummary,
    WorkloadType,
)
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.catalogue import RuntimeCatalogue
from tests.architecture import scan

INSTANT = dt.datetime(2026, 9, 7, 21, 0, tzinfo=dt.UTC)
GIB = 1024**3
SOURCE = Path(__file__).resolve().parent.parent / "src"


def _obj(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


SAFE = 24 * GIB
SMALL = 4 * GIB
LARGE = 20 * GIB


def _layered(safe: int) -> LayeredBytes:
    return LayeredBytes(
        reported_bytes=safe * 2,
        effective_bytes=safe,
        safe_bytes=safe,
        confidence=Confidence.HIGH,
        provenance=Provenance(
            producer=Name("test"),
            producer_version="t",
            observed_at=INSTANT,
            policy_version="t",
        ),
    )


def _envelope(
    *,
    devices: tuple[tuple[int, int], ...] = ((0, SAFE),),
    ram_safe: int = 48 * GIB,
    host_id: HostId | None = None,
) -> CapacityEnvelope:
    return CapacityEnvelope(
        host_id=host_id or HostId.generate(),
        host_fingerprint="test-host",
        computed_at=INSTANT,
        policy_version="test",
        memory=_layered(ram_safe),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        accelerators=tuple(
            AcceleratorCapacity(
                index=index,
                memory=_layered(safe),
                requirement=EvidenceRequirement.SUFFICIENT,
            )
            for index, safe in devices
        ),
        pools=(
            PoolCapacity(
                mount_point="/data",
                space=_layered(10**11),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="ext4",
            ),
        ),
    )


def _artifact(
    *,
    name: str = "probe-model",
    installed: int = 8 * GIB,
    state: ArtifactState = ArtifactState.STORED,
) -> ModelArtifact:
    return ModelArtifact(
        artifact_id=ArtifactId.generate(),
        model_id=ModelId.generate(),
        revision="rev-a",
        state=state,
        logical_name=name,
        installed_bytes=installed,
        quantization="q4",
    )


def _request(
    artifact: ModelArtifact,
    envelope: CapacityEnvelope,
    *,
    ram: int = 2 * GIB,
    vram: int = SMALL,
) -> ResourceRequest:
    return ResourceRequest(
        request_id=RequestId.generate(),
        host_id=envelope.host_id,
        artifact_id=artifact.artifact_id,
        model_id=artifact.model_id,
        plan_fingerprint="test-plan",
        placement=MemoryPlacement.DISCRETE_GPU,
        ram_bytes=ram,
        accelerator_bytes=vram,
        unified_bytes=NOT_PROVIDED,
        logical_name=artifact.logical_name,
        accelerator_index=0,
        incremental_storage_bytes=NOT_PROVIDED,
        workload_type=WorkloadType.INFERENCE,
        model_revision=artifact.revision,
        quantization=artifact.quantization,
    )


def _persist(
    inventory: ModelInventory, store: ModelArtifactStore, artifact: ModelArtifact
) -> ModelArtifact:
    path = store.manifest_path(artifact.artifact_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    inventory.put(artifact, HostId.generate())
    found = inventory.get(artifact.artifact_id)
    assert found is not None
    return found


class _Stack:
    def __init__(self, tmp_path: Path) -> None:
        self.store = FileStore(tmp_path / "records")
        self.clock = FixedClock(INSTANT)
        self.artifacts = ModelArtifactStore(tmp_path / "models")
        self.inventory = ModelInventory(self.store, self.artifacts)
        self.resources = ResourceManager(
            self.store, self.clock, AdmissionLock(tmp_path / "locks")
        )
        self.executions = ExecutionService(
            NativeProcessExecutor(SystemClock()), self.store
        )
        self.runtimes = RuntimeCatalogue((ReferenceServingRuntime(),))
        self.instances = InstanceService(
            self.store,
            self.clock,
            self.inventory,
            self.resources,
            self.executions,
            self.runtimes,
            startup_timeout=1.2,
        )
        self.envelope = _envelope()

    def stored(
        self,
        *,
        name: str = "probe-model",
        installed: int = 8 * GIB,
        state: ArtifactState = ArtifactState.STORED,
    ) -> ModelArtifact:
        return _persist(
            self.inventory,
            self.artifacts,
            _artifact(name=name, installed=installed, state=state),
        )

    def reserve(self, artifact: ModelArtifact, *, vram: int) -> ResourceReservation:
        decision = self.resources.admit(
            _request(artifact, self.envelope, vram=vram), self.envelope, artifact
        )
        assert decision.reservation is not None
        return decision.reservation

    def health(self, envelope: CapacityEnvelope | None = None) -> LedgerHealth:
        return self.resources.summary(envelope or self.envelope).health


def _platform(tmp_path: Path) -> Platform:
    configuration = config_schema().load(
        {"platform": {"state_root": str(tmp_path / "state")}}
    )
    return build(
        configuration,
        fixture=fixtures.DEFAULT_SHAPE,
        acquisition_adapter="fixture",
    )


def _call(
    platform: Platform,
    path: str,
    *,
    method: Method = Method.GET,
    query: dict[str, str] | None = None,
) -> ApiResponse:
    return platform.router.handle(
        ApiRequest(method=method, path=f"/v1{path}", query=query or {})
    )


def _health_body(instance: InferenceInstance) -> dict[str, object]:
    assert instance.endpoint is not None
    url = (
        f"{instance.endpoint.scheme}://{instance.endpoint.address}:"
        f"{instance.endpoint.port}/health"
    )
    with urllib.request.urlopen(url, timeout=1) as response:
        parsed: object = json.loads(response.read().decode("utf-8"))
        assert isinstance(parsed, dict)
        return parsed


class TestContracts:
    def test_instance_id_is_typed_and_not_a_pid(self) -> None:
        token = InstanceId.generate()
        assert token.value.startswith("inst_")
        assert token.value != "0"

    def test_desired_and_observed_are_distinct(self) -> None:
        assert {item.value for item in DesiredState} == {"running", "stopped"}
        assert {item.value for item in ObservedState} == {
            "created",
            "starting",
            "running",
            "stopping",
            "stopped",
            "failed",
            "unknown",
        }

    def test_no_static_partition_fields(self) -> None:
        names = {item.name for item in fields(ResourceSummary)}
        names |= {item.name for item in fields(InferenceInstance)}
        assert "stored_partition_bytes" not in names
        assert "active_partition_bytes" not in names
        assert "stored_plus_active_bytes" not in names


class TestCreatePreconditions:
    def test_requires_stored_and_active_match(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        stored = stack.stored()
        missing = _artifact(state=ArtifactState.ACQUIRING)
        reservation = stack.reserve(stored, vram=SMALL)
        with pytest.raises(PreconditionFailedError):
            stack.instances.create(missing, reservation)
        other = stack.stored(name="other")
        with pytest.raises(ValidationError):
            stack.instances.create(other, reservation)
        created = stack.instances.create(stored, reservation)
        assert created.observed_state is ObservedState.CREATED
        assert created.desired_state is DesiredState.STOPPED
        assert created.artifact_id == stored.artifact_id
        assert created.reservation_id == reservation.reservation_id

    def test_one_live_instance_per_reservation(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=SMALL)
        first = stack.instances.create(artifact, reservation)
        try:
            stack.instances.start(first.instance_id, ledger_health=stack.health())
            with pytest.raises(ConflictError, match="live instance"):
                stack.instances.create(artifact, reservation)
        finally:
            stack.instances.stop(first.instance_id)


class TestLifecycle:
    def test_created_start_running_stop_stopped(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=SMALL)
        instance = stack.instances.create(artifact, reservation)
        try:
            running = stack.instances.start(
                instance.instance_id, ledger_health=stack.health()
            )
            assert running.observed_state is ObservedState.RUNNING
            assert running.desired_state is DesiredState.RUNNING
            assert running.ready is True
            assert is_resolved(running.pid)
            body = _health_body(running)
            assert body["ready"] is True
            assert body["runtime"] == "reference-serving"
            same = stack.instances.start(
                instance.instance_id, ledger_health=stack.health()
            )
            assert same.pid == running.pid
            stopped = stack.instances.stop(instance.instance_id)
            assert stopped.observed_state is ObservedState.STOPPED
            again = stack.instances.stop(instance.instance_id)
            assert again.observed_state is ObservedState.STOPPED
            held = stack.resources.get(reservation.reservation_id)
            assert held is not None
            assert held.state is ReservationState.ACTIVE
        finally:
            stack.instances.stop(instance.instance_id)

    def test_restart_reuses_the_same_reservation(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=SMALL)
        instance = stack.instances.create(artifact, reservation)
        try:
            stack.instances.start(instance.instance_id, ledger_health=stack.health())
            stack.instances.stop(instance.instance_id)
            restarted = stack.instances.start(
                instance.instance_id, ledger_health=stack.health()
            )
            assert restarted.observed_state is ObservedState.RUNNING
            assert restarted.reservation_id == reservation.reservation_id
            assert restarted.instance_id == instance.instance_id
        finally:
            stack.instances.stop(instance.instance_id)

    def test_startup_exit_fails(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=SMALL)
        instance = stack.instances.create(artifact, reservation)
        failed = stack.instances.start(
            instance.instance_id,
            ledger_health=stack.health(),
            serving_mode="exit-immediately",
        )
        assert failed.observed_state is ObservedState.FAILED
        held = stack.resources.get(reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE

    def test_never_ready_fails(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=SMALL)
        instance = stack.instances.create(artifact, reservation)
        failed = stack.instances.start(
            instance.instance_id,
            ledger_health=stack.health(),
            serving_mode="never-ready",
        )
        assert failed.observed_state is ObservedState.FAILED
        assert is_resolved(failed.failure_reason)

    def test_unexpected_exit_fails_without_release(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=SMALL)
        instance = stack.instances.create(artifact, reservation)
        try:
            running = stack.instances.start(
                instance.instance_id,
                ledger_health=stack.health(),
                serving_mode="crash-after-ready",
            )
            assert running.observed_state is ObservedState.RUNNING
            import time

            deadline = time.monotonic() + 2
            observed = running
            while time.monotonic() < deadline:
                observed = stack.instances.observe(instance.instance_id)
                if observed.observed_state is ObservedState.FAILED:
                    break
                time.sleep(0.05)
            assert observed.observed_state is ObservedState.FAILED
            held = stack.resources.get(reservation.reservation_id)
            assert held is not None
            assert held.state is ReservationState.ACTIVE
        finally:
            stack.instances.stop(instance.instance_id)


class TestMultipleInstances:
    def test_independent_processes_and_stop(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        first_res = stack.reserve(artifact, vram=SMALL)
        second_res = stack.reserve(artifact, vram=SMALL)
        first = stack.instances.create(artifact, first_res)
        second = stack.instances.create(artifact, second_res)
        try:
            a = stack.instances.start(first.instance_id, ledger_health=stack.health())
            b = stack.instances.start(second.instance_id, ledger_health=stack.health())
            assert a.instance_id != b.instance_id
            assert a.reservation_id != b.reservation_id
            assert a.pid != b.pid
            assert a.endpoint is not None
            assert b.endpoint is not None
            assert a.endpoint.port != b.endpoint.port
            stack.instances.stop(a.instance_id)
            left = stack.instances.observe(b.instance_id)
            assert left.observed_state is ObservedState.RUNNING
            _health_body(left)
        finally:
            stack.instances.stop(first.instance_id)
            stack.instances.stop(second.instance_id)


class TestReservationGuard:
    def test_release_blocked_while_live_then_allowed(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=SMALL)
        instance = stack.instances.create(artifact, reservation)
        try:
            running = stack.instances.start(
                instance.instance_id, ledger_health=stack.health()
            )
            assert stack.instances.blocks_release(reservation.reservation_id)
            assert running.observed_state is ObservedState.RUNNING
        finally:
            stack.instances.stop(instance.instance_id)
        assert not stack.instances.blocks_release(reservation.reservation_id)
        released = stack.resources.release(reservation.reservation_id)
        assert released.state is ReservationState.RELEASED


class TestDynamicMobility:
    def test_capacity_follows_the_active_workload(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        large = stack.stored(name="large", installed=20 * GIB)
        small = stack.stored(name="small", installed=4 * GIB)
        small_res = stack.reserve(small, vram=SMALL)
        small_inst = stack.instances.create(small, small_res)
        try:
            stack.instances.start(small_inst.instance_id, ledger_health=stack.health())
            summary = stack.resources.summary(stack.envelope)
            assert summary.accelerators[0].safe_bytes == SAFE
            assert summary.accelerators[0].reserved_bytes == SMALL
            assert summary.accelerators[0].available_bytes == SAFE - SMALL
            assert summary.running_instances == 0
            assert not hasattr(summary, "stored_partition_bytes")
            stack.instances.stop(small_inst.instance_id)
            stack.resources.release(small_res.reservation_id)
            empty = stack.resources.summary(stack.envelope)
            assert empty.accelerators[0].reserved_bytes == 0
            assert empty.accelerators[0].available_bytes == SAFE

            large_res = stack.reserve(large, vram=LARGE)
            large_inst = stack.instances.create(large, large_res)
            stack.instances.start(large_inst.instance_id, ledger_health=stack.health())
            busy = stack.resources.summary(stack.envelope)
            assert busy.accelerators[0].reserved_bytes == LARGE
            assert busy.accelerators[0].available_bytes == SAFE - LARGE
            stack.instances.stop(large_inst.instance_id)
            stack.resources.release(large_res.reservation_id)

            again_res = stack.reserve(small, vram=SMALL)
            again = stack.instances.create(small, again_res)
            stack.instances.start(again.instance_id, ledger_health=stack.health())
            back = stack.resources.summary(stack.envelope)
            assert back.accelerators[0].reserved_bytes == SMALL
            assert back.accelerators[0].available_bytes == SAFE - SMALL
            stack.instances.stop(again.instance_id)
            stack.resources.release(again_res.reservation_id)
        finally:
            for item in stack.instances.list():
                stack.instances.stop(item.instance_id)

    def test_stored_does_not_claim_active_vram(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        large = stack.stored(name="large", installed=20 * GIB)
        small = stack.stored(name="small", installed=4 * GIB)
        reservation = stack.reserve(small, vram=SMALL)
        instance = stack.instances.create(small, reservation)
        try:
            stack.instances.start(instance.instance_id, ledger_health=stack.health())
            summary = stack.resources.summary(stack.envelope)
            assert summary.accelerators[0].reserved_bytes == SMALL
            assert large.state is ArtifactState.STORED
            stored_large = stack.inventory.get(large.artifact_id)
            assert stored_large is not None
            assert stored_large.state is ArtifactState.STORED
            assert summary.reserved_incremental_storage_bytes == 0
        finally:
            stack.instances.stop(instance.instance_id)


class TestCapacityShrink:
    def test_running_survives_overcommit(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=LARGE)
        instance = stack.instances.create(artifact, reservation)
        try:
            stack.instances.start(instance.instance_id, ledger_health=stack.health())
            shrunk = _envelope(devices=((0, 16 * GIB),), host_id=stack.envelope.host_id)
            summary = stack.resources.summary(shrunk)
            assert summary.health is LedgerHealth.OVERCOMMITTED
            assert summary.accelerators[0].available_bytes == 0
            observed = stack.instances.observe(instance.instance_id)
            assert observed.observed_state is ObservedState.RUNNING
            held = stack.resources.get(reservation.reservation_id)
            assert held is not None
            assert held.state is ReservationState.ACTIVE
            stack.instances.stop(instance.instance_id)
            with pytest.raises(PreconditionFailedError, match="OVERCOMMITTED"):
                stack.instances.start(
                    instance.instance_id, ledger_health=LedgerHealth.OVERCOMMITTED
                )
        finally:
            stack.instances.stop(instance.instance_id)


class TestReconciliation:
    def test_stale_running_is_not_trusted(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=SMALL)
        instance = stack.instances.create(artifact, reservation)
        try:
            stack.instances.start(instance.instance_id, ledger_health=stack.health())
            other_exec = ExecutionService(
                NativeProcessExecutor(SystemClock()), stack.store
            )
            other = InstanceService(
                stack.store,
                stack.clock,
                stack.inventory,
                stack.resources,
                other_exec,
                stack.runtimes,
            )
            other.reconcile()
            seen = other.observe(instance.instance_id)
            assert seen.observed_state is ObservedState.UNKNOWN
            held = stack.resources.get(reservation.reservation_id)
            assert held is not None
            assert held.state is ReservationState.ACTIVE
            assert other.blocks_release(reservation.reservation_id)
        finally:
            stack.instances.stop(instance.instance_id)


class TestSurfaces:
    def test_api_cli_console(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
        monkeypatch.setenv("KULTRUN_FIXTURE", fixtures.DEFAULT_SHAPE)
        monkeypatch.setenv("KULTRUN_MODEL_ACQUISITION_PROVIDER", "fixture")
        assert main(["models", "acquire", "tinyllama-1.1b-chat-q4"]) == 0
        platform = _platform(tmp_path)
        artifact = platform.inventory.artifacts()[0]
        reserved = _call(
            platform,
            "/resources/reservations",
            method=Method.POST,
            query={"artifact_id": artifact.artifact_id.value},
        )
        assert reserved.status == 200
        reservation = _obj(_obj(reserved.body["payload"])["reservation"])
        reservation_id = str(reservation["reservation_id"])
        refused = _call(
            platform,
            "/inference/instances",
            method=Method.POST,
            query={"reservation_id": reservation_id, "executable": "/bin/true"},
        )
        assert refused.status == 400
        created = _call(
            platform,
            "/inference/instances",
            method=Method.POST,
            query={"reservation_id": reservation_id},
        )
        assert created.status == 200
        instance_id = str(_obj(created.body["payload"])["instance_id"])
        started = None
        try:
            started = _call(
                platform,
                "/inference/instances/start",
                method=Method.POST,
                query={"instance_id": instance_id},
            )
            assert started.status == 200
            assert _obj(started.body["payload"])["observed_state"] == "running"
            blocked = _call(
                platform,
                "/resources/reservations",
                method=Method.DELETE,
                query={"reservation_id": reservation_id},
            )
            assert blocked.status == 409
            assert (
                _obj(_obj(blocked.body["error"])["context"])["reason"]
                == "reservation_in_use"
            )
            listing = _call(platform, "/inference/instances")
            listed = _obj(listing.body["payload"])
            assert listed["count"] == 1
            assert listed["fixed_stored_active_partition"] is False
            assert _call(platform, "/chat/completions").status == 404
            assert _call(platform, "/generate").status == 404
            assert main(["instances"]) == 0
            assert main(["instances", "inspect", instance_id]) == 0
        finally:
            _call(
                platform,
                "/inference/instances/stop",
                method=Method.POST,
                query={"instance_id": instance_id},
            )
        assert main(["instances", "stop", instance_id]) == 0
        released = _call(
            platform,
            "/resources/reservations",
            method=Method.DELETE,
            query={"reservation_id": reservation_id},
        )
        assert released.status == 200
        html = (asset_root() / "index.html").read_text(encoding="utf-8")
        script = (asset_root() / "app.js").read_text(encoding="utf-8")
        assert "Inference instances" in html
        assert "SAFE / RESERVED / AVAILABLE" in script or "SAFE, RESERVED" in html
        assert "capacity partitions" in script
        assert "Active Pool" not in script
        assert "/inference/instances" in script
        assert "chat" not in script
        printed = capsys.readouterr().out
        assert "inst_" in printed or instance_id in printed


class TestArchitecture:
    def test_inference_does_not_import_planning_or_platform(self) -> None:
        edges = [
            edge
            for edge in scan(SOURCE)
            if edge.source_package == "inference"
            and edge.target_package in {"planning", "platform"}
        ]
        assert edges == []

    def test_resource_does_not_import_inference(self) -> None:
        edges = [
            edge
            for edge in scan(SOURCE)
            if edge.source_package == "resource" and edge.target_package == "inference"
        ]
        assert edges == []

    def test_no_prompt_routes(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        paths = " ".join(platform.router.paths())
        assert "/chat/completions" not in paths
        assert "/generate" not in paths

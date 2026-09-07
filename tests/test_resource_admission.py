"""Stage 1.5A — admission arithmetic, reservations, release, persistence."""

from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

import pytest

from kultrun.adapters.host import fixtures
from kultrun.adapters.http.console import asset_root
from kultrun.api.contracts import ApiRequest, ApiResponse, Method
from kultrun.capacity.contracts import (
    AcceleratorCapacity,
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.errors import NotFoundError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.main import Platform, build, config_schema, main
from kultrun.model.contracts import (
    AcquisitionReceipt,
    ArtifactId,
    ArtifactState,
    MemoryPlacement,
    ModelArtifact,
    ModelId,
)
from kultrun.resource.contracts import (
    AdmissionReason,
    AdmissionVerdict,
    LedgerHealth,
    RequestId,
    ReservationId,
    ReservationState,
    ResourceRequest,
    WorkloadType,
)
from kultrun.resource.ledger import available_for_new_work, reserved_accelerator
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.manager import ResourceManager
from tests.architecture import scan

INSTANT = dt.datetime(2026, 9, 7, 10, 0, tzinfo=dt.UTC)
GIB = 1024**3
SOURCE = Path(__file__).resolve().parent.parent / "src"


def _layered(reported: int, effective: int, safe: int) -> LayeredBytes:
    return LayeredBytes(
        reported_bytes=reported,
        effective_bytes=effective,
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
    ram_safe: int = 48 * GIB,
    devices: tuple[tuple[int, int], ...] = ((0, 24 * GIB),),
    host_id: HostId | None = None,
) -> CapacityEnvelope:
    return CapacityEnvelope(
        host_id=host_id or HostId.generate(),
        host_fingerprint="test-host",
        computed_at=INSTANT,
        policy_version="test",
        memory=_layered(64 * GIB, 56 * GIB, ram_safe),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        accelerators=tuple(
            AcceleratorCapacity(
                index=index,
                memory=_layered(safe * 2, safe, safe),
                requirement=EvidenceRequirement.SUFFICIENT,
            )
            for index, safe in devices
        ),
        pools=(
            PoolCapacity(
                mount_point="/data",
                space=_layered(10**18, 10**12, 10**11),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="ext4",
            ),
        ),
    )


def _artifact(*, state: ArtifactState = ArtifactState.STORED) -> ModelArtifact:
    return ModelArtifact(
        artifact_id=ArtifactId.generate(),
        model_id=ModelId.generate(),
        revision="rev-a",
        state=state,
        logical_name="probe-model",
        installed_bytes=20 * GIB,
    )


def _request(
    artifact: ModelArtifact,
    envelope: CapacityEnvelope,
    *,
    ram: int = 8 * GIB,
    vram: int = 10 * GIB,
    index: int | None = 0,
    placement: MemoryPlacement = MemoryPlacement.DISCRETE_GPU,
    request_id: RequestId | None = None,
    unified: Maybe[int] = NOT_PROVIDED,
) -> ResourceRequest:
    return ResourceRequest(
        request_id=request_id or RequestId.generate(),
        host_id=envelope.host_id,
        artifact_id=artifact.artifact_id,
        model_id=artifact.model_id,
        plan_fingerprint="test-plan",
        placement=placement,
        ram_bytes=ram,
        accelerator_bytes=(
            vram if placement is MemoryPlacement.DISCRETE_GPU else NOT_PROVIDED
        ),
        unified_bytes=unified,
        logical_name="probe-model",
        accelerator_index=index,
        incremental_storage_bytes=NOT_PROVIDED,
        workload_type=WorkloadType.INFERENCE,
    )


def _manager(tmp_path: Path) -> ResourceManager:
    store = __import__(
        "kultrun.adapters.persistence.file_store", fromlist=["FileStore"]
    ).FileStore(tmp_path / "records")
    return ResourceManager(
        store, FixedClock(INSTANT), AdmissionLock(tmp_path / "state")
    )


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


def _store(platform: Platform, name: str) -> AcquisitionReceipt:
    host = platform.hosts.current
    envelope = platform.capacity.compute(host, {})
    entry = platform.models.acquirable(name)
    assert entry is not None
    from kultrun.model.acquisition import request_from_entry

    return platform.acquisition.acquire(
        request_from_entry(entry), envelope, host.host_id
    )


class TestArithmetic:
    def test_reservable_is_safe_minus_active(self) -> None:
        assert available_for_new_work(24 * GIB, 10 * GIB) == 14 * GIB

    def test_available_is_never_negative(self) -> None:
        assert available_for_new_work(16 * GIB, 20 * GIB) == 0

    def test_unresolved_safe_is_not_zero(self) -> None:
        assert not is_resolved(available_for_new_work(None, 10))

    def test_gpus_are_not_aggregated(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(devices=((0, 24 * GIB), (1, 24 * GIB)))
        artifact = _artifact()
        decision = manager.admit(
            _request(artifact, envelope, vram=30 * GIB, index=0),
            envelope,
            artifact,
        )
        assert decision.verdict is AdmissionVerdict.REJECTED
        assert (
            decision.reason_code
            == AdmissionReason.INSUFFICIENT_SAFE_ACCELERATOR.value
        )


class TestAdmissionLifecycle:
    def test_cumulative_and_release(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope()
        first = _artifact()
        second = _artifact()
        third = _artifact()
        a = manager.admit(_request(first, envelope, vram=10 * GIB), envelope, first)
        assert a.verdict is AdmissionVerdict.ADMITTED
        assert a.serving is False
        b = manager.admit(_request(second, envelope, vram=12 * GIB), envelope, second)
        assert b.verdict is AdmissionVerdict.ADMITTED
        c = manager.admit(_request(third, envelope, vram=8 * GIB), envelope, third)
        assert c.verdict is AdmissionVerdict.REJECTED
        assert a.reservation is not None
        manager.release(a.reservation.reservation_id)
        again = manager.admit(_request(third, envelope, vram=8 * GIB), envelope, third)
        assert again.verdict is AdmissionVerdict.ADMITTED
        summary = manager.summary(envelope)
        assert summary.active_count == 2
        assert summary.accelerators[0].reserved_bytes == 20 * GIB
        assert summary.accelerators[0].available_bytes == 4 * GIB
        assert summary.running_instances == 0

    def test_same_artifact_two_reservations(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope()
        artifact = _artifact()
        first = manager.admit(
            _request(artifact, envelope, vram=8 * GIB), envelope, artifact
        )
        second = manager.admit(
            _request(artifact, envelope, vram=8 * GIB), envelope, artifact
        )
        assert first.verdict is AdmissionVerdict.ADMITTED
        assert second.verdict is AdmissionVerdict.ADMITTED
        assert first.reservation is not None
        assert second.reservation is not None
        assert first.reservation.reservation_id != second.reservation.reservation_id

    def test_exact_re_request_is_idempotent(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope()
        artifact = _artifact()
        request = _request(artifact, envelope, vram=8 * GIB)
        first = manager.admit(request, envelope, artifact)
        second = manager.admit(request, envelope, artifact)
        assert second.reused is True
        assert first.reservation is not None
        assert second.reservation is not None
        assert second.reservation.reservation_id == first.reservation.reservation_id
        assert manager.summary(envelope).active_count == 1

    def test_release_is_idempotent(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope()
        artifact = _artifact()
        decision = manager.admit(_request(artifact, envelope), envelope, artifact)
        assert decision.reservation is not None
        first = manager.release(decision.reservation.reservation_id)
        second = manager.release(decision.reservation.reservation_id)
        assert first.state is ReservationState.RELEASED
        assert second.state is ReservationState.RELEASED
        assert manager.summary(envelope).active_count == 0

    def test_non_stored_is_rejected(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope()
        for state in (
            ArtifactState.REMOTE,
            ArtifactState.ACQUIRING,
            ArtifactState.INVALID,
            ArtifactState.DELETED,
        ):
            artifact = _artifact(state=state)
            decision = manager.admit(_request(artifact, envelope), envelope, artifact)
            assert decision.verdict is AdmissionVerdict.REJECTED
            assert decision.reason_code == AdmissionReason.ARTIFACT_NOT_STORED.value

    def test_cpu_only(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(devices=())
        artifact = _artifact()
        decision = manager.admit(
            _request(
                artifact,
                envelope,
                placement=MemoryPlacement.CPU_ONLY,
                index=None,
                vram=0,
            ),
            envelope,
            artifact,
        )
        assert decision.verdict is AdmissionVerdict.ADMITTED
        assert decision.reservation is not None
        assert decision.reservation.accelerator_index is None

    def test_unresolved_requirement(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope()
        artifact = _artifact()
        request = _request(artifact, envelope)
        request = ResourceRequest(
            request_id=request.request_id,
            host_id=request.host_id,
            artifact_id=request.artifact_id,
            model_id=request.model_id,
            plan_fingerprint=request.plan_fingerprint,
            placement=request.placement,
            ram_bytes=NOT_PROVIDED,
            accelerator_bytes=10 * GIB,
            unified_bytes=NOT_PROVIDED,
            accelerator_index=0,
        )
        decision = manager.admit(request, envelope, artifact)
        assert decision.verdict is AdmissionVerdict.UNRESOLVED

    def test_stored_disk_is_not_reserved(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope()
        artifact = _artifact()
        manager.admit(_request(artifact, envelope), envelope, artifact)
        summary = manager.summary(envelope)
        assert summary.reserved_incremental_storage_bytes == 0
        assert artifact.installed_bytes == 20 * GIB

    def test_unknown_reservation_release(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        with pytest.raises(NotFoundError):
            manager.release(ReservationId.generate())

    def test_unknown_accelerator_is_rejected(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope()
        artifact = _artifact()
        decision = manager.admit(
            _request(artifact, envelope, index=7), envelope, artifact
        )
        assert decision.verdict is AdmissionVerdict.REJECTED
        assert (
            decision.reason_code
            == AdmissionReason.SELECTED_ACCELERATOR_UNKNOWN.value
        )


class TestOvercommitAndRestart:
    def test_capacity_shrink_does_not_resize(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        wide = _envelope()
        artifact = _artifact()
        decision = manager.admit(
            _request(artifact, wide, vram=20 * GIB), wide, artifact
        )
        assert decision.verdict is AdmissionVerdict.ADMITTED
        assert decision.reservation is not None
        assert decision.reservation.state is ReservationState.ACTIVE
        narrow = _envelope(devices=((0, 16 * GIB),), host_id=wide.host_id)
        summary = manager.summary(narrow)
        assert summary.health is LedgerHealth.OVERCOMMITTED
        assert summary.accelerators[0].reserved_bytes == 20 * GIB
        assert summary.accelerators[0].available_bytes == 0
        other = _artifact()
        denied = manager.admit(
            _request(other, narrow, vram=1 * GIB), narrow, other
        )
        assert denied.verdict is AdmissionVerdict.REJECTED
        assert denied.reason_code == AdmissionReason.LEDGER_OVERCOMMITTED.value
        held = manager.get(decision.reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE
        assert held.admitted_vram_bytes == 20 * GIB

    def test_restart_recomputes_availability(self, tmp_path: Path) -> None:
        first = _manager(tmp_path)
        envelope = _envelope()
        artifact = _artifact()
        decision = first.admit(
            _request(artifact, envelope, vram=10 * GIB), envelope, artifact
        )
        assert decision.reservation is not None
        second = _manager(tmp_path)
        found = second.get(decision.reservation.reservation_id)
        assert found is not None
        assert found.state is ReservationState.ACTIVE
        summary = second.summary(envelope)
        assert summary.active_count == 1
        assert summary.accelerators[0].available_bytes == 14 * GIB

    def test_concurrent_admission_does_not_oversubscribe(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(devices=((0, 10 * GIB),))
        results: list[str] = []

        def run(vram: int) -> None:
            artifact = _artifact()
            decision = manager.admit(
                _request(artifact, envelope, ram=1 * GIB, vram=vram),
                envelope,
                artifact,
            )
            results.append(decision.verdict.value)

        workers = [
            threading.Thread(target=run, args=(8 * GIB,)) for _ in range(2)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert results.count("admitted") == 1
        assert results.count("rejected") == 1
        assert manager.summary(envelope).active_count == 1
        assert reserved_accelerator(manager.reservations(), 0) == 8 * GIB


class TestProductSurfaces:
    def test_api_derives_amounts(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        acquired = _store(platform, "tinyllama-1.1b-chat-q4")
        refused = _call(
            platform,
            "/resources/reservations",
            method=Method.POST,
            query={"artifact_id": acquired.artifact_id.value, "vram_bytes": "1"},
        )
        assert refused.status == 400
        empty = _call(platform, "/resources")
        assert empty.status == 200
        payload = empty.body["payload"]
        assert isinstance(payload, dict)
        assert payload["serving"] is False
        assert payload["running_instances"] == 0
        summary = payload["summary"]
        assert isinstance(summary, dict)
        assert summary["active_count"] == 0
        reserved = _call(
            platform,
            "/resources/reservations",
            method=Method.POST,
            query={"artifact_id": acquired.artifact_id.value},
        )
        assert reserved.status == 200
        decision = reserved.body["payload"]
        assert isinstance(decision, dict)
        assert decision["verdict"] == "admitted"
        assert decision["serving"] is False
        listing = _call(platform, "/resources/reservations").body["payload"]
        assert isinstance(listing, dict)
        assert listing["count"] == 1
        reservation = decision["reservation"]
        assert isinstance(reservation, dict)
        reservation_id = reservation["reservation_id"]
        released = _call(
            platform,
            "/resources/reservations",
            method=Method.DELETE,
            query={"reservation_id": str(reservation_id)},
        )
        assert released.status == 200
        after = _call(platform, "/resources/reservations").body["payload"]
        assert isinstance(after, dict)
        assert after["count"] == 0

    def test_cli_and_console(
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
        artifact_id = platform.inventory.artifacts()[0].artifact_id.value
        assert main(["resources"]) == 0
        assert "reserved is not running" in capsys.readouterr().out
        assert main(["resources", "reserve", artifact_id]) == 0
        assert main(["resources", "reservations"]) == 0
        printed = capsys.readouterr().out
        assert "serving no" in printed
        reservation_id = platform.resources.reservations()[0].reservation_id.value
        assert main(["resources", "release", reservation_id]) == 0
        html = (asset_root() / "index.html").read_text(encoding="utf-8")
        script = (asset_root() / "app.js").read_text(encoding="utf-8")
        assert "Resource reservations" in html
        assert "Reserved resources are platform commitments" in html
        assert "/resources/reservations" in script
        assert "renderResources" in script
        assert "GPU allocated" not in script

    def test_regressions(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        assert _call(platform, "/host").status == 200
        assert _call(platform, "/capacity").status == 200
        assert _call(platform, "/storage/sanity").status == 200
        catalog = _call(platform, "/models").body["payload"]
        assert isinstance(catalog, dict)
        assert len(catalog["candidates"]) == 19
        selection = _call(platform, "/models/selection").body["payload"]
        assert isinstance(selection, dict)
        assert selection["download"] is False
        inventory = _call(platform, "/models/inventory").body["payload"]
        assert isinstance(inventory, dict)
        assert inventory["serving"] is False


class TestArchitecture:
    def test_planning_does_not_import_resource(self) -> None:
        edges = [
            edge
            for edge in scan(SOURCE)
            if edge.source_package == "planning" and edge.target_package == "resource"
        ]
        assert edges == []

    def test_resource_does_not_import_planning_or_inference(self) -> None:
        edges = [
            edge
            for edge in scan(SOURCE)
            if edge.source_package == "resource"
            and edge.target_package in {"planning", "inference", "runtime"}
        ]
        assert edges == []

    def test_no_inference_instance_created(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope()
        artifact = _artifact()
        manager.admit(_request(artifact, envelope), envelope, artifact)
        from kultrun.inference.contracts import InferenceInstance

        store = manager._store
        assert store.records(InferenceInstance) == ()

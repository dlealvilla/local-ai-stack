"""Stage 1.4C — acquisition, verification, plural inventory, safe delete."""

from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

import pytest

from kultrun.adapters.acquisition.fixture import FixtureAcquisitionProvider
from kultrun.adapters.host import fixtures
from kultrun.adapters.http.console import asset_root
from kultrun.adapters.model_source.candidates import (
    ACCEPTANCE_LOGICAL,
    packaged_candidates,
)
from kultrun.api.contracts import ApiRequest, ApiResponse, Method
from kultrun.capacity.contracts import (
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.errors import (
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import to_dict
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.main import ACQUISITION_VARIABLE, Platform, build, config_schema, main
from kultrun.model.acquisition import (
    AcquisitionService,
    identity_key,
    needed_bytes,
    request_from_entry,
    safe_storage,
)
from kultrun.model.contracts import (
    AcquisitionFailureReason,
    AcquisitionId,
    ArtifactId,
    ArtifactState,
    InventoryState,
    ModelAcquisitionRequest,
    ModelId,
)
from kultrun.model.inventory import ModelInventory
from kultrun.model.ports import ModelAcquisitionProvider
from kultrun.model.store import ModelArtifactStore
from kultrun.storage.topology import mount_for_path
from tests.architecture import scan
from tests.test_capacity import host as capacity_host
from tests.test_capacity import mount
from tests.test_capacity import service as capacity_service

INSTANT = dt.datetime(2026, 9, 7, 9, 0, tzinfo=dt.UTC)
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
    *, reported: int = 10**18, effective: int = 10**12, safe: int = 10**9
) -> CapacityEnvelope:
    return CapacityEnvelope(
        host_id=HostId.generate(),
        host_fingerprint="test",
        computed_at=INSTANT,
        policy_version="test",
        memory=_layered(64, 64, 32),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        pools=(
            PoolCapacity(
                mount_point="/data",
                space=_layered(reported, effective, safe),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="ext4",
            ),
        ),
    )


def _request(**overrides: object) -> ModelAcquisitionRequest:
    fields: dict[str, object] = {
        "request_id": AcquisitionId.generate(),
        "model_id": ModelId.generate(),
        "logical_name": Name("probe-model"),
        "source": Name("huggingface"),
        "source_ref": "probe/model",
        "requested_revision": "rev-a",
        "quantization": "q4_k",
        "expected_storage_bytes": 1000,
        "expected_peak_bytes": 2000,
    }
    fields.update(overrides)
    return ModelAcquisitionRequest(**fields)  # type: ignore[arg-type]


def _service(
    tmp_path: Path, *, fail: str | None = None
) -> tuple[AcquisitionService, ModelInventory, ModelArtifactStore, HostId]:
    store = __import__(
        "kultrun.adapters.persistence.file_store", fromlist=["FileStore"]
    ).FileStore(tmp_path / "records")
    artifacts = ModelArtifactStore(tmp_path / "state")
    inventory = ModelInventory(store, artifacts)
    service = AcquisitionService(
        FixtureAcquisitionProvider(fail=fail),
        inventory,
        artifacts,
        FixedClock(INSTANT),
    )
    return service, inventory, artifacts, HostId.generate()


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


class TestContractsAndPort:
    def test_the_provider_is_a_port(self) -> None:
        provider: ModelAcquisitionProvider = FixtureAcquisitionProvider()
        assert provider.identity.value == "fixture"
        assert provider.pin_revision(_request()) == "rev-a"

    def test_artifact_id_is_not_a_repo_name(self) -> None:
        artifact_id = ArtifactId.generate()
        assert artifact_id.value.startswith("artifact_")
        assert "/" not in artifact_id.value

    def test_revisions_are_distinct_identities(self) -> None:
        first = identity_key(
            model_id="model_aa", revision="aaa", quantization="q4", artifact_format=""
        )
        second = identity_key(
            model_id="model_aa", revision="bbb", quantization="q4", artifact_format=""
        )
        assert first != second

    def test_quantizations_are_distinct_identities(self) -> None:
        first = identity_key(
            model_id="model_aa", revision="aaa", quantization="q4", artifact_format=""
        )
        second = identity_key(
            model_id="model_aa", revision="aaa", quantization="fp16", artifact_format=""
        )
        assert first != second

    def test_lifecycle_has_no_serving_states(self) -> None:
        assert {item.value for item in ArtifactState} == {
            "remote",
            "acquiring",
            "stored",
            "invalid",
            "deleted",
        }
        assert "running" not in {item.value for item in ArtifactState}

    def test_request_rejects_nothing_because_paths_are_not_fields(self) -> None:
        request = _request()
        assert not hasattr(request, "destination")
        assert not hasattr(request, "path")

    def test_unresolved_size_is_not_zero(self) -> None:
        request = _request(
            expected_storage_bytes=NOT_PROVIDED, expected_peak_bytes=NOT_PROVIDED
        )
        assert needed_bytes(request) is None


class TestSafeStoragePreflight:
    def test_safe_is_authoritative(self) -> None:
        envelope = _envelope(reported=10**18, effective=10**15, safe=50)
        mount_point, safe = safe_storage(envelope)
        assert mount_point == "/data"
        assert safe == 50

    def test_insufficient_safe_storage_fails_before_mutation(
        self, tmp_path: Path
    ) -> None:
        service, inventory, artifacts, host_id = _service(tmp_path)
        with pytest.raises(PreconditionFailedError) as error:
            service.acquire(
                _request(expected_peak_bytes=10_000),
                _envelope(safe=100),
                host_id,
            )
        assert error.value.context["reason"] == (
            AcquisitionFailureReason.INSUFFICIENT_SAFE_STORAGE.value
        )
        assert inventory.artifacts() == ()
        assert not any(artifacts.root.joinpath("artifacts").iterdir())

    def test_unresolved_requirement_is_refused(self, tmp_path: Path) -> None:
        service, inventory, _, host_id = _service(tmp_path)
        with pytest.raises(PreconditionFailedError) as error:
            service.acquire(
                _request(
                    expected_peak_bytes=NOT_PROVIDED,
                    expected_storage_bytes=NOT_PROVIDED,
                ),
                _envelope(),
                host_id,
            )
        assert error.value.context["reason"] == (
            AcquisitionFailureReason.UNRESOLVED_STORAGE_REQUIREMENT.value
        )
        assert inventory.artifacts() == ()


class TestFixtureLifecycle:
    def test_empty_one_and_many(self, tmp_path: Path) -> None:
        service, inventory, _, host_id = _service(tmp_path)
        envelope = _envelope()
        assert inventory.artifacts() == ()
        first = service.acquire(_request(logical_name=Name("one")), envelope, host_id)
        assert first.outcome == "stored"
        assert first.state is ArtifactState.STORED
        assert first.serving is False
        second = service.acquire(
            _request(logical_name=Name("two"), requested_revision="rev-b"),
            envelope,
            host_id,
        )
        third = service.acquire(
            _request(logical_name=Name("three"), quantization="fp16"),
            envelope,
            host_id,
        )
        stored = inventory.artifacts()
        assert len(stored) == 3
        assert {item.artifact_id for item in stored} == {
            first.artifact_id,
            second.artifact_id,
            third.artifact_id,
        }

    def test_revisions_and_quantizations_stay_distinct(self, tmp_path: Path) -> None:
        service, inventory, _, host_id = _service(tmp_path)
        envelope = _envelope()
        model = ModelId.generate()
        service.acquire(
            _request(model_id=model, requested_revision="aaa", quantization="q4_k"),
            envelope,
            host_id,
        )
        service.acquire(
            _request(model_id=model, requested_revision="bbb", quantization="q4_k"),
            envelope,
            host_id,
        )
        service.acquire(
            _request(model_id=model, requested_revision="aaa", quantization="fp16"),
            envelope,
            host_id,
        )
        assert len(inventory.artifacts()) == 3

    def test_exact_reacquire_reuses(self, tmp_path: Path) -> None:
        service, inventory, _, host_id = _service(tmp_path)
        request = _request()
        first = service.acquire(request, _envelope(), host_id)
        second = service.acquire(request, _envelope(), host_id)
        assert second.reused is True
        assert second.artifact_id == first.artifact_id
        assert len(inventory.artifacts()) == 1

    def test_failed_acquisition_is_not_stored(self, tmp_path: Path) -> None:
        service, inventory, artifacts, host_id = _service(tmp_path, fail="network")
        receipt = service.acquire(_request(), _envelope(), host_id)
        assert receipt.outcome == "failed"
        assert receipt.state is ArtifactState.INVALID
        stored = [
            item for item in inventory.artifacts() if item.state is ArtifactState.STORED
        ]
        assert stored == []
        assert not any((artifacts.root / "artifacts").glob("*"))

    def test_corrupt_file_is_not_stored(self, tmp_path: Path) -> None:
        service, inventory, _, host_id = _service(tmp_path, fail="corrupt")
        receipt = service.acquire(_request(), _envelope(), host_id)
        assert receipt.outcome == "failed"
        assert (
            receipt.failure_reason == AcquisitionFailureReason.VERIFICATION_FAILED.value
        )
        assert all(
            item.state is not ArtifactState.STORED for item in inventory.artifacts()
        )

    def test_interrupted_acquisition_is_not_stored(self, tmp_path: Path) -> None:
        service, _, artifacts, host_id = _service(tmp_path, fail="interrupt")
        receipt = service.acquire(_request(), _envelope(), host_id)
        assert receipt.state is not ArtifactState.STORED
        assert not any((artifacts.root / "artifacts").glob("*"))

    def test_delete_one_leaves_the_other(self, tmp_path: Path) -> None:
        service, inventory, artifacts, host_id = _service(tmp_path)
        first = service.acquire(
            _request(logical_name=Name("keep")), _envelope(), host_id
        )
        second = service.acquire(
            _request(logical_name=Name("drop"), requested_revision="other"),
            _envelope(),
            host_id,
        )
        deleted = service.delete(second.artifact_id, host_id)
        assert deleted.state is ArtifactState.DELETED
        remaining = inventory.artifacts()
        assert [item.artifact_id for item in remaining] == [first.artifact_id]
        assert artifacts.artifact_dir(first.artifact_id).is_dir()
        assert not artifacts.artifact_dir(second.artifact_id).exists()
        tombstones = inventory.artifacts(include_deleted=True)
        assert any(item.state is ArtifactState.DELETED for item in tombstones)

    def test_missing_manifest_is_not_healthy(self, tmp_path: Path) -> None:
        service, inventory, artifacts, host_id = _service(tmp_path)
        receipt = service.acquire(_request(), _envelope(), host_id)
        artifacts.manifest_path(receipt.artifact_id).unlink()
        observed = inventory.get(receipt.artifact_id)
        assert observed is not None
        assert observed.state is ArtifactState.INVALID

    def test_concurrent_exact_acquire_does_not_duplicate(self, tmp_path: Path) -> None:
        service, inventory, _, host_id = _service(tmp_path)
        request = _request()
        envelope = _envelope()
        results: list[str] = []

        def run() -> None:
            receipt = service.acquire(request, envelope, host_id)
            results.append(receipt.artifact_id.value)

        workers = [threading.Thread(target=run) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert len(set(results)) == 1
        assert len(inventory.artifacts()) == 1


class TestDeleteSafety:
    def test_path_traversal_is_not_an_artifact_id(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactId.parse("../etc/passwd")
        with pytest.raises(ValidationError):
            ArtifactId.parse("/tmp/model")

    def test_delete_outside_the_store_is_impossible(self, tmp_path: Path) -> None:
        service, _, artifacts, host_id = _service(tmp_path)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret").write_text("no", encoding="utf-8")
        assert not artifacts.contains(outside)
        with pytest.raises(NotFoundError):
            service.delete(ArtifactId.generate(), host_id)
        assert (outside / "secret").read_text(encoding="utf-8") == "no"


class TestCredentialsStayOut:
    def test_persisted_artifact_has_no_token(self, tmp_path: Path) -> None:
        service, inventory, _, host_id = _service(tmp_path)
        request = _request(credential_ref="HF_TOKEN")
        receipt = service.acquire(request, _envelope(), host_id)
        artifact = inventory.get(receipt.artifact_id)
        assert artifact is not None
        payload = str(to_dict(artifact))
        assert "hf_" not in payload
        assert "HF_TOKEN" not in payload or "credential" not in payload.lower()
        assert "token" not in payload.lower()


class TestApiCliConsole:
    def test_catalog_selection_and_inventory_are_distinct(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        catalog = _call(platform, "/models")
        assert catalog.status == 200
        payload = catalog.body["payload"]
        assert isinstance(payload, dict)
        assert payload["download"] is False
        assert len(payload["candidates"]) == 19
        selection = _call(platform, "/models/selection")
        assert selection.status == 200
        inventory = _call(platform, "/models/inventory")
        assert inventory.status == 200
        body = inventory.body["payload"]
        assert isinstance(body, dict)
        assert body["artifacts"] == []
        assert body["stored_implies_running"] is False
        assert body["serving"] is False
        assert body["running"] == []

    def test_acquire_and_delete_through_the_api(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        refused = _call(
            platform,
            "/models/acquire",
            method=Method.POST,
            query={"candidate": ACCEPTANCE_LOGICAL, "path": "/tmp/out"},
        )
        assert refused.status == 400
        acquired = _call(
            platform,
            "/models/acquire",
            method=Method.POST,
            query={"candidate": ACCEPTANCE_LOGICAL},
        )
        assert acquired.status == 200
        receipt = acquired.body["payload"]
        assert isinstance(receipt, dict)
        assert receipt["serving"] is False
        assert receipt["state"] == "stored"
        second = _call(
            platform,
            "/models/acquire",
            method=Method.POST,
            query={"candidate": "tinyllama-1.1b-chat-q4"},
        )
        assert second.status == 200
        listing = _call(platform, "/models/inventory").body["payload"]
        assert isinstance(listing, dict)
        assert listing["count"] == 2
        artifact_id = receipt["artifact_id"]
        deleted = _call(
            platform,
            "/models/artifact",
            method=Method.DELETE,
            query={"artifact_id": str(artifact_id)},
        )
        assert deleted.status == 200
        left = _call(platform, "/models/inventory").body["payload"]
        assert isinstance(left, dict)
        assert left["count"] == 1
        remaining = left["artifacts"]
        assert isinstance(remaining, list)
        assert remaining[0]["logical_name"] == "tinyllama-1.1b-chat-q4"

    def test_cli_inventory_acquire_delete(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv(ACQUISITION_VARIABLE, "fixture")
        monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
        monkeypatch.setenv("KULTRUN_FIXTURE", fixtures.DEFAULT_SHAPE)
        assert main(["models", "inventory"]) == 0
        assert "empty inventory" in capsys.readouterr().out
        assert main(["models", "acquire", ACCEPTANCE_LOGICAL]) == 0
        assert main(["models", "acquire", "tinyllama-1.1b-chat-q4"]) == 0
        assert main(["models", "inventory"]) == 0
        printed = capsys.readouterr().out
        assert "serving no" in printed
        assert "stored is not running" in printed
        platform = _platform(tmp_path)
        artifacts = platform.inventory.artifacts()
        assert len(artifacts) == 2
        assert main(["models", "delete", artifacts[0].artifact_id.value]) == 0
        assert len(_platform(tmp_path).inventory.artifacts()) == 1

    def test_console_has_an_inventory_panel(self) -> None:
        html = (asset_root() / "index.html").read_text(encoding="utf-8")
        script = (asset_root() / "app.js").read_text(encoding="utf-8")
        assert "Model inventory" in html
        assert "Stored is not running" in html
        assert "/models/inventory" in script
        assert "renderInventory" in script
        assert "Stop" not in html.split('id="inventory-panel"')[1].split("<section")[0]
        assert "Unload" not in script


class TestPipelineRegression:
    def test_catalog_count_and_source_still_do_not_download(self) -> None:
        assert len(packaged_candidates()) == 19
        names = {entry.metadata.logical_name.value for entry in packaged_candidates()}
        assert ACCEPTANCE_LOGICAL not in names
        source = (
            Path(__file__).resolve().parent.parent
            / "src/kultrun/adapters/model_source/huggingface.py"
        ).read_text(encoding="utf-8")
        assert "import huggingface_hub" not in source
        assert "from huggingface_hub" not in source

    def test_acquisition_preserves_candidate_identity(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        entry = next(
            item
            for item in platform.models.entries()
            if item.metadata.logical_name.value == "tinyllama-1.1b-chat-q4"
        )
        request = request_from_entry(entry)
        assert request.model_id == entry.metadata.model_id
        assert request.quantization == entry.metadata.quantization
        assert request.source_ref == entry.metadata.source_ref
        host = platform.hosts.current
        envelope = platform.capacity.compute(host, {})
        receipt = platform.acquisition.acquire(
            request,
            envelope,
            host.host_id,
            destination_mount=mount_for_path(
                platform.plane.state_root / "models", host
            ),
        )
        stored = platform.inventory.get(receipt.artifact_id)
        assert stored is not None
        assert stored.model_id == entry.metadata.model_id
        assert stored.quantization == entry.metadata.quantization

    def test_selection_is_unchanged(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        payload = _call(platform, "/models/selection").body["payload"]
        assert isinstance(payload, dict)
        assert payload["download"] is False
        recommendation = payload["recommendation"]
        assert recommendation is not None

    def test_host_capacity_sonar_still_answer(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        assert _call(platform, "/host").status == 200
        assert _call(platform, "/capacity").status == 200
        assert _call(platform, "/storage/sanity").status == 200

    def test_real_capacity_service_still_uses_safe(self) -> None:
        envelope = capacity_service().compute(
            capacity_host(mounts=(mount("/data", filesystem="ext4"),)), {}
        )
        mount_point, safe = safe_storage(envelope)
        assert mount_point == "/data"
        assert is_resolved(safe)
        pool = envelope.pools[0]
        assert safe == pool.space.safe_bytes
        assert safe != pool.space.reported_bytes


class TestArchitectureBoundaries:
    def test_core_model_does_not_import_the_hub(self) -> None:
        for path in (SOURCE / "kultrun" / "model").glob("*.py"):
            assert "huggingface_hub" not in path.read_text(encoding="utf-8")

    def test_acquisition_does_not_import_planning_or_resource(self) -> None:
        edges = [
            edge
            for edge in scan(SOURCE)
            if (
                edge.source_module.startswith("kultrun.model.acquisition")
                or edge.source_module.startswith("kultrun.adapters.acquisition")
            )
            and edge.target_package in {"planning", "resource", "inference", "runtime"}
        ]
        assert edges == []

    def test_inventory_state_running_is_never_written(self, tmp_path: Path) -> None:
        service, inventory, _, host_id = _service(tmp_path)
        service.acquire(_request(), _envelope(), host_id)
        for artifact in inventory.artifacts():
            record = inventory.record(artifact.artifact_id)
            assert record is not None
            assert record.state is not InventoryState.RUNNING
            assert record.state is not InventoryState.LOADED
            assert record.state is not InventoryState.STOPPED

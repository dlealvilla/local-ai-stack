"""Rukan deployment coordinator. The physical runtime is the local probe."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.machi.test_plan import _device, _envelope, _foundation, _inputs
from tests.machi.test_serve import ProbeRuntime

from machi.adapters.admit.log import StoreReservationLog
from machi.adapters.foundation.process import NativeProcessRunner
from machi.adapters.model.warehouse import prepare_staging, promote, warehouse_root
from machi.adapters.persistence.file_store import FileStore
from machi.adapters.rukan.deploy import DeploymentCoordinator, reject_deploy_body
from machi.adapters.serve.endpoint import choose_port
from machi.adapters.serve.log import StoreServeLog
from machi.admit.contracts import ReservationState, ResourceReservation
from machi.admit.service import ResourceManager
from machi.foundation.contracts import ManagedGeneration
from machi.kernel.clock import SystemClock
from machi.kernel.errors import ValidationError
from machi.model.contracts import ModelArtifact, ModelFileRecord
from machi.serve.policy import ServePolicy
from machi.serve.service import ServeService

NOW = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


def test_browser_cannot_submit_plan_authority() -> None:
    assert reject_deploy_body({"artifact_id": "mart", "request_key": "k", "plan_id": "p"})  # noqa: E501
    assert reject_deploy_body({"artifact_id": "mart"})


def test_deploy_reaches_ready_and_is_idempotent(tmp_path: Path) -> None:
    content = b"weights-for-probe"
    digest = hashlib.sha256(content).hexdigest()
    staged = prepare_staging(tmp_path, "mart_plan")
    (staged / "model.safetensors").write_bytes(content)
    inputs = _inputs()
    artifact = inputs.artifact
    assert artifact is not None
    artifact = ModelArtifact(
        artifact_id=artifact.artifact_id,
        model_id=artifact.model_id,
        source_kind=artifact.source_kind,
        repository=artifact.repository,
        immutable_revision=artifact.immutable_revision,
        variant=artifact.variant,
        lifecycle=artifact.lifecycle,
        total_bytes=len(content),
        files=(
            ModelFileRecord(
                relative_path="model.safetensors",
                size_bytes=len(content),
                sha256=digest,
            ),
        ),
        config_sha256=artifact.config_sha256,
        derivation=artifact.derivation,
        base_model=artifact.base_model,
        parent_artifact_id=artifact.parent_artifact_id,
        acquired_at=artifact.acquired_at,
    )
    inputs = _inputs(artifact=artifact)
    promote(tmp_path, artifact, staged)
    _store_inputs(tmp_path, inputs)
    coordinator = _coordinator(tmp_path)
    first = coordinator.deploy(
        artifact_id=artifact.artifact_id, request_key="req-1", actor="local_admin_ui", now=NOW  # noqa: E501
    )
    assert first.state == "ready"
    assert first.reservation_id
    assert first.instance_id
    again = coordinator.deploy(
        artifact_id=artifact.artifact_id, request_key="req-1", actor="local_admin_ui", now=NOW  # noqa: E501
    )
    assert again.operation_id == first.operation_id
    assert again.instance_id == first.instance_id
    with pytest.raises(ValidationError, match="reused"):
        coordinator.deploy(
            artifact_id="mart_other", request_key="req-1", actor="local_admin_ui", now=NOW  # noqa: E501
        )
    _stop(coordinator, first.instance_id)
    coordinator.close()


def test_missing_foundation_fails_before_admission(tmp_path: Path) -> None:
    content = b"weights-for-probe"
    digest = hashlib.sha256(content).hexdigest()
    staged = prepare_staging(tmp_path, "mart_plan")
    (staged / "model.safetensors").write_bytes(content)
    inputs = _inputs()
    artifact = inputs.artifact
    assert artifact is not None
    artifact = ModelArtifact(
        artifact_id=artifact.artifact_id,
        model_id=artifact.model_id,
        source_kind=artifact.source_kind,
        repository=artifact.repository,
        immutable_revision=artifact.immutable_revision,
        variant=artifact.variant,
        lifecycle=artifact.lifecycle,
        total_bytes=len(content),
        files=(ModelFileRecord("model.safetensors", len(content), digest),),
        config_sha256=artifact.config_sha256,
        derivation=artifact.derivation,
        base_model=artifact.base_model,
        parent_artifact_id=artifact.parent_artifact_id,
        acquired_at=artifact.acquired_at,
    )
    promote(tmp_path, artifact, staged)
    coordinator = _coordinator(tmp_path)
    view = coordinator.deploy(
        artifact_id=artifact.artifact_id, request_key="req-missing", actor="local_admin_ui", now=NOW  # noqa: E501
    )
    assert view.state == "failed"
    assert view.failure == "foundation_not_ready"
    assert view.reservation_id == ""
    coordinator.close()


def _coordinator(root: Path, mode: str = "ok") -> DeploymentCoordinator:
    store = FileStore(root)
    manager = ResourceManager(StoreReservationLog(store))
    runtime = ProbeRuntime(NativeProcessRunner(), mode)
    serve = ServeService(
        StoreServeLog(store),
        runtime,
        manager,
        ServePolicy(startup_timeout_seconds=2, stop_grace_seconds=1),
        SystemClock(),
        root,
        choose_port,
    )
    return DeploymentCoordinator(root, state_root=root, serve=serve, manager=manager)


def _stop(coordinator: DeploymentCoordinator, instance_id: str) -> None:
    if instance_id:
        coordinator._serve.stop(instance_id)


def _store_inputs(root: Path, inputs: object) -> None:
    store = FileStore(root)
    plan = inputs
    assert plan.artifact is not None
    generation = plan.foundation.generation_id
    assert isinstance(generation, str)
    store.create(plan.artifact.artifact_id, plan.artifact)
    store.create(plan.foundation.selection_id, plan.foundation)
    store.create(plan.envelope.evidence_id, plan.envelope)
    store.create(plan.selection.selection_id, plan.selection)
    store.create(plan.available.snapshot_id, plan.available)
    store.create(plan.deployable.snapshot_id, plan.deployable)
    store.create(plan.qualification.qualification_id, plan.qualification)
    store.create("cap_runtime", plan.capability)
    store.create(
        generation,
        ManagedGeneration(
            generation_id=generation,
            candidate_id="vllm-0.18.0-cuda",
            python_path="/usr/bin/python3",
            vllm_version="0.18.0",
            created_at=NOW,
        ),
    )


def _prepared(tmp_path: Path):
    content = b"weights-for-probe"
    digest = hashlib.sha256(content).hexdigest()
    staged = prepare_staging(tmp_path, "mart_plan")
    (staged / "model.safetensors").write_bytes(content)
    base = _inputs()
    artifact = base.artifact
    assert artifact is not None
    artifact = ModelArtifact(
        artifact_id=artifact.artifact_id,
        model_id=artifact.model_id,
        source_kind=artifact.source_kind,
        repository=artifact.repository,
        immutable_revision=artifact.immutable_revision,
        variant=artifact.variant,
        lifecycle=artifact.lifecycle,
        total_bytes=len(content),
        files=(ModelFileRecord("model.safetensors", len(content), digest),),
        config_sha256=artifact.config_sha256,
        derivation=artifact.derivation,
        base_model=artifact.base_model,
        parent_artifact_id=artifact.parent_artifact_id,
        acquired_at=artifact.acquired_at,
    )
    inputs = _inputs(artifact=artifact)
    promote(tmp_path, artifact, staged)
    return artifact, inputs


def test_missing_and_corrupt_artifacts_fail_closed(tmp_path: Path) -> None:
    artifact, inputs = _prepared(tmp_path)
    _store_inputs(tmp_path, inputs)
    coordinator = _coordinator(tmp_path)
    missing = coordinator.deploy(
        artifact_id="mart_absent", request_key="missing", actor="local_admin_ui", now=NOW  # noqa: E501
    )
    assert missing.state == "failed"
    assert missing.failure == "artifact_missing"
    assert missing.reservation_id == ""
    stored = warehouse_root(tmp_path) / artifact.artifact_id / "model.safetensors"
    stored.write_bytes(b"tampered-weights!!")
    corrupt = coordinator.deploy(
        artifact_id=artifact.artifact_id, request_key="corrupt", actor="local_admin_ui", now=NOW  # noqa: E501
    )
    assert corrupt.state == "failed"
    assert corrupt.failure == "artifact_corrupt"
    assert corrupt.reservation_id == ""
    coordinator.close()


def test_plan_refusal_does_not_admit(tmp_path: Path) -> None:
    _artifact, inputs = _prepared(tmp_path)
    tiny = _envelope(_device("accel_0", 1), evidence="cev_tiny")
    foundation = _foundation(evidence="cev_tiny")
    inputs = _inputs(artifact=inputs.artifact, envelope=tiny, foundation=foundation)
    _store_inputs(tmp_path, inputs)
    coordinator = _coordinator(tmp_path)
    view = coordinator.deploy(
        artifact_id=inputs.artifact.artifact_id,
        request_key="tiny",
        actor="local_admin_ui",
        now=NOW,
    )
    assert view.state == "failed"
    assert view.reservation_id == ""
    assert coordinator._manager.list_active_reservations() == ()
    coordinator.close()


def test_admission_rejection_does_not_start(tmp_path: Path) -> None:
    artifact, inputs = _prepared(tmp_path)
    _store_inputs(tmp_path, inputs)
    StoreReservationLog(FileStore(tmp_path)).create(
        "rsv_block",
        ResourceReservation(
            reservation_id="rsv_block",
            plan_id="pln_block",
            fingerprint="finger-block",
            request_id="req_block",
            capacity_evidence_id=inputs.envelope.evidence_id,
            accelerator_identity="accel_0",
            accelerator_memory_bytes=1,
            host_memory_bytes=1,
            persistent_bytes=0,
            transient_bytes=0,
            cpu_count=1,
            policy_version="m8.admit.1",
            state=ReservationState.RESERVED,
        ),
    )
    coordinator = _coordinator(tmp_path)
    view = coordinator.deploy(
        artifact_id=artifact.artifact_id,
        request_key="blocked",
        actor="local_admin_ui",
        now=NOW,
    )
    assert view.state == "failed"
    assert view.failure == "admission_rejected"
    assert view.instance_id == ""
    coordinator.close()


def test_serve_failure_releases_only_after_stop(tmp_path: Path) -> None:
    artifact, inputs = _prepared(tmp_path)
    _store_inputs(tmp_path, inputs)
    coordinator = _coordinator(tmp_path, mode="exit")
    view = coordinator.deploy(
        artifact_id=artifact.artifact_id,
        request_key="exit",
        actor="local_admin_ui",
        now=NOW,
    )
    assert view.state in {"failed", "recovery_required"}
    assert view.failure in {"serve_failed", "release_unproven"}
    if view.state == "failed":
        assert coordinator._manager.list_active_reservations() == ()
    coordinator.close()


def test_restart_returns_the_same_ready_deployment(tmp_path: Path) -> None:
    artifact, inputs = _prepared(tmp_path)
    _store_inputs(tmp_path, inputs)
    first = _coordinator(tmp_path)
    view = first.deploy(
        artifact_id=artifact.artifact_id, request_key="again", actor="local_admin_ui", now=NOW  # noqa: E501
    )
    assert view.state == "ready"
    first.close()
    second = _coordinator(tmp_path)
    again = second.deploy(
        artifact_id=artifact.artifact_id, request_key="again", actor="local_admin_ui", now=NOW  # noqa: E501
    )
    assert again.operation_id == view.operation_id
    assert again.instance_id == view.instance_id
    assert again.state == "ready"
    assert len(second._manager.list_active_reservations()) == 1
    _stop(second, again.instance_id)
    second.close()


def test_stop_does_not_release(tmp_path: Path) -> None:
    artifact, inputs = _prepared(tmp_path)
    _store_inputs(tmp_path, inputs)
    coordinator = _coordinator(tmp_path)
    view = coordinator.deploy(
        artifact_id=artifact.artifact_id, request_key="life", actor="local_admin_ui", now=NOW  # noqa: E501
    )
    stopped = coordinator._serve.stop(view.instance_id)
    assert stopped.outcome.value == "stopped"
    assert coordinator._manager.list_active_reservations()
    coordinator.mark_stopped(NOW)
    assert coordinator.current().state == "stopped"
    released = coordinator._manager.release(view.reservation_id)
    assert released.outcome.value == "released"
    coordinator.mark_released(NOW)
    assert coordinator.current().state == "released"
    coordinator.close()


def test_ready_emits_a_material_reason(tmp_path: Path) -> None:
    artifact, inputs = _prepared(tmp_path)
    _store_inputs(tmp_path, inputs)

    class Note:
        def __init__(self) -> None:
            self.reasons: list[tuple[str, ...]] = []

        def note(self, reasons: tuple[str, ...], now: object, immediate: bool = False) -> None:  # noqa: E501
            del now, immediate
            self.reasons.append(tuple(reasons))

    note = Note()
    coordinator = _coordinator(tmp_path)
    coordinator._note = note
    view = coordinator.deploy(
        artifact_id=artifact.artifact_id, request_key="note", actor="local_admin_ui", now=NOW  # noqa: E501
    )
    assert view.state == "ready"
    assert ("deployment_ready",) in note.reasons
    _stop(coordinator, view.instance_id)
    coordinator.close()


def test_stopped_chain_keeps_the_unreleased_deployment_hold() -> None:
    from machi.adapters.rukan.project import _latest_instance
    from machi.admit.contracts import ReservationRelease
    from machi.serve.contracts import HealthState, InstanceState, ServingInstance

    def instance(instance_id: str, reservation_id: str) -> ServingInstance:
        return ServingInstance(
            instance_id=instance_id,
            plan_id="plan_test",
            fingerprint="finger",
            reservation_id=reservation_id,
            generation_id="fgen_test",
            artifact_id="mart_test",
            serve_provider="vllm",
            executor_kind="native_process",
            endpoint_id="ep_test",
            state=InstanceState.STOPPED,
            health=HealthState.UNREADY,
            evidence_id="sev_test",
            policy_version="m9.serve.1",
        )

    probe = instance("sin_bd7cf6045525c630", "rsv_probe")
    deployment = instance("sin_7b6bdb1a6b1196fe", "rsv_deploy")
    release = ReservationRelease(
        release_id="rel_probe",
        reservation_id="rsv_probe",
        plan_id="plan_probe",
    )
    _kind, chosen = _latest_instance((probe, deployment), (), (release,))
    assert chosen.reservation_id == "rsv_deploy"


def test_distribution_declares_the_hub_client() -> None:
    text = Path("pyproject.machi.toml").read_text(encoding="utf-8")
    assert 'huggingface_hub>=0.26,<1' in text

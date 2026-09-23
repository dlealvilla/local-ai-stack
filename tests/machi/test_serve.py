"""Serve lifecycle against a local probe process. No GPU and no vLLM."""

from __future__ import annotations

import datetime as dt
import socket
import sys
from dataclasses import replace
from pathlib import Path

from tests.machi.test_admit import (
    _configuration,
    _decision,
    _envelope,
    _reservation,
)

from machi.adapters.admit.log import StoreReservationLog
from machi.adapters.foundation.process import (
    NativeProcessRunner,
    ProcessView,
    SpawnedProcess,
)
from machi.adapters.persistence.file_store import FileStore
from machi.adapters.serve.endpoint import choose_port
from machi.adapters.serve.log import StoreServeLog
from machi.adapters.serve.vllm import vllm_argv
from machi.admit.contracts import ResourceReservation
from machi.admit.service import ResourceManager
from machi.foundation.contracts import (
    AcceleratorBackend,
    ExecutorKind,
    FailureCode,
    FoundationEngine,
    FoundationFamily,
    FoundationSelection,
    ManagedGeneration,
    SupportState,
)
from machi.kernel.clock import FixedClock
from machi.kernel.schema import to_dict
from machi.kernel.unresolved import NOT_PROVIDED, is_resolved
from machi.model.contracts import (
    ArtifactLifecycle,
    DerivationKind,
    ModelArtifact,
    ModelSourceKind,
)
from machi.plan.contracts import (
    DeploymentConfiguration,
    PlanFailure,
    PlanProvenance,
    PlanSetting,
)
from machi.serve.contracts import InstanceState, ServeFailure, ServeOutcome
from machi.serve.native import NativeProcessEvidence
from machi.serve.policy import ServePolicy
from machi.serve.ports import InferResult, LaunchRequest
from machi.serve.service import ServeService

FIXED = FixedClock(dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.UTC))
PROBE = """
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port = int(sys.argv[1])
mode = sys.argv[2]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] == "/health" and mode != "unready":
            self.send_response(200)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        code = 500 if mode == "infer_fail" else 200
        body = b'{"choices":[{"text":"ok"}],"usage":{"completion_tokens":1}}'
        if code != 200:
            body = b"{}"
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return

ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


class ProbeRuntime:
    """Local HTTP stand-in. Not a product inference provider."""

    provider_name = "vllm"
    executor_kind = "native_process"

    def __init__(self, runner: NativeProcessRunner, mode: str = "ok") -> None:
        self._runner = runner
        self._mode = mode
        self._spawned: dict[str, SpawnedProcess] = {}
        self.launches = 0

    def launch(self, request: LaunchRequest) -> NativeProcessEvidence:
        self.launches += 1
        if self._mode == "exit":
            argv = [sys.executable, "-c", "import sys; sys.exit(3)"]
        elif self._mode == "hang":
            argv = [sys.executable, "-c", "import time; time.sleep(30)"]
        else:
            argv = [sys.executable, "-c", PROBE, str(request.port), self._mode]
        spawned = self._runner.spawn(
            argv,
            cwd=request.cwd,
            env=None,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
        )
        self._spawned[request.evidence_id] = spawned
        return NativeProcessEvidence(
            evidence_id=request.evidence_id,
            instance_id=request.instance_id,
            pid=spawned.pid,
            process_stamp=spawned.process_stamp,
            identity_token=spawned.identity_token,
            argv_fingerprint=spawned.argv_fingerprint,
            python_basename="python",
            bind_scope="loopback",
            port=request.port,
            started_at=FIXED.now(),
        )

    def _view(
        self, evidence: NativeProcessEvidence
    ) -> tuple[SpawnedProcess, ProcessView]:
        found = self._spawned.get(evidence.evidence_id)
        spawned = found or SpawnedProcess(
            pid=evidence.pid,
            process_stamp=evidence.process_stamp,
            identity_token=evidence.identity_token,
            argv_fingerprint=evidence.argv_fingerprint,
        )
        return spawned, self._runner.view(spawned)

    def ready(self, evidence: NativeProcessEvidence) -> bool:
        from machi.adapters.serve.vllm import _status, _url

        return _status(_url(evidence.port, "/health"), timeout=1) == 200

    def infer(self, evidence: NativeProcessEvidence, artifact_id: str) -> InferResult:
        from machi.adapters.serve.vllm import VllmServeProvider

        provider = VllmServeProvider(self._runner, FIXED)
        provider._spawned = self._spawned
        return provider.infer(evidence, artifact_id)

    def identity_ok(self, evidence: NativeProcessEvidence) -> bool:
        _spawned, view = self._view(evidence)
        return view.identity_ok

    def alive(self, evidence: NativeProcessEvidence) -> bool:
        _spawned, view = self._view(evidence)
        return view.alive

    def stop(self, evidence: NativeProcessEvidence, *, grace_seconds: float) -> bool:
        spawned, _view = self._view(evidence)
        view = self._runner.terminate(spawned, grace_seconds=grace_seconds)
        return not view.alive and view.identity_ok

    def returncode(self, evidence: NativeProcessEvidence) -> int | None:
        _spawned, view = self._view(evidence)
        return view.returncode


def _settings() -> tuple[PlanSetting, ...]:
    def setting(name: str, value: str) -> PlanSetting:
        return PlanSetting(
            name=name,
            value=value,
            provenance=PlanProvenance.PRODUCT_DEFAULT,
            reason="serve test",
        )

    return (
        setting("trust_remote_code", "false"),
        setting("tensor_parallel_size", "1"),
        setting("max_model_len", "128"),
        setting("max_num_seqs", "1"),
        setting("gpu_memory_utilization", "0.90"),
        setting("dtype", "float32"),
        setting("quantization", "none"),
        setting("qualification_id", "qev_serve"),
    )


def _world(
    tmp_path: Path, mode: str = "ok"
) -> tuple[
    ServeService,
    ResourceManager,
    DeploymentConfiguration,
    ResourceReservation,
    ProbeRuntime,
    ModelArtifact,
    FoundationSelection,
    ManagedGeneration,
    Path,
]:
    store = FileStore(tmp_path / "store")
    manager = ResourceManager(StoreReservationLog(store))
    decision = _decision()
    admitted = manager.admit(decision, _envelope(), PlanFailure.NONE)
    reservation = _reservation(admitted)
    configuration = replace(_configuration(decision), settings=_settings())
    model_path = tmp_path / "model"
    model_path.mkdir()
    artifact = ModelArtifact(
        artifact_id=configuration.artifact_id,
        model_id="mdl_a",
        source_kind=ModelSourceKind.LOCAL,
        repository="fixture",
        immutable_revision="rev-a",
        variant="float32",
        lifecycle=ArtifactLifecycle.STORED,
        total_bytes=1,
        files=(),
        config_sha256=NOT_PROVIDED,
        derivation=DerivationKind.ORIGINAL,
        base_model=NOT_PROVIDED,
        parent_artifact_id=NOT_PROVIDED,
        acquired_at=FIXED.now(),
    )
    selection = FoundationSelection(
        selection_id="fsel_serve",
        family=FoundationFamily.DIRECT,
        engine=FoundationEngine.VLLM,
        executor=ExecutorKind.NATIVE_PROCESS,
        backend=AcceleratorBackend.CUDA,
        support=SupportState.READY,
        failure=FailureCode.NONE,
        candidate_id="vllm-test",
        generation_id=configuration.generation_id,
        capacity_evidence_id=configuration.capacity_evidence_id,
        reason="fixture",
    )
    generation = ManagedGeneration(
        generation_id=configuration.generation_id,
        candidate_id="vllm-test",
        python_path=sys.executable,
        vllm_version="0.18.0",
        created_at=FIXED.now(),
    )
    runtime = ProbeRuntime(NativeProcessRunner(), mode)
    service = ServeService(
        StoreServeLog(store),
        runtime,
        manager,
        ServePolicy(startup_timeout_seconds=1.5, stop_grace_seconds=1),
        FIXED,
        tmp_path / "state",
        choose_port,
    )
    return (
        service,
        manager,
        configuration,
        reservation,
        runtime,
        artifact,
        selection,
        generation,
        model_path,
    )


def test_vllm_argv_uses_only_planned_settings() -> None:
    argv = vllm_argv(
        python_path="/managed/python",
        model_path="/warehouse/mart",
        artifact_id="mart_example",
        port=18080,
        settings={
            "trust_remote_code": "false",
            "tensor_parallel_size": "1",
            "max_model_len": "128",
            "max_num_seqs": "4",
            "gpu_memory_utilization": "0.90",
            "dtype": "float32",
            "quantization": "none",
        },
    )
    assert "vllm.entrypoints.openai.api_server" in argv
    assert "--max-model-len" in argv
    assert "--max-num-seqs" in argv
    assert "--trust-remote-code" not in argv
    assert "--quantization" not in argv
    assert "--host" in argv
    assert "127.0.0.1" in argv
    served = argv.index("--served-model-name")
    assert argv[served + 1] == "mart_example"
    try:
        vllm_argv(
            python_path="python",
            model_path="model",
            artifact_id="mart_example",
            port=1,
            settings={"trust_remote_code": "true"},
        )
    except ValueError:
        return
    raise AssertionError("remote code was accepted")


def test_authorization_refuses_without_a_live_reservation(tmp_path: Path) -> None:
    (
        service,
        manager,
        configuration,
        reservation,
        runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path)
    bare = service.start(
        configuration,
        "rsv_missing",
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert bare.failure is ServeFailure.RESERVATION_REQUIRED
    assert runtime.launches == 0
    released = manager.release(reservation.reservation_id)
    assert released.failure.value == "none"
    again = service.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert again.failure is ServeFailure.RESERVATION_RELEASED
    assert runtime.launches == 0


def test_serve_refuses_a_plan_without_qualification_coverage(tmp_path: Path) -> None:
    (
        service,
        _manager,
        configuration,
        reservation,
        runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path)
    bare = replace(
        configuration,
        settings=tuple(
            item for item in configuration.settings if item.name != "qualification_id"
        ),
    )
    started = service.start(
        bare,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert started.outcome is ServeOutcome.REFUSED
    assert started.failure is ServeFailure.PLAN_RESERVATION_MISMATCH
    assert runtime.launches == 0


def test_lifecycle_proof_and_release_order(tmp_path: Path) -> None:
    (
        service,
        manager,
        configuration,
        reservation,
        runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path)
    started = service.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert started.outcome is ServeOutcome.READY
    assert not is_resolved(started.proof)
    assert is_resolved(started.instance)
    assert started.instance.state is InstanceState.READY
    assert not hasattr(started.instance, "pid")
    assert service.release_eligible(started.instance.instance_id) is False
    held = service.release_after_stop(started.instance.instance_id)
    assert held.failure is ServeFailure.SERVING_STATE_INVALID
    assert len(manager.list_active_reservations()) == 1
    repeat = service.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert is_resolved(repeat.instance)
    assert repeat.instance.instance_id == started.instance.instance_id
    assert runtime.launches == 1
    proof = service.prove(started.instance.instance_id)
    assert proof.outcome is ServeOutcome.PROVEN
    assert is_resolved(proof.proof)
    assert proof.proof.structurally_valid is True
    rendered = " ".join(to_dict(event)["event_type"] for event in service.emitted)
    assert "serve.started" in rendered
    assert "serve.ready" in rendered
    assert "inference.completed" in rendered
    blob = str([to_dict(event) for event in service.emitted])
    assert "machi-serve-proof" not in blob
    assert "127.0.0.1" not in blob
    stopped = service.stop(started.instance.instance_id)
    assert stopped.outcome is ServeOutcome.STOPPED
    assert service.stop(started.instance.instance_id).outcome is ServeOutcome.STOPPED
    assert service.release_eligible(started.instance.instance_id) is True
    released = service.release_after_stop(started.instance.instance_id)
    assert released.failure.value == "none"
    assert manager.list_active_reservations() == ()


def test_port_conflict_does_not_kill_the_occupant(tmp_path: Path) -> None:
    (
        service,
        _manager,
        configuration,
        reservation,
        runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path)
    service._policy = ServePolicy(
        port_base=39221, port_span=1, startup_timeout_seconds=1
    )
    holder = socket.socket()
    holder.bind(("127.0.0.1", 39221))
    try:
        refused = service.start(
            configuration,
            reservation.reservation_id,
            selection,
            generation,
            artifact,
            model_path=model_path,
            artifact_verified=True,
        )
        assert refused.failure is ServeFailure.PORT_CONFLICT
        assert runtime.launches == 0
        assert len(service.list_instances()) == 0
    finally:
        holder.close()


def test_early_exit_and_timeout(tmp_path: Path) -> None:
    (
        early,
        _manager,
        configuration,
        reservation,
        _runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path, "exit")
    failed = early.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert failed.failure is ServeFailure.PROCESS_EXITED_BEFORE_READY
    assert is_resolved(failed.instance)
    assert failed.instance.state is InstanceState.FAILED
    (
        hung,
        _manager,
        configuration,
        reservation,
        _runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path / "hang", "hang")
    timed = hung.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert timed.failure is ServeFailure.READINESS_TIMEOUT
    assert is_resolved(timed.instance)
    assert hung.release_eligible(timed.instance.instance_id) is False


def test_inference_failure_keeps_the_instance_ready(tmp_path: Path) -> None:
    (
        service,
        _manager,
        configuration,
        reservation,
        _runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path, "infer_fail")
    started = service.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert is_resolved(started.instance)
    proof = service.prove(started.instance.instance_id)
    assert proof.failure is ServeFailure.INFERENCE_FAILED
    current = service.get_instance(started.instance.instance_id)
    assert current is not None
    assert current.state is InstanceState.READY
    service.stop(started.instance.instance_id)


def test_reentry_keeps_the_managed_process_and_ignores_others(tmp_path: Path) -> None:
    (
        service,
        manager,
        configuration,
        reservation,
        _runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path)
    started = service.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert is_resolved(started.instance)
    revived = ServeService(
        StoreServeLog(FileStore(tmp_path / "store")),
        ProbeRuntime(NativeProcessRunner(), "ok"),
        manager,
        service._policy,
        FIXED,
        tmp_path / "state",
        choose_port,
    )
    found = revived.get_instance(started.instance.instance_id)
    assert found is not None
    assert found.state is InstanceState.READY
    assert revived.reconcile() == ()
    stranger = NativeProcessRunner()
    other = stranger.spawn(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=str(tmp_path),
        env=None,
        stdout_path=tmp_path / "other.out",
        stderr_path=tmp_path / "other.err",
    )
    mismatched = SpawnedProcess(
        pid=other.pid,
        process_stamp="not-the-real-stamp",
        identity_token="not-the-token",
        argv_fingerprint=other.argv_fingerprint,
    )
    view = stranger.terminate(mismatched, grace_seconds=0.2)
    assert view.identity_ok is False
    assert view.alive is True
    stranger.terminate(other, grace_seconds=1)
    revived.stop(started.instance.instance_id)

"""Serve one local probe from the installed package. No GPU and no vLLM."""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
from pathlib import Path

from machi.adapters.admit.log import StoreReservationLog
from machi.adapters.foundation.process import NativeProcessRunner, SpawnedProcess
from machi.adapters.persistence.file_store import FileStore
from machi.adapters.serve.endpoint import choose_port
from machi.adapters.serve.log import StoreServeLog
from machi.admit.service import ResourceManager
from machi.capacity.contracts import (
    AcceleratorCapacity,
    CapacityEnvelope,
    EvidenceStrength,
    MemoryCapacity,
    StorageDomainCapacity,
)
from machi.capacity.policy import default_capacity_settings
from machi.capacity.sonar import not_attempted
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
from machi.kernel.unresolved import NOT_PROVIDED, is_resolved
from machi.model.contracts import (
    ArtifactLifecycle,
    DerivationKind,
    ModelArtifact,
    ModelSourceKind,
)
from machi.model.environment import execution_environment_fingerprint
from machi.model.qualification import (
    POLICY_VERSION as QUALIFICATION_POLICY,
)
from machi.model.qualification import (
    DeployableMember,
    DeployableModels,
    QualificationEvidence,
    QualificationOutcome,
    covers,
    qualification_identity,
    select_id,
)
from machi.plan.contracts import (
    DeploymentConfiguration,
    PlanDecision,
    PlanFailure,
    PlanProvenance,
    PlanSetting,
    PlanStatus,
    ResourceRequest,
)
from machi.serve.contracts import ServeFailure, ServeOutcome
from machi.serve.native import NativeProcessEvidence
from machi.serve.policy import ServePolicy
from machi.serve.ports import InferResult, LaunchRequest
from machi.serve.service import ServeService

FIXED = FixedClock(dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.UTC))
PROBE = """
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
port = int(sys.argv[1])

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        body = b'{"choices":[{"text":"ok"}],"usage":{"completion_tokens":1}}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return

ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


class ProbeRuntime:
    provider_name = "vllm"
    executor_kind = "native_process"

    def __init__(self) -> None:
        self._runner = NativeProcessRunner()
        self._spawned: dict[str, SpawnedProcess] = {}

    def launch(self, request: LaunchRequest) -> NativeProcessEvidence:
        spawned = self._runner.spawn(
            [sys.executable, "-c", PROBE, str(request.port)],
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

    def _spawned_for(self, evidence: NativeProcessEvidence) -> SpawnedProcess:
        found = self._spawned.get(evidence.evidence_id)
        if found is not None:
            return found
        return SpawnedProcess(
            pid=evidence.pid,
            process_stamp=evidence.process_stamp,
            identity_token=evidence.identity_token,
            argv_fingerprint=evidence.argv_fingerprint,
        )

    def ready(self, evidence: NativeProcessEvidence) -> bool:
        from machi.adapters.serve.vllm import _status, _url

        return _status(_url(evidence.port, "/health"), timeout=1) == 200

    def infer(self, evidence: NativeProcessEvidence, artifact_id: str) -> InferResult:
        from machi.adapters.serve.vllm import VllmServeProvider

        provider = VllmServeProvider(self._runner, FIXED)
        provider._spawned = self._spawned
        return provider.infer(evidence, artifact_id)

    def identity_ok(self, evidence: NativeProcessEvidence) -> bool:
        return self._runner.view(self._spawned_for(evidence)).identity_ok

    def alive(self, evidence: NativeProcessEvidence) -> bool:
        return self._runner.view(self._spawned_for(evidence)).alive

    def stop(self, evidence: NativeProcessEvidence, *, grace_seconds: float) -> bool:
        view = self._runner.terminate(
            self._spawned_for(evidence), grace_seconds=grace_seconds
        )
        return (not view.alive) and view.identity_ok

    def returncode(self, evidence: NativeProcessEvidence) -> int | None:
        return self._runner.view(self._spawned_for(evidence)).returncode


def _setting(name: str, value: str, provenance: PlanProvenance) -> PlanSetting:
    return PlanSetting(name=name, value=value, provenance=provenance, reason="fixture")


def _settings(qualification_id: str) -> tuple[PlanSetting, ...]:
    default = PlanProvenance.PRODUCT_DEFAULT
    meta = PlanProvenance.MODEL_METADATA
    derived = PlanProvenance.DERIVED
    return (
        _setting("trust_remote_code", "false", default),
        _setting("tensor_parallel_size", "1", default),
        _setting("max_model_len", "128", default),
        _setting("max_num_seqs", "1", default),
        _setting("gpu_memory_utilization", "0.90", default),
        _setting("dtype", "float32", meta),
        _setting("quantization", "none", meta),
        _setting("qualification_id", qualification_id, derived),
    )


def _coverage() -> str:
    """Real pass evidence and deployable membership for this fixture plan."""
    environment = execution_environment_fingerprint(
        vendor="nvidia",
        accelerator_model="fixture",
        capability="unspecified",
        runtime_capability="fixture-runtime",
        generation_id="fgen_serve",
    )
    qualification_id = qualification_identity(
        revision="rev-serve",
        generation_id="fgen_serve",
        engine="vllm",
        engine_version="0.18.0",
        backend="cuda",
        hardware_class="unspecified",
        execution_environment_fingerprint=environment,
        dtype="float32",
        quantization="none",
        context=128,
        concurrency=1,
        tensor_parallel=1,
        policy_version=QUALIFICATION_POLICY,
    )
    evidence = QualificationEvidence(
        qualification_id=qualification_id,
        artifact_id="mart_serve",
        immutable_revision="rev-serve",
        generation_id="fgen_serve",
        engine="vllm",
        engine_version="0.18.0",
        backend="cuda",
        hardware_class="unspecified",
        execution_environment_fingerprint=environment,
        dtype="float32",
        quantization="none",
        context=128,
        concurrency=1,
        tensor_parallel=1,
        policy_version=QUALIFICATION_POLICY,
        outcome=QualificationOutcome.PASS,
        failure="none",
        load_seconds=NOT_PROVIDED,
        ttft_seconds=NOT_PROVIDED,
        tokens_per_second=NOT_PROVIDED,
        peak_vram_bytes=NOT_PROVIDED,
        peak_ram_bytes=NOT_PROVIDED,
        measured=False,
        observed_at=FIXED.now(),
    )
    deployable = DeployableModels(
        snapshot_id="dep_serve",
        capacity_snapshot_id="cev_serve",
        members=(
            DeployableMember(
                model_id="mdl_serve",
                immutable_revision="rev-serve",
                qualification_id=qualification_id,
                total_required_vram_bytes=40,
            ),
        ),
        observed_at=FIXED.now(),
    )
    member = select_id(deployable, "mdl_serve")
    if member is None or member.qualification_id != qualification_id:
        raise SystemExit("deployable membership does not cite qualification")
    if not covers(
        evidence,
        revision="rev-serve",
        generation_id="fgen_serve",
        engine="vllm",
        engine_version="0.18.0",
        backend="cuda",
        hardware_class="unspecified",
        execution_environment_fingerprint=environment,
        dtype="float32",
        quantization="none",
        context=128,
        concurrency=1,
        tensor_parallel=1,
        policy_version=QUALIFICATION_POLICY,
    ):
        raise SystemExit("qualification evidence does not cover this plan")
    return qualification_id


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="machi-serve-"))
    store = FileStore(root / "store")
    token = "a" * 32
    qualification_id = _coverage()
    configuration = DeploymentConfiguration(
        plan_id="plan_serve",
        status=PlanStatus.PLANNED,
        model_id="mdl_serve",
        artifact_id="mart_serve",
        immutable_revision="rev-serve",
        foundation_id="fgen_serve",
        generation_id="fgen_serve",
        capacity_evidence_id="cev_serve",
        provider="vllm",
        accelerator_count=1,
        accelerator_identity="accel_serve",
        context_length=128,
        concurrency=1,
        dtype="float32",
        quantization="none",
        policy_version="m7.plan.1",
        fingerprint=token,
        settings=_settings(qualification_id),
    )
    request = ResourceRequest(
        request_id="preq_serve",
        plan_id="plan_serve",
        fingerprint=token,
        foundation_id="fgen_serve",
        generation_id="fgen_serve",
        capacity_evidence_id="cev_serve",
        artifact_id="mart_serve",
        accelerator_count=1,
        accelerator_memory_bytes=40,
        host_memory_bytes=40,
        persistent_bytes=10,
        transient_bytes=0,
        cpu_count=1,
    )
    decision = PlanDecision(
        decision_id="pdec_serve",
        failure=PlanFailure.NONE,
        reason="planned",
        fingerprint=token,
        configuration=configuration,
        request=request,
    )
    envelope = CapacityEnvelope(
        evidence_id="cev_serve",
        input_token="capacity-serve",
        memory=MemoryCapacity(
            physical_bytes=NOT_PROVIDED,
            execution_limit_bytes=NOT_PROVIDED,
            hard_ceiling_bytes=NOT_PROVIDED,
            reserve_bytes=0,
            safe_bytes=100,
            strength=EvidenceStrength.REPORTED,
            reason="fixture",
        ),
        accelerators=(
            AcceleratorCapacity(
                identity="accel_serve",
                ordinal=0,
                topology="discrete",
                physical_bytes=NOT_PROVIDED,
                current_used_bytes=NOT_PROVIDED,
                reserve_bytes=0,
                safe_bytes=100,
                strength=EvidenceStrength.REPORTED,
                reason="fixture",
            ),
        ),
        storage_domains=(
            StorageDomainCapacity(
                domain_id="dom_serve",
                backing_resolved=True,
                reported_available_bytes=NOT_PROVIDED,
                specialist_remaining_bytes=NOT_PROVIDED,
                hard_bound_bytes=NOT_PROVIDED,
                reserve_bytes=0,
                safe_bytes=100,
                protected_occupancy_bytes=NOT_PROVIDED,
                reclaimable_bytes=NOT_PROVIDED,
                potential_after_reclaim_bytes=NOT_PROVIDED,
                usable=True,
                strength=EvidenceStrength.REPORTED,
                sonar=not_attempted(),
                reason="fixture",
            ),
        ),
        settings=default_capacity_settings(),
        observed_at=FIXED.now(),
        provider="native",
    )
    manager = ResourceManager(StoreReservationLog(store))
    admitted = manager.admit(decision, envelope, PlanFailure.NONE)
    if not is_resolved(admitted.reservation):
        raise SystemExit(f"admit refused: {admitted.failure.value}")
    model_path = root / "model"
    model_path.mkdir()
    artifact = ModelArtifact(
        artifact_id="mart_serve",
        model_id="mdl_serve",
        source_kind=ModelSourceKind.LOCAL,
        repository="fixture",
        immutable_revision="rev-serve",
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
        candidate_id="vllm-fixture",
        generation_id="fgen_serve",
        capacity_evidence_id="cev_serve",
        reason="fixture",
    )
    generation = ManagedGeneration(
        generation_id="fgen_serve",
        candidate_id="vllm-fixture",
        python_path=sys.executable,
        vllm_version="0.18.0",
        created_at=FIXED.now(),
    )
    service = ServeService(
        StoreServeLog(store),
        ProbeRuntime(),
        manager,
        ServePolicy(startup_timeout_seconds=5, stop_grace_seconds=2),
        FIXED,
        root / "state",
        choose_port,
    )
    started = service.start(
        configuration,
        admitted.reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    if started.outcome is not ServeOutcome.READY or not is_resolved(started.instance):
        raise SystemExit(f"serve did not become ready: {started.failure.value}")
    if service.release_eligible(started.instance.instance_id):
        raise SystemExit("running instance looked releasable")
    proof = service.prove(started.instance.instance_id)
    if proof.outcome is not ServeOutcome.PROVEN:
        raise SystemExit(f"inference was not proven: {proof.failure.value}")
    stopped = service.stop(started.instance.instance_id)
    if stopped.outcome is not ServeOutcome.STOPPED:
        raise SystemExit(f"stop failed: {stopped.failure.value}")
    released = service.release_after_stop(started.instance.instance_id)
    if released.failure is not ServeFailure.NONE and released.failure.value != "none":
        raise SystemExit(f"release failed: {released.failure.value}")
    print(f"serve_ok {started.instance.instance_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Start a reserved plan. Do not provision, acquire, plan, or admit."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from machi.admit.contracts import AdmissionDecision
from machi.admit.service import ResourceManager
from machi.foundation.contracts import (
    FailureCode,
    FoundationSelection,
    ManagedGeneration,
    SupportState,
)
from machi.kernel.clock import Clock
from machi.kernel.events import EventRecord
from machi.kernel.unresolved import NOT_PROVIDED
from machi.model.contracts import ArtifactLifecycle, ModelArtifact
from machi.plan.contracts import DeploymentConfiguration, PlanStatus
from machi.serve.contracts import (
    HealthState,
    InferenceProof,
    InstanceState,
    ServeDecision,
    ServeFailure,
    ServeOutcome,
    ServeTransition,
    ServingInstance,
    refused,
)
from machi.serve.events import serve_event
from machi.serve.identity import (
    endpoint_id,
    evidence_id,
    exit_id,
    instance_id,
    proof_id,
    transition_id,
)
from machi.serve.native import NativeProcessEvidence, NativeProcessExit
from machi.serve.policy import ServePolicy
from machi.serve.ports import InferResult, LaunchRequest, ServeLog, ServeRuntime

_TERMINAL = frozenset({InstanceState.STOPPED, InstanceState.FAILED})


class ServeService:
    """One host, one instance. The reservation stays held until stop is confirmed."""

    def __init__(
        self,
        log: ServeLog,
        runtime: ServeRuntime,
        manager: ResourceManager,
        policy: ServePolicy,
        clock: Clock,
        state_root: Path,
        choose_port: Callable[[str, ServePolicy], int | None],
    ) -> None:
        self._log = log
        self._runtime = runtime
        self._manager = manager
        self._policy = policy
        self._clock = clock
        self._root = state_root
        self._choose_port = choose_port
        self.emitted: list[EventRecord] = []

    def start(
        self,
        configuration: DeploymentConfiguration,
        reservation_id_value: str,
        selection: FoundationSelection,
        generation: ManagedGeneration,
        artifact: ModelArtifact,
        *,
        model_path: Path,
        artifact_verified: bool,
    ) -> ServeDecision:
        """Launch only when M8 has authorized this exact plan."""
        blocked = self._authorize(
            configuration,
            reservation_id_value,
            selection,
            generation,
            artifact,
            model_path=model_path,
            artifact_verified=artifact_verified,
        )
        if blocked is not None:
            return self._emit(blocked)
        self.reconcile()
        existing = self._live_match(configuration, reservation_id_value)
        if existing is not None:
            if existing.state is InstanceState.READY:
                return self._emit(_ready(existing, "existing instance"))
            evidence = self._evidence_for(existing)
            if evidence is not None:
                return self._wait_ready(existing, evidence)
        port = self._choose_port(reservation_id_value, self._policy)
        if port is None:
            return self._emit(
                refused(ServeFailure.PORT_CONFLICT, "loopback port is busy")
            )
        identity = instance_id(
            reservation_id=reservation_id_value,
            fingerprint=configuration.fingerprint,
            sequence=self._sequence(reservation_id_value, configuration.fingerprint),
        )
        native_id = evidence_id(identity)
        try:
            evidence = self._runtime.launch(
                LaunchRequest(
                    instance_id=identity,
                    evidence_id=native_id,
                    python_path=generation.python_path,
                    model_path=str(model_path),
                    artifact_id=artifact.artifact_id,
                    settings=tuple(
                        (item.name, item.value) for item in configuration.settings
                    ),
                    port=port,
                    stdout_path=self._log_path(identity, "stdout"),
                    stderr_path=self._log_path(identity, "stderr"),
                    cwd=str(self._root),
                )
            )
        except OSError:
            return self._emit(
                refused(ServeFailure.PROCESS_LAUNCH_FAILED, "process did not start")
            )
        instance = self._log.create_instance(
            ServingInstance(
                instance_id=identity,
                plan_id=configuration.plan_id,
                fingerprint=configuration.fingerprint,
                reservation_id=reservation_id_value,
                generation_id=generation.generation_id,
                artifact_id=artifact.artifact_id,
                serve_provider=self._runtime.provider_name,
                executor_kind=self._runtime.executor_kind,
                endpoint_id=endpoint_id(identity),
                state=InstanceState.STARTING,
                health=HealthState.UNKNOWN,
                evidence_id=evidence.evidence_id,
                policy_version=self._policy.version,
            )
        )
        self._log.create_evidence(evidence)
        self._emit(_started(instance))
        return self._wait_ready(instance, evidence)

    def prove(self, instance_id_value: str) -> ServeDecision:
        """One request. A failed request does not by itself stop a live runtime."""
        instance = self.get_instance(instance_id_value)
        evidence = None if instance is None else self._evidence_for(instance)
        if instance is None or evidence is None:
            return self._emit(
                refused(ServeFailure.SERVING_STATE_INVALID, "instance is unknown")
            )
        if not self._runtime.identity_ok(evidence):
            return self._emit(
                _failed(instance, ServeFailure.PROCESS_IDENTITY_UNRESOLVED)
            )
        if not self._runtime.alive(evidence):
            failed = self._mark(instance, InstanceState.FAILED, HealthState.UNREADY)
            return self._emit(_failed(failed, ServeFailure.PROCESS_EXITED_BEFORE_READY))
        if instance.state is not InstanceState.READY:
            return self._emit(_failed(instance, ServeFailure.READINESS_FAILED))
        result = self._runtime.infer(evidence, instance.artifact_id)
        proof = self._store_proof(instance, result)
        if result.structurally_valid and result.status_code == 200:
            return self._emit(_proven(instance, proof))
        if not self._runtime.alive(evidence):
            failed = self._mark(instance, InstanceState.FAILED, HealthState.UNREADY)
            return self._emit(_inference_failed(failed, proof))
        return self._emit(_inference_failed(instance, proof))

    def stop(self, instance_id_value: str) -> ServeDecision:
        """Confirm process death before STOPPED. A second stop converges."""
        instance = self.get_instance(instance_id_value)
        if instance is None:
            return self._emit(
                refused(ServeFailure.SERVING_STATE_INVALID, "instance is unknown")
            )
        if instance.state is InstanceState.STOPPED:
            return self._emit(_stopped(instance, "stop already recorded"))
        evidence = self._evidence_for(instance)
        if evidence is None:
            return self._emit(
                _failed(instance, ServeFailure.PROCESS_IDENTITY_UNRESOLVED)
            )
        if self._runtime.alive(evidence) and not self._runtime.identity_ok(evidence):
            return self._emit(
                _failed(instance, ServeFailure.PROCESS_IDENTITY_UNRESOLVED)
            )
        stopping = self._mark(instance, InstanceState.STOPPING, HealthState.UNREADY)
        dead = self._runtime.stop(
            evidence, grace_seconds=self._policy.stop_grace_seconds
        )
        if not dead:
            return self._emit(_failed(stopping, ServeFailure.PROCESS_STOP_FAILED))
        self._record_exit(evidence, "stopped")
        stopped = self._mark(stopping, InstanceState.STOPPED, HealthState.UNREADY)
        return self._emit(_stopped(stopped, "process confirmed dead"))

    def release_eligible(self, instance_id_value: str) -> bool:
        """True only after STOPPED and the managed process is dead."""
        instance = self.get_instance(instance_id_value)
        if instance is None or instance.state is not InstanceState.STOPPED:
            return False
        evidence = self._evidence_for(instance)
        if evidence is None:
            return False
        return not self._runtime.alive(evidence)

    def release_after_stop(
        self, instance_id_value: str
    ) -> ServeDecision | AdmissionDecision:
        """Delegate to M8 only after process death. Otherwise the hold stays."""
        instance = self.get_instance(instance_id_value)
        if instance is None or not self.release_eligible(instance_id_value):
            if instance is None:
                return self._emit(
                    refused(
                        ServeFailure.SERVING_STATE_INVALID,
                        "reservation stays held",
                    )
                )
            return self._emit(_failed(instance, ServeFailure.SERVING_STATE_INVALID))
        return self._manager.release(instance.reservation_id)

    def reconcile(self) -> tuple[ServingInstance, ...]:
        """Mark a dead managed process failed. Do not adopt any other pid."""
        changed: list[ServingInstance] = []
        for instance in self.list_instances():
            if instance.state in _TERMINAL or instance.state is InstanceState.STOPPED:
                continue
            evidence = self._evidence_for(instance)
            if evidence is None or not self._runtime.identity_ok(evidence):
                continue
            if self._runtime.alive(evidence):
                continue
            self._record_exit(evidence, "exited")
            changed.append(
                self._mark(instance, InstanceState.FAILED, HealthState.UNREADY)
            )
        return tuple(changed)

    def get_instance(self, instance_id_value: str) -> ServingInstance | None:
        for item in self.list_instances():
            if item.instance_id == instance_id_value:
                return item
        return None

    def list_instances(self) -> tuple[ServingInstance, ...]:
        transitions = self._log.transitions()
        visible: list[ServingInstance] = []
        for item in self._log.instances():
            latest = _latest(transitions, item.instance_id)
            if latest is None:
                visible.append(item)
            else:
                visible.append(replace(item, state=latest.state, health=latest.health))
        return tuple(visible)

    def _wait_ready(
        self, instance: ServingInstance, evidence: NativeProcessEvidence
    ) -> ServeDecision:
        deadline = time.monotonic() + self._policy.startup_timeout_seconds
        while time.monotonic() < deadline:
            if not self._runtime.identity_ok(evidence):
                failed = self._mark(instance, InstanceState.FAILED, HealthState.UNREADY)
                return self._emit(
                    _failed(failed, ServeFailure.PROCESS_IDENTITY_UNRESOLVED)
                )
            if not self._runtime.alive(evidence):
                self._record_exit(evidence, "exited")
                failed = self._mark(instance, InstanceState.FAILED, HealthState.UNREADY)
                return self._emit(
                    _failed(failed, ServeFailure.PROCESS_EXITED_BEFORE_READY)
                )
            if self._runtime.ready(evidence):
                ready = self._mark(instance, InstanceState.READY, HealthState.READY)
                return self._emit(_ready(ready, "runtime reported ready"))
            time.sleep(0.05)
        dead = self._runtime.stop(
            evidence, grace_seconds=self._policy.stop_grace_seconds
        )
        if not dead:
            return self._emit(_failed(instance, ServeFailure.PROCESS_STOP_FAILED))
        self._record_exit(evidence, "timeout")
        failed = self._mark(instance, InstanceState.FAILED, HealthState.UNREADY)
        return self._emit(_failed(failed, ServeFailure.READINESS_TIMEOUT))

    def _authorize(
        self,
        configuration: DeploymentConfiguration,
        reservation_id_value: str,
        selection: FoundationSelection,
        generation: ManagedGeneration,
        artifact: ModelArtifact,
        *,
        model_path: Path,
        artifact_verified: bool,
    ) -> ServeDecision | None:
        if configuration.status is not PlanStatus.PLANNED:
            return refused(
                ServeFailure.PLAN_RESERVATION_MISMATCH, "plan is not current"
            )
        reservation = self._manager.get_reservation(reservation_id_value)
        if reservation is None:
            return refused(ServeFailure.RESERVATION_REQUIRED, "no reservation")
        if reservation.state.value != "reserved":
            return refused(ServeFailure.RESERVATION_RELEASED, "reservation is released")
        if not self._manager.execution_authorized(reservation_id_value, configuration):
            return refused(
                ServeFailure.RESERVATION_NOT_AUTHORIZED,
                "reservation does not authorize this plan",
            )
        if (
            reservation.plan_id != configuration.plan_id
            or reservation.fingerprint != configuration.fingerprint
            or reservation.accelerator_identity != configuration.accelerator_identity
        ):
            return refused(
                ServeFailure.PLAN_RESERVATION_MISMATCH,
                "reservation bindings differ from the plan",
            )
        if (
            selection.support is not SupportState.READY
            or selection.failure is not FailureCode.NONE
        ):
            return refused(ServeFailure.FOUNDATION_NOT_READY, "foundation is not ready")
        if self._runtime.provider_name != "vllm":
            return refused(
                ServeFailure.UNSUPPORTED_SERVE_PROVIDER,
                "this increment serves native vLLM",
            )
        if generation.generation_id != configuration.generation_id:
            return refused(
                ServeFailure.FOUNDATION_MISMATCH,
                "generation does not match the plan",
            )
        if (
            artifact.artifact_id != configuration.artifact_id
            or artifact.lifecycle is not ArtifactLifecycle.STORED
            or not model_path.is_dir()
        ):
            return refused(
                ServeFailure.MODEL_ARTIFACT_NOT_STORED,
                "warehouse artifact is not stored",
            )
        if not artifact_verified:
            return refused(
                ServeFailure.MODEL_ARTIFACT_INTEGRITY_FAILED,
                "artifact hashes do not match",
            )
        settings = {item.name: item.value for item in configuration.settings}
        if settings.get("trust_remote_code") != "false":
            return refused(
                ServeFailure.UNSUPPORTED_SERVE_PROVIDER,
                "remote code stays refused",
            )
        if settings.get("tensor_parallel_size") != "1":
            return refused(
                ServeFailure.UNSUPPORTED_SERVE_PROVIDER,
                "only one accelerator is served",
            )
        return None

    def _live_match(
        self, configuration: DeploymentConfiguration, reservation_id_value: str
    ) -> ServingInstance | None:
        for item in self.list_instances():
            if item.state in _TERMINAL:
                continue
            if (
                item.reservation_id != reservation_id_value
                or item.fingerprint != configuration.fingerprint
            ):
                continue
            evidence = self._evidence_for(item)
            if evidence is None:
                continue
            if self._runtime.identity_ok(evidence) and self._runtime.alive(evidence):
                return item
        return None

    def _sequence(self, reservation_id_value: str, fingerprint: str) -> int:
        return sum(
            1
            for item in self.list_instances()
            if item.reservation_id == reservation_id_value
            and item.fingerprint == fingerprint
            and item.state in _TERMINAL
        )

    def _mark(
        self, instance: ServingInstance, state: InstanceState, health: HealthState
    ) -> ServingInstance:
        sequence = sum(
            1
            for item in self._log.transitions()
            if item.instance_id == instance.instance_id
        )
        self._log.create_transition(
            ServeTransition(
                transition_id=transition_id(instance.instance_id, sequence),
                instance_id=instance.instance_id,
                sequence=sequence,
                state=state,
                health=health,
            )
        )
        return replace(instance, state=state, health=health)

    def _evidence_for(self, instance: ServingInstance) -> NativeProcessEvidence | None:
        for item in self._log.evidence():
            if item.evidence_id == instance.evidence_id:
                return item
        return None

    def _record_exit(self, evidence: NativeProcessEvidence, reason: str) -> None:
        code = self._runtime.returncode(evidence)
        self._log.create_exit(
            NativeProcessExit(
                exit_id=exit_id(evidence.evidence_id),
                evidence_id=evidence.evidence_id,
                returncode=NOT_PROVIDED if code is None else code,
                reason=reason,
            )
        )

    def _store_proof(
        self, instance: ServingInstance, result: InferResult
    ) -> InferenceProof:
        sequence = sum(
            1 for item in self._log.proofs() if item.instance_id == instance.instance_id
        )
        failure = (
            ServeFailure.NONE
            if result.structurally_valid and result.status_code == 200
            else ServeFailure.INFERENCE_FAILED
        )
        return self._log.create_proof(
            InferenceProof(
                proof_id=proof_id(instance.instance_id, sequence),
                instance_id=instance.instance_id,
                plan_id=instance.plan_id,
                fingerprint=instance.fingerprint,
                reservation_id=instance.reservation_id,
                generation_id=instance.generation_id,
                artifact_id=instance.artifact_id,
                request_kind="completion",
                status_code=result.status_code,
                completion_tokens=(
                    NOT_PROVIDED
                    if result.completion_tokens is None
                    else result.completion_tokens
                ),
                structurally_valid=result.structurally_valid,
                failure=failure,
            )
        )

    def _log_path(self, instance: str, stream: str) -> Path:
        return self._root / "serve" / "logs" / f"{instance}.{stream}"

    def _emit(self, decision: ServeDecision) -> ServeDecision:
        self.emitted.append(serve_event(decision, clock=self._clock))
        return decision


def _latest(
    transitions: tuple[ServeTransition, ...], instance_id_value: str
) -> ServeTransition | None:
    found = [item for item in transitions if item.instance_id == instance_id_value]
    if not found:
        return None
    return max(found, key=lambda item: item.sequence)


def _started(instance: ServingInstance) -> ServeDecision:
    return ServeDecision(
        outcome=ServeOutcome.STARTED,
        failure=ServeFailure.NONE,
        reason="process starting",
        instance=instance,
        proof=NOT_PROVIDED,
    )


def _ready(instance: ServingInstance, reason: str) -> ServeDecision:
    return ServeDecision(
        outcome=ServeOutcome.READY,
        failure=ServeFailure.NONE,
        reason=reason,
        instance=instance,
        proof=NOT_PROVIDED,
    )


def _stopped(instance: ServingInstance, reason: str) -> ServeDecision:
    return ServeDecision(
        outcome=ServeOutcome.STOPPED,
        failure=ServeFailure.NONE,
        reason=reason,
        instance=instance,
        proof=NOT_PROVIDED,
    )


def _failed(instance: ServingInstance, failure: ServeFailure) -> ServeDecision:
    return ServeDecision(
        outcome=ServeOutcome.FAILED,
        failure=failure,
        reason=failure.value,
        instance=instance,
        proof=NOT_PROVIDED,
    )


def _proven(instance: ServingInstance, proof: InferenceProof) -> ServeDecision:
    return ServeDecision(
        outcome=ServeOutcome.PROVEN,
        failure=ServeFailure.NONE,
        reason="inference structurally valid",
        instance=instance,
        proof=proof,
    )


def _inference_failed(
    instance: ServingInstance, proof: InferenceProof
) -> ServeDecision:
    return ServeDecision(
        outcome=ServeOutcome.FAILED,
        failure=ServeFailure.INFERENCE_FAILED,
        reason="inference was not structurally valid",
        instance=instance,
        proof=proof,
    )

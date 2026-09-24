"""Provider serving under a Machi reservation. Residency is not authorization."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Protocol

from machi.admit.contracts import ReservationState
from machi.admit.service import ResourceManager
from machi.kernel.clock import Clock
from machi.kernel.errors import PersistenceError, ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.journal import Journal
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, Maybe, is_resolved
from machi.plan.contracts import PlanStatus
from machi.plan.provider import ProviderDeploymentConfiguration
from machi.serve.contracts import (
    HealthState,
    InstanceState,
    ServeFailure,
    ServeOutcome,
    ServeTransition,
    _bounded,
)
from machi.serve.identity import (
    provider_evidence_id,
    provider_instance_id,
    provider_proof_id,
    transition_id,
)
from machi.serve.policy import PROVIDER_POLICY_VERSION

_TOKEN_MAX = 80
_TERMINAL = frozenset({InstanceState.STOPPED, InstanceState.FAILED})


@contract(kind="serve.provider_instance", version=1)
@dataclass(frozen=True, slots=True)
class ProviderServingInstance(Contract):
    """One authorized provider deployment. The digest is not a warehouse artifact."""

    instance_id: str = meaning("identity of this deployment")
    plan_id: str = meaning("provider plan this instance serves")
    fingerprint: str = meaning("provider plan fingerprint at start")
    reservation_id: str = meaning("reservation that authorized the start")
    generation_id: str = meaning("verified foundation generation")
    digest: str = meaning("immutable provider model digest")
    display_name: str = meaning("catalog address used to reach that digest")
    serve_provider: str = meaning("runtime provider")
    context_length: int = meaning("context sent as num_ctx")
    concurrency: int = meaning("concurrency this instance serves")
    state: InstanceState = meaning("lifecycle")
    health: HealthState = meaning("residency readiness, separate from authorization")
    evidence_id: str = meaning("residency evidence identity")
    policy_version: str = meaning("provider serve policy")

    def __post_init__(self) -> None:
        for label, value in (
            ("instance", self.instance_id),
            ("plan", self.plan_id),
            ("fingerprint", self.fingerprint),
            ("reservation", self.reservation_id),
            ("generation", self.generation_id),
            ("digest", self.digest),
            ("name", self.display_name),
            ("provider", self.serve_provider),
            ("evidence", self.evidence_id),
            ("policy", self.policy_version),
        ):
            _bounded(value, what=label, maximum=_TOKEN_MAX)
        if not self.serve_provider:
            raise ValidationError("provider instance needs a provider name")
        if self.context_length < 1 or self.concurrency != 1:
            raise ValidationError(
                "provider instance serves one context and one sequence"
            )


@contract(kind="serve.provider_inference", version=1)
@dataclass(frozen=True, slots=True)
class ProviderInferenceProof(Contract):
    """One provider request proof. Prompt text and generated text stay out."""

    proof_id: str = meaning("identity of this proof")
    instance_id: str = meaning("instance that served the request")
    plan_id: str = meaning("provider plan")
    fingerprint: str = meaning("provider plan fingerprint")
    reservation_id: str = meaning("reservation")
    generation_id: str = meaning("foundation generation")
    digest: str = meaning("provider digest proved before and after the request")
    request_kind: str = meaning("provider request kind")
    input_tokens: Maybe[int] = meaning("prompt tokens when the provider reported them")
    output_tokens: Maybe[int] = meaning("output tokens when the provider reported them")
    generation_seconds: Maybe[float] = meaning("provider generation duration")
    tokens_per_second: Maybe[float] = meaning("derived rate when both operands exist")
    size_vram_bytes: Maybe[int] = meaning("runtime-reported resident vram")
    size_vram_semantics: str = meaning("runtime_reported; not an observed peak")
    structurally_valid: bool = meaning("the provider returned a countable result")
    failure: ServeFailure = meaning("none when the proof succeeded")

    def __post_init__(self) -> None:
        for label, value in (
            ("proof", self.proof_id),
            ("instance", self.instance_id),
            ("plan", self.plan_id),
            ("fingerprint", self.fingerprint),
            ("reservation", self.reservation_id),
            ("generation", self.generation_id),
            ("digest", self.digest),
            ("request", self.request_kind),
            ("semantics", self.size_vram_semantics),
        ):
            _bounded(value, what=label, maximum=_TOKEN_MAX)
        if self.size_vram_semantics != "runtime_reported":
            raise ValidationError("provider vram is runtime-reported")


@contract(kind="serve.provider_decision", version=1)
@dataclass(frozen=True, slots=True)
class ProviderServeDecision(Contract):
    """Started, proven, stopped, or refused. This is not a native artifact serve."""

    outcome: ServeOutcome = meaning("what provider serve did")
    failure: ServeFailure = meaning("none when the outcome succeeded")
    reason: str = meaning("short explanation")
    instance: Maybe[ProviderServingInstance] = meaning("instance when one exists")
    proof: Maybe[ProviderInferenceProof] = meaning("proof when one was recorded")

    def __post_init__(self) -> None:
        _bounded(self.reason, what="reason", maximum=240)
        if self.outcome is ServeOutcome.REFUSED and is_resolved(self.instance):
            raise ValidationError("a refusal before launch has no instance")
        if self.outcome is ServeOutcome.PROVEN and (
            not is_resolved(self.proof) or self.failure is not ServeFailure.NONE
        ):
            raise ValidationError("a proven outcome carries a successful proof")


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    """One /api/ps classification. It does not authorize resources."""

    state: str
    digest: str | None
    size_vram_bytes: int | None
    expires_at: str | None


@dataclass(frozen=True, slots=True)
class ProviderInferResult:
    """Structural generation result. No prompt and no response text."""

    failure: str
    input_tokens: int
    output_tokens: int
    generation_seconds: float | None


class ProviderRuntimePort(Protocol):
    """Public provider mechanics behind an already authorized plan."""

    def refresh(self, name: str, *, context: int) -> str:
        """Request residency. The return is a failure code or none."""

    def observe(self, name: str, digest: str) -> ProviderObservation:
        """Read current residency."""

    def infer(self, name: str, *, context: int) -> ProviderInferResult:
        """One bounded request at the plan context."""

    def unload(self, name: str) -> str:
        """Request unload. The return is a failure code or none."""


class ProviderServeLog(Protocol):
    """Exclusive provider serve records. Native artifact records stay separate."""

    def create_instance(
        self, record: ProviderServingInstance
    ) -> ProviderServingInstance:
        """Store the binding."""

    def create_transition(self, record: ServeTransition) -> ServeTransition:
        """Append one lifecycle step."""

    def create_proof(self, record: ProviderInferenceProof) -> ProviderInferenceProof:
        """Store one inference proof."""

    def instances(self) -> tuple[ProviderServingInstance, ...]:
        """Stored bindings."""

    def transitions(self) -> tuple[ServeTransition, ...]:
        """Lifecycle steps."""

    def proofs(self) -> tuple[ProviderInferenceProof, ...]:
        """Inference proofs."""


class ProviderServeService:
    """Serve one admitted provider plan. STOP does not release the reservation."""

    def __init__(
        self,
        log: ProviderServeLog,
        provider: ProviderRuntimePort,
        manager: ResourceManager,
        clock: Clock,
        journal: Journal | None = None,
        absence_wait_seconds: float = 5,
    ) -> None:
        self._log = log
        self._provider = provider
        self._manager = manager
        self._clock = clock
        self._journal = journal
        self._absence_wait = absence_wait_seconds
        self.emitted: list[EventRecord] = []

    def start(
        self,
        configuration: ProviderDeploymentConfiguration,
        reservation_id_value: str,
        *,
        foundation_ready: bool,
        covered: bool,
    ) -> ProviderServeDecision:
        """Establish residency only after the reservation authorizes this plan."""
        blocked = self._authorize(
            configuration,
            reservation_id_value,
            foundation_ready=foundation_ready,
            covered=covered,
        )
        if blocked is not None:
            return self._emit(blocked)
        existing = self._live(configuration, reservation_id_value)
        if existing is not None and existing.state is InstanceState.READY:
            seen = self._provider.observe(
                configuration.display_name, configuration.digest
            )
            if seen.state == "expected_resident":
                return self._emit(_ready(existing, "existing residency"))
        refreshed = self._provider.refresh(
            configuration.display_name, context=configuration.context_length
        )
        if refreshed != "none":
            return self._emit(
                _refused(ServeFailure.PROVIDER_API_FAILED, "residency refresh failed")
            )
        seen = self._provider.observe(
            configuration.display_name, configuration.digest
        )
        if seen.state != "expected_resident":
            return self._emit(
                _refused(
                    ServeFailure.PROVIDER_RESIDENCY_MISMATCH,
                    "expected digest is not resident",
                )
            )
        identity = provider_instance_id(
            reservation_id=reservation_id_value,
            fingerprint=configuration.fingerprint,
            sequence=self._sequence(reservation_id_value, configuration.fingerprint),
        )
        instance = self._log.create_instance(
            ProviderServingInstance(
                instance_id=identity,
                plan_id=configuration.plan_id,
                fingerprint=configuration.fingerprint,
                reservation_id=reservation_id_value,
                generation_id=configuration.generation_id,
                digest=configuration.digest,
                display_name=configuration.display_name,
                serve_provider=configuration.provider,
                context_length=configuration.context_length,
                concurrency=configuration.concurrency,
                state=InstanceState.READY,
                health=HealthState.READY,
                evidence_id=provider_evidence_id(identity),
                policy_version=PROVIDER_POLICY_VERSION,
            )
        )
        return self._emit(_ready(instance, "expected digest is resident"))

    def prove(self, instance_id_value: str) -> ProviderServeDecision:
        """Prove the digest, infer once, then prove the same digest."""
        instance = self.get_instance(instance_id_value)
        if instance is None or instance.state is not InstanceState.READY:
            return self._emit(
                _refused(ServeFailure.SERVING_STATE_INVALID, "instance is not ready")
            )
        if not self._still_authorized(instance):
            return self._emit(
                _refused(
                    ServeFailure.RESERVATION_RELEASED,
                    "reservation no longer authorizes serving",
                )
            )
        before = self._provider.observe(instance.display_name, instance.digest)
        if before.state != "expected_resident":
            failed = self._mark(instance, InstanceState.FAILED, HealthState.UNREADY)
            return self._emit(
                _failed(failed, ServeFailure.PROVIDER_RESIDENCY_MISMATCH)
            )
        generated = self._provider.infer(
            instance.display_name, context=instance.context_length
        )
        after = self._provider.observe(instance.display_name, instance.digest)
        proof = self._store_proof(instance, generated, after.size_vram_bytes)
        if (
            generated.failure == "none"
            and generated.output_tokens > 0
            and after.state == "expected_resident"
        ):
            return self._emit(_proven(instance, proof))
        if after.state != "expected_resident":
            failed = self._mark(instance, InstanceState.FAILED, HealthState.UNREADY)
            return self._emit(_inference_failed(failed, proof))
        return self._emit(_inference_failed(instance, proof))

    def stop(self, instance_id_value: str) -> ProviderServeDecision:
        """Unload and prove absence. The reservation stays reserved."""
        instance = self.get_instance(instance_id_value)
        if instance is None:
            return self._emit(
                _refused(ServeFailure.SERVING_STATE_INVALID, "instance is unknown")
            )
        if instance.state is InstanceState.STOPPED:
            return self._emit(_stopped(instance, "stop already recorded"))
        stopping = self._mark(instance, InstanceState.STOPPING, HealthState.UNREADY)
        self._provider.unload(instance.display_name)
        seen = self._absent(instance.display_name, instance.digest)
        if seen is None:
            return self._emit(
                _failed(stopping, ServeFailure.PROVIDER_UNLOAD_FAILED)
            )
        stopped = self._mark(stopping, InstanceState.STOPPED, HealthState.UNREADY)
        return self._emit(_stopped(stopped, "expected digest is absent"))

    def get_instance(self, instance_id_value: str) -> ProviderServingInstance | None:
        for item in self.list_instances():
            if item.instance_id == instance_id_value:
                return item
        return None

    def list_instances(self) -> tuple[ProviderServingInstance, ...]:
        transitions = self._log.transitions()
        visible: list[ProviderServingInstance] = []
        for item in self._log.instances():
            latest = _latest(transitions, item.instance_id)
            if latest is None:
                visible.append(item)
            else:
                visible.append(replace(item, state=latest.state, health=latest.health))
        return tuple(visible)

    def _absent(self, name: str, digest: str) -> ProviderObservation | None:
        """Poll /api/ps briefly. Absence is the stop proof."""
        deadline = time.monotonic() + self._absence_wait
        seen = self._provider.observe(name, digest)
        while seen.state != "absent" and time.monotonic() < deadline:
            time.sleep(0.05)
            seen = self._provider.observe(name, digest)
        if seen.state == "absent":
            return seen
        return None

    def _authorize(
        self,
        configuration: ProviderDeploymentConfiguration,
        reservation_id_value: str,
        *,
        foundation_ready: bool,
        covered: bool,
    ) -> ProviderServeDecision | None:
        if configuration.status is not PlanStatus.PLANNED:
            return _refused(
                ServeFailure.PLAN_RESERVATION_MISMATCH, "plan is not current"
            )
        if not foundation_ready:
            return _refused(
                ServeFailure.FOUNDATION_NOT_READY, "foundation is not ready"
            )
        reservation = self._manager.get_reservation(reservation_id_value)
        if reservation is None:
            return _refused(ServeFailure.RESERVATION_REQUIRED, "no reservation")
        if reservation.state is not ReservationState.RESERVED:
            return _refused(
                ServeFailure.RESERVATION_RELEASED, "reservation is released"
            )
        if not self._manager.execution_authorized_provider(
            reservation_id_value, configuration
        ):
            return _refused(
                ServeFailure.RESERVATION_NOT_AUTHORIZED,
                "reservation does not authorize this plan",
            )
        if not covered:
            return _refused(
                ServeFailure.PLAN_RESERVATION_MISMATCH,
                "qualification does not cover this plan",
            )
        return None

    def _still_authorized(self, instance: ProviderServingInstance) -> bool:
        reservation = self._manager.get_reservation(instance.reservation_id)
        if reservation is None or reservation.state is not ReservationState.RESERVED:
            return False
        return (
            reservation.plan_id == instance.plan_id
            and reservation.fingerprint == instance.fingerprint
        )

    def _live(
        self,
        configuration: ProviderDeploymentConfiguration,
        reservation_id_value: str,
    ) -> ProviderServingInstance | None:
        for item in self.list_instances():
            if item.state in _TERMINAL:
                continue
            if (
                item.reservation_id == reservation_id_value
                and item.fingerprint == configuration.fingerprint
                and item.digest == configuration.digest
            ):
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
        self,
        instance: ProviderServingInstance,
        state: InstanceState,
        health: HealthState,
    ) -> ProviderServingInstance:
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

    def _store_proof(
        self,
        instance: ProviderServingInstance,
        generated: ProviderInferResult,
        size_vram_bytes: int | None,
    ) -> ProviderInferenceProof:
        sequence = sum(
            1 for item in self._log.proofs() if item.instance_id == instance.instance_id
        )
        succeeded = (
            generated.failure == "none"
            and generated.output_tokens > 0
            and generated.generation_seconds is not None
            and generated.generation_seconds > 0
        )
        rate: Maybe[float] = NOT_MEASURED
        if succeeded and generated.generation_seconds:
            rate = generated.output_tokens / generated.generation_seconds
        proof = ProviderInferenceProof(
            proof_id=provider_proof_id(instance.instance_id, sequence),
            instance_id=instance.instance_id,
            plan_id=instance.plan_id,
            fingerprint=instance.fingerprint,
            reservation_id=instance.reservation_id,
            generation_id=instance.generation_id,
            digest=instance.digest,
            request_kind="provider.generate",
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            generation_seconds=(
                generated.generation_seconds
                if isinstance(generated.generation_seconds, float)
                else NOT_MEASURED
            ),
            tokens_per_second=rate,
            size_vram_bytes=(
                size_vram_bytes if isinstance(size_vram_bytes, int) else NOT_MEASURED
            ),
            size_vram_semantics="runtime_reported",
            structurally_valid=(
                generated.failure == "none" and generated.output_tokens > 0
            ),
            failure=(
                ServeFailure.NONE
                if generated.failure == "none" and generated.output_tokens > 0
                else ServeFailure.INFERENCE_FAILED
            ),
        )
        return self._log.create_proof(proof)

    def _emit(self, decision: ProviderServeDecision) -> ProviderServeDecision:
        event = provider_serve_event(decision, clock=self._clock)
        self.emitted.append(event)
        if self._journal is not None:
            try:
                self._journal.append(event)
            except PersistenceError:
                return decision
        return decision


def _refused(failure: ServeFailure, reason: str) -> ProviderServeDecision:
    return ProviderServeDecision(
        outcome=ServeOutcome.REFUSED,
        failure=failure,
        reason=reason,
        instance=NOT_PROVIDED,
        proof=NOT_PROVIDED,
    )


def _ready(instance: ProviderServingInstance, reason: str) -> ProviderServeDecision:
    return ProviderServeDecision(
        ServeOutcome.READY, ServeFailure.NONE, reason, instance, NOT_PROVIDED
    )


def _stopped(instance: ProviderServingInstance, reason: str) -> ProviderServeDecision:
    return ProviderServeDecision(
        ServeOutcome.STOPPED, ServeFailure.NONE, reason, instance, NOT_PROVIDED
    )


def _proven(
    instance: ProviderServingInstance, proof: ProviderInferenceProof
) -> ProviderServeDecision:
    return ProviderServeDecision(
        ServeOutcome.PROVEN,
        ServeFailure.NONE,
        "digest held across inference",
        instance,
        proof,
    )


def _failed(
    instance: ProviderServingInstance, failure: ServeFailure
) -> ProviderServeDecision:
    return ProviderServeDecision(
        ServeOutcome.FAILED, failure, failure.value, instance, NOT_PROVIDED
    )


def _inference_failed(
    instance: ProviderServingInstance, proof: ProviderInferenceProof
) -> ProviderServeDecision:
    return ProviderServeDecision(
        ServeOutcome.FAILED,
        ServeFailure.INFERENCE_FAILED,
        "inference did not prove the expected digest",
        instance,
        proof,
    )


def _latest(
    transitions: tuple[ServeTransition, ...], instance_id_value: str
) -> ServeTransition | None:
    found = [item for item in transitions if item.instance_id == instance_id_value]
    if not found:
        return None
    return max(found, key=lambda item: item.sequence)


PROVIDER_READY_TYPE = "serve.provider.ready"
PROVIDER_FAILED_TYPE = "serve.provider.failed"
PROVIDER_STOPPED_TYPE = "serve.provider.stopped"
PROVIDER_INFERENCE_TYPE = "serve.provider.inference"


def provider_serve_event(
    decision: ProviderServeDecision, *, clock: Clock
) -> EventRecord:
    """Operational witness. No prompt, response, path, or address."""
    if decision.outcome is ServeOutcome.PROVEN and is_resolved(decision.proof):
        payload: Contract = decision.proof
        event_type = PROVIDER_INFERENCE_TYPE
        outcome = EventOutcome.PASS
    elif decision.outcome is ServeOutcome.STOPPED and is_resolved(decision.instance):
        payload = decision.instance
        event_type = PROVIDER_STOPPED_TYPE
        outcome = EventOutcome.PASS
    elif decision.outcome is ServeOutcome.READY and is_resolved(decision.instance):
        payload = decision.instance
        event_type = PROVIDER_READY_TYPE
        outcome = EventOutcome.PASS
    else:
        payload = decision
        event_type = PROVIDER_FAILED_TYPE
        outcome = (
            EventOutcome.FAIL
            if decision.failure is not ServeFailure.NONE
            else EventOutcome.INFO
        )
    return EventRecord.create(
        event_type=event_type,
        block_id="9",
        component_id="9",
        outcome=outcome,
        privacy=PrivacyClass.OPERATIONAL,
        payload=payload,
        clock=clock,
    )

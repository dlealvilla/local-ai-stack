"""Provider plan, shared admission, and Ollama serve. Fixtures only."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from tests.machi.test_admit import _decision, _envelope, _manager
from tests.machi.test_ollama_qualification import _candidate

from machi.adapters.journal.jsonl import JsonlJournal
from machi.adapters.model.ollama_api import FakeOllamaApi
from machi.adapters.model.ollama_qualifier import qualify_ollama
from machi.adapters.serve.ollama import start_ollama
from machi.admit.contracts import AdmissionFailure, AdmissionOutcome, ReservationState
from machi.foundation.contracts import FailureCode, SupportState
from machi.foundation.ollama import OllamaAssessment
from machi.kernel.clock import FixedClock
from machi.kernel.schema import to_dict
from machi.kernel.unresolved import is_resolved
from machi.model.provider_candidate import candidate_id_for
from machi.model.provider_qualification import qualification_covers
from machi.plan.contracts import PlanFailure
from machi.plan.provider import (
    ProviderDeploymentConfiguration,
    ProviderPlanInputs,
    compose_provider_plan,
)
from machi.serve.contracts import (
    InstanceState,
    ServeFailure,
    ServeOutcome,
    ServeTransition,
)
from machi.serve.provider import (
    ProviderInferenceProof,
    ProviderInferResult,
    ProviderObservation,
    ProviderServeService,
    ProviderServingInstance,
    VerifiedProviderRuntime,
)

FIXED = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.UTC)
CLOCK = FixedClock(FIXED)
DIGEST = "ab" * 32


def _runtime(**changes: object) -> VerifiedProviderRuntime:
    values: dict[str, object] = {
        "provider": "ollama",
        "generation_id": "fgen_ollama",
        "execution_environment_fingerprint": "exe_ollama_fixture",
        "ready": True,
    }
    values.update(changes)
    return VerifiedProviderRuntime(
        provider=str(values["provider"]),
        generation_id=str(values["generation_id"]),
        execution_environment_fingerprint=str(
            values["execution_environment_fingerprint"]
        ),
        ready=bool(values["ready"]),
    )


def _begin(service, configuration, reservation_id, evidence, runtime=None):
    chosen = _runtime() if runtime is None else runtime
    covered = evidence.qualification_id == configuration.qualification_id
    covered = covered and qualification_covers(
        evidence,
        digest=configuration.digest,
        generation_id=configuration.generation_id,
        context=configuration.context_length,
        concurrency=configuration.concurrency,
    )
    return service.start(configuration, reservation_id, chosen, covered=covered)


def _qualification(context: int = 2048):
    return qualify_ollama(
        FakeOllamaApi(name="tiny:latest", digest=DIGEST),
        _candidate(),
        generation_id="fgen_ollama",
        engine_version="0.34.3",
        hardware_class="8.9",
        execution_environment_fingerprint="exe_ollama_fixture",
        context=context,
        concurrency=1,
        observed_at=FIXED,
    )


def _inputs(
    evidence,
    *,
    context: int = 2048,
    evidence_id: str = "cev_admit",
    foundation_id: str = "fgen_ollama",
    generation_id: str = "fgen_ollama",
):
    return ProviderPlanInputs(
        display_name="tiny:latest",
        digest=DIGEST,
        candidate_id=candidate_id_for(DIGEST),
        qualification=evidence,
        envelope=_envelope(host=100, accel=100, storage=100, evidence=evidence_id),
        foundation_id=foundation_id,
        generation_id=generation_id,
        foundation_ready=True,
        accelerator_identity="accel_0",
        execution_environment_fingerprint="exe_ollama_fixture",
        context=context,
        concurrency=1,
    )


@dataclass
class _Port:
    resident: bool = False
    unload_failure: str = "none"
    output_tokens: int = 4
    contexts: list[int] = field(default_factory=list)
    inferred: int = 0

    def refresh(self, name: str, *, context: int) -> str:
        del name
        self.contexts.append(context)
        self.resident = True
        return "none"

    def observe(self, name: str, digest: str) -> ProviderObservation:
        del name
        if not self.resident:
            return ProviderObservation("absent", None, None, None)
        return ProviderObservation(
            "expected_resident", digest, 374, "2026-09-24T12:00:00Z"
        )

    def infer(self, name: str, *, context: int) -> ProviderInferResult:
        del name
        self.contexts.append(context)
        self.inferred += 1
        return ProviderInferResult("none", 3, self.output_tokens, 0.2)

    def unload(self, name: str) -> str:
        del name
        if self.unload_failure != "none":
            return self.unload_failure
        self.resident = False
        return "none"


class _Log:
    def __init__(self) -> None:
        self._instances: list[ProviderServingInstance] = []
        self._transitions: list[ServeTransition] = []
        self._proofs: list[ProviderInferenceProof] = []

    def create_instance(
        self, record: ProviderServingInstance
    ) -> ProviderServingInstance:
        self._instances.append(record)
        return record

    def create_transition(self, record: ServeTransition) -> ServeTransition:
        self._transitions.append(record)
        return record

    def create_proof(self, record: ProviderInferenceProof) -> ProviderInferenceProof:
        self._proofs.append(record)
        return record

    def instances(self) -> tuple[ProviderServingInstance, ...]:
        return tuple(self._instances)

    def transitions(self) -> tuple[ServeTransition, ...]:
        return tuple(self._transitions)

    def proofs(self) -> tuple[ProviderInferenceProof, ...]:
        return tuple(self._proofs)


def test_runtime_environment_id_cannot_be_the_plan_generation() -> None:
    evidence = _qualification()
    refused = compose_provider_plan(
        _inputs(evidence, generation_id="renv_ceedac1939fecd21")
    )
    assert refused.failure is PlanFailure.FOUNDATION_MISMATCH
    mismatched_foundation = compose_provider_plan(
        _inputs(evidence, foundation_id="renv_ceedac1939fecd21")
    )
    assert mismatched_foundation.failure is PlanFailure.FOUNDATION_MISMATCH


def test_requested_context_is_required_for_coverage() -> None:
    evidence = _qualification()
    assert evidence.schema_version == 2
    assert evidence.context_binding == "requested"
    assert evidence.context == 2048
    assert qualification_covers(
        evidence,
        digest=DIGEST,
        generation_id="fgen_ollama",
        context=2048,
        concurrency=1,
    )
    assert not qualification_covers(
        evidence,
        digest=DIGEST,
        generation_id="fgen_ollama",
        context=4096,
        concurrency=1,
    )


def test_provider_plan_has_no_warehouse_identity_and_shares_the_ledger(
    tmp_path: Path,
) -> None:
    evidence = _qualification()
    decision = compose_provider_plan(_inputs(evidence))
    assert decision.failure is PlanFailure.NONE
    configuration = decision.configuration
    request = decision.request
    assert is_resolved(configuration)
    assert is_resolved(request)
    rendered = json.dumps(to_dict(configuration))
    assert "artifact_id" not in rendered
    assert "immutable_revision" not in rendered
    assert "dtype" not in rendered
    assert configuration.digest == DIGEST
    assert request.accelerator_memory_bytes == 100
    assert request.persistent_bytes == 0
    wider = compose_provider_plan(_inputs(evidence, context=4096))
    assert wider.failure is PlanFailure.QUALIFICATION_DOES_NOT_COVER
    manager = _manager(tmp_path)
    native = manager.admit(_decision(host=40, accel=40), _envelope(), PlanFailure.NONE)
    assert native.outcome is AdmissionOutcome.ADMITTED
    blocked = manager.admit_provider(decision, _envelope(), PlanFailure.NONE)
    assert blocked.outcome is AdmissionOutcome.REFUSED
    assert blocked.failure is AdmissionFailure.INSUFFICIENT_HOST_MEMORY
    stale = manager.admit_provider(
        decision,
        _envelope(evidence="cev_other"),
        PlanFailure.NONE,
    )
    assert stale.failure is AdmissionFailure.STALE_CAPACITY_INPUT


def test_serve_stop_keeps_the_reservation_and_release_refuses_restart(
    tmp_path: Path,
) -> None:
    evidence = _qualification()
    decision = compose_provider_plan(_inputs(evidence))
    manager = _manager(tmp_path)
    admitted = manager.admit_provider(decision, _envelope(), PlanFailure.NONE)
    assert admitted.outcome is AdmissionOutcome.ADMITTED
    reservation = admitted.reservation
    assert is_resolved(reservation)
    configuration = decision.configuration
    assert isinstance(configuration, ProviderDeploymentConfiguration)
    bare = ProviderServeService(_Log(), _Port(), manager, CLOCK)
    missing = _begin(bare, configuration, "rsv_missing", evidence, _runtime())
    assert missing.failure is ServeFailure.RESERVATION_REQUIRED
    journal = JsonlJournal(tmp_path / "journal")
    port = _Port()
    service = ProviderServeService(_Log(), port, manager, CLOCK, journal)
    started = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
    )
    assert started.outcome is ServeOutcome.READY
    assert port.contexts == [2048]
    assert is_resolved(started.instance)
    proved = service.prove(started.instance.instance_id)
    assert proved.outcome is ServeOutcome.PROVEN
    assert port.inferred == 1
    assert is_resolved(proved.proof)
    body = json.dumps(to_dict(proved.proof))
    assert "Reply with ok." not in body
    assert proved.proof.digest == DIGEST
    assert proved.proof.output_tokens == 4
    stopped = service.stop(started.instance.instance_id)
    assert stopped.outcome is ServeOutcome.STOPPED
    assert port.resident is False
    held = manager.get_reservation(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.RESERVED
    restarted = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
    )
    assert restarted.outcome is ServeOutcome.READY
    assert is_resolved(restarted.instance)
    assert restarted.instance.instance_id != started.instance.instance_id
    again = service.prove(restarted.instance.instance_id)
    assert again.outcome is ServeOutcome.PROVEN
    service.stop(restarted.instance.instance_id)
    released = manager.release(reservation.reservation_id)
    assert released.outcome is AdmissionOutcome.RELEASED
    refused = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
    )
    assert refused.outcome is ServeOutcome.REFUSED
    assert refused.failure is ServeFailure.RESERVATION_RELEASED
    assert manager.list_active_reservations() == ()
    text = (tmp_path / "journal" / "events.jsonl").read_text(encoding="utf-8")
    assert "Reply with ok." not in text
    assert "serve.provider.inference" in text


def test_unload_failure_does_not_release_or_mark_stopped(tmp_path: Path) -> None:
    evidence = _qualification()
    decision = compose_provider_plan(_inputs(evidence))
    manager = _manager(tmp_path)
    admitted = manager.admit_provider(decision, _envelope(), PlanFailure.NONE)
    reservation = admitted.reservation
    assert is_resolved(reservation)
    configuration = decision.configuration
    assert isinstance(configuration, ProviderDeploymentConfiguration)
    port = _Port(unload_failure="unload_failed")
    service = ProviderServeService(
        _Log(), port, manager, CLOCK, absence_wait_seconds=0.2
    )
    started = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
    )
    assert is_resolved(started.instance)
    stopped = service.stop(started.instance.instance_id)
    assert stopped.failure is ServeFailure.PROVIDER_UNLOAD_FAILED
    assert service.get_instance(started.instance.instance_id) is not None
    current = service.get_instance(started.instance.instance_id)
    assert current is not None
    assert current.state is not InstanceState.STOPPED
    held = manager.get_reservation(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.RESERVED


def test_wrong_digest_does_not_infer(tmp_path: Path) -> None:
    evidence = _qualification()
    decision = compose_provider_plan(_inputs(evidence))
    manager = _manager(tmp_path)
    admitted = manager.admit_provider(decision, _envelope(), PlanFailure.NONE)
    reservation = admitted.reservation
    assert is_resolved(reservation)
    configuration = decision.configuration
    assert isinstance(configuration, ProviderDeploymentConfiguration)

    class _Wrong(_Port):
        def observe(self, name: str, digest: str) -> ProviderObservation:
            del name, digest
            return ProviderObservation("wrong_identity", "cd" * 32, 1, None)

    port = _Wrong()
    service = ProviderServeService(_Log(), port, manager, CLOCK)
    started = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
    )
    assert started.failure is ServeFailure.PROVIDER_RESIDENCY_MISMATCH
    assert port.inferred == 0
    assert not is_resolved(started.proof)


def test_stop_waits_until_the_digest_is_absent(tmp_path: Path) -> None:
    evidence = _qualification()
    decision = compose_provider_plan(_inputs(evidence))
    manager = _manager(tmp_path)
    admitted = manager.admit_provider(decision, _envelope(), PlanFailure.NONE)
    reservation = admitted.reservation
    assert is_resolved(reservation)
    configuration = decision.configuration
    assert isinstance(configuration, ProviderDeploymentConfiguration)

    class _Lag(_Port):
        def __init__(self) -> None:
            super().__init__()
            self.reads = 0

        def unload(self, name: str) -> str:
            del name
            return "none"

        def observe(self, name: str, digest: str) -> ProviderObservation:
            self.reads += 1
            if self.reads < 4:
                return ProviderObservation("expected_resident", digest, 10, None)
            return ProviderObservation("absent", None, None, None)

    port = _Lag()
    service = ProviderServeService(_Log(), port, manager, CLOCK)
    started = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
    )
    assert is_resolved(started.instance)
    stopped = service.stop(started.instance.instance_id)
    assert stopped.outcome is ServeOutcome.STOPPED
    held = manager.get_reservation(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.RESERVED


def _admitted(tmp_path: Path):
    evidence = _qualification()
    decision = compose_provider_plan(_inputs(evidence))
    manager = _manager(tmp_path)
    admitted = manager.admit_provider(decision, _envelope(), PlanFailure.NONE)
    reservation = admitted.reservation
    assert is_resolved(reservation)
    configuration = decision.configuration
    assert isinstance(configuration, ProviderDeploymentConfiguration)
    return evidence, configuration, manager, reservation


def test_wrong_generation_is_refused_before_residency(tmp_path: Path) -> None:
    evidence, configuration, manager, reservation = _admitted(tmp_path)
    port = _Port()
    service = ProviderServeService(_Log(), port, manager, CLOCK)
    refused = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
        _runtime(generation_id="fgen_other"),
    )
    assert refused.failure is ServeFailure.FOUNDATION_MISMATCH
    assert port.contexts == []
    assert port.inferred == 0
    assert service.list_instances() == ()
    environment = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
        _runtime(generation_id="renv_ceedac1939fecd21"),
    )
    assert environment.failure is ServeFailure.FOUNDATION_MISMATCH
    assert port.contexts == []


def test_wrong_execution_fingerprint_is_refused_before_residency(
    tmp_path: Path,
) -> None:
    evidence, configuration, manager, reservation = _admitted(tmp_path)
    port = _Port()
    service = ProviderServeService(_Log(), port, manager, CLOCK)
    refused = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
        _runtime(execution_environment_fingerprint="exe_other"),
    )
    assert refused.failure is ServeFailure.FOUNDATION_MISMATCH
    assert port.contexts == []


def test_unready_foundation_is_refused_before_residency(tmp_path: Path) -> None:
    evidence, configuration, manager, reservation = _admitted(tmp_path)
    port = _Port()
    service = ProviderServeService(_Log(), port, manager, CLOCK)
    refused = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
        _runtime(ready=False),
    )
    assert refused.failure is ServeFailure.FOUNDATION_NOT_READY
    assert port.contexts == []
    unresolved = start_ollama(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
        OllamaAssessment(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "foundation is not verified",
        ),
    )
    assert unresolved.failure is ServeFailure.FOUNDATION_NOT_READY
    assert port.contexts == []


def test_same_digest_on_the_wrong_foundation_does_not_serve(
    tmp_path: Path,
) -> None:
    evidence, configuration, manager, reservation = _admitted(tmp_path)
    assert configuration.digest == DIGEST
    port = _Port()
    service = ProviderServeService(_Log(), port, manager, CLOCK)
    refused = _begin(
        service,
        configuration,
        reservation.reservation_id,
        evidence,
        _runtime(generation_id="fgen_wrong_host"),
    )
    assert refused.failure is ServeFailure.FOUNDATION_MISMATCH
    assert port.resident is False


def test_stop_lag_reconciles_to_stopped_without_release(tmp_path: Path) -> None:
    evidence, configuration, manager, reservation = _admitted(tmp_path)

    class _Sticky(_Port):
        def unload(self, name: str) -> str:
            del name
            return "none"

    port = _Sticky()
    service = ProviderServeService(_Log(), port, manager, CLOCK, absence_wait_seconds=0)
    started = _begin(service, configuration, reservation.reservation_id, evidence)
    assert is_resolved(started.instance)
    stopped = service.stop(started.instance.instance_id)
    assert stopped.failure is ServeFailure.PROVIDER_UNLOAD_FAILED
    current = service.get_instance(started.instance.instance_id)
    assert current is not None
    assert current.state is InstanceState.STOPPING
    port.resident = False
    reconciled = service.reconcile()
    assert len(reconciled) == 1
    assert reconciled[0].outcome is ServeOutcome.STOPPED
    finished = service.get_instance(started.instance.instance_id)
    assert finished is not None
    assert finished.state is InstanceState.STOPPED
    held = manager.get_reservation(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.RESERVED
    again = service.reconcile()
    assert again == ()


def test_reconcile_does_not_treat_wrong_identity_as_stopped(
    tmp_path: Path,
) -> None:
    evidence, configuration, manager, reservation = _admitted(tmp_path)

    class _Switch(_Port):
        def __init__(self) -> None:
            super().__init__()
            self.mode = "expected_resident"

        def unload(self, name: str) -> str:
            del name
            return "none"

        def observe(self, name: str, digest: str) -> ProviderObservation:
            del name
            if self.mode == "expected_resident":
                return ProviderObservation("expected_resident", digest, 1, None)
            return ProviderObservation("wrong_identity", "cd" * 32, 1, None)

    port = _Switch()
    service = ProviderServeService(_Log(), port, manager, CLOCK, absence_wait_seconds=0)
    started = _begin(service, configuration, reservation.reservation_id, evidence)
    assert is_resolved(started.instance)
    port.mode = "wrong_identity"
    stopped = service.stop(started.instance.instance_id)
    assert stopped.failure is ServeFailure.PROVIDER_UNLOAD_FAILED
    reconciled = service.reconcile()
    assert reconciled[0].failure is ServeFailure.PROVIDER_RESIDENCY_MISMATCH
    current = service.get_instance(started.instance.instance_id)
    assert current is not None
    assert current.state is InstanceState.STOPPING
    held = manager.get_reservation(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.RESERVED

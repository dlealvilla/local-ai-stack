"""PrerequisiteReadiness events (MACHI 2.5.1).

Operational metadata only. Absolute paths, pip transcripts, and customer
content stay out of event payloads. Interpreter identity uses basenames.
"""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.ids import InstallId, InstallRunId, Name
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe
from machi.prerequisites.contracts import (
    ActionKind,
    ActionStatus,
    DiagnosisCode,
    InterpreterResolution,
    PolicyMode,
    PrerequisiteDiagnosis,
    PrerequisiteInspection,
    PrerequisitePlan,
    ReadinessState,
    RemediationResult,
    RemediationSourceKind,
    VerificationResult,
)

PREREQUISITE_BLOCK = "2"
PREREQUISITE_COMPONENT = "2.5.1"
INSPECTED_TYPE = "prerequisite.inspected"
DIAGNOSED_TYPE = "prerequisite.diagnosed"
PLAN_CREATED_TYPE = "prerequisite.plan_created"
REMEDIATION_STARTED_TYPE = "prerequisite.remediation_started"
REMEDIATION_COMPLETED_TYPE = "prerequisite.remediation_completed"
REMEDIATION_FAILED_TYPE = "prerequisite.remediation_failed"
VERIFIED_TYPE = "prerequisite.verified"


def _outcome_for(readiness: ReadinessState) -> EventOutcome:
    if readiness is ReadinessState.READY:
        return EventOutcome.PASS
    if readiness is ReadinessState.NOT_APPLICABLE:
        return EventOutcome.INFO
    if readiness in {ReadinessState.BLOCKED, ReadinessState.REMEDIABLE}:
        return EventOutcome.BLOCKED
    if readiness is ReadinessState.UNKNOWN:
        return EventOutcome.UNRESOLVED
    return EventOutcome.FAIL


@contract(kind="prerequisite.inspected", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteInspectedPayload(Contract):
    """Safe operational body for one inspection."""

    target_id: Name = meaning("target identity")
    adapter_id: str = meaning("adapter identifier")
    applicable: bool = meaning("whether the adapter applies on this host")
    executable_found: bool = meaning("whether the executable was resolved")
    invocation_ok: bool = meaning("whether the health invocation exited zero")
    timed_out: bool = meaning("whether the health invocation timed out")
    permission_denied: bool = meaning("whether permissions refused execution")
    interpreter_resolved: bool = meaning("whether a unique interpreter was identified")
    readiness: ReadinessState = meaning("readiness implied by inspection")


@contract(kind="prerequisite.diagnosed", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteDiagnosedPayload(Contract):
    """Safe operational body for one diagnosis."""

    target_id: Name = meaning("target identity")
    adapter_id: str = meaning("adapter identifier")
    code: DiagnosisCode = meaning("stable diagnosis class")
    module_name: Maybe[str] = meaning("missing import name when that is the class")
    remediable: bool = meaning("whether an allowlisted action exists")
    readiness: ReadinessState = meaning("readiness after diagnosis")


@contract(kind="prerequisite.plan_created", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisitePlanCreatedPayload(Contract):
    """Safe operational body for a created plan. Not a mutation."""

    target_id: Name = meaning("target identity")
    adapter_id: str = meaning("adapter identifier")
    plan_id: str = meaning("opaque plan identity")
    policy_mode: PolicyMode = meaning("policy mode that produced the plan")
    action_kind: ActionKind = meaning("primary planned action kind")
    source: RemediationSourceKind = meaning("dependency source represented by the plan")
    diagnosis_code: DiagnosisCode = meaning("diagnosis that produced the plan")


@contract(kind="prerequisite.remediation_started", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteRemediationStartedPayload(Contract):
    """Safe operational body recorded before an allowlisted mutation."""

    target_id: Name = meaning("target identity")
    adapter_id: str = meaning("adapter identifier")
    plan_id: str = meaning("opaque plan identity")
    action_id: str = meaning("opaque action identity")
    action_kind: ActionKind = meaning("action about to run")
    package_name: str = meaning("allowlisted package name; empty for no-op")


@contract(kind="prerequisite.remediation_completed", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteRemediationCompletedPayload(Contract):
    """Safe operational body after a mutation attempt that did not fail closed."""

    target_id: Name = meaning("target identity")
    adapter_id: str = meaning("adapter identifier")
    plan_id: str = meaning("opaque plan identity")
    action_id: str = meaning("opaque action identity")
    status: ActionStatus = meaning("action status after the attempt")
    attempted: bool = meaning("whether a host command ran")
    changed: bool = meaning("whether the adapter believes the environment changed")
    interpreter_basename: str = meaning("interpreter basename that was targeted")


@contract(kind="prerequisite.remediation_failed", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteRemediationFailedPayload(Contract):
    """Safe operational body after a failed or blocked mutation attempt."""

    target_id: Name = meaning("target identity")
    adapter_id: str = meaning("adapter identifier")
    plan_id: str = meaning("opaque plan identity")
    action_id: str = meaning("opaque action identity")
    status: ActionStatus = meaning("failed or blocked")
    attempted: bool = meaning("whether a host command ran")


@contract(kind="prerequisite.verified", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteVerifiedPayload(Contract):
    """Safe operational body for post-cycle verification."""

    target_id: Name = meaning("target identity")
    adapter_id: str = meaning("adapter identifier")
    ready: bool = meaning("true only when verification readiness is ready")
    readiness: ReadinessState = meaning("readiness after verification")
    diagnosis_code: DiagnosisCode = meaning("verification diagnosis")


def _mint(
    *,
    event_type: str,
    outcome: EventOutcome,
    privacy: PrivacyClass,
    payload: Contract,
    install_id: Maybe[InstallId] | None,
    install_run_id: Maybe[InstallRunId] | None,
    clock: Clock | None,
) -> EventRecord:
    event = EventRecord.create(
        event_type=event_type,
        block_id=PREREQUISITE_BLOCK,
        component_id=PREREQUISITE_COMPONENT,
        outcome=outcome,
        privacy=privacy,
        payload=payload,
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock or SystemClock(),
    )
    if event.privacy is PrivacyClass.CUSTOMER_CONTENT:
        raise ValidationError("prerequisite events must not be customer_content")
    return event


def prerequisite_inspected(
    inspection: PrerequisiteInspection,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint inspection evidence. Does not persist it."""
    return _mint(
        event_type=INSPECTED_TYPE,
        outcome=_outcome_for(inspection.readiness),
        privacy=PrivacyClass.OPERATIONAL,
        payload=PrerequisiteInspectedPayload(
            target_id=inspection.target.target_id,
            adapter_id=inspection.target.adapter_id,
            applicable=inspection.applicable,
            executable_found=inspection.executable_found,
            invocation_ok=inspection.invocation_ok,
            timed_out=inspection.timed_out,
            permission_denied=inspection.permission_denied,
            interpreter_resolved=inspection.interpreter_resolution
            in {
                InterpreterResolution.SHEBANG_ABSOLUTE,
                InterpreterResolution.ENV_WHICH,
            },
            readiness=inspection.readiness,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )


def prerequisite_diagnosed(
    diagnosis: PrerequisiteDiagnosis,
    *,
    target_id: Name,
    adapter_id: str,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint diagnosis evidence. Does not persist it."""
    return _mint(
        event_type=DIAGNOSED_TYPE,
        outcome=_outcome_for(diagnosis.readiness),
        privacy=PrivacyClass.OPERATIONAL,
        payload=PrerequisiteDiagnosedPayload(
            target_id=target_id,
            adapter_id=adapter_id,
            code=diagnosis.code,
            module_name=diagnosis.module_name,
            remediable=diagnosis.remediable,
            readiness=diagnosis.readiness,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )


def prerequisite_plan_created(
    plan: PrerequisitePlan,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint plan evidence. Does not persist it. Does not mutate."""
    primary = plan.actions[0]
    return _mint(
        event_type=PLAN_CREATED_TYPE,
        outcome=EventOutcome.INFO,
        privacy=PrivacyClass.OPERATIONAL,
        payload=PrerequisitePlanCreatedPayload(
            target_id=plan.target.target_id,
            adapter_id=plan.target.adapter_id,
            plan_id=plan.plan_id.value,
            policy_mode=plan.policy_mode,
            action_kind=primary.action_kind,
            source=primary.source,
            diagnosis_code=plan.diagnosis.code,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )


def prerequisite_remediation_started(
    plan: PrerequisitePlan,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint a start marker before an allowlisted mutation."""
    primary = plan.actions[0]
    package = primary.dependency.package_name if primary.dependency is not None else ""
    return _mint(
        event_type=REMEDIATION_STARTED_TYPE,
        outcome=EventOutcome.INFO,
        privacy=PrivacyClass.OPERATIONAL,
        payload=PrerequisiteRemediationStartedPayload(
            target_id=plan.target.target_id,
            adapter_id=plan.target.adapter_id,
            plan_id=plan.plan_id.value,
            action_id=primary.action_id.value,
            action_kind=primary.action_kind,
            package_name=package,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )


def prerequisite_remediation_completed(
    plan: PrerequisitePlan,
    result: RemediationResult,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint a completion marker. Does not imply READY."""
    return _mint(
        event_type=REMEDIATION_COMPLETED_TYPE,
        outcome=EventOutcome.INFO,
        privacy=PrivacyClass.OPERATIONAL,
        payload=PrerequisiteRemediationCompletedPayload(
            target_id=plan.target.target_id,
            adapter_id=plan.target.adapter_id,
            plan_id=plan.plan_id.value,
            action_id=result.action.action_id.value,
            status=result.action.status,
            attempted=result.attempted,
            changed=result.changed,
            interpreter_basename=result.interpreter_basename,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )


def prerequisite_remediation_failed(
    plan: PrerequisitePlan,
    result: RemediationResult,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint a failure marker. Never a READY claim."""
    return _mint(
        event_type=REMEDIATION_FAILED_TYPE,
        outcome=EventOutcome.FAIL,
        privacy=PrivacyClass.OPERATIONAL,
        payload=PrerequisiteRemediationFailedPayload(
            target_id=plan.target.target_id,
            adapter_id=plan.target.adapter_id,
            plan_id=plan.plan_id.value,
            action_id=result.action.action_id.value,
            status=result.action.status,
            attempted=result.attempted,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )


def prerequisite_verified(
    verification: VerificationResult,
    *,
    target_id: Name,
    adapter_id: str,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint verification evidence after re-inspect."""
    return _mint(
        event_type=VERIFIED_TYPE,
        outcome=_outcome_for(verification.readiness),
        privacy=PrivacyClass.OPERATIONAL,
        payload=PrerequisiteVerifiedPayload(
            target_id=target_id,
            adapter_id=adapter_id,
            ready=verification.ready,
            readiness=verification.readiness,
            diagnosis_code=verification.diagnosis.code,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )

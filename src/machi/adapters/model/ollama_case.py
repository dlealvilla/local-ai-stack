"""One local Ollama qualification case. Shadow follows admission."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace

from machi.adapters.model.ollama_api import OllamaModelApi
from machi.adapters.model.ollama_qualifier import qualify_ollama
from machi.admit.contracts import AdmissionDecision, AdmissionOutcome
from machi.admit.service import ResourceManager
from machi.capacity.contracts import CapacityEnvelope
from machi.kernel.clock import FixedClock
from machi.kernel.errors import PersistenceError
from machi.kernel.journal import Journal
from machi.kernel.unresolved import is_resolved
from machi.model.comparison import QualificationComparison, compare
from machi.model.events import comparison_event
from machi.model.provider_candidate import (
    OllamaCatalogCandidate,
    canonical_digest,
)
from machi.model.provider_qualification import OllamaQualificationEvidence
from machi.model.qualification import QualificationOutcome
from machi.model.shadow import ShadowEvaluation, evaluate_shadow
from machi.plan.policy import POLICY_VERSION
from machi.plan.qualification_probe import make_qualification_probe


@dataclass(frozen=True, slots=True)
class OllamaQualificationCase:
    """Shadow, one reservation, provider evidence, and optional journal id."""

    shadow: ShadowEvaluation | None
    admission: AdmissionDecision
    evidence: OllamaQualificationEvidence | None
    comparison: QualificationComparison | None
    status: str
    reservation_released: bool
    journal_event_id: str | None
    journal_failure: str | None


def run_ollama_qualification_case(
    *,
    candidate: OllamaCatalogCandidate,
    envelope: CapacityEnvelope,
    manager: ResourceManager,
    api: OllamaModelApi,
    generation_id: str,
    foundation_id: str,
    engine_version: str,
    hardware_class: str,
    execution_environment_fingerprint: str,
    accelerator_identity: str,
    context: int,
    concurrency: int,
    observed_at: dt.datetime,
    journal: Journal | None = None,
) -> OllamaQualificationCase:
    """Admit the remaining SAFE envelope, then let Ollama decide."""
    probe = make_qualification_probe(
        provider="ollama",
        candidate_id=candidate.candidate_id,
        digest=candidate.digest,
        foundation_id=foundation_id,
        generation_id=generation_id,
        capacity_evidence_id=envelope.evidence_id,
        accelerator_identity=accelerator_identity,
        policy_version=POLICY_VERSION,
    )
    admission = manager.admit_probe(probe, envelope)
    if admission.outcome is not AdmissionOutcome.ADMITTED:
        return OllamaQualificationCase(
            None, admission, None, None, "not_admitted", False, None, None
        )
    reservation = admission.reservation
    if not is_resolved(reservation):
        return OllamaQualificationCase(
            None, admission, None, None, "not_admitted", False, None, None
        )
    shadow = evaluate_shadow(
        candidate,
        capacity_evidence_id=envelope.evidence_id,
        accelerator_identity=accelerator_identity,
        authorized_accelerator_bytes=reservation.accelerator_memory_bytes,
        authorized_host_bytes=reservation.host_memory_bytes,
        context=context,
        concurrency=concurrency,
        observed_at=observed_at,
    )
    evidence = qualify_ollama(
        api,
        candidate,
        generation_id=generation_id,
        engine_version=engine_version,
        hardware_class=hardware_class,
        execution_environment_fingerprint=execution_environment_fingerprint,
        context=context,
        concurrency=concurrency,
        observed_at=observed_at,
    )
    cleanup = _cleanup(
        api,
        candidate,
        attempted=evidence.failure != "catalog_identity_changed",
    )
    released = False
    status = "refused"
    if cleanup != "none":
        status = "cleanup_reconcile_required"
        if evidence.outcome is QualificationOutcome.PASS:
            evidence = replace(
                evidence,
                outcome=QualificationOutcome.FAIL_HOST,
                failure="cleanup_reconcile_required",
                unload_failure=cleanup,
            )
        else:
            evidence = replace(evidence, unload_failure=cleanup)
    else:
        if evidence.outcome is QualificationOutcome.PASS:
            evidence = replace(evidence, unload_failure="none")
            status = "clean"
        manager.release(reservation.reservation_id)
        released = True
    comparison = compare(
        shadow,
        evidence,
        hardware_class=hardware_class,
        execution_environment_fingerprint=execution_environment_fingerprint,
        observed_at=observed_at,
    )
    event_id, journal_failure = _journal(journal, comparison, observed_at)
    return OllamaQualificationCase(
        shadow,
        admission,
        evidence,
        comparison,
        status,
        released,
        event_id,
        journal_failure,
    )


def _cleanup(
    api: OllamaModelApi,
    candidate: OllamaCatalogCandidate,
    *,
    attempted: bool,
) -> str:
    if attempted:
        result = api.unload(candidate.display_name)
        if result.failure != "none":
            return result.failure
    if _resident(api, candidate):
        return "resident_after_unload"
    return "none"


def _resident(api: OllamaModelApi, candidate: OllamaCatalogCandidate) -> bool:
    for item in api.running_models():
        if item.name != candidate.display_name:
            continue
        if canonical_digest(item.digest) == candidate.digest:
            return True
    return False


def _journal(
    journal: Journal | None,
    comparison: QualificationComparison,
    observed_at: dt.datetime,
) -> tuple[str | None, str | None]:
    if journal is None:
        return None, None
    try:
        event = journal.append(
            comparison_event(comparison, clock=FixedClock(observed_at))
        )
    except PersistenceError:
        return None, "journal_append_failed"
    return str(event.event_id), None

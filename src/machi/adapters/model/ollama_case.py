"""One local Ollama qualification case. Shadow runs before the provider."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from machi.adapters.model.ollama_api import OllamaModelApi
from machi.adapters.model.ollama_qualifier import qualify_ollama
from machi.admit.contracts import AdmissionDecision, AdmissionOutcome
from machi.admit.service import ResourceManager
from machi.capacity.contracts import CapacityEnvelope
from machi.kernel.unresolved import is_resolved
from machi.model.comparison import QualificationComparison, compare
from machi.model.provider_candidate import OllamaCatalogCandidate
from machi.model.provider_qualification import OllamaQualificationEvidence
from machi.model.shadow import ShadowEvaluation, evaluate_shadow
from machi.plan.policy import POLICY_VERSION
from machi.plan.qualification_probe import make_qualification_probe


@dataclass(frozen=True, slots=True)
class OllamaQualificationCase:
    """Shadow, one reservation, and the provider result when it ran."""

    shadow: ShadowEvaluation
    admission: AdmissionDecision
    evidence: OllamaQualificationEvidence | None
    comparison: QualificationComparison | None


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
    accelerator_memory_bytes: int,
    host_memory_bytes: int,
    context: int,
    concurrency: int,
    observed_at: dt.datetime,
) -> OllamaQualificationCase:
    """Authorize once, then let Ollama decide. Shadow cannot veto."""
    shadow = evaluate_shadow(
        candidate,
        envelope,
        accelerator_identity=accelerator_identity,
        context=context,
        concurrency=concurrency,
        observed_at=observed_at,
    )
    probe = make_qualification_probe(
        provider="ollama",
        candidate_id=candidate.candidate_id,
        digest=candidate.digest,
        foundation_id=foundation_id,
        generation_id=generation_id,
        capacity_evidence_id=envelope.evidence_id,
        accelerator_identity=accelerator_identity,
        accelerator_memory_bytes=accelerator_memory_bytes,
        host_memory_bytes=host_memory_bytes,
        policy_version=POLICY_VERSION,
    )
    admission = manager.admit_probe(probe, envelope)
    if admission.outcome is not AdmissionOutcome.ADMITTED:
        return OllamaQualificationCase(shadow, admission, None, None)
    evidence: OllamaQualificationEvidence | None = None
    try:
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
    finally:
        reservation = admission.reservation
        if is_resolved(reservation):
            manager.release(reservation.reservation_id)
    comparison = compare(
        shadow,
        evidence,
        hardware_class=hardware_class,
        execution_environment_fingerprint=execution_environment_fingerprint,
        observed_at=observed_at,
    )
    return OllamaQualificationCase(shadow, admission, evidence, comparison)

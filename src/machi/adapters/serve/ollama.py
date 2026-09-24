"""Map the public Ollama client onto the provider serve port."""

from __future__ import annotations

from machi.adapters.model.ollama_api import OllamaApiError, OllamaModelApi
from machi.adapters.model.ollama_residency import observe_residency
from machi.foundation.contracts import FailureCode, SupportState
from machi.foundation.ollama import OllamaAssessment
from machi.model.provider_qualification import (
    OllamaQualificationEvidence,
    qualification_covers,
)
from machi.plan.provider import ProviderDeploymentConfiguration
from machi.serve.provider import (
    ProviderInferResult,
    ProviderObservation,
    ProviderServeDecision,
    ProviderServeService,
    VerifiedProviderRuntime,
)


class OllamaServeAdapter:
    """Provider mechanics only. This object does not admit or release resources."""

    def __init__(self, api: OllamaModelApi) -> None:
        self._api = api

    def refresh(self, name: str, *, context: int) -> str:
        try:
            result = self._api.preload(name, context=context)
        except OllamaApiError as exc:
            return exc.code
        return result.failure

    def observe(self, name: str, digest: str) -> ProviderObservation:
        try:
            seen = observe_residency(self._api, name=name, digest=digest)
        except OllamaApiError:
            return ProviderObservation("unresolved", None, None, None)
        return ProviderObservation(
            seen.state.value,
            seen.digest,
            seen.size_vram_bytes,
            seen.expires_at,
        )

    def infer(self, name: str, *, context: int) -> ProviderInferResult:
        try:
            result = self._api.generate_probe(name, context=context)
        except OllamaApiError as exc:
            return ProviderInferResult(exc.code, 0, 0, None)
        return ProviderInferResult(
            result.failure,
            result.input_tokens,
            result.output_tokens,
            result.generation_seconds,
        )

    def unload(self, name: str) -> str:
        try:
            result = self._api.unload(name)
        except OllamaApiError as exc:
            return exc.code
        return result.failure


def start_ollama(
    service: ProviderServeService,
    configuration: ProviderDeploymentConfiguration,
    reservation_id: str,
    qualification: OllamaQualificationEvidence,
    assessment: OllamaAssessment,
) -> ProviderServeDecision:
    """Require coverage and the verified Foundation, then serve."""
    covered = qualification.qualification_id == configuration.qualification_id
    covered = covered and qualification_covers(
        qualification,
        digest=configuration.digest,
        generation_id=configuration.generation_id,
        context=configuration.context_length,
        concurrency=configuration.concurrency,
    )
    return service.start(
        configuration,
        reservation_id,
        _verified_runtime(assessment),
        covered=covered,
    )


def _verified_runtime(assessment: OllamaAssessment) -> VerifiedProviderRuntime:
    substrate = assessment.substrate
    ready = (
        assessment.support is SupportState.READY
        and assessment.failure is FailureCode.NONE
        and substrate is not None
    )
    if substrate is None:
        return VerifiedProviderRuntime(
            provider="ollama",
            generation_id="unresolved",
            execution_environment_fingerprint="unresolved",
            ready=False,
        )
    return VerifiedProviderRuntime(
        provider="ollama",
        generation_id=substrate.generation.generation_id,
        execution_environment_fingerprint=(
            substrate.generation.execution_environment_fingerprint
        ),
        ready=ready,
    )

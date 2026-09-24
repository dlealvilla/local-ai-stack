"""Map fixture Ollama results into provider qualification evidence."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from machi.adapters.model.ollama_api import (
    GenerateResult,
    ListedModel,
    OllamaApiError,
    OllamaModelApi,
    RunningModel,
)
from machi.foundation.metrics import MetricAvailability
from machi.kernel.unresolved import NOT_MEASURED, Maybe
from machi.model.provider_candidate import (
    OllamaCatalogCandidate,
    canonical_digest,
)
from machi.model.provider_qualification import (
    OllamaQualificationEvidence,
    ProviderFitState,
    ollama_qualification_id,
)
from machi.model.qualification import QualificationOutcome

_VRAM_SOURCE = "ollama.api.ps"
_VRAM_ABSENT = "not_exposed"


def qualify_ollama(
    api: OllamaModelApi,
    candidate: OllamaCatalogCandidate,
    *,
    generation_id: str,
    engine_version: str,
    hardware_class: str,
    execution_environment_fingerprint: str,
    context: int,
    concurrency: int,
    observed_at: dt.datetime,
) -> OllamaQualificationEvidence:
    """Authoritative provider result. This function does not read a shadow."""
    try:
        return _qualify(
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
    except OllamaApiError as exc:
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_HOST,
            provider_fit=ProviderFitState.UNRESOLVED,
            failure=f"provider_{exc.code}",
            token_proved=False,
            observed_at=observed_at,
        )


def _qualify(
    api: OllamaModelApi,
    candidate: OllamaCatalogCandidate,
    *,
    generation_id: str,
    engine_version: str,
    hardware_class: str,
    execution_environment_fingerprint: str,
    context: int,
    concurrency: int,
    observed_at: dt.datetime,
) -> OllamaQualificationEvidence:
    listed = _listed(api, candidate.display_name)
    if listed is None or canonical_digest(listed.digest) != candidate.digest:
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_MODEL,
            provider_fit=ProviderFitState.UNRESOLVED,
            failure="catalog_identity_changed",
            token_proved=False,
            observed_at=observed_at,
        )
    preloaded = api.preload(candidate.display_name)
    preload_load = preloaded.load_seconds
    if preloaded.failure == "host":
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_HOST,
            provider_fit=ProviderFitState.UNRESOLVED,
            failure="provider_host_failure",
            token_proved=False,
            observed_at=observed_at,
        )
    if preloaded.failure == "no_fit":
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_MODEL,
            provider_fit=ProviderFitState.NO_FIT,
            failure="provider_no_fit",
            token_proved=False,
            observed_at=observed_at,
        )
    resident = _resident(api, candidate)
    if resident is None:
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_MODEL,
            provider_fit=ProviderFitState.UNRESOLVED,
            failure="loaded_digest_absent",
            token_proved=False,
            observed_at=observed_at,
        )
    generated = api.generate_probe(candidate.display_name)
    proved = generated.output_tokens > 0 and generated.failure == "none"
    after = _resident(api, candidate)
    metrics = _metrics(resident, generated, proved, preload_load)
    if after is None:
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_MODEL,
            provider_fit=ProviderFitState.FIT,
            failure="post_token_identity_mismatch",
            token_proved=False,
            observed_at=observed_at,
            size_bytes=metrics.size_bytes,
            size_vram_bytes=metrics.size_vram_bytes,
            load_seconds=metrics.load_seconds,
            generation_seconds=metrics.generation_seconds,
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
            tokens_per_second=metrics.tokens_per_second,
        )
    if not proved:
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_MODEL,
            provider_fit=ProviderFitState.FIT,
            failure="token_proof_missing",
            token_proved=False,
            observed_at=observed_at,
            size_bytes=metrics.size_bytes,
            size_vram_bytes=metrics.size_vram_bytes,
            load_seconds=metrics.load_seconds,
            generation_seconds=metrics.generation_seconds,
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
            tokens_per_second=metrics.tokens_per_second,
        )
    return _evidence(
        candidate,
        generation_id=generation_id,
        engine_version=engine_version,
        hardware_class=hardware_class,
        execution_environment_fingerprint=execution_environment_fingerprint,
        context=context,
        concurrency=concurrency,
        outcome=QualificationOutcome.PASS,
        provider_fit=ProviderFitState.FIT,
        failure="none",
        token_proved=True,
        observed_at=observed_at,
        size_bytes=metrics.size_bytes,
        size_vram_bytes=metrics.size_vram_bytes,
        load_seconds=metrics.load_seconds,
        generation_seconds=metrics.generation_seconds,
        input_tokens=metrics.input_tokens,
        output_tokens=metrics.output_tokens,
        tokens_per_second=metrics.tokens_per_second,
    )


def _metrics(
    resident: RunningModel,
    generated: GenerateResult,
    proved: bool,
    preload_load_seconds: float | None,
) -> _ProbeMetrics:
    return _ProbeMetrics(
        size_bytes=_maybe_int(resident.size_bytes),
        size_vram_bytes=_maybe_int(resident.size_vram_bytes),
        load_seconds=preload_load_seconds,
        generation_seconds=generated.generation_seconds,
        input_tokens=generated.input_tokens,
        output_tokens=generated.output_tokens,
        tokens_per_second=_rate(
            generated.output_tokens, generated.generation_seconds, proved
        ),
    )


@dataclass(frozen=True, slots=True)
class _ProbeMetrics:
    size_bytes: Maybe[int]
    size_vram_bytes: Maybe[int]
    load_seconds: float | None
    generation_seconds: float | None
    input_tokens: int
    output_tokens: int
    tokens_per_second: Maybe[float]


def _listed(api: OllamaModelApi, name: str) -> ListedModel | None:
    for item in api.list_models():
        if item.name == name:
            return item
    return None


def _resident(
    api: OllamaModelApi, candidate: OllamaCatalogCandidate
) -> RunningModel | None:
    for item in api.running_models():
        if item.name != candidate.display_name:
            continue
        if canonical_digest(item.digest) == candidate.digest:
            return item
    return None


def _rate(tokens: int, seconds: float | None, proved: bool) -> Maybe[float]:
    if proved and isinstance(seconds, float) and seconds > 0 and tokens > 0:
        return tokens / seconds
    return NOT_MEASURED


def _maybe_int(value: int | None) -> Maybe[int]:
    if isinstance(value, int) and value >= 0:
        return value
    return NOT_MEASURED


def _evidence(
    candidate: OllamaCatalogCandidate,
    *,
    generation_id: str,
    engine_version: str,
    hardware_class: str,
    execution_environment_fingerprint: str,
    context: int,
    concurrency: int,
    outcome: QualificationOutcome,
    provider_fit: ProviderFitState,
    failure: str,
    token_proved: bool,
    observed_at: dt.datetime,
    load_seconds: float | None = None,
    generation_seconds: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    tokens_per_second: Maybe[float] = NOT_MEASURED,
    size_bytes: Maybe[int] = NOT_MEASURED,
    size_vram_bytes: Maybe[int] = NOT_MEASURED,
) -> OllamaQualificationEvidence:
    vram_known = isinstance(size_vram_bytes, int)
    return OllamaQualificationEvidence(
        qualification_id=ollama_qualification_id(
            digest=candidate.digest,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
        ),
        digest=candidate.digest,
        display_name=candidate.display_name,
        generation_id=generation_id,
        engine_version=engine_version,
        hardware_class=hardware_class,
        execution_environment_fingerprint=execution_environment_fingerprint,
        context=context,
        concurrency=concurrency,
        outcome=outcome,
        provider_fit=provider_fit,
        failure=failure,
        authority="ollama",
        size_bytes=size_bytes,
        size_vram_bytes=size_vram_bytes,
        size_vram_availability=(
            MetricAvailability.OBSERVED
            if vram_known
            else MetricAvailability.NOT_EXPOSED
        ),
        size_vram_source=_VRAM_SOURCE if vram_known else _VRAM_ABSENT,
        size_vram_semantics="runtime_reported",
        load_seconds=(
            load_seconds if isinstance(load_seconds, float) else NOT_MEASURED
        ),
        input_tokens=(
            input_tokens if isinstance(input_tokens, int) else NOT_MEASURED
        ),
        output_tokens=(
            output_tokens if isinstance(output_tokens, int) else NOT_MEASURED
        ),
        generation_seconds=(
            generation_seconds
            if isinstance(generation_seconds, float)
            else NOT_MEASURED
        ),
        tokens_per_second=tokens_per_second,
        token_proved=token_proved,
        unload_failure="not_attempted",
        observed_at=observed_at,
    )

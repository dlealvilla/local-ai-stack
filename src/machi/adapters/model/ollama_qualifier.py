"""Map a fixture Ollama result into provider qualification evidence."""

from __future__ import annotations

import datetime as dt

from machi.adapters.model.ollama_api import OllamaModelApi
from machi.foundation.metrics import MetricAvailability
from machi.kernel.unresolved import NOT_MEASURED, Maybe
from machi.model.provider_candidate import (
    OllamaCatalogCandidate,
    canonical_digest,
)
from machi.model.provider_qualification import (
    OllamaQualificationEvidence,
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
    shown = api.show_model(candidate.display_name)
    if shown is None or canonical_digest(shown.digest) != candidate.digest:
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_MODEL,
            failure="digest_mismatch",
            token_proved=False,
            unload_failure="not_attempted",
            observed_at=observed_at,
        )
    generated = api.generate(candidate.display_name)
    if generated.failure == "host":
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_HOST,
            failure="provider_host_failure",
            token_proved=False,
            unload_failure="not_attempted",
            load_seconds=generated.load_seconds,
            observed_at=observed_at,
        )
    if generated.failure == "no_fit":
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_MODEL,
            failure="provider_no_fit",
            token_proved=False,
            unload_failure="not_attempted",
            load_seconds=generated.load_seconds,
            size_bytes=_maybe_int(generated.size_bytes),
            observed_at=observed_at,
        )
    running = api.running_models()
    matched = [
        item
        for item in running
        if canonical_digest(item.digest) == candidate.digest
    ]
    unload = api.unload(candidate.display_name)
    unload_failure = unload.failure if unload.failure != "none" else "none"
    if not matched:
        return _evidence(
            candidate,
            generation_id=generation_id,
            engine_version=engine_version,
            hardware_class=hardware_class,
            execution_environment_fingerprint=execution_environment_fingerprint,
            context=context,
            concurrency=concurrency,
            outcome=QualificationOutcome.FAIL_MODEL,
            failure="loaded_digest_absent",
            token_proved=False,
            unload_failure=unload_failure,
            load_seconds=generated.load_seconds,
            observed_at=observed_at,
        )
    resident = matched[0]
    proved = generated.output_tokens > 0 and generated.failure == "none"
    rate: Maybe[float] = NOT_MEASURED
    if (
        proved
        and isinstance(generated.generation_seconds, float)
        and generated.generation_seconds > 0
    ):
        rate = generated.output_tokens / generated.generation_seconds
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
            failure="token_proof_missing",
            token_proved=False,
            unload_failure=unload_failure,
            load_seconds=generated.load_seconds,
            generation_seconds=generated.generation_seconds,
            output_tokens=generated.output_tokens,
            size_bytes=_maybe_int(resident.size_bytes),
            size_vram_bytes=_maybe_int(resident.size_vram_bytes),
            observed_at=observed_at,
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
        failure="none",
        token_proved=True,
        unload_failure=unload_failure,
        load_seconds=generated.load_seconds,
        generation_seconds=generated.generation_seconds,
        output_tokens=generated.output_tokens,
        tokens_per_second=rate,
        size_bytes=_maybe_int(resident.size_bytes),
        size_vram_bytes=_maybe_int(resident.size_vram_bytes),
        observed_at=observed_at,
    )


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
    failure: str,
    token_proved: bool,
    unload_failure: str,
    observed_at: dt.datetime,
    load_seconds: float | None = None,
    generation_seconds: float | None = None,
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
        input_tokens=NOT_MEASURED,
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
        unload_failure=unload_failure,
        observed_at=observed_at,
    )

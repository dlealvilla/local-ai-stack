"""Map a finished runtime probe onto qualification evidence. No process launcher."""

from __future__ import annotations

import datetime as dt

from machi.kernel.unresolved import NOT_MEASURED, Maybe
from machi.model.qualification import (
    QualificationEvidence,
    QualificationOutcome,
    QualificationRequest,
    qualification_identity,
)

_MODEL_FAILURES = frozenset(
    {
        "inference_failed",
        "process_exited_before_ready",
    }
)


def probe_outcome(*, ready: bool, proved: bool, failure: str) -> QualificationOutcome:
    """Health alone is not a pass. A host fault must not be blamed on the model."""
    if proved and ready:
        return QualificationOutcome.PASS
    if failure in _MODEL_FAILURES:
        return QualificationOutcome.FAIL_MODEL
    return QualificationOutcome.FAIL_HOST


def evidence_for_probe(
    request: QualificationRequest,
    *,
    artifact_id: str,
    ready: bool,
    proved: bool,
    failure: str,
    completion_tokens: int | None,
    load_seconds: float | None,
    generate_seconds: float | None,
    peak_vram_bytes: int | None,
    peak_ram_bytes: int | None,
    observed_at: dt.datetime,
) -> QualificationEvidence:
    """Persist one probe. Estimated figures are not written into measured fields."""
    outcome = probe_outcome(ready=ready, proved=proved, failure=failure)
    tokens_per_second: Maybe[float] = NOT_MEASURED
    if (
        outcome is QualificationOutcome.PASS
        and isinstance(completion_tokens, int)
        and completion_tokens > 0
        and isinstance(generate_seconds, float)
        and generate_seconds > 0
    ):
        tokens_per_second = completion_tokens / generate_seconds
    identity = qualification_identity(
        revision=request.immutable_revision,
        generation_id=request.generation_id,
        engine=request.engine,
        engine_version=request.engine_version,
        backend=request.backend,
        hardware_class=request.hardware_class,
        execution_environment_fingerprint=(
            request.execution_environment_fingerprint
        ),
        dtype=request.dtype,
        quantization=request.quantization,
        context=request.context,
        concurrency=request.concurrency,
        tensor_parallel=request.tensor_parallel,
        policy_version=request.policy_version,
    )
    measured = outcome is QualificationOutcome.PASS and isinstance(load_seconds, float)
    return QualificationEvidence(
        qualification_id=identity,
        artifact_id=artifact_id,
        immutable_revision=request.immutable_revision,
        generation_id=request.generation_id,
        engine=request.engine,
        engine_version=request.engine_version,
        backend=request.backend,
        hardware_class=request.hardware_class,
        execution_environment_fingerprint=(
            request.execution_environment_fingerprint
        ),
        dtype=request.dtype,
        quantization=request.quantization,
        context=request.context,
        concurrency=request.concurrency,
        tensor_parallel=request.tensor_parallel,
        policy_version=request.policy_version,
        outcome=outcome,
        failure="none" if outcome is QualificationOutcome.PASS else failure or "probe",
        load_seconds=load_seconds if isinstance(load_seconds, float) else NOT_MEASURED,
        ttft_seconds=NOT_MEASURED,
        tokens_per_second=tokens_per_second,
        peak_vram_bytes=(
            peak_vram_bytes if isinstance(peak_vram_bytes, int) else NOT_MEASURED
        ),
        peak_ram_bytes=(
            peak_ram_bytes if isinstance(peak_ram_bytes, int) else NOT_MEASURED
        ),
        measured=measured,
        observed_at=observed_at,
    )

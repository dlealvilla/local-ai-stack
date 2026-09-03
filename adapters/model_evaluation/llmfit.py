"""llmfit model-evaluation adapter.

AI_DEPLOYMENT_MODEL_EVALUATION_LLMFIT

Everything llmfit-specific lives here: how it is invoked, how its JSON
is shaped, how its hardware overrides are spelled, and how its failures
are classified. Core sees only normalized evidence, so replacing llmfit
means writing a sibling adapter and changing one configuration value.

Capacity authority stays with the platform. llmfit detects hardware
itself, and its own view would ignore the platform's protected headroom
and any managed reservations, so this adapter always passes explicit
overrides derived from the CapacityEnvelope. The figure handed over is
the safe amount available for an additional workload — never physical
capacity, never raw free capacity, and never headroom subtracted a
second time.

The tool is asked about one candidate at a time via `info`, rather than
for its own top picks via `recommend`. Measured on the reference host,
`recommend` answers a different question — what looks good in llmfit's
whole catalogue — and answers it nondeterministically: every top entry
ties at a score of 100.0, and repeated invocations with identical flags
returned different models, with one model's position moving between 6
and 42 and even the returned set changing. `info` asked about a named
model returned an identical verdict on every run, which is what
evaluating a known candidate set requires. Both modes share the same
JSON envelope.

Read-only by construction: `info` has no side effects, and no server,
daemon or HTTP mode is used.
"""

from __future__ import annotations

import json
import subprocess

from core.model_evaluation import (
    MODEL_EVALUATION_SCHEMA_VERSION,
    ModelEvaluationEvidence,
    ModelEvaluationResult,
    unavailable,
)
from core.runtime_manager import (
    runtime_executable,
    runtime_is_ready,
)


PROVIDER_ID = "llmfit"

RUNTIME_NAME = "llmfit"


#
# llmfit accepts sizes like "28866M". Mebibytes are used so the override
# is precise: rounding up to whole gibibytes would hand llmfit more
# memory than the platform considers safe.
#
MIB = 1024 * 1024


#
# Accelerator memory kinds this adapter can describe to llmfit's single
# `--memory` override, most specific first. This is the capability
# translation boundary, which is why the vocabulary appears here rather
# than in core.
#
PRIMARY_MEMORY_TYPES = (
    "dedicated_vram",
    "unified_memory",
)

SYSTEM_MEMORY_TYPE = "system_ram"


DEFAULT_TIMEOUT_SECONDS = 120


def _settings(config):
    if not config:
        return {}

    return config.get("model_evaluation", {}) or {}


def _mebibytes(value_bytes):
    """Floor to whole mebibytes; never round a safe figure upward."""

    if not isinstance(value_bytes, int):
        return None

    if value_bytes <= 0:
        return None

    mebibytes = value_bytes // MIB

    if mebibytes <= 0:
        return None

    return mebibytes


def _safe_pool_bytes(envelope, memory_type):
    """Safe bytes available for an additional workload in one pool kind."""

    best = None

    for pool in envelope.memory_pools:
        if pool.memory_type != memory_type:
            continue

        figure = (
            pool.safe_available_for_additional_workload_bytes
        )

        if figure is None:
            continue

        if best is None or figure > best:
            best = figure

    return best


def build_overrides(envelope):
    """Describe platform-safe capacity in llmfit's own flags.

    Returns the flag list plus the byte figures used, so a caller can
    prove which capacity was handed over.
    """

    flags = []
    used = {}

    primary_bytes = None
    primary_type = None

    for memory_type in PRIMARY_MEMORY_TYPES:
        primary_bytes = _safe_pool_bytes(
            envelope,
            memory_type,
        )

        if primary_bytes is not None:
            primary_type = memory_type
            break

    primary_mib = _mebibytes(primary_bytes)

    if primary_mib is not None:
        flags.append(
            f"--memory={primary_mib}M"
        )
        used["primary_memory_bytes"] = primary_bytes
        used["primary_memory_type"] = primary_type

    #
    # Safe host RAM is supplied whenever the platform knows it. Whether
    # a MODEL's RAM requirement is resolved is a separate question and
    # does not prevent describing the host honestly.
    #
    ram_bytes = _safe_pool_bytes(
        envelope,
        SYSTEM_MEMORY_TYPE,
    )

    ram_mib = _mebibytes(ram_bytes)

    if ram_mib is not None:
        flags.append(f"--ram={ram_mib}M")
        used["system_ram_bytes"] = ram_bytes

    return flags, used


def parse_model(payload, identity):
    """Find `identity` in an llmfit response.

    llmfit wraps single-model output in the same
    `{"models": [...], "system": {...}}` envelope it uses elsewhere.
    Returns `(shape_recognized, model)`, because the two failures mean
    different things: an unrecognized envelope means the tool did not
    behave as expected, while a recognized envelope without the model
    means the tool simply has nothing for that candidate.

    The returned name must equal what was asked for. Accepting a
    different name would silently evaluate the wrong model.
    """

    if not isinstance(payload, dict):
        return False, None

    models = payload.get("models")

    if not isinstance(models, list):
        return False, None

    for model in models:
        if not isinstance(model, dict):
            continue

        if model.get("name") == identity:
            return True, model

    return True, None


def _evidence(candidate, model, rank):
    components = (
        model.get("score_components") or {}
    )

    if not isinstance(components, dict):
        components = {}

    notes = tuple(
        str(note)
        for note in (model.get("notes") or [])
        if isinstance(note, str)
    )

    return ModelEvaluationEvidence(
        candidate_id=candidate.candidate_id,
        provider=PROVIDER_ID,
        usable=True,
        rank=rank,
        overall_score=model.get("score"),
        fit_score=components.get("fit"),
        quality_score=components.get("quality"),
        speed_score=components.get("speed"),
        context_score=components.get("context"),
        fit_level=model.get("fit_level"),
        recommended_quantization=model.get(
            "best_quant"
        ),
        notes=notes,
    )


def _unusable(candidate, note):
    return ModelEvaluationEvidence(
        candidate_id=candidate.candidate_id,
        provider=PROVIDER_ID,
        usable=False,
        notes=(note,),
    )


def _rank_by_score(scored):
    """Dense rank over distinct scores, best first.

    Equal scores get equal rank so the selector's own tie-break — the
    caller's order — decides, rather than an arbitrary provider
    ordering.
    """

    scores = sorted(
        {
            model.get("score")
            for _candidate, model in scored
            if isinstance(
                model.get("score"),
                (int, float),
            )
        },
        reverse=True,
    )

    rank_of_score = {
        score: rank
        for rank, score in enumerate(scores)
    }

    unscored = len(scores)

    return [
        _evidence(
            candidate,
            model,
            rank_of_score.get(
                model.get("score"),
                unscored,
            ),
        )
        for candidate, model in scored
    ]


def evaluate(
    *,
    candidates,
    envelope,
    config=None,
    runner=None,
):
    """Ask llmfit to rank the supplied candidates.

    Any inability to consult llmfit — not provisioned, non-zero exit,
    timeout, unparseable output, unexpected shape — is reported as
    unavailable with a reason. Raising instead would let a advisory
    provider break selection.
    """

    candidates = list(candidates)

    if not candidates:
        return unavailable(
            PROVIDER_ID,
            "no candidates to evaluate",
        )

    if not runtime_is_ready(RUNTIME_NAME):
        return unavailable(
            PROVIDER_ID,
            (
                "llmfit is not provisioned; run "
                "'./ai prepare' with the provider enabled"
            ),
        )

    settings = _settings(config)

    overrides, used_capacity = build_overrides(
        envelope
    )

    timeout = float(
        settings.get(
            "timeout_seconds",
            DEFAULT_TIMEOUT_SECONDS,
        )
    )

    executable = str(
        runtime_executable(RUNTIME_NAME)
    )

    invocation = {
        "subcommand": "info",
        "overrides": overrides,
        "capacity": used_capacity,
        "timeout_seconds": timeout,
        "commands": [],
    }

    execute = runner or _run

    scored = []
    unusable = []
    failures = []
    responded = False

    for candidate in candidates:
        identity = candidate.provider_identity

        #
        # Argument array, never a shell string: candidate identities
        # come from a catalogue and must never be interpolated into a
        # shell. Global overrides precede the subcommand, which is what
        # llmfit requires.
        #
        command = (
            [executable]
            + overrides
            + ["--json", "info", identity]
        )

        invocation["commands"].append(command)

        try:
            completed = execute(command, timeout)

        except subprocess.TimeoutExpired:
            failures.append(
                f"llmfit timed out after {timeout}s"
            )
            unusable.append(
                _unusable(
                    candidate,
                    "llmfit timed out",
                )
            )
            continue

        except OSError as exc:
            #
            # The tool itself cannot run, so no candidate will fare
            # any better.
            #
            return ModelEvaluationResult(
                schema_version=(
                    MODEL_EVALUATION_SCHEMA_VERSION
                ),
                provider=PROVIDER_ID,
                available=False,
                reason=(
                    f"llmfit could not be executed: {exc}"
                ),
                invocation=invocation,
            )

        if completed.returncode != 0:
            detail = (
                completed.stderr or ""
            ).strip()[:200]

            failures.append(
                "llmfit exited "
                + str(completed.returncode)
                + (f": {detail}" if detail else "")
            )
            unusable.append(
                _unusable(
                    candidate,
                    (
                        "llmfit could not evaluate "
                        + identity
                    ),
                )
            )
            continue

        try:
            payload = json.loads(completed.stdout)

        except ValueError as exc:
            failures.append(
                f"llmfit output was not valid JSON: {exc}"
            )
            unusable.append(
                _unusable(
                    candidate,
                    (
                        "llmfit returned unparseable "
                        "output for " + identity
                    ),
                )
            )
            continue

        recognized, model = parse_model(
            payload,
            identity,
        )

        if not recognized:
            failures.append(
                "llmfit output had no models array"
            )
            unusable.append(
                _unusable(
                    candidate,
                    (
                        "llmfit returned an unrecognized "
                        "response for " + identity
                    ),
                )
            )
            continue

        #
        # The envelope was recognized, so the tool is working.
        #
        responded = True

        if model is None:
            unusable.append(
                _unusable(
                    candidate,
                    (
                        "llmfit returned no matching "
                        "model for " + identity
                    ),
                )
            )
            continue

        scored.append((candidate, model))

    if not responded:
        return ModelEvaluationResult(
            schema_version=(
                MODEL_EVALUATION_SCHEMA_VERSION
            ),
            provider=PROVIDER_ID,
            available=False,
            reason=(
                failures[0]
                if failures
                else "llmfit produced no usable output"
            ),
            invocation=invocation,
        )

    #
    # Evidence is returned in the caller's candidate order so the
    # selector's tie-break stays meaningful.
    #
    by_candidate = {
        entry.candidate_id: entry
        for entry in (
            _rank_by_score(scored) + unusable
        )
    }

    return ModelEvaluationResult(
        schema_version=(
            MODEL_EVALUATION_SCHEMA_VERSION
        ),
        provider=PROVIDER_ID,
        available=True,
        reason=None,
        evidence=tuple(
            by_candidate[candidate.candidate_id]
            for candidate in candidates
            if candidate.candidate_id in by_candidate
        ),
        invocation=invocation,
    )


def _run(command, timeout):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


class LlmfitEvaluationAdapter:
    """Provider object satisfying core.ModelEvaluationProvider."""

    provider = PROVIDER_ID

    def __init__(self, runner=None):
        self._runner = runner

    def evaluate(
        self,
        *,
        candidates,
        envelope,
        config=None,
    ):
        return evaluate(
            candidates=candidates,
            envelope=envelope,
            config=config,
            runner=self._runner,
        )

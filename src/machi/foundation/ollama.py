"""Ollama runtime substrate. A daemon fact, not a model deployment.

The pinned release was read from the official GitHub release channel on
2026-09-24. ``v0.34.3`` was the latest release, not a draft and not a
prerelease. The Linux amd64 checksum is the ``sha256sum.txt`` line for
``ollama-linux-amd64.tar.zst``, and it matches that release asset digest.
A later channel read does not change an existing generation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from machi.foundation.contracts import (
    AcceleratorBackend,
    ExecutorKind,
    FailureCode,
    FeatureState,
    FoundationEngine,
    FoundationFamily,
    FoundationSelection,
    RuntimeCapability,
    SupportState,
)
from machi.foundation.metrics import (
    FoundationMetric,
    FoundationMetricSet,
    MetricAvailability,
)
from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning

_TOKEN_MAX = 80
_REASON_MAX = 240
_PINNED_VERSION = "0.34.3"
_PINNED_TAG = "v0.34.3"
_ARTIFACT_NAME = "ollama-linux-amd64.tar.zst"
_ARTIFACT_SHA256 = "e83a089fd0cd2f79ee2933cca2085846a2065f497adbc6467c402177c68423f9"
_ARTIFACT_BYTES = 1_427_391_999
_SOURCE_URL = (
    "https://github.com/ollama/ollama/releases/download/"
    "v0.34.3/ollama-linux-amd64.tar.zst"
)
_CHECKSUM_URL = (
    "https://github.com/ollama/ollama/releases/download/v0.34.3/sha256sum.txt"
)
_VERSION_TOKEN = re.compile(r"\b(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\b")
_PRERELEASE_MARKERS = ("alpha", "beta", "rc", "preview", "nightly", "dev")
_PRIVATE_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_EXECUTED_BINARY = "executed_binary"
_UNRESOLVED = "unresolved"


class OllamaProviderMode(StrEnum):
    """How this daemon was obtained. Not a serving mode."""

    VERIFIED_EXISTING = "verified_existing"
    MANAGED_PREFIX = "managed_prefix"


class CloudMode(StrEnum):
    """Local happy path requires the vendor cloud to be off."""

    DISABLED = "disabled"
    ENABLED = "enabled"
    UNRESOLVED = "unresolved"


@contract(kind="foundation.ollama_recipe", version=1)
@dataclass(frozen=True, slots=True)
class OllamaRuntimeRecipe(Contract):
    """Checksummed runtime artifact. The delivery URL is provenance only."""

    recipe_id: str = meaning("stable id of this version and artifact")
    version: str = meaning("exact stable version, without a leading v")
    artifact_name: str = meaning("official archive file name")
    artifact_sha256: str = meaning("sha256 of the official archive")
    artifact_bytes: int = meaning("compressed archive size in bytes")
    source_url: str = meaning("release asset url with no credentials")
    checksum_url: str = meaning("official checksum file url")
    license_name: str = meaning("software license of the runtime")
    stable: bool = meaning("true only for a non-prerelease pin")

    def __post_init__(self) -> None:
        _bounded(self.recipe_id, what="recipe", maximum=_TOKEN_MAX)
        _bounded(self.version, what="version", maximum=32)
        _bounded(self.artifact_name, what="artifact", maximum=_TOKEN_MAX)
        _sha256(self.artifact_sha256)
        if self.artifact_bytes < 1:
            raise ValidationError("artifact size must be positive")
        _bounded(self.source_url, what="source", maximum=_REASON_MAX)
        _bounded(self.checksum_url, what="checksum", maximum=_REASON_MAX)
        _bounded(self.license_name, what="license", maximum=32)
        if not self.stable:
            raise ValidationError("ollama recipe must be a stable pin")


@contract(kind="foundation.ollama_raw", version=1)
@dataclass(frozen=True, slots=True)
class OllamaRawEvidence(Contract):
    """Provider text kept apart from the normalized metrics."""

    provider_mode: str = meaning("verified existing or managed prefix")
    version_text: str = meaning("version text from the identified executable")
    api_version: str = meaning("version returned by the local version endpoint")
    artifact_sha256: str = meaning("archive sha256, or unresolved")
    cloud_mode: str = meaning("disabled, enabled, or unresolved")
    endpoint_class: str = meaning("loopback when the bind is private")

    def __post_init__(self) -> None:
        _bounded(self.provider_mode, what="provider", maximum=_TOKEN_MAX)
        _bounded(self.version_text, what="version text", maximum=_REASON_MAX)
        _bounded(self.api_version, what="api version", maximum=32)
        if self.artifact_sha256 != _UNRESOLVED:
            _sha256(self.artifact_sha256)
        _bounded(self.cloud_mode, what="cloud", maximum=16)
        _bounded(self.endpoint_class, what="endpoint", maximum=16)


@contract(kind="foundation.ollama_generation", version=1)
@dataclass(frozen=True, slots=True)
class OllamaFoundationGeneration(Contract):
    """Identity of one Ollama daemon substrate. A new pin is a new id."""

    generation_id: str = meaning("identity of this daemon substrate")
    recipe_id: str = meaning("recipe this generation was verified against")
    provider_mode: OllamaProviderMode = meaning("verified existing or managed")
    version: str = meaning("exact runtime version")
    artifact_sha256: str = meaning("archive sha256, or unresolved")
    runtime_identity_sha256: str = meaning(
        "content identity of the realized runtime, or unresolved"
    )
    identity_strength: str = meaning(
        "archive, runtime closure, or partial executable"
    )
    qualification_reusable: bool = meaning(
        "true only when immutable runtime identity can cover later evidence"
    )
    execution_environment_fingerprint: str = meaning(
        "accelerator environment this generation is bound to"
    )
    cloud_mode: CloudMode = meaning("cloud must be disabled for a happy path")
    endpoint: str = meaning("private endpoint this generation serves")
    created_at: dt.datetime = meaning("when this generation was recorded; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", require_utc(self.created_at, what="created_at")
        )
        _bounded(self.generation_id, what="generation", maximum=_TOKEN_MAX)
        _bounded(self.recipe_id, what="recipe", maximum=_TOKEN_MAX)
        _bounded(self.version, what="version", maximum=32)
        if self.artifact_sha256 != _UNRESOLVED:
            _sha256(self.artifact_sha256)
        if self.runtime_identity_sha256 != _UNRESOLVED:
            _sha256(self.runtime_identity_sha256)
        if self.identity_strength not in {
            "archive",
            "runtime_closure",
            "partial_executable",
            "absent",
        }:
            raise ValidationError("runtime identity strength is not supported")
        if self.qualification_reusable and self.identity_strength not in {
            "archive",
            "runtime_closure",
        }:
            raise ValidationError(
                "partial runtime identity is not qualification evidence"
            )
        _bounded(
            self.execution_environment_fingerprint,
            what="environment",
            maximum=_TOKEN_MAX,
        )
        _bounded(self.endpoint, what="endpoint", maximum=_REASON_MAX)


@contract(kind="foundation.ollama_substrate", version=1)
@dataclass(frozen=True, slots=True)
class OllamaSubstrate(Contract):
    """Verified local daemon. This is not deployment readiness."""

    selection: FoundationSelection = meaning("macropath decision for this daemon")
    generation: OllamaFoundationGeneration = meaning("material daemon identity")
    capability: RuntimeCapability = meaning(
        "runtime profile; serving stays unsupported"
    )
    metrics: FoundationMetricSet = meaning("normalized foundation metrics")
    raw: OllamaRawEvidence = meaning("provider evidence behind the metrics")
    observed_at: dt.datetime = meaning("when verification finished; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        if self.selection.engine is not FoundationEngine.OLLAMA:
            raise ValidationError("ollama substrate requires the ollama engine")
        if self.capability.engine is not FoundationEngine.OLLAMA:
            raise ValidationError("ollama capability requires the ollama engine")
        if self.capability.server_launch is not FeatureState.UNSUPPORTED:
            raise ValidationError("daemon health is not model serving")


@dataclass(frozen=True, slots=True)
class ExistingOllamaObservation:
    """Facts gathered from one executable. A process name is not enough."""

    identified_by: str
    executable_path: str
    version_text: str
    endpoint: str
    api_version: str | None
    cloud_disabled: bool | None
    auto_update: bool | None
    binary_sha256: str | None = None
    runtime_identity_sha256: str | None = None
    identity_strength: str = "absent"


@dataclass(frozen=True, slots=True)
class OllamaAssessment:
    """A verified substrate or a typed refusal. Refusal does not repair a host."""

    failure: FailureCode
    support: SupportState
    reason: str
    substrate: OllamaSubstrate | None = None


def pinned_recipe() -> OllamaRuntimeRecipe:
    """The stable Linux NVIDIA artifact frozen for this generation."""
    return OllamaRuntimeRecipe(
        recipe_id=f"ollama-{_PINNED_VERSION}-linux-amd64",
        version=_PINNED_VERSION,
        artifact_name=_ARTIFACT_NAME,
        artifact_sha256=_ARTIFACT_SHA256,
        artifact_bytes=_ARTIFACT_BYTES,
        source_url=_SOURCE_URL,
        checksum_url=_CHECKSUM_URL,
        license_name="MIT",
        stable=True,
    )


def runtime_environment_id(recipe: OllamaRuntimeRecipe) -> str:
    """Owned-prefix id. Version and checksum count. The delivery URL does not."""
    digest = hashlib.sha256(
        "\n".join(
            (
                "runtime-artifact",
                recipe.recipe_id,
                recipe.version,
                recipe.artifact_sha256,
            )
        ).encode()
    ).hexdigest()
    return "renv_" + digest[:16]


def channel_refusal(*, tag: str, prerelease: bool, draft: bool) -> str | None:
    """Refuse anything other than the frozen stable tag. None means accept."""
    if draft:
        return "draft releases are outside the stable pin"
    if prerelease or _prerelease_text(tag):
        return "prerelease releases are outside the stable pin"
    normalized = tag[1:] if tag.startswith("v") else tag
    if normalized != _PINNED_VERSION:
        return "observed release is not the frozen stable pin"
    return None


def ollama_generation_id(
    *,
    recipe_id: str,
    provider_mode: OllamaProviderMode,
    version: str,
    content_sha256: str,
    identity_strength: str,
    execution_environment_fingerprint: str,
    security_class: str,
) -> str:
    """Qualification identity. An endpoint port is not part of it."""
    digest = hashlib.sha256(
        "\n".join(
            (
                "ollama-foundation",
                recipe_id,
                provider_mode.value,
                version,
                content_sha256,
                identity_strength,
                execution_environment_fingerprint,
                security_class,
            )
        ).encode()
    ).hexdigest()
    return "fgen_" + digest[:16]


def assess_existing(
    observation: ExistingOllamaObservation,
    recipe: OllamaRuntimeRecipe,
    *,
    execution_environment_fingerprint: str,
    capacity_evidence_id: str,
    observed_at: dt.datetime,
    verify_seconds: float | None,
) -> OllamaAssessment:
    """Judge an existing daemon. Does not install, pull, or load a model."""
    failed = _existing_failure(observation, recipe)
    if failed is not None:
        failure, reason = failed
        return OllamaAssessment(failure, _support(failure), reason)
    assert observation.api_version is not None
    assert observation.cloud_disabled is True
    strength = observation.identity_strength
    runtime_sha = observation.runtime_identity_sha256
    if strength == "absent" and observation.binary_sha256:
        strength = "partial_executable"
        runtime_sha = observation.binary_sha256
    return _verified(
        recipe=recipe,
        provider_mode=OllamaProviderMode.VERIFIED_EXISTING,
        version=recipe.version,
        version_text=observation.version_text,
        api_version=observation.api_version,
        endpoint=observation.endpoint,
        artifact_sha256=_UNRESOLVED,
        runtime_identity_sha256=runtime_sha or _UNRESOLVED,
        identity_strength=strength,
        execution_environment_fingerprint=execution_environment_fingerprint,
        capacity_evidence_id=capacity_evidence_id,
        observed_at=observed_at,
        startup_seconds=None,
        verify_seconds=verify_seconds,
        footprint_bytes=None,
        install_seconds=None,
        lifecycle="verified_existing",
    )


def assess_managed(
    *,
    recipe: OllamaRuntimeRecipe,
    version_text: str,
    api_version: str | None,
    endpoint: str,
    cloud_disabled: bool,
    artifact_sha256: str,
    execution_environment_fingerprint: str,
    capacity_evidence_id: str,
    observed_at: dt.datetime,
    startup_seconds: float | None,
    verify_seconds: float | None,
    footprint_bytes: int | None,
    install_seconds: float | None,
    lifecycle: str,
) -> OllamaAssessment:
    """Judge a daemon Machi started from an owned prefix."""
    if api_version is None:
        return OllamaAssessment(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "daemon api is unavailable",
        )
    if (
        version_text != recipe.version
        and _parsed_version(version_text) != recipe.version
    ):
        return OllamaAssessment(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "executable version does not match the pinned recipe",
        )
    if api_version != recipe.version:
        return OllamaAssessment(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "daemon version does not match the executable",
        )
    if not cloud_disabled:
        return OllamaAssessment(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "cloud is enabled",
        )
    if private_endpoint(endpoint) is None:
        return OllamaAssessment(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "endpoint is not a private loopback address",
        )
    return _verified(
        recipe=recipe,
        provider_mode=OllamaProviderMode.MANAGED_PREFIX,
        version=recipe.version,
        version_text=version_text,
        api_version=api_version,
        endpoint=endpoint,
        artifact_sha256=artifact_sha256,
        runtime_identity_sha256=artifact_sha256,
        identity_strength="archive",
        execution_environment_fingerprint=execution_environment_fingerprint,
        capacity_evidence_id=capacity_evidence_id,
        observed_at=observed_at,
        startup_seconds=startup_seconds,
        verify_seconds=verify_seconds,
        footprint_bytes=footprint_bytes,
        install_seconds=install_seconds,
        lifecycle=lifecycle,
    )


def private_endpoint(endpoint: str) -> tuple[str, int] | None:
    """Host and port when the URL is loopback HTTP. Public binds are refused."""
    parsed = urlparse(endpoint)
    host = parsed.hostname
    if parsed.scheme != "http" or host not in _PRIVATE_HOSTS:
        return None
    if parsed.username or parsed.password or parsed.port is None:
        return None
    return host, parsed.port


def _existing_failure(
    observation: ExistingOllamaObservation,
    recipe: OllamaRuntimeRecipe,
) -> tuple[FailureCode, str] | None:
    if observation.identified_by != _EXECUTED_BINARY:
        return (
            FailureCode.VERIFICATION_FAILED,
            "process name, unit, path entry, or image tag is not runtime proof",
        )
    if (
        "/" not in observation.executable_path
        and "\\" not in observation.executable_path
    ):
        return (
            FailureCode.VERIFICATION_FAILED,
            "a bare command name is not an identified executable",
        )
    parsed = _parsed_version(observation.version_text)
    if parsed is None:
        return (FailureCode.VERIFICATION_FAILED, "executable version was not reported")
    if _prerelease_text(parsed):
        return (
            FailureCode.HOST_UNSUPPORTED,
            "prerelease releases are outside the stable pin",
        )
    if parsed != recipe.version:
        return (
            FailureCode.VERIFICATION_FAILED,
            "executable version does not match the pinned recipe",
        )
    if observation.auto_update is not False:
        return (
            FailureCode.VERIFICATION_FAILED,
            "observed install can auto-update this generation",
        )
    if private_endpoint(observation.endpoint) is None:
        return (
            FailureCode.VERIFICATION_FAILED,
            "endpoint is not a private loopback address",
        )
    if observation.cloud_disabled is not True:
        reason = (
            "cloud is enabled"
            if observation.cloud_disabled is False
            else "cloud mode is unresolved"
        )
        return (FailureCode.VERIFICATION_FAILED, reason)
    if observation.api_version is None:
        return (FailureCode.VERIFICATION_FAILED, "daemon api is unavailable")
    if observation.api_version != recipe.version:
        return (
            FailureCode.VERIFICATION_FAILED,
            "daemon version does not match the executable",
        )
    return None


def _verified(
    *,
    recipe: OllamaRuntimeRecipe,
    provider_mode: OllamaProviderMode,
    version: str,
    version_text: str,
    api_version: str,
    endpoint: str,
    artifact_sha256: str,
    runtime_identity_sha256: str,
    identity_strength: str,
    execution_environment_fingerprint: str,
    capacity_evidence_id: str,
    observed_at: dt.datetime,
    startup_seconds: float | None,
    verify_seconds: float | None,
    footprint_bytes: int | None,
    install_seconds: float | None,
    lifecycle: str,
) -> OllamaAssessment:
    reusable = identity_strength in {"archive", "runtime_closure"}
    content = (
        artifact_sha256
        if identity_strength == "archive"
        else runtime_identity_sha256
    )
    generation_id = ollama_generation_id(
        recipe_id=recipe.recipe_id,
        provider_mode=provider_mode,
        version=version,
        content_sha256=content,
        identity_strength=identity_strength,
        execution_environment_fingerprint=execution_environment_fingerprint,
        security_class="loopback_cloud_disabled",
    )
    selection = FoundationSelection(
        selection_id="fsel_" + generation_id.removeprefix("fgen_"),
        family=FoundationFamily.DIRECT,
        engine=FoundationEngine.OLLAMA,
        executor=ExecutorKind.NATIVE_PROCESS,
        backend=AcceleratorBackend.CUDA,
        support=SupportState.READY,
        failure=FailureCode.NONE,
        candidate_id=recipe.recipe_id,
        generation_id=generation_id,
        capacity_evidence_id=capacity_evidence_id,
        reason="local ollama daemon matches the frozen recipe",
    )
    capability = RuntimeCapability(
        engine=FoundationEngine.OLLAMA,
        version=version,
        backend=AcceleratorBackend.CUDA,
        import_state=FeatureState.VERIFIED,
        entrypoint_state=FeatureState.VERIFIED,
        server_launch=FeatureState.UNSUPPORTED,
        streaming=FeatureState.UNRESOLVED,
        structured_output=FeatureState.UNRESOLVED,
        lora=FeatureState.UNRESOLVED,
        metrics=FeatureState.UNRESOLVED,
    )
    generation = OllamaFoundationGeneration(
        generation_id=generation_id,
        recipe_id=recipe.recipe_id,
        provider_mode=provider_mode,
        version=version,
        artifact_sha256=artifact_sha256,
        runtime_identity_sha256=runtime_identity_sha256,
        identity_strength=identity_strength,
        qualification_reusable=reusable,
        execution_environment_fingerprint=execution_environment_fingerprint,
        cloud_mode=CloudMode.DISABLED,
        endpoint=endpoint,
        created_at=observed_at,
    )
    raw = OllamaRawEvidence(
        provider_mode=provider_mode.value,
        version_text=version_text[:_REASON_MAX],
        api_version=api_version,
        artifact_sha256=artifact_sha256,
        cloud_mode=CloudMode.DISABLED.value,
        endpoint_class="loopback",
    )
    metrics = _metrics(
        provider_mode=provider_mode,
        version=version,
        artifact_sha256=artifact_sha256,
        startup_seconds=startup_seconds,
        verify_seconds=verify_seconds,
        footprint_bytes=footprint_bytes,
        install_seconds=install_seconds,
        lifecycle=lifecycle,
    )
    return OllamaAssessment(
        FailureCode.NONE,
        SupportState.READY,
        "foundation daemon verified; model residency is not claimed",
        OllamaSubstrate(
            selection=selection,
            generation=generation,
            capability=capability,
            metrics=metrics,
            raw=raw,
            observed_at=observed_at,
        ),
    )


def _metrics(
    *,
    provider_mode: OllamaProviderMode,
    version: str,
    artifact_sha256: str,
    startup_seconds: float | None,
    verify_seconds: float | None,
    footprint_bytes: int | None,
    install_seconds: float | None,
    lifecycle: str,
) -> FoundationMetricSet:
    sha_known = artifact_sha256 != _UNRESOLVED
    rows = (
        _text_metric("foundation.engine", "ollama", "substrate.engine"),
        _text_metric("provider.mode", provider_mode.value, "substrate.provider"),
        _text_metric("runtime.version", version, "daemon.version"),
        FoundationMetric(
            name="artifact.sha256",
            value=artifact_sha256,
            availability=(
                MetricAvailability.OBSERVED
                if sha_known
                else MetricAvailability.UNRESOLVED
            ),
            unit="text",
            source="archive.sha256",
            privacy="operational",
        ),
        _seconds("install.duration_seconds", install_seconds, "prefix.install"),
        _bytes("install.footprint_bytes", footprint_bytes, "prefix.bytes"),
        _seconds("daemon.startup_seconds", startup_seconds, "daemon.start"),
        _seconds("daemon.verify_seconds", verify_seconds, "daemon.version_endpoint"),
        _text_metric("endpoint.bind", "loopback", "daemon.bind"),
        _text_metric("cloud.mode", "disabled", "daemon.cloud"),
        _text_metric("lifecycle.outcome", lifecycle, "daemon.lifecycle"),
        _text_metric("failure.reason", "none", "daemon.failure"),
    )
    return FoundationMetricSet(metrics=rows)


def _text_metric(name: str, value: str, source: str) -> FoundationMetric:
    return FoundationMetric(
        name=name,
        value=value,
        availability=MetricAvailability.OBSERVED,
        unit="text",
        source=source,
        privacy="operational",
    )


def _seconds(name: str, value: float | None, source: str) -> FoundationMetric:
    if value is None:
        return FoundationMetric(
            name=name,
            value=_UNRESOLVED,
            availability=MetricAvailability.UNRESOLVED,
            unit="seconds",
            source=source,
            privacy="operational",
        )
    return FoundationMetric(
        name=name,
        value=f"{value:.6f}",
        availability=MetricAvailability.OBSERVED,
        unit="seconds",
        source=source,
        privacy="operational",
    )


def _bytes(name: str, value: int | None, source: str) -> FoundationMetric:
    if value is None:
        return FoundationMetric(
            name=name,
            value=_UNRESOLVED,
            availability=MetricAvailability.UNRESOLVED,
            unit="bytes",
            source=source,
            privacy="operational",
        )
    return FoundationMetric(
        name=name,
        value=str(value),
        availability=MetricAvailability.OBSERVED,
        unit="bytes",
        source=source,
        privacy="operational",
    )


def _parsed_version(text: str) -> str | None:
    match = _VERSION_TOKEN.search(text)
    if match is None:
        return None
    return match.group(1)


def _prerelease_text(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _PRERELEASE_MARKERS)


def _support(failure: FailureCode) -> SupportState:
    if failure is FailureCode.VERIFICATION_FAILED:
        return SupportState.VERIFICATION_FAILED
    if failure is FailureCode.HOST_UNSUPPORTED:
        return SupportState.UNSUPPORTED
    if failure is FailureCode.PREREQUISITE_BLOCKED:
        return SupportState.BLOCKED_BY_PREREQUISITE
    return SupportState.UNSUPPORTED


def _sha256(value: str) -> None:
    hex_digits = "0123456789abcdef"
    if len(value) != 64 or any(character not in hex_digits for character in value):
        raise ValidationError("sha256 must be 64 lowercase hex characters")


def _bounded(value: str, *, what: str, maximum: int) -> None:
    if not value or len(value) > maximum:
        raise ValidationError(
            f"{what} must be a non-empty bounded string",
            maximum=maximum,
        )

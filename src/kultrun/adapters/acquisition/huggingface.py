"""Hugging Face acquisition adapter. Files only — not ModelSource.

Uses huggingface_hub snapshot_download. Does not choose the permanent
location, does not mark STORED, and never persists a token.
"""

from __future__ import annotations

import os
from importlib import metadata
from pathlib import Path
from typing import Any

from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.model.contracts import AcquisitionFailureReason, ModelAcquisitionRequest
from kultrun.model.ports import AcquisitionProviderError, ProviderFetchResult

IDENTITY = Name("huggingface")
FALLBACK_VERSION = "undeclared"
DEFAULT_REVISION = "main"
PIN_TIMEOUT_SECONDS = 30
FETCH_TIMEOUT_SECONDS = 120
_TOKEN_ENV = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")


class HuggingFaceAcquisitionProvider:
    """Obtain files from the Hub into a Kultrun staging directory."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    @property
    def version(self) -> str:
        try:
            return metadata.version("huggingface_hub")
        except metadata.PackageNotFoundError:
            return FALLBACK_VERSION

    def pin_revision(self, request: ModelAcquisitionRequest) -> str:
        api_cls, _ = _hub()
        revision = _requested_revision(request)
        token = _token(request)
        try:
            info = api_cls(token=token, timeout=PIN_TIMEOUT_SECONDS).model_info(
                request.source_ref,
                revision=revision,
            )
        except Exception as error:
            raise _normalize(error) from error
        sha = getattr(info, "sha", None)
        if not isinstance(sha, str) or not sha:
            raise AcquisitionProviderError(
                AcquisitionFailureReason.REVISION_NOT_FOUND.value,
                "provider did not return an immutable revision",
            )
        return sha

    def fetch(
        self, request: ModelAcquisitionRequest, staging_dir: Path
    ) -> ProviderFetchResult:
        _, snapshot_download = _hub()
        revision = self.pin_revision(request)
        token = _token(request)
        patterns = _allow_patterns(request)
        try:
            snapshot_download(
                repo_id=request.source_ref,
                revision=revision,
                local_dir=str(staging_dir),
                allow_patterns=patterns,
                token=token,
                max_workers=1,
            )
        except Exception as error:
            raise _normalize(error) from error
        files, total = _list_files(staging_dir)
        evidence = [f"huggingface_sha:{revision}"]
        if patterns:
            evidence.append("allow_patterns:" + ",".join(patterns))
        else:
            evidence.append("allow_patterns:all")
        return ProviderFetchResult(
            resolved_revision=revision,
            files=files,
            bytes_written=total,
            integrity_evidence=tuple(evidence),
        )


def build() -> HuggingFaceAcquisitionProvider:
    return HuggingFaceAcquisitionProvider()


def _hub() -> tuple[Any, Any]:
    try:
        from huggingface_hub import (  # type: ignore[import-not-found]
            HfApi,
            snapshot_download,
        )
    except ImportError as error:
        raise AcquisitionProviderError(
            AcquisitionFailureReason.PROVIDER_UNAVAILABLE.value,
            "huggingface_hub is not installed",
        ) from error
    return HfApi, snapshot_download


def _requested_revision(request: ModelAcquisitionRequest) -> str:
    if is_resolved(request.requested_revision) and request.requested_revision:
        return str(request.requested_revision)
    return DEFAULT_REVISION


def _token(request: ModelAcquisitionRequest) -> str | None:
    if is_resolved(request.credential_ref) and request.credential_ref:
        return os.environ.get(str(request.credential_ref))
    for name in _TOKEN_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _allow_patterns(request: ModelAcquisitionRequest) -> list[str] | None:
    if request.file_intent:
        return list(request.file_intent)
    fmt = str(request.artifact_format) if is_resolved(request.artifact_format) else ""
    if not fmt:
        return None
    base = [
        "*.json",
        "*.txt",
        "*.md",
        "LICENSE*",
        "license*",
        "tokenizer*",
        "*.model",
    ]
    lowered = fmt.lower()
    if lowered in {"safetensors", "st"}:
        base.extend(["*.safetensors", "*.safetensors.index.json"])
    elif lowered == "gguf":
        base.append("*.gguf")
    elif lowered in {"pytorch", "bin"}:
        base.extend(["*.bin", "pytorch_model*.bin"])
    else:
        return None
    return base


def _list_files(staging_dir: Path) -> tuple[tuple[str, ...], int]:
    names: list[str] = []
    total = 0
    root = staging_dir.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        names.append(str(path.relative_to(root)))
        total += path.stat().st_size
    return tuple(names), total


def _normalize(error: Exception) -> AcquisitionProviderError:
    name = type(error).__name__
    text = str(error)
    lowered = f"{name} {text}".lower()
    if (
        "401" in lowered
        or "unauthorized" in lowered
        or name == "LocalTokenNotFoundError"
    ):
        reason = AcquisitionFailureReason.AUTHENTICATION_REQUIRED
    elif "gated" in lowered or name == "GatedRepoError" or "403" in lowered:
        reason = (
            AcquisitionFailureReason.AUTHENTICATION_REQUIRED
            if "401" in lowered
            else AcquisitionFailureReason.ACCESS_DENIED
        )
    elif name == "RevisionNotFoundError" or "revisionnotfound" in lowered:
        reason = AcquisitionFailureReason.REVISION_NOT_FOUND
    elif name == "RepositoryNotFoundError" or "404" in lowered:
        reason = AcquisitionFailureReason.MODEL_NOT_FOUND
    elif "timeout" in lowered:
        reason = AcquisitionFailureReason.PROVIDER_TIMEOUT
    elif any(token in lowered for token in ("connection", "network", "resolve")):
        reason = AcquisitionFailureReason.NETWORK_FAILURE
    else:
        reason = AcquisitionFailureReason.PROVIDER_EXECUTION_ERROR
    return AcquisitionProviderError(reason.value, _public_message(reason))


def _public_message(reason: AcquisitionFailureReason) -> str:
    return {
        AcquisitionFailureReason.AUTHENTICATION_REQUIRED: (
            "authentication required for this model"
        ),
        AcquisitionFailureReason.ACCESS_DENIED: "access denied or gated",
        AcquisitionFailureReason.REVISION_NOT_FOUND: "revision not found",
        AcquisitionFailureReason.MODEL_NOT_FOUND: "model not found",
        AcquisitionFailureReason.PROVIDER_TIMEOUT: "provider timed out",
        AcquisitionFailureReason.NETWORK_FAILURE: "network or provider failure",
        AcquisitionFailureReason.PROVIDER_UNAVAILABLE: (
            "huggingface_hub is not installed"
        ),
    }.get(reason, "provider execution error")

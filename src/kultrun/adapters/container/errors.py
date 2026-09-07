"""Classify and sanitize engine CLI failures. No vendor objects leave here."""

from __future__ import annotations

from kultrun.execution.contracts import EngineFailureKind
from kultrun.execution.engine import EngineCommandResult


def classify(result: EngineCommandResult) -> EngineFailureKind:
    """Map CLI evidence onto a domain failure kind."""
    if not result.found:
        return EngineFailureKind.BINARY_MISSING
    text = f"{result.stderr}\n{result.stdout}\n{result.detail or ''}".lower()
    if "permission denied" in text:
        return EngineFailureKind.PERMISSION_DENIED
    if (
        "cannot connect to the docker daemon" in text
        or "is the docker daemon running" in text
        or "cannot connect to the docker endpoint" in text
    ):
        return EngineFailureKind.DAEMON_UNAVAILABLE
    if (
        "unable to find image" in text
        or "manifest unknown" in text
        or "pull access denied" in text
        or "repository does not exist" in text
    ):
        return EngineFailureKind.IMAGE_MISSING
    if "invalid reference format" in text or "invalid image" in text:
        return EngineFailureKind.INVALID_IMAGE
    if "executable file not found" in text or "no such file or directory" in text:
        return EngineFailureKind.COMMAND_UNAVAILABLE
    if (
        "address already in use" in text
        or "port is already allocated" in text
        or "failed to bind" in text
        or "driver failed programming external connectivity" in text
    ):
        return EngineFailureKind.NETWORK_FAILURE
    if "unsupported" in text and "version" in text:
        return EngineFailureKind.UNSUPPORTED_VERSION
    return EngineFailureKind.EXECUTION_FAILURE


def sanitized_detail(kind: EngineFailureKind, result: EngineCommandResult) -> str:
    """A short domain sentence. Not raw CLI stderr."""
    if kind is EngineFailureKind.BINARY_MISSING:
        return "container engine binary is not available"
    if kind is EngineFailureKind.DAEMON_UNAVAILABLE:
        return "container engine is not operational"
    if kind is EngineFailureKind.PERMISSION_DENIED:
        return "container engine refused permission"
    if kind is EngineFailureKind.IMAGE_MISSING:
        return "container image is not present"
    if kind is EngineFailureKind.INVALID_IMAGE:
        return "container image reference is invalid"
    if kind is EngineFailureKind.COMMAND_UNAVAILABLE:
        return "command is not available inside the execution environment"
    if kind is EngineFailureKind.NETWORK_FAILURE:
        return "container network realization failed"
    if kind is EngineFailureKind.UNSUPPORTED_VERSION:
        return "container engine version is not supported"
    extra = (result.detail or "").split(":", 1)[-1].strip()[:120]
    if extra:
        return f"container engine command failed: {extra}"
    return "container engine command failed"

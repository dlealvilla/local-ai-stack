"""Runtime-family identity. Not ranking, not admission, not executability."""

from __future__ import annotations

from kultrun.host.contracts import Architecture, HostCapabilities
from kultrun.runtime.contracts import RuntimeCandidate, RuntimeFamily

INTENDED_FAMILIES: tuple[str, ...] = (
    RuntimeFamily.VLLM.value,
    RuntimeFamily.LLAMA_CPP.value,
    RuntimeFamily.MLX.value,
)


def is_apple_silicon(host: HostCapabilities) -> bool:
    """Darwin arm64 is Apple Silicon. Intel Macs are not."""
    environment = host.operating_environment
    family = environment.os_name.strip().lower()
    if family not in {"darwin", "macos"}:
        return False
    return environment.architecture is Architecture.ARM64


def family_of(candidate: RuntimeCandidate) -> str:
    """v0 runtime identity is the family name."""
    return candidate.runtime_family.value or candidate.runtime.value


def is_intended_family(name: str) -> bool:
    return name in INTENDED_FAMILIES

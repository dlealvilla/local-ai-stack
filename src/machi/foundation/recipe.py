"""Match a host to the pinned vLLM artifact. No install and no I/O."""

from __future__ import annotations

from dataclasses import dataclass

from machi.foundation.policy import (
    DEFAULT_PYTHON,
    DEFAULT_VLLM,
    ROCM700_ARCHS,
    ROCM700_GLIBC,
    ROCM700_LIBS,
    ROCM700_LINE,
    ROCM700_VARIANT,
)


@dataclass(frozen=True, slots=True)
class HostRuntimeFacts:
    """Facts an adapter observed. None means the fact was not observed."""

    rocm_version: str | None = None
    glibc_version: str | None = None
    accelerator_architecture: str | None = None
    present_libraries: frozenset[str] = frozenset()
    library_prefix: str = "none"
    driver_line: str | None = None


def version_line(text: str) -> tuple[int, int] | None:
    """Return major.minor. Patch and build suffixes are not a new identity."""
    head = text.strip().split("-", 1)[0]
    parts = head.split(".")
    if len(parts) < 2:
        return None
    if not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def glibc_satisfies(observed: str, minimum: tuple[int, int]) -> bool:
    """True when observed glibc is at least the recipe minimum."""
    line = version_line(observed)
    if line is None:
        return False
    return line >= minimum


def rocm700_userspace(
    host: HostRuntimeFacts,
    *,
    python_version: str,
) -> tuple[str, tuple[str, str] | None]:
    """Return verified, realize, or refuse.

    Missing userspace is ``realize`` once gfx and glibc match. An observed
    userspace must still match the recipe line and sonames. Driver-line
    policy is not decided here.
    """
    if python_version != DEFAULT_PYTHON:
        return (
            "refuse",
            (
                "package_resolution_failed",
                (
                    f"requested python {python_version}; artifact requires "
                    f"{DEFAULT_PYTHON}; variant {ROCM700_VARIANT}; "
                    f"vllm {DEFAULT_VLLM}"
                ),
            ),
        )
    architecture = host.accelerator_architecture
    if architecture is None or architecture not in ROCM700_ARCHS:
        shown = architecture or "unobserved"
        return (
            "refuse",
            (
                "driver_or_backend_incompatible",
                (
                    f"observed accelerator {shown}; variant {ROCM700_VARIANT} "
                    f"does not list it; vllm {DEFAULT_VLLM}"
                ),
            ),
        )
    glibc = host.glibc_version
    if glibc is None or not glibc_satisfies(glibc, ROCM700_GLIBC):
        shown = glibc or "unobserved"
        minimum = f"{ROCM700_GLIBC[0]}.{ROCM700_GLIBC[1]}"
        return (
            "refuse",
            (
                "driver_or_backend_incompatible",
                (
                    f"observed glibc {shown}; required glibc >= {minimum}; "
                    f"variant {ROCM700_VARIANT}; vllm {DEFAULT_VLLM}"
                ),
            ),
        )
    observed = host.rocm_version
    if observed is None:
        return ("realize", None)
    line = version_line(observed)
    if line != ROCM700_LINE:
        shown = observed.strip() or "unparsed"
        return (
            "refuse",
            (
                "driver_or_backend_incompatible",
                (
                    f"observed rocm {shown}; required {ROCM700_VARIANT} "
                    f"rocm {ROCM700_LINE[0]}.{ROCM700_LINE[1]}; "
                    f"vllm {DEFAULT_VLLM}; "
                    "wheel variant does not match the host"
                ),
            ),
        )
    missing = [name for name in ROCM700_LIBS if name not in host.present_libraries]
    if missing:
        joined = ",".join(missing)
        shown = joined if len(joined) <= 160 else f"{len(missing)} sonames"
        return (
            "refuse",
            (
                "prerequisite_blocked",
                (
                    f"missing {shown}; observed rocm {observed.strip()}; "
                    f"required {ROCM700_VARIANT}; vllm {DEFAULT_VLLM}"
                ),
            ),
        )
    return ("verified", None)


def rocm700_refusal(
    host: HostRuntimeFacts,
    *,
    python_version: str,
) -> tuple[str, str] | None:
    """Return a hard refusal. Realize is not a refusal."""
    kind, detail = rocm700_userspace(host, python_version=python_version)
    if kind != "refuse" or detail is None:
        return None
    return detail

import os
import shutil
from pathlib import Path


def _resolve(candidates):
    for candidate in candidates:
        if (
            candidate.is_file()
            and os.access(candidate, os.X_OK)
        ):
            return str(candidate)

    return None


def resolve_vllm_executable():
    candidates = []

    override = os.environ.get("AI_VLLM_EXECUTABLE")
    if override:
        candidates.append(Path(override))

    candidates.append(
        Path(
            "/opt/ai-stack/runtime/"
            "vllm/.venv/bin/vllm"
        )
    )

    system_vllm = shutil.which("vllm")
    if system_vllm:
        candidates.append(Path(system_vllm))

    return _resolve(candidates)


def resolve_openwebui_executable():
    candidates = []

    override = os.environ.get(
        "AI_OPENWEBUI_EXECUTABLE"
    )

    if override:
        candidates.append(Path(override))

    candidates.append(
        Path(
            "/opt/ai-stack/runtime/"
            "openwebui/.venv/bin/open-webui"
        )
    )

    system_openwebui = shutil.which("open-webui")
    if system_openwebui:
        candidates.append(Path(system_openwebui))

    return _resolve(candidates)


def resolve_platform_tools_python():
    """
    Resolve the lightweight platform-tools Python runtime.

    This runtime hosts optional adapter dependencies such as
    huggingface_hub and remains separate from inference runtimes.
    """

    candidates = []

    override = os.environ.get(
        "AI_PLATFORM_TOOLS_PYTHON"
    )

    if override:
        candidates.append(
            Path(override)
        )

    candidates.append(
        Path(
            "/opt/ai-stack/runtime/"
            "platform_tools/.venv/bin/python"
        )
    )

    return _resolve(
        candidates
    )

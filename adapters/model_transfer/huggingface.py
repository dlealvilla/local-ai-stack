import json
import os
import subprocess

from pathlib import Path

from core.runtime_paths import (
    resolve_platform_tools_python,
)


PROVIDER = "huggingface"


def download(
    *,
    source_model_id,
    revision,
    destination,
    config,
):
    """
    Download one Hugging Face repository using the isolated
    platform_tools runtime.

    The AI Stack core never imports huggingface_hub directly.
    """

    python = (
        resolve_platform_tools_python()
    )

    if not python:
        raise RuntimeError(
            "platform_tools runtime is unavailable. "
            "Run ./ai prepare."
        )

    worker = (
        Path(__file__)
        .with_name(
            "huggingface_worker.py"
        )
        .resolve()
    )

    environment = os.environ.copy()

    result = subprocess.run(
        [
            python,
            str(worker),
            "--repo-id",
            source_model_id,
            "--revision",
            revision or "main",
            "--destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
        env=environment,
    )

    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or "Unknown Hugging Face transfer failure."
        )

        raise RuntimeError(
            "Hugging Face download failed: "
            + detail[-3000:]
        )

    lines = [
        line.strip()
        for line
        in result.stdout.splitlines()
        if line.strip()
    ]

    if not lines:
        raise RuntimeError(
            "Hugging Face worker returned no result."
        )

    try:
        return json.loads(
            lines[-1]
        )

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Could not parse Hugging Face worker result."
        ) from exc

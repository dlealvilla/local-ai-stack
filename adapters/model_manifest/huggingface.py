import json
import os
import subprocess
import sys

from pathlib import Path


_WORKER = (
    Path(
        __file__
    )
    .with_name(
        "huggingface_worker.py"
    )
)


def _resolve_worker_python():
    """
    Current lightweight dependency isolation.

    The Hugging Face SDK lives in the platform_tools runtime rather
    than being forced into the control-plane Python environment.

    The environment variable keeps this replaceable for future
    installers/runtime-profile resolution.
    """

    override = os.environ.get(
        "AI_STACK_PLATFORM_TOOLS_PYTHON"
    )


    candidates = [
        override,

        (
            "/opt/ai-stack/runtime/"
            "platform_tools/.venv/bin/python"
        ),

        sys.executable,
    ]


    for candidate in candidates:

        if not candidate:
            continue

        path = Path(
            candidate
        )

        if (
            path.exists()
            and os.access(
                path,
                os.X_OK,
            )
        ):
            return str(
                path
            )


    raise RuntimeError(
        "No usable Python interpreter was found "
        "for Hugging Face manifest inspection."
    )


def inspect_repository(
    *,
    repo_id,
    revision="main",
):
    """
    Retrieve repository file metadata without downloading model
    artifacts.
    """

    python = (
        _resolve_worker_python()
    )


    result = subprocess.run(
        [
            python,
            str(
                _WORKER
            ),

            "--repo-id",
            str(
                repo_id
            ),

            "--revision",
            str(
                revision
                or "main"
            ),
        ],

        capture_output=True,
        text=True,
        check=False,
    )


    if result.returncode != 0:
        raise RuntimeError(
            "Hugging Face manifest inspection failed: "
            + (
                result.stderr.strip()
                or result.stdout.strip()
                or (
                    "worker exited with code "
                    + str(
                        result.returncode
                    )
                )
            )
        )


    try:
        payload = json.loads(
            result.stdout
        )

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Hugging Face manifest worker returned "
            "invalid JSON."
        ) from exc


    return payload

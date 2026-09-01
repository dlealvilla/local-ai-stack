import os
import shutil
import subprocess
from pathlib import Path


# PROVISIONAL:
# /opt is our current fast local runtime location.
# Later this should be selected from detected local storage.
RUNTIME_ROOT = Path(
    os.environ.get(
        "AI_RUNTIME_ROOT",
        "/opt/ai-stack/runtime",
    )
)


# PROVISIONAL FALLBACK PROFILES:
# These are known-good bootstrap combinations.
# Later replace with compatibility-aware runtime profiles.
RUNTIME_PROFILES = {
    "vllm": {
        "python": "3.12",
        "packages": [
            "vllm==0.10.2",
            "transformers==4.55.2",
            "numpy==2.2.6",
            "numba==0.61.2",
        ],
        "executable": ".venv/bin/vllm",
        "torch_backend": "auto",
    },

    "openwebui": {
        "python": "3.12",
        "packages": [
            "open-webui==0.11.0",
        ],
        "executable": ".venv/bin/open-webui",
        "torch_backend": None,
    },

    "platform_tools": {
        "python": "3.12",
        "packages": [
            "huggingface_hub==1.28.0",
        ],
        # The Python executable itself is the readiness marker.
        "executable": ".venv/bin/python",
        "torch_backend": None,
    },
}


def runtime_dir(name):
    return RUNTIME_ROOT / name


def runtime_executable(name):
    profile = RUNTIME_PROFILES[name]

    return (
        runtime_dir(name)
        / profile["executable"]
    )


def runtime_is_ready(name):
    executable = runtime_executable(name)

    return (
        executable.is_file()
        and os.access(executable, os.X_OK)
    )


def ensure_runtime(name):
    if name not in RUNTIME_PROFILES:
        raise ValueError(
            f"Unknown runtime profile: {name}"
        )

    if runtime_is_ready(name):
        return {
            "name": name,
            "status": "existing",
            "executable": str(
                runtime_executable(name)
            ),
        }

    if shutil.which("uv") is None:
        raise RuntimeError(
            "uv is required to create native runtimes."
        )

    profile = RUNTIME_PROFILES[name]
    target = runtime_dir(name)
    venv = target / ".venv"

    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    environment = os.environ.copy()

    # Avoid hardlink warnings when cache/runtime
    # live on different filesystems.
    environment["UV_LINK_MODE"] = "copy"

    subprocess.run(
        [
            "uv",
            "venv",
            str(venv),
            "--python",
            profile["python"],
            "--seed",
        ],
        check=True,
        env=environment,
    )

    command = [
        "uv",
        "pip",
        "install",
        "--python",
        str(venv / "bin/python"),
        *profile["packages"],
    ]

    if profile["torch_backend"]:
        command.extend(
            [
                "--torch-backend",
                profile["torch_backend"],
            ]
        )

    subprocess.run(
        command,
        check=True,
        env=environment,
    )

    if not runtime_is_ready(name):
        raise RuntimeError(
            f"{name} runtime installation "
            "completed but executable is missing."
        )

    return {
        "name": name,
        "status": "created",
        "executable": str(
            runtime_executable(name)
        ),
    }


def required_runtimes(config):
    required = []

    if (
        config["runtime"]["executor"]
        == "process"
    ):
        if (
            config["inference"]["provider"]
            == "vllm"
        ):
            required.append("vllm")

        if (
            config["frontend"]["enabled"]
            and
            config["frontend"]["provider"]
            == "openwebui"
        ):
            required.append("openwebui")

    transfer = config.get(
        "model_transfer",
        {},
    )

    if transfer.get(
        "enabled",
        False,
    ):
        providers = transfer.get(
            "providers",
            [],
        )

        if "huggingface" in providers:
            required.append(
                "platform_tools"
            )

    transfer = config.get(
        "model_transfer",
        {},
    )

    if transfer.get(
        "enabled",
        False,
    ):
        providers = transfer.get(
            "providers",
            [],
        )

        if "huggingface" in providers:
            required.append(
                "platform_tools"
            )

    # Keep runtime preparation idempotent even if multiple
    # platform features depend on the same runtime profile.
    return list(dict.fromkeys(required))

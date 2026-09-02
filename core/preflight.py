import shutil
import socket
import subprocess
from pathlib import Path

from core.runtime_paths import resolve_vllm_executable


def result(name, status, detail):
    return {
        "name": name,
        "status": status,
        "detail": detail,
    }


def check_command(name):
    path = shutil.which(name)

    if path:
        return result(
            f"{name} command",
            "pass",
            path,
        )

    return result(
        f"{name} command",
        "fail",
        f"{name} was not found in PATH.",
    )


def check_docker_daemon():
    if shutil.which("docker") is None:
        return result(
            "Docker daemon",
            "fail",
            "Docker is not installed.",
        )

    try:
        completed = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )

        if completed.returncode == 0:
            return result(
                "Docker daemon",
                "pass",
                "Docker is responding.",
            )

        return result(
            "Docker daemon",
            "fail",
            completed.stderr.strip()
            or "Docker daemon is not responding.",
        )

    except Exception as exc:
        return result(
            "Docker daemon",
            "fail",
            str(exc),
        )


def check_nvidia_gpu():
    if shutil.which("nvidia-smi") is None:
        return result(
            "NVIDIA GPU",
            "fail",
            "nvidia-smi was not found.",
        )

    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if completed.returncode != 0:
            return result(
                "NVIDIA GPU",
                "fail",
                completed.stderr.strip(),
            )

        names = [
            line.strip()
            for line in completed.stdout.splitlines()
            if line.strip()
        ]

        if not names:
            return result(
                "NVIDIA GPU",
                "fail",
                "No NVIDIA GPU was returned.",
            )

        return result(
            "NVIDIA GPU",
            "pass",
            ", ".join(names),
        )

    except Exception as exc:
        return result(
            "NVIDIA GPU",
            "fail",
            str(exc),
        )


def check_path(name, path):
    path = Path(path)

    if path.exists():
        return result(
            name,
            "pass",
            str(path),
        )

    return result(
        name,
        "fail",
        f"Path does not exist: {path}",
    )


def check_port_available(host, port):
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    try:
        sock.bind((host, port))

        return result(
            f"Port {host}:{port}",
            "pass",
            "Available.",
        )

    except OSError as exc:
        return result(
            f"Port {host}:{port}",
            "fail",
            f"Unavailable: {exc}",
        )

    finally:
        sock.close()


def run_preflight(manifest, config):
    checks = []

    executor = manifest["runtime"]["executor"]

    if executor == "docker":
        checks.append(
            check_command("docker")
        )

        checks.append(
            check_docker_daemon()
        )

    elif executor == "process":
        checks.append(
            check_command("python3")
        )

        vllm_executable = resolve_vllm_executable()

        if vllm_executable:
            checks.append(
                result(
                    "vLLM runtime",
                    "pass",
                    vllm_executable,
                )
            )
        else:
            checks.append(
                result(
                    "vLLM runtime",
                    "fail",
                    "No usable native vLLM runtime was found.",
                )
            )

    else:
        checks.append(
            result(
                "Runtime executor",
                "fail",
                f"Unsupported executor: {executor}",
            )
        )

    checks.append(
        check_nvidia_gpu()
    )

    if manifest["model"]:
        checks.append(
            check_path(
                "Selected model",
                manifest["model"]["path"],
            )
        )

    else:
        checks.append(
            result(
                "Selected model",
                "fail",
                "No model is selected.",
            )
        )

    checks.append(
        check_path(
            "Open WebUI data",
            config["platform"]["data_root"]
            + "/open-webui-data",
        )
    )

    network = config["network"]

    checks.append(
        check_port_available(
            network["inference_host"],
            network["inference_port"],
        )
    )

    if config["frontend"]["enabled"]:
        checks.append(
            check_port_available(
                network["frontend_host"],
                network["frontend_port"],
            )
        )

    return checks

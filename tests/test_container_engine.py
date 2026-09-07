"""Docker CLI adapter: structured argv, normalized failures, no SDK."""

from __future__ import annotations

from pathlib import Path

from kultrun.adapters.container.docker import DockerCliEngine
from kultrun.execution.contracts import (
    ContainerExecutionConfig,
    EngineFailureKind,
    ExecutorAvailability,
)
from kultrun.execution.engine import EngineCommandResult


def _result(
    *,
    found: bool = True,
    completed: bool = True,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    detail: str | None = None,
) -> EngineCommandResult:
    return EngineCommandResult(
        found=found,
        completed=completed,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        detail=detail,
    )


def test_probe_binary_missing() -> None:
    engine = DockerCliEngine(
        runner=lambda *_a, **_k: _result(found=False, completed=False)
    )
    probe = engine.probe()
    assert probe.availability is ExecutorAvailability.UNAVAILABLE
    assert probe.failure_kind == EngineFailureKind.BINARY_MISSING.value


def test_probe_daemon_unavailable() -> None:
    engine = DockerCliEngine(
        runner=lambda *_a, **_k: _result(
            completed=False,
            returncode=1,
            stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock",
            detail="docker exited 1",
        )
    )
    probe = engine.probe()
    assert probe.failure_kind == EngineFailureKind.DAEMON_UNAVAILABLE.value
    assert "Cannot connect" not in str(probe.reason)


def test_probe_permission_denied() -> None:
    engine = DockerCliEngine(
        runner=lambda *_a, **_k: _result(
            completed=False,
            returncode=1,
            stderr="permission denied while trying to connect",
            detail="docker exited 1",
        )
    )
    probe = engine.probe()
    assert probe.failure_kind == EngineFailureKind.PERMISSION_DENIED.value


def test_probe_reads_server_version() -> None:
    payload = '{"Client":{"Version":"27.0.0"},"Server":{"Version":"27.1.2"}}'

    def run(argv: list[str], **_k: object) -> EngineCommandResult:
        assert argv[0] == "docker"
        assert "shell" not in argv
        return _result(stdout=payload)

    engine = DockerCliEngine(runner=run)
    probe = engine.probe()
    assert probe.availability is ExecutorAvailability.AVAILABLE
    assert probe.version == "27.1.2"


def test_create_uses_structured_argv_and_host_network() -> None:
    seen: list[list[str]] = []

    def run(argv: list[str], **_k: object) -> EngineCommandResult:
        seen.append(list(argv))
        return _result(stdout="abc123\n")

    engine = DockerCliEngine(runner=run)
    config = ContainerExecutionConfig(image="kultrun-reference-serving:stage-16a")
    created = engine.create(
        name="kultrun-exec-1",
        config=config,
        command=("python", "-m", "kultrun.adapters.runtime.serving_workload"),
        environment=("KULTRUN_REFERENCE_SERVING=1",),
        labels=("kultrun.managed=1",),
    )
    assert created.ok is True
    assert created.container_id == "abc123"
    argv = seen[0]
    assert argv[:2] == ["docker", "create"]
    assert "--network" in argv
    assert "host" in argv
    assert "-e" in argv
    assert "kultrun-reference-serving:stage-16a" in argv
    assert "sh" not in argv
    assert "-c" not in argv


def test_image_missing_on_create() -> None:
    engine = DockerCliEngine(
        runner=lambda *_a, **_k: _result(
            completed=False,
            returncode=1,
            stderr="Unable to find image 'missing:latest' locally",
            detail="docker exited 1",
        )
    )
    created = engine.create(
        name="kultrun-exec-1",
        config=ContainerExecutionConfig(image="missing:latest"),
        command=("python",),
        environment=(),
        labels=("kultrun.managed=1",),
    )
    assert created.ok is False
    assert created.failure is EngineFailureKind.IMAGE_MISSING
    assert created.detail == "container image is not present"


def test_adapter_source_never_sets_shell_true() -> None:
    from kultrun.adapters.container import cli as cli_mod
    from kultrun.adapters.container import docker as docker_mod

    docker_source = Path(docker_mod.__file__).read_text(encoding="utf-8")
    cli_source = Path(cli_mod.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in docker_source
    assert "shell = True" not in docker_source
    assert "shell=False" in cli_source

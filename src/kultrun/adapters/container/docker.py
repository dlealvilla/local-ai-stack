"""Docker Engine via structured CLI. Replaceable; not a domain type."""

from __future__ import annotations

import json
from collections.abc import Callable

from kultrun.adapters.container import cli
from kultrun.adapters.container.errors import classify, sanitized_detail
from kultrun.execution.contracts import (
    ContainerEngineProbe,
    ContainerExecutionConfig,
    EngineFailureKind,
    ExecutorAvailability,
    PullPolicy,
)
from kultrun.execution.engine import (
    ContainerCreateResult,
    ContainerInspection,
    ContainerLogs,
    EngineCommandResult,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED

IDENTITY = Name("docker")
_PROBE_TIMEOUT = 8.0


class DockerCliEngine:
    """`docker create/start/inspect/logs/stop/kill/rm` with `shell=False`."""

    def __init__(
        self,
        *,
        executable: str = "docker",
        runner: Callable[..., EngineCommandResult] | None = None,
    ) -> None:
        self._executable = executable
        self._run = runner or cli.run

    @property
    def identity(self) -> Name:
        return IDENTITY

    def probe(self) -> ContainerEngineProbe:
        result = self._run(
            [self._executable, "version", "--format", "{{json .}}"],
            timeout=_PROBE_TIMEOUT,
        )
        if not result.found:
            return ContainerEngineProbe(
                engine=self.identity,
                availability=ExecutorAvailability.UNAVAILABLE,
                failure_kind=EngineFailureKind.BINARY_MISSING.value,
                version=NOT_PROVIDED,
                reason="container engine binary is not available",
                evidence=("probe=docker-version", "binary=missing"),
            )
        if not result.completed:
            kind = classify(result)
            return ContainerEngineProbe(
                engine=self.identity,
                availability=ExecutorAvailability.UNAVAILABLE,
                failure_kind=kind.value,
                version=NOT_PROVIDED,
                reason=sanitized_detail(kind, result),
                evidence=("probe=docker-version", f"failure={kind.value}"),
            )
        version = _server_version(result.stdout)
        if version is None:
            return ContainerEngineProbe(
                engine=self.identity,
                availability=ExecutorAvailability.UNAVAILABLE,
                failure_kind=EngineFailureKind.DAEMON_UNAVAILABLE.value,
                version=NOT_PROVIDED,
                reason="container engine is not operational",
                evidence=("probe=docker-version", "server=absent"),
            )
        return ContainerEngineProbe(
            engine=self.identity,
            availability=ExecutorAvailability.AVAILABLE,
            failure_kind=NOT_PROVIDED,
            version=version,
            reason=NOT_PROVIDED,
            evidence=("probe=docker-version", f"version={version}"),
        )

    def create(
        self,
        *,
        name: str,
        config: ContainerExecutionConfig,
        command: tuple[str, ...],
        environment: tuple[str, ...],
        labels: tuple[str, ...],
    ) -> ContainerCreateResult:
        pulled = self._apply_pull_policy(config)
        if pulled is not None:
            return pulled
        argv = [
            self._executable,
            "create",
            "--name",
            name,
            "--network",
            config.network_mode.value,
        ]
        for label in labels:
            argv.extend(["--label", label])
        for entry in environment:
            argv.extend(["-e", entry])
        if config.working_directory:
            argv.extend(["-w", config.working_directory])
        argv.append(config.image)
        argv.extend(command)
        result = self._run(argv)
        if not result.completed:
            kind = classify(result)
            return ContainerCreateResult(
                ok=False,
                container_id=None,
                failure=kind,
                detail=sanitized_detail(kind, result),
            )
        container_id = result.stdout.strip().splitlines()[-1].strip()
        if not container_id:
            return ContainerCreateResult(
                ok=False,
                container_id=None,
                failure=EngineFailureKind.EXECUTION_FAILURE,
                detail="container engine command failed",
            )
        return ContainerCreateResult(
            ok=True,
            container_id=container_id,
            failure=None,
            detail="",
        )

    def start(self, container_id: str) -> ContainerCreateResult:
        result = self._run([self._executable, "start", container_id])
        if not result.completed:
            kind = classify(result)
            return ContainerCreateResult(
                ok=False,
                container_id=container_id,
                failure=kind,
                detail=sanitized_detail(kind, result),
            )
        return ContainerCreateResult(
            ok=True,
            container_id=container_id,
            failure=None,
            detail="",
        )

    def inspect(self, container_id: str) -> ContainerInspection | None:
        result = self._run(
            [self._executable, "inspect", "--format", "{{json .}}", container_id]
        )
        if not result.completed:
            return None
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        state = payload.get("State")
        if not isinstance(state, dict):
            state = {}
        status = str(state.get("Status") or "")
        running = bool(state.get("Running"))
        exit_raw = state.get("ExitCode")
        exit_code = int(exit_raw) if isinstance(exit_raw, int) else None
        pid_raw = state.get("Pid")
        host_pid = int(pid_raw) if isinstance(pid_raw, int) and pid_raw > 0 else None
        error = str(state.get("Error") or "")
        name = str(payload.get("Name") or "").lstrip("/")
        identity = str(payload.get("Id") or container_id)
        return ContainerInspection(
            container_id=identity,
            name=name,
            status=status,
            running=running,
            exit_code=exit_code,
            host_pid=host_pid,
            error=error,
        )

    def logs(self, container_id: str, *, limit_bytes: int) -> ContainerLogs:
        result = self._run(
            [self._executable, "logs", container_id],
            output_limit_bytes=max(limit_bytes, 1),
        )
        stdout = result.stdout
        stderr = result.stderr
        truncated = (
            len(stdout.encode("utf-8")) >= limit_bytes
            or len(stderr.encode("utf-8")) >= limit_bytes
        )
        return ContainerLogs(
            stdout=_clip(stdout, limit_bytes),
            stderr=_clip(stderr, limit_bytes),
            truncated=truncated,
        )

    def stop(self, container_id: str, *, grace_period_seconds: float) -> None:
        grace = max(1, round(grace_period_seconds))
        self._run(
            [self._executable, "stop", "-t", str(grace), container_id],
            timeout=grace + 5,
        )

    def kill(self, container_id: str) -> None:
        self._run([self._executable, "kill", container_id], timeout=8.0)

    def remove(self, container_id: str) -> None:
        self._run([self._executable, "rm", container_id], timeout=8.0)

    def _apply_pull_policy(
        self, config: ContainerExecutionConfig
    ) -> ContainerCreateResult | None:
        if config.pull_policy is PullPolicy.NEVER:
            return None
        present = self._run(
            [self._executable, "image", "inspect", config.image],
            timeout=8.0,
        )
        if present.completed and config.pull_policy is PullPolicy.IF_MISSING:
            return None
        pulled = self._run(
            [self._executable, "pull", config.image],
            timeout=120.0,
        )
        if pulled.completed:
            return None
        kind = classify(pulled)
        return ContainerCreateResult(
            ok=False,
            container_id=None,
            failure=kind,
            detail=sanitized_detail(kind, pulled),
        )


def build(*, executable: str = "docker") -> DockerCliEngine:
    return DockerCliEngine(executable=executable)


def _server_version(stdout: str) -> str | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    server = payload.get("Server")
    if not isinstance(server, dict):
        return None
    version = server.get("Version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def _clip(text: str, limit: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="replace")

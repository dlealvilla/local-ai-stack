"""Deterministic ContainerEngine fixture. Does not talk to Docker."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from kultrun.execution.contracts import (
    ContainerEngineProbe,
    ContainerExecutionConfig,
    EngineFailureKind,
    ExecutorAvailability,
)
from kultrun.execution.engine import (
    ContainerCreateResult,
    ContainerInspection,
    ContainerLogs,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED

IDENTITY = Name("recording")


@dataclass
class _Box:
    name: str
    image: str
    command: tuple[str, ...]
    environment: tuple[str, ...]
    labels: tuple[str, ...]
    status: str = "created"
    running: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    removed: bool = False


@dataclass
class RecordingContainerEngine:
    """In-memory engine for T0/T1 ContainerExecutor tests."""

    identity_name: Name = IDENTITY
    probe_available: bool = True
    probe_failure: EngineFailureKind | None = None
    probe_version: str = "recording"
    fail_create: EngineFailureKind | None = None
    boxes: dict[str, _Box] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    _next: int = 1

    @property
    def identity(self) -> Name:
        return self.identity_name

    def probe(self) -> ContainerEngineProbe:
        if not self.probe_available:
            kind = self.probe_failure or EngineFailureKind.DAEMON_UNAVAILABLE
            return ContainerEngineProbe(
                engine=self.identity,
                availability=ExecutorAvailability.UNAVAILABLE,
                failure_kind=kind.value,
                version=NOT_PROVIDED,
                reason=kind.value.replace("_", " "),
                evidence=("recording-container-engine",),
            )
        return ContainerEngineProbe(
            engine=self.identity,
            availability=ExecutorAvailability.AVAILABLE,
            failure_kind=NOT_PROVIDED,
            version=self.probe_version,
            reason=NOT_PROVIDED,
            evidence=("recording-container-engine",),
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
        self.calls.append(("create", name))
        if self.fail_create is not None:
            return ContainerCreateResult(
                ok=False,
                container_id=None,
                failure=self.fail_create,
                detail=self.fail_create.value.replace("_", " "),
            )
        if config.image in {"missing.example/none:latest", "missing:latest"}:
            return ContainerCreateResult(
                ok=False,
                container_id=None,
                failure=EngineFailureKind.IMAGE_MISSING,
                detail="container image is not present",
            )
        if " " in config.image or config.image.startswith("invalid"):
            return ContainerCreateResult(
                ok=False,
                container_id=None,
                failure=EngineFailureKind.INVALID_IMAGE,
                detail="container image reference is invalid",
            )
        container_id = f"ctr{self._next:08d}"
        self._next += 1
        stdout = "kultrun-reference-serving:ready 127.0.0.1 18765\n"
        exit_code: int | None = None
        status = "created"
        running = False
        if command and command[0] == "missing-command":
            status = "exited"
            exit_code = 127
            stdout = "command not found\n"
        elif any(part == "exit-immediately" for part in command):
            status = "exited"
            exit_code = 2
            stdout = "kultrun-reference-serving:fail\n"
        self.boxes[container_id] = _Box(
            name=name,
            image=config.image,
            command=command,
            environment=environment,
            labels=labels,
            status=status,
            running=running,
            exit_code=exit_code,
            stdout=stdout,
        )
        return ContainerCreateResult(
            ok=True,
            container_id=container_id,
            failure=None,
            detail="",
        )

    def start(self, container_id: str) -> ContainerCreateResult:
        self.calls.append(("start", container_id))
        box = self.boxes.get(container_id)
        if box is None or box.removed:
            return ContainerCreateResult(
                ok=False,
                container_id=container_id,
                failure=EngineFailureKind.EXECUTION_FAILURE,
                detail="container engine command failed",
            )
        if box.status == "exited":
            return ContainerCreateResult(
                ok=True,
                container_id=container_id,
                failure=None,
                detail="",
            )
        box.status = "running"
        box.running = True
        return ContainerCreateResult(
            ok=True, container_id=container_id, failure=None, detail=""
        )

    def inspect(self, container_id: str) -> ContainerInspection | None:
        self.calls.append(("inspect", container_id))
        box = self.boxes.get(container_id)
        if box is None or box.removed:
            return None
        return ContainerInspection(
            container_id=container_id,
            name=box.name,
            status=box.status,
            running=box.running,
            exit_code=box.exit_code,
            host_pid=None,
            error="",
        )

    def logs(self, container_id: str, *, limit_bytes: int) -> ContainerLogs:
        self.calls.append(("logs", container_id))
        box = self.boxes.get(container_id)
        if box is None:
            return ContainerLogs(stdout="", stderr="", truncated=False)
        stdout = box.stdout.encode("utf-8")[:limit_bytes].decode(
            "utf-8", errors="replace"
        )
        stderr = box.stderr.encode("utf-8")[:limit_bytes].decode(
            "utf-8", errors="replace"
        )
        truncated = len(box.stdout.encode("utf-8")) > limit_bytes
        return ContainerLogs(stdout=stdout, stderr=stderr, truncated=truncated)

    def stop(self, container_id: str, *, grace_period_seconds: float) -> None:
        del grace_period_seconds
        self.calls.append(("stop", container_id))
        box = self.boxes.get(container_id)
        if box is None or box.removed:
            return
        box.status = "exited"
        box.running = False
        if box.exit_code is None:
            box.exit_code = 0
        box.stdout = box.stdout + "kultrun-reference-serving:stopped\n"

    def kill(self, container_id: str) -> None:
        self.calls.append(("kill", container_id))
        box = self.boxes.get(container_id)
        if box is None or box.removed:
            return
        box.status = "exited"
        box.running = False
        box.exit_code = 137

    def remove(self, container_id: str) -> None:
        self.calls.append(("remove", container_id))
        box = self.boxes.get(container_id)
        if box is None:
            return
        box.removed = True

    def force_exit(self, container_id: str, code: int) -> None:
        box = self.boxes[container_id]
        self.boxes[container_id] = replace(
            box, status="exited", running=False, exit_code=code
        )


def build() -> RecordingContainerEngine:
    return RecordingContainerEngine()

"""Container-engine result types. Not vendor objects and not Runtime fields."""

from __future__ import annotations

from dataclasses import dataclass

from kultrun.execution.contracts import EngineFailureKind


@dataclass(frozen=True, slots=True)
class ContainerCreateResult:
    """Outcome of creating a container. Id is engine-native, not ExecutionId."""

    ok: bool
    container_id: str | None
    failure: EngineFailureKind | None
    detail: str


@dataclass(frozen=True, slots=True)
class ContainerInspection:
    """Normalized inspect. Status strings are engine-native until mapped."""

    container_id: str
    name: str
    status: str
    running: bool
    exit_code: int | None
    host_pid: int | None
    error: str


@dataclass(frozen=True, slots=True)
class ContainerLogs:
    """Bounded log evidence. Truncation is a fact, not a failure."""

    stdout: str
    stderr: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class EngineCommandResult:
    """One structured CLI invocation. Never a shell string."""

    found: bool
    completed: bool
    returncode: int
    stdout: str
    stderr: str
    detail: str | None = None

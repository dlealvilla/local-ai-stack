"""Native process evidence. The generic instance does not require these fields."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe

_TOKEN_MAX = 80


@contract(kind="serve.native_process", version=1)
@dataclass(frozen=True, slots=True)
class NativeProcessEvidence(Contract):
    """Pid and bind facts for the native executor. Not a generic requirement."""

    evidence_id: str = meaning("identity of this process evidence")
    instance_id: str = meaning("instance this process belongs to")
    pid: int = meaning("operating-system process id")
    process_stamp: str = meaning("start stamp that detects pid reuse")
    identity_token: str = meaning("token passed to that process")
    argv_fingerprint: str = meaning("fingerprint of the argument list, not the list")
    python_basename: str = meaning("interpreter file name, not its directory")
    bind_scope: str = meaning("loopback; not an address")
    port: int = meaning("local port")
    started_at: dt.datetime = meaning("when the process was spawned; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "started_at", require_utc(self.started_at, what="started_at")
        )
        for name, value in (
            ("evidence", self.evidence_id),
            ("instance", self.instance_id),
            ("stamp", self.process_stamp),
            ("token", self.identity_token),
            ("argv", self.argv_fingerprint),
            ("python", self.python_basename),
            ("bind", self.bind_scope),
        ):
            if not value or len(value) > _TOKEN_MAX:
                raise ValidationError(
                    f"{name} must be a non-empty bounded string",
                    maximum=_TOKEN_MAX,
                )
        if self.pid <= 1:
            raise ValidationError("pid must name a managed process")
        if self.port < 1 or self.port > 65535:
            raise ValidationError("port is outside the local range")


@contract(kind="serve.native_exit", version=1)
@dataclass(frozen=True, slots=True)
class NativeProcessExit(Contract):
    """Exit evidence. The process record itself stays in the store."""

    exit_id: str = meaning("identity of this exit record")
    evidence_id: str = meaning("process evidence that ended")
    returncode: Maybe[int] = meaning("exit status when the parent could read it")
    reason: str = meaning("stopped, exited, or timeout")

    def __post_init__(self) -> None:
        for name, value in (
            ("exit", self.exit_id),
            ("evidence", self.evidence_id),
            ("reason", self.reason),
        ):
            if not value or len(value) > _TOKEN_MAX:
                raise ValidationError(
                    f"{name} must be a non-empty bounded string",
                    maximum=_TOKEN_MAX,
                )

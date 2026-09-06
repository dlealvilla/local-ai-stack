"""Runtime identity and the launch recipe it produces.

Platform concepts (context, concurrency, memory) are translated here into
an executable plus arguments. Runtime-specific flags stay inside an
adapter; they must not appear as fields on these contracts.

These contracts do not import `execution`. The composition root copies a
launch spec into an `ExecutorSpec`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import Contract, contract, meaning


@contract(kind="runtime.profile", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeProfile(Contract):
    """What a runtime adapter can do. Not a running process."""

    runtime: Name = meaning("stable runtime identity, e.g. reference-process")
    display_name: str = meaning("human-readable name for consoles")
    executor_kind: Name = meaning(
        "which executor this recipe is intended for, e.g. native-process"
    )
    capabilities: tuple[str, ...] = meaning(
        "generic capability tags; never vendor-specific option names"
    )
    required_components: tuple[Name, ...] = meaning(
        "components this runtime needs, by name; empty if none", default=()
    )


@contract(kind="runtime.launch_spec", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeLaunchSpec(Contract):
    """An executable recipe. Copied into an ExecutorSpec by composition."""

    runtime: Name = meaning("which runtime produced this recipe")
    profile: Name = meaning("which profile it was produced from")
    executable: str = meaning("the program to exec; not a shell line")
    arguments: tuple[str, ...] = meaning("argv after the executable")
    environment: tuple[str, ...] = meaning(
        "extra environment bindings as NAME=value strings", default=()
    )
    working_directory: str | None = meaning(
        "working directory, or the executor's default", default=None
    )
    output_limit_bytes: int = meaning(
        "capture bound the executor should honour", default=16 * 1024
    )
    grace_period_seconds: float = meaning(
        "SIGTERM grace the executor should honour", default=2.0
    )
    device_indexes: tuple[int, ...] = meaning(
        "Kultrun accelerator indexes already chosen; empty in Stage 1.3",
        default=(),
    )

    def __post_init__(self) -> None:
        if not self.executable.strip():
            raise ValidationError("executable must not be empty")
        if "\0" in self.executable:
            raise ValidationError("executable must not contain a NUL")
        if Path(self.executable).name in {
            "sh",
            "bash",
            "zsh",
            "dash",
            "csh",
            "ksh",
            "fish",
        }:
            raise ValidationError(
                "executable must not be a shell; Kultrun does not expose sh -c",
                executable=self.executable,
            )
        for argument in self.arguments:
            if "\0" in argument:
                raise ValidationError("arguments must not contain a NUL")
        for entry in self.environment:
            if "=" not in entry:
                raise ValidationError(
                    "environment entry must be NAME=value",
                    entry=entry,
                )
            name, value = entry.split("=", 1)
            if not name or "\0" in value:
                raise ValidationError(
                    "environment entry is malformed",
                    entry=entry,
                )
        if self.output_limit_bytes < 1:
            raise ValidationError(
                "output limit must be at least one byte",
                output_limit_bytes=self.output_limit_bytes,
            )
        if self.grace_period_seconds <= 0:
            raise ValidationError(
                "grace period must be positive",
                grace_period_seconds=self.grace_period_seconds,
            )
        if any(index < 0 for index in self.device_indexes):
            raise ValidationError("device indexes must be non-negative")

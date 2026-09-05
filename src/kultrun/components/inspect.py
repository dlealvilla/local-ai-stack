"""Is the component here, and at what version?

Presence is a host-independent question, which is the whole reason this
module exists separately from compatibility evaluation. Asking whether a
command exists at an acceptable version needs no host facts; asking whether
it is *compatible* with this machine does. Keeping them apart is what stops
tier 2 acquiring a cycle when `host` needs a component in order to observe
the host.

This module reads. It never provisions — `install` acts on what it reports,
which is why a component check is safe to run on a machine nobody wants
modified.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

from kultrun.components.contracts import (
    ComponentRequirement,
    ComponentResolution,
    ResolutionOutcome,
)
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe

_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


@dataclass(frozen=True, slots=True)
class Presence:
    """What an inspection found."""

    present: bool
    version: Maybe[str]
    path: str | None
    detail: str | None = None


class ComponentInspector:
    """Reports whether a requirement is already satisfied."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def inspect(self, requirement: ComponentRequirement) -> Presence:
        """Look for the component without changing anything."""
        probe = requirement.probe_command or requirement.component.value
        location = shutil.which(probe)
        if location is None:
            return Presence(
                present=False,
                version=NOT_PROVIDED,
                path=None,
                detail=f"{probe} not on PATH",
            )
        return Presence(
            present=True, version=_read_version(probe), path=location
        )

    def satisfied(self, requirement: ComponentRequirement, found: Presence) -> bool:
        """Whether what was found meets the requirement.

        An unreadable version against a stated minimum is **not** satisfied.
        Unknown is not a pass: proceeding on a version nobody could read is
        the same as proceeding on no evidence.
        """
        if not found.present:
            return False
        minimum = requirement.minimum_version
        if isinstance(minimum, str):
            if not isinstance(found.version, str):
                return False
            return _at_least(found.version, minimum)
        return True

    def resolution(
        self,
        requirement: ComponentRequirement,
        found: Presence,
        *,
        outcome: ResolutionOutcome,
        source: Maybe[str] = NOT_PROVIDED,
        detail: str | None = None,
    ) -> ComponentResolution:
        """Render an inspection into the recorded outcome."""
        return ComponentResolution(
            component=requirement.component,
            outcome=outcome,
            resolved_at=self._clock.now(),
            resolved_version=found.version,
            source=source,
            verified=found.present,
            detail=detail or found.detail,
        )


def _read_version(probe: str) -> Maybe[str]:
    for flag in ("--version", "-V"):
        try:
            finished = subprocess.run(  # fixed argv, never a shell
                [probe, flag],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        match = _VERSION.search(f"{finished.stdout}\n{finished.stderr}")
        if match is not None:
            return match.group(0)
    return NOT_PROVIDED


def _at_least(found: str, minimum: str) -> bool:
    return _parts(found) >= _parts(minimum)


def _parts(version: str) -> tuple[int, ...]:
    match = _VERSION.search(version)
    if match is None:
        return (0,)
    return tuple(int(part) for part in match.groups(default="0"))

"""What is needed, and what was found.

Deliberately two contracts and no more. `docs/ARCHITECTURE.md` Part IX warns
against a core abstraction whose only idea is downloading: a component may
come from an existing binary, a package manager, a managed environment, a
verified release, an image, a mirror or an offline bundle, so the stable
concept is *requirement to resolution* and the mechanism stays an
implementation detail of `install`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.kernel.ids import Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


class ComponentNecessity(StrEnum):
    """Whether Kultrun can proceed without it."""

    REQUIRED = "required"
    OPTIONAL = "optional"


class ResolutionOutcome(StrEnum):
    """How a requirement was met, or why it was not.

    ``ALREADY_PRESENT`` and ``PROVISIONED`` are kept apart because a repeat
    run that reports provisioning again has failed to reuse what it already
    had, and that is a defect an operator should be able to see.
    """

    ALREADY_PRESENT = "already_present"
    PROVISIONED = "provisioned"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@contract(kind="components.requirement", version=1)
@dataclass(frozen=True, slots=True)
class ComponentRequirement(Contract):
    """One third-party piece Kultrun needs, and why."""

    component: Name = meaning("what is needed, as a stable name")
    necessity: ComponentNecessity = meaning(
        "whether Kultrun can proceed without it"
    )
    purpose: str = meaning(
        "why it is needed, so a reader can judge whether it still is"
    )
    minimum_version: Maybe[str] = meaning(
        "lowest acceptable version; unresolved means any version will do",
        default=NOT_PROVIDED,
    )
    probe_command: str | None = meaning(
        "how presence is checked, which is an implementation hint rather "
        "than part of the requirement",
        default=None,
    )


@contract(kind="components.resolution", version=1)
@dataclass(frozen=True, slots=True)
class ComponentResolution(Contract):
    """What was found or done about a requirement."""

    component: Name = meaning("which component this concerns")
    outcome: ResolutionOutcome = meaning("how the requirement was met, or was not")
    resolved_at: dt.datetime = meaning("when resolution ran, UTC")
    resolved_version: Maybe[str] = meaning(
        "the version now available; unresolved when nothing is",
        default=NOT_PROVIDED,
    )
    source: Maybe[str] = meaning(
        "where it came from, so the result is reproducible",
        default=NOT_PROVIDED,
    )
    verified: bool = meaning(
        "whether the component was confirmed to run after resolution; "
        "installing is not the same as working",
        default=False,
    )
    detail: str | None = meaning(
        "what went wrong, when something did", default=None
    )

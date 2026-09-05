"""Captured real-host evidence, shipped as product data.

This is not test data any more. Fixture replay is a **product mode**: an
installed Kultrun runs its real parsers, real normalization, real capacity
policy and real sanity controller against evidence captured from a machine
that once existed, and serves the result through the ordinary Platform API.
So the evidence ships in the wheel.

That is what makes local development possible. `docs/DEVELOPMENT_WORKFLOW.md`
is explicit that a rented host is a laboratory rather than a home, and this
is the mechanism: everything above the evidence boundary is exercised
without any hardware at all.

**Replay is never dressed up as live.** Every surface that reports it says
so, because evidence captured in September describing a machine that has
since been released is not a statement about anything running now.

Adding a shape means capturing one real host and committing the sanitized
result. One physical test, permanent coverage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

#: The shape replayed when none is named. The identifier is the one
#: `tests/fixtures/hosts/shapes.json` records evidence against, so a shape
#: has exactly one name across the product and the ledger. `KULTRUN_FIXTURE`
#: accepts `default` as shorthand.
DEFAULT_SHAPE = "linux-x86_64-nvidia-blackwell-rtxpro4500"


@dataclass(frozen=True, slots=True)
class FixtureShape:
    """One captured machine, and what is honest to say about it.

    The description exists so a console can tell an operator *what* they are
    looking at without the frontend knowing anything about hardware.
    """

    shape_id: str
    description: str
    captured: str
    evidence_level: str
    deployment_profile: str
    note: str


#: Every shape that can be replayed. Deliberately a literal: one shape
#: exists, and a discovery mechanism for a single entry would be pretence.
#: `tests/fixtures/hosts/shapes.json` remains the authority on what evidence
#: each shape has earned, and a test keeps the two consistent.
SHAPES: dict[str, FixtureShape] = {
    DEFAULT_SHAPE: FixtureShape(
        shape_id=DEFAULT_SHAPE,
        description=(
            "Ubuntu 24.04 container on an AMD EPYC 7763, 251.5 GiB reported "
            "memory limited to 57.7 GiB, one assigned NVIDIA RTX PRO 4500 "
            "Blackwell of four visible, a 30 GiB overlay root and a "
            "petabyte-class FUSE network mount"
        ),
        captured="2026-09-05",
        evidence_level="L2",
        deployment_profile="compatible",
        note=(
            "Captured from a rented host that no longer exists. Replaying it "
            "exercises today's implementation against yesterday's real "
            "evidence; it proves nothing about any machine running now."
        ),
    )
}


def available() -> tuple[str, ...]:
    """Shape identifiers that can be replayed."""
    return tuple(sorted(SHAPES))


def root(shape_id: str = DEFAULT_SHAPE) -> Path:
    """Where one shape's captured evidence lives inside the package."""
    return Path(str(resources.files(__name__))) / shape_id


def hwloc_xml(shape_id: str = DEFAULT_SHAPE) -> str:
    return (root(shape_id) / "provider-hwloc.xml").read_text(encoding="utf-8")


def nvidia_csv(shape_id: str = DEFAULT_SHAPE) -> str:
    return (root(shape_id) / "provider-nvidia.csv").read_text(encoding="utf-8")


def native_capture(shape_id: str = DEFAULT_SHAPE) -> dict[str, object]:
    text = (root(shape_id) / "provider-native-linux.json").read_text(encoding="utf-8")
    loaded: dict[str, object] = json.loads(text)
    return loaded


def normalized(shape_id: str = DEFAULT_SHAPE) -> dict[str, object]:
    """What Kultrun concluded on the day of capture.

    Used by the fixture regression test to catch a change in what the
    platform *decides* from unchanged observations. Not used to serve the
    console: replay runs the real logic rather than replaying a conclusion.
    """
    text = (root(shape_id) / "normalized-host-capabilities.json").read_text(
        encoding="utf-8"
    )
    loaded: dict[str, object] = json.loads(text)
    return loaded

"""The hardware shape registry must not drift from reality.

A registry that claims a fixture exists, or an evidence level nothing
earned, is worse than no registry: it is the mechanism by which "we support
NVIDIA" gets said out loud without anyone having checked.

So these tests treat the manifest as an assertion about the repository and
verify it against the repository — that claimed fixtures exist, that claimed
evidence levels correspond to recorded acceptance, and above all that no
shape has been given a support profile its evidence does not justify.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPOSITORY = Path(__file__).resolve().parent.parent
REGISTRY = REPOSITORY / "tests" / "fixtures" / "hosts" / "shapes.json"

#: The evidence a profile requires. `docs/PRODUCT_VISION.md` §89: a profile
#: is earned from the acceptance level reached on that shape, never declared.
PROFILE_REQUIRES = {
    "unsupported": {"none", "L1", "L2", "L3", "L4"},
    "experimental": {"none", "L1"},
    "compatible": {"L2", "L3", "L4"},
    "supported": {"L3", "L4"},
    "certified": {"L4"},
}


@pytest.fixture(scope="module")
def shapes() -> list[dict[str, Any]]:
    loaded = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = loaded["shapes"]
    return entries


def test_the_registry_is_readable_and_not_empty(shapes: list[dict[str, Any]]) -> None:
    assert len(shapes) >= 1


def test_shape_identifiers_are_unique(shapes: list[dict[str, Any]]) -> None:
    identifiers = [shape["shape_id"] for shape in shapes]
    assert len(identifiers) == len(set(identifiers))


def test_every_shape_declares_the_fields_a_decision_needs(
    shapes: list[dict[str, Any]],
) -> None:
    """Enough to answer "should we test this on real hardware next?"."""
    required = (
        "shape_id",
        "os_family",
        "architecture",
        "accelerator_family",
        "fixture_available",
        "evidence_level",
        "deployment_profile",
        "blocking",
    )
    for shape in shapes:
        missing = [field for field in required if field not in shape]
        assert missing == [], f"{shape.get('shape_id')} omits {missing}"


def test_a_claimed_fixture_actually_exists(shapes: list[dict[str, Any]]) -> None:
    """The claim this registry is most likely to get wrong over time."""
    for shape in shapes:
        if not shape["fixture_available"]:
            assert "fixture_path" not in shape, (
                f"{shape['shape_id']} has no fixture but names a path"
            )
            continue
        directory = REPOSITORY / shape["fixture_path"]
        assert directory.is_dir(), f"{shape['shape_id']}: {directory} is missing"
        for name in shape["fixture_files"]:
            assert (directory / name).is_file(), f"{shape['shape_id']}: {name} missing"


def test_a_fixture_claimed_in_ci_is_replayed_by_a_real_test(
    shapes: list[dict[str, Any]],
) -> None:
    for shape in shapes:
        if not shape.get("replayed_in_ci"):
            continue
        replayer = REPOSITORY / shape["replayed_by"]
        assert replayer.is_file(), f"{shape['shape_id']}: {replayer} is missing"
        assert shape["fixture_path"].split("/")[-2] in replayer.read_text()


def test_no_shape_claims_a_profile_its_evidence_does_not_support(
    shapes: list[dict[str, Any]],
) -> None:
    """The whole point of the registry.

    A fixture is not support and a green CI job is not support. If this ever
    fails, someone has promised a customer something no hardware proved.
    """
    for shape in shapes:
        profile = shape["deployment_profile"]
        level = shape["evidence_level"]
        assert profile in PROFILE_REQUIRES, f"{shape['shape_id']}: unknown profile"
        assert level in PROFILE_REQUIRES[profile], (
            f"{shape['shape_id']} claims {profile!r} on {level!r} evidence"
        )


def test_a_shape_with_real_evidence_names_where_it_was_recorded(
    shapes: list[dict[str, Any]],
) -> None:
    """L2 and above are claims about hardware, so they cite a stage package."""
    for shape in shapes:
        if shape["evidence_level"] in ("none", "L1"):
            continue
        record = REPOSITORY / shape["evidence_record"]
        assert record.is_file(), f"{shape['shape_id']}: {record} is missing"
        assert shape["evidence_date"]
        assert shape["evidence_commit"]


def test_a_shape_without_real_evidence_explains_the_gap(
    shapes: list[dict[str, Any]],
) -> None:
    """And says what would make it worth revisiting, rather than a date."""
    for shape in shapes:
        if shape["evidence_level"] not in ("none", "L1"):
            continue
        assert shape.get("gap"), f"{shape['shape_id']} states no gap"
        assert shape.get("revisit_trigger"), f"{shape['shape_id']} has no trigger"


def test_exactly_one_blocking_shape(shapes: list[dict[str, Any]]) -> None:
    """Milestone 1 is one host, one model, one answer.

    More than one blocking shape means the vertical has widened, which
    `docs/ROADMAP.md` forbids before the Milestone 1 gate.
    """
    blocking = [shape["shape_id"] for shape in shapes if shape["blocking"]]
    assert len(blocking) == 1, f"expected one blocking shape, found {blocking}"


def test_every_fixture_directory_is_registered() -> None:
    """A fixture nobody registered is a shape nobody can find."""
    root = REPOSITORY / "tests" / "fixtures" / "hosts"
    registered = {
        shape.get("fixture_path", "").rstrip("/").split("/")[-1]
        for shape in json.loads(REGISTRY.read_text())["shapes"]
    }
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        assert directory.name in registered, (
            f"{directory.name} holds fixtures but is not in shapes.json"
        )

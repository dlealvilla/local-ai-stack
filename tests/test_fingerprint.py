"""Field meaning must never change silently.

The committed fingerprint is the review surface. A change to any contract's
shape or to what a field means shows up as a diff to
``tests/golden/schema_fingerprint.json``, and this test decides whether that
diff was allowed to happen without a ``schema_version`` bump.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Importing these registers the production contracts.
from kultrun.kernel import events, persistence, results  # noqa: F401
from kultrun.kernel.schema import fingerprint
from tests.schema_compat import breaking_changes, compatible_additions

GOLDEN = Path(__file__).resolve().parent / "golden" / "schema_fingerprint.json"


def _committed() -> dict[str, Any]:
    committed: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return committed


def _write(current: dict[str, Any]) -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(
        json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_the_committed_fingerprint_matches_the_code() -> None:
    """Regenerate with KULTRUN_UPDATE_GOLDEN=1 after reviewing the diff."""
    current = fingerprint()
    if os.environ.get("KULTRUN_UPDATE_GOLDEN") == "1":
        _write(current)
        return

    committed = _committed()
    if current == committed:
        return

    breaking = breaking_changes(committed, current)
    compatible = compatible_additions(committed, current)
    message = ["the schema fingerprint has changed."]
    if breaking:
        message.append(
            "These changes are BREAKING and require a schema_version bump:"
        )
        message.extend(f"  - {item}" for item in breaking)
    if compatible:
        message.append("These changes are compatible:")
        message.extend(f"  - {item}" for item in compatible)
    message.append(
        "If every change is intended, review the diff and regenerate with "
        "KULTRUN_UPDATE_GOLDEN=1."
    )
    raise AssertionError("\n".join(message))


def test_every_field_states_what_it_means() -> None:
    """A field with no stated meaning cannot be reviewed for a change of meaning."""
    missing = [
        f"{identity}.{name}"
        for identity, entry in fingerprint().items()
        for name, field in entry["fields"].items()
        if not field["meaning"]
    ]
    assert missing == []


def test_test_contracts_stay_out_of_the_committed_record() -> None:
    identities = set(fingerprint())
    assert not any(identity.startswith("test.") for identity in identities)


class TestTheClassifier:
    """The rules themselves, checked against synthetic fingerprints."""

    @staticmethod
    def entry(**fields: Any) -> dict[str, Any]:
        return {"python": "Thing", "fields": fields}

    @staticmethod
    def field(
        type_name: str = "int",
        *,
        optional: bool = False,
        nullable: bool = False,
        may_be_unresolved: bool = False,
        meaning: str = "a quantity",
    ) -> dict[str, Any]:
        return {
            "type": type_name,
            "optional": optional,
            "nullable": nullable,
            "may_be_unresolved": may_be_unresolved,
            "meaning": meaning,
        }

    def test_adding_an_optional_field_is_compatible(self) -> None:
        old = {"thing@1": self.entry(a=self.field())}
        new = {"thing@1": self.entry(a=self.field(), b=self.field(optional=True))}
        assert breaking_changes(old, new) == []
        assert compatible_additions(old, new) == ["thing@1.b: optional field added"]

    def test_adding_a_required_field_is_breaking(self) -> None:
        old = {"thing@1": self.entry(a=self.field())}
        new = {"thing@1": self.entry(a=self.field(), b=self.field())}
        assert breaking_changes(old, new)

    def test_removing_a_field_is_breaking(self) -> None:
        old = {"thing@1": self.entry(a=self.field(), b=self.field())}
        new = {"thing@1": self.entry(a=self.field())}
        assert breaking_changes(old, new)

    def test_changing_a_field_type_is_breaking(self) -> None:
        old = {"thing@1": self.entry(a=self.field("int"))}
        new = {"thing@1": self.entry(a=self.field("str"))}
        assert breaking_changes(old, new)

    def test_restating_a_meaning_is_breaking(self) -> None:
        """The one thing a type check cannot catch, surfaced for a human."""
        old = {"thing@1": self.entry(a=self.field(meaning="bytes requested"))}
        new = {"thing@1": self.entry(a=self.field(meaning="bytes allocated"))}
        assert breaking_changes(old, new)

    def test_making_a_field_unknowable_is_breaking(self) -> None:
        old = {"thing@1": self.entry(a=self.field())}
        new = {"thing@1": self.entry(a=self.field(may_be_unresolved=True))}
        assert breaking_changes(old, new)

    def test_removing_a_shipped_contract_is_breaking(self) -> None:
        old = {"thing@1": self.entry(a=self.field())}
        assert breaking_changes(old, {})

    def test_a_new_contract_version_is_compatible(self) -> None:
        old = {"thing@1": self.entry(a=self.field())}
        new = {
            "thing@1": self.entry(a=self.field()),
            "thing@2": self.entry(a=self.field("str")),
        }
        assert breaking_changes(old, new) == []
        assert "thing@2: new contract" in compatible_additions(old, new)

    def test_an_identical_fingerprint_reports_nothing(self) -> None:
        old = {"thing@1": self.entry(a=self.field())}
        assert breaking_changes(old, dict(old)) == []
        assert compatible_additions(old, dict(old)) == []

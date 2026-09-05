"""The contract base, the codec, and what each refuses."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pytest

from kultrun.kernel.errors import (
    DuplicateRegistrationError,
    InternalError,
    UnknownKindError,
    UnknownVersionError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import (
    Contract,
    contract,
    from_dict,
    meaning,
    resolve,
    to_dict,
    unresolved_fields,
    validate_contract,
    validate_registry,
)
from kultrun.kernel.unresolved import NOT_MEASURED, Unresolved, UnresolvedReason
from tests.fixtures.contracts import Leaf, Outcome, Probe, ProbeId

INSTANT = dt.datetime(2026, 9, 5, 6, 30, tzinfo=dt.UTC)


def make_probe(**overrides: object) -> Probe:
    fields: dict[str, object] = {
        "probe_id": ProbeId.generate(),
        "logical_name": Name("local-llm"),
        "outcome": Outcome.SUCCESS,
        "started_at": INSTANT,
        "requested_bytes": 34_359_738_368,
        "ratio": 0.15,
        "verified": True,
        "leaf": Leaf(label="pool-0"),
        "tags": ["reference", "nvidia"],
        "attempts": (1024, 2048),
        "annotations": {"operator": "dan", "retries": 2},
        "detail": {"nested": [1, 2, {"deep": None}]},
        "observed_bytes": 33_000_000_000,
    }
    fields.update(overrides)
    return Probe(**fields)  # type: ignore[arg-type]


class TestRoundTrip:
    def test_every_supported_field_shape_survives(self) -> None:
        probe = make_probe()
        assert from_dict(to_dict(probe)) == probe

    def test_the_document_is_tagged_with_kind_and_version(self) -> None:
        document = to_dict(make_probe())
        assert document["kind"] == "test.probe"
        assert document["schema_version"] == 1

    def test_an_unresolved_value_survives_with_its_reason(self) -> None:
        probe = make_probe(
            observed_bytes=Unresolved(UnresolvedReason.INCONCLUSIVE, "probe cancelled")
        )
        restored = from_dict(to_dict(probe))
        assert restored == probe
        assert isinstance(restored, Probe)
        assert isinstance(restored.observed_bytes, Unresolved)
        assert restored.observed_bytes.detail == "probe cancelled"

    def test_unknown_and_not_applicable_stay_distinguishable(self) -> None:
        """The whole point of the three-way distinction, checked on the wire."""
        unknown = to_dict(make_probe(ceiling_bytes=NOT_MEASURED))["ceiling_bytes"]
        absent = to_dict(make_probe(ceiling_bytes=None))["ceiling_bytes"]
        zero = to_dict(make_probe(ceiling_bytes=0))["ceiling_bytes"]
        assert unknown == {"$unresolved": {"reason": "not_measured", "detail": None}}
        assert absent is None
        assert zero == 0

    def test_a_timestamp_is_normalized_to_utc(self) -> None:
        elsewhere = dt.datetime(
            2026, 9, 5, 16, 30, tzinfo=dt.timezone(dt.timedelta(hours=10))
        )
        document = to_dict(make_probe(started_at=elsewhere))
        assert document["started_at"] == "2026-09-05T06:30:00Z"


class TestFailsClosed:
    def test_an_unregistered_kind_is_never_guessed(self) -> None:
        with pytest.raises(UnknownKindError):
            from_dict({"kind": "test.invented", "schema_version": 1})

    def test_a_known_kind_at_an_unknown_version_is_refused(self) -> None:
        with pytest.raises(UnknownVersionError) as raised:
            resolve("test.probe", 99)
        assert raised.value.context["known_versions"] == [1]

    def test_an_unexpected_field_is_refused_rather_than_ignored(self) -> None:
        document = to_dict(make_probe())
        document["invented"] = True
        with pytest.raises(ValidationError) as raised:
            from_dict(document)
        assert raised.value.context["unexpected"] == ["invented"]

    def test_a_missing_required_field_is_refused(self) -> None:
        document = to_dict(make_probe())
        del document["requested_bytes"]
        with pytest.raises(ValidationError):
            from_dict(document)

    def test_an_unknown_enumeration_member_is_never_defaulted(self) -> None:
        document = to_dict(make_probe())
        document["outcome"] = "probably_fine"
        with pytest.raises(ValidationError) as raised:
            from_dict(document)
        assert "success" in raised.value.context["permitted"]

    def test_a_naive_timestamp_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            to_dict(make_probe(started_at=dt.datetime(2026, 9, 5, 6, 30)))

    def test_a_boolean_is_not_accepted_as_an_integer(self) -> None:
        document = to_dict(make_probe())
        document["requested_bytes"] = True
        with pytest.raises(ValidationError):
            from_dict(document)

    def test_a_value_that_is_not_json_safe_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            to_dict(make_probe(detail={"when": INSTANT}))

    def test_an_unresolved_reason_that_is_not_recognised_is_refused(self) -> None:
        document = to_dict(make_probe())
        document["observed_bytes"] = {"$unresolved": {"reason": "vibes"}}
        with pytest.raises(ValidationError):
            from_dict(document)

    def test_a_null_in_a_field_that_is_not_optional_is_refused(self) -> None:
        document = to_dict(make_probe())
        document["requested_bytes"] = None
        with pytest.raises(ValidationError):
            from_dict(document)


class TestRegistration:
    def test_a_duplicate_kind_and_version_is_refused(self) -> None:
        with pytest.raises(DuplicateRegistrationError):

            @contract(kind="test.probe", version=1)
            @dataclass(frozen=True, slots=True)
            class Rival(Contract):
                field: str = meaning("anything")

    def test_a_contract_must_be_a_frozen_dataclass(self) -> None:
        with pytest.raises(InternalError):

            @contract(kind="test.mutable", version=1)
            @dataclass
            class Mutable(Contract):
                field: str = meaning("anything")

    def test_registration_records_the_class_that_callers_actually_use(self) -> None:
        """``dataclass(slots=True)`` builds a new class; the registry must have it."""
        assert resolve("test.probe", 1) is Probe
        assert isinstance(from_dict(to_dict(make_probe())), Probe)

    def test_an_abstract_intermediate_contract_cannot_be_serialized(self) -> None:
        @dataclass(frozen=True, slots=True)
        class Abstract(Contract):
            field: str = meaning("anything")

        with pytest.raises(InternalError):
            to_dict(Abstract(field="x"))


class TestRegistryValidation:
    def test_the_production_registry_is_well_formed(self) -> None:
        validate_registry(module_prefix="kultrun.")

    def test_the_fixture_contracts_are_well_formed(self) -> None:
        # Scoped to the fixtures module, not all of `tests.`, because other
        # tests in this file register deliberately malformed contracts.
        validate_registry(module_prefix="tests.fixtures.")

    def test_a_field_without_a_stated_meaning_is_a_defect(self) -> None:
        @contract(kind="test.unmeant", version=1)
        @dataclass(frozen=True, slots=True)
        class Unmeant(Contract):
            quantity: int = 0

        with pytest.raises(InternalError, match="meaning"):
            validate_contract(Unmeant)

    def test_a_non_canonical_size_unit_is_a_defect(self) -> None:
        """The previous attempt carried both `_bytes` and `_gb` for one quantity."""

        @contract(kind="test.mixed_units", version=1)
        @dataclass(frozen=True, slots=True)
        class MixedUnits(Contract):
            minimum_reserve_gb: float = meaning("reserve floor")

        with pytest.raises(InternalError, match="bytes"):
            validate_contract(MixedUnits)

    def test_a_field_that_shadows_a_serialization_tag_is_a_defect(self) -> None:
        @contract(kind="test.shadowed", version=1)
        @dataclass(frozen=True, slots=True)
        class Shadowed(Contract):
            kind: str = meaning("collides with the tag")  # type: ignore[misc]

        with pytest.raises(InternalError, match="shadows"):
            validate_contract(Shadowed)

    def test_an_unsupported_field_type_is_a_defect(self) -> None:
        @contract(kind="test.unsupported", version=1)
        @dataclass(frozen=True, slots=True)
        class Unsupported(Contract):
            when: complex = meaning("not serializable")

        with pytest.raises(InternalError, match="unsupported"):
            validate_contract(Unsupported)


class TestUnresolvedFields:
    def test_nothing_unknown_reports_nothing(self) -> None:
        assert unresolved_fields(make_probe()) == ()

    def test_unknown_values_are_reported_by_path(self) -> None:
        probe = make_probe(observed_bytes=NOT_MEASURED, ceiling_bytes=NOT_MEASURED)
        assert unresolved_fields(probe) == ("observed_bytes", "ceiling_bytes")

    def test_a_field_holding_unknown_must_be_declared_as_such(self) -> None:
        @contract(kind="test.strict", version=1)
        @dataclass(frozen=True, slots=True)
        class Strict(Contract):
            quantity: int = meaning("a determinate quantity")

        with pytest.raises(InternalError, match="Maybe"):
            to_dict(Strict(quantity=NOT_MEASURED))  # type: ignore[arg-type]


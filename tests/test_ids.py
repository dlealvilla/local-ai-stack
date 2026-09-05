"""Minted identity and external names are different things."""

from __future__ import annotations

import pytest

from kultrun.kernel.errors import InternalError, ValidationError
from kultrun.kernel.ids import EntityId, EventId, Name


class HostId(EntityId):
    prefix = "host"


class ModelId(EntityId):
    prefix = "model"


class Unprefixed(EntityId):
    pass


def test_generated_identity_is_prefixed_and_opaque() -> None:
    host = HostId.generate()
    assert host.value.startswith("host_")
    assert len(host.value) == len("host_") + 16


def test_identity_is_typed_so_kinds_cannot_be_confused() -> None:
    """A model id must not be usable where a host id is expected."""
    model = ModelId.generate()
    with pytest.raises(ValidationError):
        HostId.parse(model.value)


def test_parse_refuses_a_malformed_body() -> None:
    with pytest.raises(ValidationError):
        HostId.parse("host_not-hex")


def test_parse_refuses_a_non_string() -> None:
    with pytest.raises(ValidationError):
        HostId.parse(42)


def test_a_subclass_without_a_prefix_is_a_defect() -> None:
    with pytest.raises(InternalError):
        Unprefixed.generate()


def test_generated_identities_do_not_collide() -> None:
    assert len({HostId.generate().value for _ in range(2000)}) == 2000


def test_event_id_has_its_own_prefix() -> None:
    assert EventId.generate().value.startswith("evt_")


@pytest.mark.parametrize(
    "value", ["local-llm", "qwen3-8b-awq", "vllm", "inference", "workload.admitted"]
)
def test_names_accept_the_values_the_platform_actually_uses(value: str) -> None:
    """These are the identities the previous attempt refused to collapse."""
    assert Name(value).value == value


@pytest.mark.parametrize(
    "value",
    ["Local-LLM", "has space", "-leading", "trailing-", "", "a" * 65, "sl/ash"],
)
def test_names_refuse_anything_that_would_drift(value: str) -> None:
    with pytest.raises(ValidationError):
        Name(value)


def test_normalize_handles_a_source_reference() -> None:
    """Source adapters meet values like this and must normalize, not store verbatim."""
    assert Name.normalize("Qwen/Qwen3-8B-AWQ").value == "qwen-qwen3-8b-awq"


def test_normalize_refuses_a_string_with_nothing_usable_in_it() -> None:
    with pytest.raises(ValidationError):
        Name.normalize("///")

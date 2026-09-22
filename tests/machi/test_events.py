"""Contract registry, EventRecord, privacy, serialization."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

import machi.capacity.events as capacity_events_module
import machi.discover.events as discover_events_module
import machi.install.events as install_events_module
import machi.kernel.store_proof as store_proof_module
import machi.prerequisites as prerequisites_module
import machi.steward.events as steward_events_module
from machi.kernel.alive import KernelAlivePayload, kernel_alive
from machi.kernel.clock import FixedClock
from machi.kernel.errors import UnknownKindError, ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.ids import EventId, HierarchyId, Name
from machi.kernel.journal import JournalDefect
from machi.kernel.privacy import FORBIDDEN_PUBLIC_OPS_KEYS, PrivacyClass
from machi.kernel.schema import (
    fingerprint,
    from_dict,
    to_dict,
    unresolved_fields,
    validate_registry,
)
from machi.kernel.unresolved import Unresolved, UnresolvedReason

FIXED = dt.datetime(2026, 9, 14, 11, 0, tzinfo=dt.UTC)
GOLDEN = Path(__file__).resolve().parent / "golden" / "schema_fingerprint.json"


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


def _missing() -> Unresolved:
    return Unresolved(
        UnresolvedReason.NOT_PROVIDED, "not provided before Install/Discover"
    )


def test_registry_accepts_registered_kernel_contracts() -> None:
    validate_registry(module_prefix="machi.")


def test_unknown_kind_is_refused() -> None:
    with pytest.raises(UnknownKindError):
        from_dict({"kind": "not.a.contract", "schema_version": 1})


def test_invalid_event_type_is_refused(clock: FixedClock) -> None:
    with pytest.raises(ValidationError):
        EventRecord.create(
            event_type="Kernel Alive!",
            block_id="0",
            component_id="0.3.1",
            outcome=EventOutcome.INFO,
            privacy=PrivacyClass.PUBLIC_OPS,
            payload=KernelAlivePayload(
                distribution="machi",
                version="0.1.0",
                origin="source",
            ),
            clock=clock,
        )


def test_hierarchy_id_accepts_component_ids() -> None:
    assert HierarchyId("0").value == "0"
    assert HierarchyId("0.3.1").value == "0.3.1"
    with pytest.raises(ValidationError):
        HierarchyId("kernel")


def test_event_id_is_prefixed_and_opaque() -> None:
    minted = EventId.generate()
    assert minted.value.startswith("evt_")
    restored = EventId.parse(minted.value)
    assert restored == minted


def test_kernel_alive_round_trips(clock: FixedClock) -> None:
    event = kernel_alive(clock=clock)
    restored = from_dict(to_dict(event))
    assert restored == event
    assert isinstance(restored, EventRecord)
    assert isinstance(restored.payload, KernelAlivePayload)
    assert restored.event_type == Name("kernel.alive")
    assert restored.block_id.value == "0"
    assert restored.component_id.value == "0.3.1"
    assert restored.schema_version == 1
    assert restored.kind == "event_record"
    assert restored.payload.kind == "kernel.alive"
    assert restored.payload.schema_version == 1


def test_install_run_is_unresolved_before_block_1(clock: FixedClock) -> None:
    event = kernel_alive(clock=clock)
    assert "install_run_id" in unresolved_fields(event)
    assert "install_id" in unresolved_fields(event)
    assert "host_id" in unresolved_fields(event)


def test_privacy_is_public_ops_and_payload_has_no_customer_keys(
    clock: FixedClock,
) -> None:
    event = kernel_alive(clock=clock)
    assert event.privacy is PrivacyClass.PUBLIC_OPS
    document = json.dumps(to_dict(event))
    for key in FORBIDDEN_PUBLIC_OPS_KEYS:
        assert f'"{key}"' not in document


def test_naive_timestamp_is_refused() -> None:
    missing = _missing()
    with pytest.raises(ValidationError):
        EventRecord(
            event_id=EventId.generate(),
            event_type=Name("kernel.alive"),
            occurred_at=dt.datetime(2026, 9, 14, 11, 0),
            install_id=missing,
            install_run_id=missing,
            host_id=missing,
            block_id=HierarchyId("0"),
            component_id=HierarchyId("0.3.1"),
            outcome=EventOutcome.INFO,
            privacy=PrivacyClass.PUBLIC_OPS,
            payload=KernelAlivePayload(
                distribution="machi", version="0.1.0", origin="source"
            ),
        )


def test_unexpected_fields_are_forbidden_on_the_api_and_ignored_on_the_journal(
    clock: FixedClock,
) -> None:
    event = kernel_alive(clock=clock)
    document: dict[str, Any] = to_dict(event)
    document["future_dimension"] = "host_class"
    with pytest.raises(ValidationError, match="fields"):
        from_dict(document)
    restored = from_dict(document, extra="ignore")
    assert isinstance(restored, EventRecord)
    assert restored.event_id == event.event_id


def test_schema_fingerprint_matches_committed_golden() -> None:
    assert capacity_events_module.ENVELOPE_TYPE == "capacity.safe_envelope.derived"
    assert discover_events_module.MOUNT_OBSERVED_TYPE == "discover.mounts.observed"
    assert install_events_module.INSTALL_BOUND_TYPE == "install.bound"
    assert store_proof_module.STORE_PROVED_TYPE == "kernel.store.proved"
    assert prerequisites_module is not None
    assert steward_events_module.OCCUPANCY_TYPE == "steward.occupancy.observed"
    assert JournalDefect.kind == "journal_defect"
    current = fingerprint(module_prefix="machi.")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert current == expected

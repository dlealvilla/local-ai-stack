"""Block 1 event payloads for state-root bind, ownership, identity, and run.

Operator-facing contracts may carry an absolute path. Event payloads do
not. A filesystem path can contain a username, organisation, or mount
name and is not ``public_ops``. Install events are ``restricted``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from machi.install.contracts import (
    InstallRecord,
    InstallRecordEstablishment,
    InstallRunEstablishment,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    SelectionSource,
    StateRootBinding,
)
from machi.kernel.clock import Clock
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.ids import InstallId, InstallRunId, LocalOwnershipId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning

INSTALL_BLOCK = "1"
STATE_ROOT_BINDER_COMPONENT = "1.2.1"
STATE_ROOT_BOUND_TYPE = "install.state_root.bound"
SELF_OWNERSHIP_COMPONENT = "1.3.1"
LOCAL_MARKED_TYPE = "install.ownership.local_marked"
REGISTRY_SEED_COMPONENT = "1.3.2"
REGISTRY_SEEDED_TYPE = "install.ownership.registry_seeded"
INSTALL_RECORD_COMPONENT = "1.1.1"
INSTALL_RECORD_ESTABLISHED_TYPE = "install.record.established"
INSTALL_RUN_COMPONENT = "1.4.1"
INSTALL_BOUND_TYPE = "install.bound"


@contract(kind="install.state_root.bound", version=1)
@dataclass(frozen=True, slots=True)
class StateRootBoundPayload(Contract):
    """Safe operational body for ``install.state_root.bound``."""

    root_fingerprint: str = meaning(
        "SHA-256 hex digest of the UTF-8 normalized absolute root; "
        "correlates binds without putting the path on the event"
    )
    selection_source: SelectionSource = meaning(
        "which single authority supplied the path"
    )
    existed: bool = meaning(
        "whether the directory already existed before this bind invocation"
    )
    created: bool = meaning("whether this invocation created the directory")


def root_fingerprint(root: str) -> str:
    """Stable non-reversible identifier of a normalized absolute path."""
    return hashlib.sha256(root.encode("utf-8")).hexdigest()


def state_root_bound(
    binding: StateRootBinding, *, clock: Clock | None = None
) -> EventRecord:
    """Mint the bind event. Does not persist it. InstallRun stays Unresolved."""
    return EventRecord.create(
        event_type=STATE_ROOT_BOUND_TYPE,
        block_id=INSTALL_BLOCK,
        component_id=STATE_ROOT_BINDER_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.RESTRICTED,
        payload=StateRootBoundPayload(
            root_fingerprint=root_fingerprint(binding.root),
            selection_source=binding.selection_source,
            existed=binding.existed,
            created=binding.created,
        ),
        clock=clock,
    )


@contract(kind="install.ownership.local_marked", version=1)
@dataclass(frozen=True, slots=True)
class LocalOwnershipMarkedPayload(Contract):
    """Safe operational body for local marker establishment. Not dual proof."""

    marker_id: LocalOwnershipId = meaning(
        "stable identity of the local marker; not an InstallId"
    )
    root_fingerprint: str = meaning(
        "SHA-256 of the bound root; the absolute path is omitted"
    )
    status: str = meaning("always local_marker_present; never ownership_verified")
    dual_ownership: bool = meaning("always false; Steward evaluates dual proof later")
    destructive_authorization: bool = meaning("always false for 1.3.1")
    existed: bool = meaning("whether the marker file already existed")
    created: bool = meaning("whether this invocation wrote the marker file")


def local_ownership_marked(
    establishment: LocalOwnershipEstablishment, *, clock: Clock | None = None
) -> EventRecord:
    """Mint the local-mark event. Does not persist it. InstallRun stays Unresolved."""
    return EventRecord.create(
        event_type=LOCAL_MARKED_TYPE,
        block_id=INSTALL_BLOCK,
        component_id=SELF_OWNERSHIP_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.RESTRICTED,
        payload=LocalOwnershipMarkedPayload(
            marker_id=establishment.marker.marker_id,
            root_fingerprint=establishment.marker.root_fingerprint,
            status=establishment.status.value,
            dual_ownership=establishment.dual_ownership,
            destructive_authorization=establishment.destructive_authorization,
            existed=establishment.existed,
            created=establishment.created,
        ),
        clock=clock,
    )


@contract(kind="install.ownership.registry_seeded", version=1)
@dataclass(frozen=True, slots=True)
class OwnershipRegistrySeededPayload(Contract):
    """Safe operational body for a registry seed. Not dual proof."""

    marker_id: LocalOwnershipId = meaning(
        "stable identity cited by the registry row; not an install identity"
    )
    root_fingerprint: str = meaning(
        "SHA-256 of the bound root; the absolute path is omitted"
    )
    status: str = meaning("always registry_seed_present; never ownership_verified")
    dual_ownership: bool = meaning("always false; Steward evaluates dual proof later")
    destructive_authorization: bool = meaning("always false for 1.3.2")
    existed: bool = meaning("whether the registry row already existed")
    created: bool = meaning("whether this invocation published a new registry row")


def ownership_registry_seeded(
    establishment: LocalOwnershipRegistryEstablishment, *, clock: Clock | None = None
) -> EventRecord:
    """Mint the registry-seed event. Does not persist it."""
    return EventRecord.create(
        event_type=REGISTRY_SEEDED_TYPE,
        block_id=INSTALL_BLOCK,
        component_id=REGISTRY_SEED_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.RESTRICTED,
        payload=OwnershipRegistrySeededPayload(
            marker_id=establishment.record.marker_id,
            root_fingerprint=establishment.record.root_fingerprint,
            status=establishment.status.value,
            dual_ownership=establishment.dual_ownership,
            destructive_authorization=establishment.destructive_authorization,
            existed=establishment.existed,
            created=establishment.created,
        ),
        clock=clock,
    )


@contract(kind="install.record.established", version=1)
@dataclass(frozen=True, slots=True)
class InstallRecordEstablishedPayload(Contract):
    """Safe operational body for InstallRecord establishment. Not a run."""

    install_id: InstallId = meaning(
        "stable installation identity minted or reused by 1.1.1"
    )
    marker_id: LocalOwnershipId = meaning(
        "local ownership identity the InstallRecord is bound to"
    )
    root_fingerprint: str = meaning(
        "SHA-256 of the bound root; the absolute path is omitted"
    )
    status: str = meaning("always install_record_present; never install.completed")
    destructive_authorization: bool = meaning("always false for 1.1.1")
    existed: bool = meaning("whether the InstallRecord already existed")
    created: bool = meaning("whether this invocation published a new InstallRecord")


def install_record_established(
    establishment: InstallRecordEstablishment, *, clock: Clock | None = None
) -> EventRecord:
    """Mint the InstallRecord event with a resolved InstallId.

    InstallRun and Host stay Unresolved. Earlier events are not rewritten.
    """
    return EventRecord.create(
        event_type=INSTALL_RECORD_ESTABLISHED_TYPE,
        block_id=INSTALL_BLOCK,
        component_id=INSTALL_RECORD_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.RESTRICTED,
        payload=InstallRecordEstablishedPayload(
            install_id=establishment.record.install_id,
            marker_id=establishment.record.marker_id,
            root_fingerprint=establishment.record.root_fingerprint,
            status=establishment.status.value,
            destructive_authorization=establishment.destructive_authorization,
            existed=establishment.existed,
            created=establishment.created,
        ),
        install_id=establishment.record.install_id,
        clock=clock,
    )


@contract(kind="install.bound", version=1)
@dataclass(frozen=True, slots=True)
class InstallBoundPayload(Contract):
    """Safe operational body for final M1 install.bound correlation."""

    install_id: InstallId = meaning("stable installation identity established by 1.1.1")
    install_run_id: InstallRunId = meaning(
        "durable install-run identity minted or reused by 1.4.1"
    )
    marker_id: LocalOwnershipId = meaning(
        "local ownership identity already bound to the InstallRecord"
    )
    root_fingerprint: str = meaning(
        "SHA-256 of the bound root; the absolute path is omitted"
    )
    status: str = meaning("always install_bound; never install.completed")
    destructive_authorization: bool = meaning("always false for 1.4.1")
    existed: bool = meaning("whether the InstallRunRecord already existed")
    created: bool = meaning("whether this invocation published a new InstallRunRecord")


def install_bound(
    establishment: InstallRunEstablishment,
    record: InstallRecord,
    *,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint the M1 bind event with resolved InstallId and InstallRunId.

    Host stays Unresolved. Earlier events are not rewritten.
    """
    return EventRecord.create(
        event_type=INSTALL_BOUND_TYPE,
        block_id=INSTALL_BLOCK,
        component_id=INSTALL_RUN_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.RESTRICTED,
        payload=InstallBoundPayload(
            install_id=record.install_id,
            install_run_id=establishment.record.install_run_id,
            marker_id=record.marker_id,
            root_fingerprint=record.root_fingerprint,
            status="install_bound",
            destructive_authorization=establishment.destructive_authorization,
            existed=establishment.existed,
            created=establishment.created,
        ),
        install_id=record.install_id,
        install_run_id=establishment.record.install_run_id,
        clock=clock,
    )

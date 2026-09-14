"""Block 1 event payloads for state-root bind and local ownership marking.

Operator-facing contracts may carry an absolute path. Event payloads do
not. A filesystem path can contain a username, organisation, or mount
name and is not ``public_ops``. Local-mark events are ``restricted``:
they name a marker identity, not dual ownership.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from machi.install.contracts import (
    LocalOwnershipEstablishment,
    SelectionSource,
    StateRootBinding,
)
from machi.kernel.clock import Clock
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.ids import LocalOwnershipId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning

INSTALL_BLOCK = "1"
STATE_ROOT_BINDER_COMPONENT = "1.2.1"
STATE_ROOT_BOUND_TYPE = "install.state_root.bound"
SELF_OWNERSHIP_COMPONENT = "1.3.1"
LOCAL_MARKED_TYPE = "install.ownership.local_marked"


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
    dual_ownership: bool = meaning("always false until 1.3.2 agrees")
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

"""Block 1 event payload for a successful state-root bind.

The operator-facing ``StateRootBinding`` carries the absolute path.
This payload does not. A filesystem path can contain a username,
organisation, or mount name and is not ``public_ops``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from machi.install.contracts import SelectionSource, StateRootBinding
from machi.kernel.clock import Clock
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning

INSTALL_BLOCK = "1"
STATE_ROOT_BINDER_COMPONENT = "1.2.1"
STATE_ROOT_BOUND_TYPE = "install.state_root.bound"


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

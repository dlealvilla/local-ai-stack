"""Install contracts owned by Block 1.

``StateRootBinding`` is the 1.2.1 output. It records *where* this
installation's managed state will live. It is not ownership proof, not
an InstallRecord, and not an InstallRun.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.clock import require_utc
from machi.kernel.schema import Contract, contract, meaning


class SelectionSource(StrEnum):
    """Which authority selected the state root. One winner; never mixed."""

    EXPLICIT = "explicit"
    ENVIRONMENT = "environment"
    PLATFORM_DEFAULT = "platform_default"


@contract(kind="state_root_binding", version=1)
@dataclass(frozen=True, slots=True)
class StateRootBinding(Contract):
    """The filesystem root under which this Machi installation will keep state.

    Presence of this document means the path was resolved and the
    directory exists. It does not mean Machi owns the tree. Ownership
    evidence is Component 1.3.1.
    """

    root: str = meaning(
        "absolute, normalized filesystem path of the bound state root; "
        "local operator data, not a public_ops field"
    )
    selection_source: SelectionSource = meaning(
        "which single authority supplied the path: explicit invocation, "
        "MACHI_STATE_ROOT, or the platform default"
    )
    existed: bool = meaning(
        "whether the directory already existed before this bind invocation"
    )
    created: bool = meaning(
        "whether this invocation created the directory; false on re-entry"
    )
    bound_at: dt.datetime = meaning("when this bind resolved; timezone-aware UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "bound_at", require_utc(self.bound_at, what="bound_at")
        )

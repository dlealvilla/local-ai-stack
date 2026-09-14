"""Install contracts owned by Block 1.

``StateRootBinding`` is the 1.2.1 output. It records *where* this
installation's managed state will live. It is not ownership proof, not
an InstallRecord, and not an InstallRun.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.ids import LocalOwnershipId
from machi.kernel.schema import Contract, contract, meaning

_ROOT_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


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


class LocalOwnershipStatus(StrEnum):
    """What local marker presence means. It is not dual ownership."""

    LOCAL_MARKER_PRESENT = "local_marker_present"


@contract(kind="local_ownership_marker", version=1)
@dataclass(frozen=True, slots=True)
class LocalOwnershipMarker(Contract):
    """Local Machi ownership evidence for one bound state root.

    Presence of this file is not dual ownership and does not authorize
    destruction. Component 1.3.2 must later agree before Steward may delete.
    """

    marker_id: LocalOwnershipId = meaning(
        "stable identity of this local marker; 1.3.2 may cite the same value"
    )
    product: str = meaning("product namespace; always machi")
    root_fingerprint: str = meaning(
        "SHA-256 hex digest of the UTF-8 normalized absolute root this marker "
        "was created for; a copied file is invalid on any other root"
    )
    created_at: dt.datetime = meaning(
        "when this marker was first written; timezone-aware UTC; never rewritten"
    )
    created_by_build_id: str | None = meaning(
        "build id of the artifact that first wrote the marker; None in a checkout",
        default=None,
    )
    created_by_origin: str | None = meaning(
        "artifact or source origin of the writer; not a host path",
        default=None,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", require_utc(self.created_at, what="created_at")
        )
        if self.product != "machi":
            raise ValidationError(
                "local ownership marker product must be machi",
                product=self.product,
            )
        if not _ROOT_FINGERPRINT.match(self.root_fingerprint):
            raise ValidationError(
                "root_fingerprint must be a SHA-256 hex digest",
                root_fingerprint=self.root_fingerprint,
            )


@contract(kind="local_ownership_establishment", version=1)
@dataclass(frozen=True, slots=True)
class LocalOwnershipEstablishment(Contract):
    """Result of 1.3.1. Local evidence only; never destructive authority."""

    marker: LocalOwnershipMarker = meaning(
        "the validated or newly written local marker"
    )
    status: LocalOwnershipStatus = meaning(
        "local_marker_present; never ownership_verified or install_owned"
    )
    dual_ownership: bool = meaning(
        "whether local marker and registry currently agree; 1.3.1 is always false"
    )
    destructive_authorization: bool = meaning(
        "whether this result may authorize delete/reclaim; 1.3.1 is always false"
    )
    existed: bool = meaning("whether the marker file already existed before this call")
    created: bool = meaning("whether this invocation wrote the marker file")

    def __post_init__(self) -> None:
        if self.status is not LocalOwnershipStatus.LOCAL_MARKER_PRESENT:
            raise ValidationError(
                "1.3.1 status must be local_marker_present",
                status=self.status.value,
            )
        if self.dual_ownership:
            raise ValidationError(
                "1.3.1 must not claim dual ownership",
            )
        if self.destructive_authorization:
            raise ValidationError(
                "1.3.1 must not authorize destruction",
            )

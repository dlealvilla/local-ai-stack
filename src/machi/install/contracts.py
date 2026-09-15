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
from machi.kernel.ids import InstallId, InstallRunId, LocalOwnershipId
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
        "whether local marker and registry currently agree; 1.3.1 is always false; "
        "1.3.2 still does not evaluate dual proof"
    )
    destructive_authorization: bool = meaning(
        "whether this result may authorize delete/reclaim; 1.3.1 and 1.3.2 "
        "are always false"
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


class RegistrySeedStatus(StrEnum):
    """What a seeded registry row means. It is not dual-proof evaluation."""

    REGISTRY_SEED_PRESENT = "registry_seed_present"


@contract(kind="local_ownership_registry_record", version=1)
@dataclass(frozen=True, slots=True)
class LocalOwnershipRegistryRecord(Contract):
    """Control-plane registry half of local ownership evidence.

    This record lives in an injected Store, not in the claimed state
    root. Presence of this document plus a local marker is not dual
    ownership and does not authorize destruction. Steward evaluates
    both authorities later.
    """

    marker_id: LocalOwnershipId = meaning(
        "the same local marker identity this registry row cites; Store key"
    )
    product: str = meaning("product namespace; always machi")
    root_fingerprint: str = meaning(
        "SHA-256 hex digest of the UTF-8 normalized absolute root; "
        "must match the local marker; the path itself is omitted"
    )
    created_at: dt.datetime = meaning(
        "when this registry row was first written; timezone-aware UTC; never rewritten"
    )
    created_by_build_id: str | None = meaning(
        "build id of the artifact that first seeded the row; None in a checkout",
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
                "ownership registry product must be machi",
                product=self.product,
            )
        if not _ROOT_FINGERPRINT.match(self.root_fingerprint):
            raise ValidationError(
                "root_fingerprint must be a SHA-256 hex digest",
                root_fingerprint=self.root_fingerprint,
            )


@contract(kind="local_ownership_registry_establishment", version=1)
@dataclass(frozen=True, slots=True)
class LocalOwnershipRegistryEstablishment(Contract):
    """Result of 1.3.2. Registry evidence only; never destructive authority."""

    record: LocalOwnershipRegistryRecord = meaning(
        "the validated or newly written control-plane registry row"
    )
    status: RegistrySeedStatus = meaning(
        "registry_seed_present; never ownership_verified or dual_ownership_verified"
    )
    dual_ownership: bool = meaning(
        "whether Steward has evaluated both authorities; 1.3.2 is always false"
    )
    destructive_authorization: bool = meaning(
        "whether this result may authorize delete/reclaim; 1.3.2 is always false"
    )
    existed: bool = meaning("whether the registry row already existed before this call")
    created: bool = meaning("whether this invocation published a new registry row")

    def __post_init__(self) -> None:
        if self.status is not RegistrySeedStatus.REGISTRY_SEED_PRESENT:
            raise ValidationError(
                "1.3.2 status must be registry_seed_present",
                status=self.status.value,
            )
        if self.dual_ownership:
            raise ValidationError(
                "1.3.2 must not claim dual ownership",
            )
        if self.destructive_authorization:
            raise ValidationError(
                "1.3.2 must not authorize destruction",
            )


class InstallRecordStatus(StrEnum):
    """What a persisted InstallRecord means. It is not a run or a host."""

    INSTALL_RECORD_PRESENT = "install_record_present"


@contract(kind="install_record", version=1)
@dataclass(frozen=True, slots=True)
class InstallRecord(Contract):
    """Stable identity of one Machi installation.

    Minted once for a coherent ownership identity. Build fields are
    creation provenance, not the currently running software version.
    This is not an InstallRun, not a HostId, and not delete authority.
    """

    install_id: InstallId = meaning(
        "stable identity of this installation; minted once; not an InstallRunId"
    )
    product: str = meaning("product namespace; always machi")
    marker_id: LocalOwnershipId = meaning(
        "local ownership identity this installation is bound to; Store lookup key"
    )
    root_fingerprint: str = meaning(
        "SHA-256 hex digest of the bound state root; must match marker and registry"
    )
    created_at: dt.datetime = meaning(
        "when this InstallRecord was first written; timezone-aware UTC; never rewritten"
    )
    created_by_version: str = meaning(
        "Machi version that first created this installation identity"
    )
    created_by_origin: str = meaning(
        "artifact or source origin of the creating build; not a host path"
    )
    created_by_build_id: str | None = meaning(
        "build id of the artifact that first created the record; None in a checkout",
        default=None,
    )
    created_by_source_commit: str | None = meaning(
        "source commit of the creating build when known; not current software",
        default=None,
    )
    created_by_clean_source: bool | None = meaning(
        "whether the creating build was a clean artifact; None when unknown",
        default=None,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", require_utc(self.created_at, what="created_at")
        )
        if self.product != "machi":
            raise ValidationError(
                "install record product must be machi",
                product=self.product,
            )
        if not _ROOT_FINGERPRINT.match(self.root_fingerprint):
            raise ValidationError(
                "root_fingerprint must be a SHA-256 hex digest",
                root_fingerprint=self.root_fingerprint,
            )


@contract(kind="install_record_establishment", version=1)
@dataclass(frozen=True, slots=True)
class InstallRecordEstablishment(Contract):
    """Result of 1.1.1. Installation identity only; never a run or delete permit."""

    record: InstallRecord = meaning("the validated or newly written InstallRecord")
    status: InstallRecordStatus = meaning(
        "install_record_present; never install.completed or ownership_verified"
    )
    dual_ownership: bool = meaning(
        "whether Steward has evaluated both ownership authorities; "
        "1.1.1 is always false"
    )
    destructive_authorization: bool = meaning(
        "whether this result may authorize delete/reclaim; 1.1.1 is always false"
    )
    existed: bool = meaning(
        "whether the InstallRecord already existed before this call"
    )
    created: bool = meaning("whether this invocation published a new InstallRecord")

    def __post_init__(self) -> None:
        if self.status is not InstallRecordStatus.INSTALL_RECORD_PRESENT:
            raise ValidationError(
                "1.1.1 status must be install_record_present",
                status=self.status.value,
            )
        if self.dual_ownership:
            raise ValidationError(
                "1.1.1 must not claim dual ownership",
            )
        if self.destructive_authorization:
            raise ValidationError(
                "1.1.1 must not authorize destruction",
            )


class InstallRunStatus(StrEnum):
    """What a persisted InstallRun means. It is not a host or a process."""

    INSTALL_RUN_PRESENT = "install_run_present"


@contract(kind="install_run", version=1)
@dataclass(frozen=True, slots=True)
class InstallRunRecord(Contract):
    """Durable installation-journey identity for one InstallRecord.

    Minted once per InstallId. Reused across CLI processes. Build fields
    are creation provenance, not the currently running software version.
    This is not a process id, not a HostId, and not delete authority.
    """

    install_run_id: InstallRunId = meaning(
        "durable journey identity of this installation; minted once; not a process"
    )
    install_id: InstallId = meaning(
        "stable installation this journey belongs to; Store lookup key"
    )
    product: str = meaning("product namespace; always machi")
    created_at: dt.datetime = meaning(
        "when this InstallRun was first written; timezone-aware UTC; never rewritten"
    )
    created_by_version: str = meaning(
        "Machi version that first created this install-run identity"
    )
    created_by_origin: str = meaning(
        "artifact or source origin of the creating build; not a host path"
    )
    created_by_build_id: str | None = meaning(
        "build id of the artifact that first created the record; None in a checkout",
        default=None,
    )
    created_by_source_commit: str | None = meaning(
        "source commit of the creating build when known; not current software",
        default=None,
    )
    created_by_clean_source: bool | None = meaning(
        "whether the creating build was a clean artifact; None when unknown",
        default=None,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", require_utc(self.created_at, what="created_at")
        )
        if self.product != "machi":
            raise ValidationError(
                "install run product must be machi",
                product=self.product,
            )


@contract(kind="install_run_establishment", version=1)
@dataclass(frozen=True, slots=True)
class InstallRunEstablishment(Contract):
    """Result of 1.4.1. Journey identity only; never a host or delete permit."""

    record: InstallRunRecord = meaning(
        "the validated or newly written InstallRunRecord"
    )
    status: InstallRunStatus = meaning(
        "install_run_present; never install.completed or ownership_verified"
    )
    dual_ownership: bool = meaning(
        "whether Steward has evaluated both ownership authorities; "
        "1.4.1 is always false"
    )
    destructive_authorization: bool = meaning(
        "whether this result may authorize delete/reclaim; 1.4.1 is always false"
    )
    existed: bool = meaning(
        "whether the InstallRunRecord already existed before this call"
    )
    created: bool = meaning("whether this invocation published a new InstallRunRecord")

    def __post_init__(self) -> None:
        if self.status is not InstallRunStatus.INSTALL_RUN_PRESENT:
            raise ValidationError(
                "1.4.1 status must be install_run_present",
                status=self.status.value,
            )
        if self.dual_ownership:
            raise ValidationError(
                "1.4.1 must not claim dual ownership",
            )
        if self.destructive_authorization:
            raise ValidationError(
                "1.4.1 must not authorize destruction",
            )

"""Read Install ownership evidence without creating or deleting it."""

from __future__ import annotations

import json
from pathlib import Path

from machi.install.contracts import (
    InstallRecord,
    LocalOwnershipMarker,
    LocalOwnershipRegistryRecord,
)
from machi.install.defaults import KULTRUN_OWNER_FILENAME, MACHI_OWNER_FILENAME
from machi.install.events import root_fingerprint
from machi.kernel.errors import (
    ConflictError,
    NotFoundError,
    UnknownKindError,
    ValidationError,
)
from machi.kernel.schema import from_dict
from machi.kernel.store import Store
from machi.steward.classify import OwnershipFacts
from machi.steward.contracts import InstallFact, MarkerFact, RegistryFact


def read_ownership(root: Path, store: Store | None) -> tuple[OwnershipFacts, str]:
    """Return facts and the fingerprint of the resolved root. Does not write."""
    resolved = root.expanduser().resolve()
    fingerprint = root_fingerprint(str(resolved))
    legacy = (resolved / KULTRUN_OWNER_FILENAME).is_file()
    marker_fact, marker = _read_marker(resolved, fingerprint)
    marker_id = marker.marker_id.value if marker is not None else None
    registry_fact = RegistryFact.NOT_CONSULTED
    install_fact = InstallFact.NOT_CONSULTED
    install_id = None
    if store is not None and marker_id is not None:
        registry_fact = _read_registry(store, marker_id, fingerprint)
        install_fact, install_id = _read_install(store, marker_id, fingerprint)
    return (
        OwnershipFacts(
            marker=marker_fact,
            registry=registry_fact,
            install_record=install_fact,
            legacy_marker=legacy,
            marker_id=marker_id,
            install_id=install_id,
        ),
        fingerprint,
    )


def _read_marker(
    root: Path, fingerprint: str
) -> tuple[MarkerFact, LocalOwnershipMarker | None]:
    dest = root / MACHI_OWNER_FILENAME
    if not dest.exists():
        return MarkerFact.ABSENT, None
    if not dest.is_file() or dest.is_symlink():
        return MarkerFact.NOT_A_FILE, None
    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return MarkerFact.MALFORMED, None
    if not isinstance(payload, dict):
        return MarkerFact.MALFORMED, None
    try:
        loaded = from_dict(payload)
    except UnknownKindError:
        return MarkerFact.UNSUPPORTED, None
    except ValidationError:
        return MarkerFact.MALFORMED, None
    if not isinstance(loaded, LocalOwnershipMarker):
        return MarkerFact.UNSUPPORTED, None
    if loaded.product != "machi":
        return MarkerFact.WRONG_PRODUCT, None
    if loaded.root_fingerprint != fingerprint:
        return MarkerFact.FINGERPRINT_MISMATCH, None
    return MarkerFact.VALID, loaded


def _read_registry(store: Store, marker_id: str, fingerprint: str) -> RegistryFact:
    try:
        record = store.get(LocalOwnershipRegistryRecord, marker_id)
    except NotFoundError:
        return RegistryFact.ABSENT
    except ValidationError:
        return RegistryFact.MALFORMED
    except ConflictError:
        return RegistryFact.MISMATCH
    if record.marker_id.value != marker_id or record.root_fingerprint != fingerprint:
        return RegistryFact.MISMATCH
    if record.product != "machi":
        return RegistryFact.MISMATCH
    return RegistryFact.MATCH


def _read_install(
    store: Store, marker_id: str, fingerprint: str
) -> tuple[InstallFact, str | None]:
    try:
        record = store.get(InstallRecord, marker_id)
    except NotFoundError:
        return InstallFact.ABSENT, None
    except (ValidationError, ConflictError):
        return InstallFact.MISMATCH, None
    if record.marker_id.value != marker_id or record.root_fingerprint != fingerprint:
        return InstallFact.MISMATCH, None
    if record.product != "machi":
        return InstallFact.MISMATCH, None
    return InstallFact.MATCH, record.install_id.value

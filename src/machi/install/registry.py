"""RegistrySeed (MACHI 1.3.2).

Persist and validate the local control-plane registry record that cites
a previously established local ownership marker. This is evidence
creation, not dual-proof evaluation and not destruction authority.

The Store is injected. This component does not choose a filesystem
location, does not write a local marker file, and does not read
process environment configuration.
"""

from __future__ import annotations

from machi.install.contracts import (
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    LocalOwnershipRegistryRecord,
    LocalOwnershipStatus,
    RegistrySeedStatus,
    StateRootBinding,
)
from machi.install.defaults import PRODUCT_NAMESPACE
from machi.install.events import root_fingerprint
from machi.kernel.build import identity as build_identity
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ConflictError, NotFoundError, ValidationError
from machi.kernel.ids import LocalOwnershipId
from machi.kernel.store import Store


class RegistrySeed:
    """Control-plane registry half. Never scans, never deletes, never evaluates."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def seed(
        self,
        binding: StateRootBinding,
        establishment: LocalOwnershipEstablishment,
        store: Store,
    ) -> LocalOwnershipRegistryEstablishment:
        """Create or validate the registry row for this local evidence.

        Consumes a binding and a successful local-marker establishment.
        Does not resolve a root of its own and does not write a marker.
        """
        if establishment.status is not LocalOwnershipStatus.LOCAL_MARKER_PRESENT:
            raise ValidationError(
                "registry seed requires local_marker_present evidence",
                status=establishment.status.value,
            )
        if establishment.dual_ownership or establishment.destructive_authorization:
            raise ValidationError(
                "registry seed refuses synthetic dual-proof or delete authority",
            )
        marker = establishment.marker
        expected = root_fingerprint(binding.root)
        if marker.root_fingerprint != expected:
            raise ConflictError(
                "state-root binding and local ownership evidence do not agree; "
                "refusing to seed a registry record for conflicting evidence",
            )
        if marker.product != PRODUCT_NAMESPACE:
            raise ConflictError(
                "local ownership evidence belongs to a different product; "
                "refusing to seed a registry record",
                product=marker.product,
            )
        key = marker.marker_id.value
        try:
            existing = store.get(LocalOwnershipRegistryRecord, key)
        except NotFoundError:
            record = LocalOwnershipRegistryRecord(
                marker_id=marker.marker_id,
                product=PRODUCT_NAMESPACE,
                root_fingerprint=expected,
                created_at=self._clock.now(),
                created_by_build_id=build_identity().build_id,
                created_by_origin=build_identity().origin.value,
            )
            result = store.create(key, record)
            persisted = store.get(LocalOwnershipRegistryRecord, key)
            return self._result(
                persisted, created=result.created, existed=result.existed
            )
        return self._existing(existing, marker.marker_id, expected)

    def _existing(
        self,
        existing: LocalOwnershipRegistryRecord,
        marker_id: LocalOwnershipId,
        expected_fingerprint: str,
    ) -> LocalOwnershipRegistryEstablishment:
        if existing.marker_id != marker_id:
            raise ConflictError(
                "registry record identity does not match the local marker; "
                "refusing to overwrite",
            )
        if existing.root_fingerprint != expected_fingerprint:
            raise ConflictError(
                "registry record already exists and does not match this "
                "local ownership evidence; refusing to overwrite",
            )
        if existing.product != PRODUCT_NAMESPACE:
            raise ConflictError(
                "registry record belongs to a different product; refusing to overwrite",
                product=existing.product,
            )
        return self._result(existing, created=False, existed=True)

    def _result(
        self,
        record: LocalOwnershipRegistryRecord,
        *,
        existed: bool,
        created: bool,
    ) -> LocalOwnershipRegistryEstablishment:
        return LocalOwnershipRegistryEstablishment(
            record=record,
            status=RegistrySeedStatus.REGISTRY_SEED_PRESENT,
            dual_ownership=False,
            destructive_authorization=False,
            existed=existed,
            created=created,
        )

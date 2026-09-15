"""InstallRunStore (MACHI 1.4.1).

Persist and validate the durable InstallRun for an already-valid
InstallRecord. This is installation-journey correlation, not a process,
not a host fingerprint, and not destruction authority.

The Store is injected. This component does not choose a filesystem
location, does not bind a state root, does not write a local marker,
does not seed the registry, and does not mint InstallId.

Lookup is by InstallId so later processes can re-enter without listing
the Store. One current run per installation is the Depth 1 semantic.

Build identity is recorded as creation provenance. A later compatible
build may re-enter the same InstallRunId without rewriting that
provenance.
"""

from __future__ import annotations

from machi.install.contracts import (
    InstallRecord,
    InstallRunEstablishment,
    InstallRunRecord,
    InstallRunStatus,
)
from machi.install.defaults import PRODUCT_NAMESPACE
from machi.kernel.build import BuildIdentity
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ConflictError, NotFoundError, ValidationError
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.store import Store


class InstallRunStore:
    """Durable install-run identity. Never binds, never scans, never deletes."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def establish(
        self,
        record: InstallRecord,
        store: Store,
        build: BuildIdentity,
    ) -> InstallRunEstablishment:
        """Create or return the InstallRun for this InstallRecord.

        Consumes a typed InstallRecord. Does not re-validate ownership
        evidence and does not create an InstallId.
        """
        self._require_install_record(record)
        key = record.install_id.value
        try:
            existing = store.get(InstallRunRecord, key)
        except NotFoundError:
            minted = InstallRunRecord(
                install_run_id=InstallRunId.generate(),
                install_id=record.install_id,
                product=PRODUCT_NAMESPACE,
                created_at=self._clock.now(),
                created_by_version=build.version,
                created_by_origin=build.origin.value,
                created_by_build_id=build.build_id,
                created_by_source_commit=build.source_commit,
                created_by_clean_source=build.clean_source,
            )
            try:
                result = store.create(key, minted)
            except ConflictError:
                winner = store.get(InstallRunRecord, key)
                return self._existing(winner, record.install_id)
            persisted = store.get(InstallRunRecord, key)
            return self._result(
                persisted, created=result.created, existed=result.existed
            )
        return self._existing(existing, record.install_id)

    def _existing(
        self,
        existing: InstallRunRecord,
        install_id: InstallId,
    ) -> InstallRunEstablishment:
        if existing.install_id != install_id:
            raise ConflictError(
                "install run already exists and does not match this "
                "installation identity; refusing to overwrite",
            )
        if existing.product != PRODUCT_NAMESPACE:
            raise ConflictError(
                "install run belongs to a different product; refusing to overwrite",
                product=existing.product,
            )
        return self._result(existing, created=False, existed=True)

    def _require_install_record(self, record: InstallRecord) -> None:
        if not isinstance(record, InstallRecord):
            raise ValidationError(
                "install run requires a valid InstallRecord",
                actual_type=type(record).__name__,
            )
        if record.product != PRODUCT_NAMESPACE:
            raise ValidationError(
                "install run refuses a non-machi InstallRecord",
                product=record.product,
            )

    def _result(
        self,
        record: InstallRunRecord,
        *,
        existed: bool,
        created: bool,
    ) -> InstallRunEstablishment:
        return InstallRunEstablishment(
            record=record,
            status=InstallRunStatus.INSTALL_RUN_PRESENT,
            dual_ownership=False,
            destructive_authorization=False,
            existed=existed,
            created=created,
        )

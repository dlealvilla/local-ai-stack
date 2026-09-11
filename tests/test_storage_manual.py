"""Last-resort administrator capacity is available only after automatic failure."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.storage.characterize import (
    Characterization,
    StorageCharacterizationService,
)
from kultrun.storage.contracts import (
    AdministratorCapacityBound,
    StorageCapacityEvidence,
    StorageEvidenceStatus,
)
from kultrun.storage.index import StorageEvidenceIndex
from kultrun.storage.limits import POLICY_VERSION
from kultrun.storage.manual import AdministratorCapacityService
from kultrun.storage.probes import ProbeRegistry
from kultrun.storage.topology import pools_from_host
from tests.test_capacity import INSTANT, host, mount
from tests.test_contracts import host_capabilities

GIB = 1024**3
TIB = 1024**4


def _fuse_host() -> HostCapabilities:
    return host(
        mounts=(
            mount(
                "/workspace",
                "fuse",
                free=180 * TIB,
                total=180 * TIB,
            ),
        )
    )


def _evidence(
    subject: HostCapabilities,
    mount_point: str,
    *,
    available: object = NOT_PROVIDED,
    source: str = "none",
    status: StorageEvidenceStatus = StorageEvidenceStatus.UNRESOLVED,
) -> StorageCapacityEvidence:
    pool = next(
        item for item in pools_from_host(subject) if item.mount_point == mount_point
    )
    return StorageCapacityEvidence(
        host_id=subject.host_id,
        mount_point=mount_point,
        quota_identity=pool.quota_identity,
        pool_fingerprint=pool.fingerprint,
        observed_at=INSTANT,
        status=status,
        confidence=Confidence.LOW,
        provenance=Provenance(
            producer=Name("test"),
            producer_version=NOT_PROVIDED,
            observed_at=INSTANT,
            policy_version=POLICY_VERSION,
        ),
        operational_available_bytes=available,
        authorizing_available_bytes=available,
        native_source=source,
        selected_reason="test",
    )


class ScriptedChar:
    def __init__(
        self,
        subject: HostCapabilities,
        mount_point: str,
        automatic: StorageCapacityEvidence,
        filled: StorageCapacityEvidence,
    ) -> None:
        self.subject = subject
        self.mount_point = mount_point
        self.automatic = automatic
        self.filled = filled
        self.calls: list[dict[str, object]] = []

    def characterize(
        self,
        host: HostCapabilities,
        *,
        run_cleanup: bool = True,
        run_empirical: bool = True,
        probe_workspace: Path | None = None,
        administrator_bounds: dict[str, int] | None = None,
        **_kwargs: object,
    ) -> Characterization:
        del host, probe_workspace
        bounds = administrator_bounds or {}
        self.calls.append(
            {
                "run_cleanup": run_cleanup,
                "run_empirical": run_empirical,
                "bounds": dict(bounds),
            }
        )
        item = self.filled if self.mount_point in bounds else self.automatic
        return Characterization(
            pools=pools_from_host(self.subject),
            evidence={self.mount_point: item},
            cleanup=None,
            low_space=(),
            empirical_ran=("/workspace",) if run_empirical else (),
        )


def _service(
    tmp_path: Path,
    subject: HostCapabilities,
    char: ScriptedChar,
) -> tuple[AdministratorCapacityService, StorageEvidenceIndex]:
    index = StorageEvidenceIndex(FileStore(tmp_path / "store"))
    service = AdministratorCapacityService(
        cast(StorageCharacterizationService, char),
        index,
        FixedClock(INSTANT),
        tmp_path / "state",
        allow_empirical=True,
    )
    return service, index


def test_set_rejected_when_native_capacity_is_established(tmp_path: Path) -> None:
    subject = host_capabilities()
    mount_point = "/"
    automatic = _evidence(
        subject,
        mount_point,
        available=80 * GIB,
        source="posix-statvfs",
        status=StorageEvidenceStatus.AUTHORITATIVE,
    )
    char = ScriptedChar(subject, mount_point, automatic, automatic)
    service, index = _service(tmp_path, subject, char)
    with pytest.raises(PreconditionFailedError) as raised:
        service.set(subject, mount_point, 100 * GIB)
    assert raised.value.context["reason"] == "capacity_already_established"
    assert index.get_administrator_bound(subject.host_id, mount_point) is None


def test_set_rejected_when_specialist_or_sonar_established(tmp_path: Path) -> None:
    subject = host_capabilities()
    mount_point = "/"
    for status, source, available in (
        (StorageEvidenceStatus.PROBED, "linux-quota", 50 * GIB),
        (StorageEvidenceStatus.BOUNDED, "empirical-fallback", 32 * GIB),
    ):
        automatic = _evidence(
            subject, mount_point, available=available, source=source, status=status
        )
        char = ScriptedChar(subject, mount_point, automatic, automatic)
        service, index = _service(tmp_path, subject, char)
        with pytest.raises(PreconditionFailedError) as raised:
            service.set(subject, mount_point, 100 * GIB)
        assert raised.value.context["reason"] == "capacity_already_established"
        assert index.get_administrator_bound(subject.host_id, mount_point) is None


def test_set_persists_when_automatic_capacity_is_unresolved(tmp_path: Path) -> None:
    subject = host_capabilities()
    mount_point = "/"
    automatic = _evidence(subject, mount_point)
    filled = _evidence(
        subject,
        mount_point,
        available=100 * GIB,
        source="administrator",
        status=StorageEvidenceStatus.BOUNDED,
    )
    char = ScriptedChar(subject, mount_point, automatic, filled)
    service, index = _service(tmp_path, subject, char)
    result = service.set(subject, mount_point, 100 * GIB)
    assert result.accepted is True
    stored = index.get_administrator_bound(subject.host_id, mount_point)
    assert stored is not None
    assert stored.available_bytes == 100 * GIB
    assert index.matching_administrator_bytes(subject)[mount_point] == 100 * GIB
    assert result.payload()["native_source"] == "administrator"


def test_identity_mismatch_omits_stored_bound(tmp_path: Path) -> None:
    subject = host_capabilities()
    pool = pools_from_host(subject)[0]
    index = StorageEvidenceIndex(FileStore(tmp_path / "store"))
    index.put_administrator_bound(
        AdministratorCapacityBound(
            host_id=subject.host_id,
            mount_point=pool.mount_point,
            quota_identity=pool.quota_identity,
            pool_fingerprint="other-fingerprint",
            available_bytes=100 * GIB,
            observed_at=INSTANT,
            provenance=Provenance(
                producer=Name("storage.administrator"),
                producer_version=NOT_PROVIDED,
                observed_at=INSTANT,
                policy_version=POLICY_VERSION,
            ),
        )
    )
    assert index.matching_administrator_bytes(subject) == {}


def test_cheap_get_does_not_apply_manual_bound() -> None:
    subject = _fuse_host()
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry(()),
        use_live_native=False,
    )
    cheap = service.characterize(
        subject,
        run_cleanup=False,
        run_empirical=False,
        administrator_bounds={"/workspace": 8 * GIB},
    )
    item = cheap.evidence["/workspace"]
    assert item.status is StorageEvidenceStatus.UNRESOLVED
    assert not is_resolved(item.authorizing_available_bytes)


def test_expensive_path_applies_manual_after_automatic_unresolved() -> None:
    subject = _fuse_host()
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry(()),
        use_live_native=False,
    )
    expensive = service.characterize(
        subject,
        run_cleanup=False,
        run_empirical=True,
        administrator_bounds={"/workspace": 8 * GIB},
    )
    item = expensive.evidence["/workspace"]
    assert item.status is StorageEvidenceStatus.BOUNDED
    assert item.operational_available_bytes == 8 * GIB
    assert item.native_source == "administrator"


def test_inspect_does_not_characterize(tmp_path: Path) -> None:
    subject = host_capabilities()
    mount_point = "/"
    automatic = _evidence(subject, mount_point)
    filled = _evidence(
        subject,
        mount_point,
        available=40 * GIB,
        source="administrator",
        status=StorageEvidenceStatus.BOUNDED,
    )
    char = ScriptedChar(subject, mount_point, automatic, filled)
    service, _index = _service(tmp_path, subject, char)
    service.set(subject, mount_point, 40 * GIB)
    calls = len(char.calls)
    payload = service.inspect(subject, mount_point)
    assert len(char.calls) == calls
    assert payload["mutations"] is False
    assert payload["count"] == 1
    assert payload["bounds"][0]["available_bytes"] == 40 * GIB

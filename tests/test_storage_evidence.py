"""10% arbitration and native/probe evidence states."""

from __future__ import annotations

from kultrun.kernel.clock import FixedClock
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import StorageCapacityEvidence, StorageEvidenceStatus
from kultrun.storage.evidence import arbitrate, disagreement_ratio
from tests.test_capacity import INSTANT, host

GIB = 1024**3
CLOCK = FixedClock(INSTANT)
HOST = host().host_id


def _evidence(
    *,
    native_available: Maybe[int] = NOT_PROVIDED,
    probe_available: Maybe[int] = NOT_PROVIDED,
    hard_maximum: Maybe[int] = NOT_PROVIDED,
    reported_available: Maybe[int] = NOT_PROVIDED,
    native_source: Maybe[str] = NOT_PROVIDED,
    administrator_bound: Maybe[int] = NOT_PROVIDED,
    native_trusted: bool = True,
    mount_point: str = "/workspace",
    quota_identity: Maybe[str] = "fuse:x:/workspace",
) -> StorageCapacityEvidence:
    return arbitrate(
        host_id=HOST,
        mount_point=mount_point,
        quota_identity=quota_identity,
        pool_fingerprint="fp",
        clock=CLOCK,
        reported_available=reported_available,
        native_available=native_available,
        probe_available=probe_available,
        hard_maximum=hard_maximum,
        native_source=native_source,
        administrator_bound=administrator_bound,
        native_trusted=native_trusted,
    )


def test_zero_safe_ratio() -> None:
    assert disagreement_ratio(0, 0) == 0.0


def test_native_only_is_authoritative() -> None:
    item = _evidence(native_available=10 * GIB)
    assert item.status is StorageEvidenceStatus.AUTHORITATIVE
    assert item.operational_available_bytes == 10 * GIB
    assert item.probe_executed is False


def test_native_and_probe_equal_is_corroborated() -> None:
    item = _evidence(native_available=10 * GIB, probe_available=10 * GIB)
    assert item.status is StorageEvidenceStatus.CORROBORATED
    assert item.operational_available_bytes == 10 * GIB


def test_five_percent_apart_uses_native() -> None:
    native = 1000
    probe = 950
    item = _evidence(native_available=native, probe_available=probe)
    assert disagreement_ratio(native, probe) == 0.05
    assert item.status is StorageEvidenceStatus.CORROBORATED
    assert item.operational_available_bytes == native


def test_exactly_ten_percent_is_corroborated() -> None:
    native = 1000
    probe = 900
    assert disagreement_ratio(native, probe) == 0.10
    item = _evidence(native_available=native, probe_available=probe)
    assert item.status is StorageEvidenceStatus.CORROBORATED
    assert item.operational_available_bytes == native


def test_more_than_ten_percent_uses_probe() -> None:
    item = _evidence(native_available=1000, probe_available=800)
    assert item.status is StorageEvidenceStatus.CONTRADICTED
    assert item.operational_available_bytes == 800
    assert item.declared_available_bytes == 1000
    assert item.probe_available_bytes == 800


def test_probe_lower_than_native() -> None:
    item = _evidence(native_available=50 * GIB, probe_available=6 * GIB)
    assert item.status is StorageEvidenceStatus.CONTRADICTED
    assert item.operational_available_bytes == 6 * GIB


def test_probe_higher_than_hard_quota_is_capped() -> None:
    item = _evidence(
        native_available=70 * GIB,
        probe_available=70 * GIB,
        hard_maximum=50 * GIB,
    )
    assert item.operational_available_bytes == 50 * GIB
    # equal after cap still corroborated from native vs probe before cap
    assert item.status in {
        StorageEvidenceStatus.CORROBORATED,
        StorageEvidenceStatus.BOUNDED,
    }


def test_absurd_statvfs_without_probe_stays_native() -> None:
    item = _evidence(
        reported_available=186 * 1024**4,
        native_available=186 * 1024**4,
        native_source="posix-statvfs",
    )
    assert item.status is StorageEvidenceStatus.AUTHORITATIVE
    assert item.operational_available_bytes == 186 * 1024**4


def test_untrusted_native_does_not_authorize() -> None:
    item = _evidence(
        reported_available=186 * 1024**4,
        native_available=186 * 1024**4,
        native_source="posix-statvfs",
        native_trusted=False,
    )
    assert item.status is StorageEvidenceStatus.UNRESOLVED
    assert not is_resolved(item.authorizing_available_bytes)
    assert item.declared_available_bytes == 186 * 1024**4


def test_unresolved_when_nothing_is_known() -> None:
    item = _evidence()
    assert item.status is StorageEvidenceStatus.UNRESOLVED
    assert not is_resolved(item.operational_available_bytes)


def test_manual_bound_does_not_override_smaller_hard() -> None:
    item = _evidence(
        administrator_bound=80 * GIB,
        hard_maximum=10 * GIB,
        native_available=9 * GIB,
    )
    assert item.operational_available_bytes == 9 * GIB


def test_manual_fills_unresolved_below_hard() -> None:
    item = _evidence(administrator_bound=8 * GIB, hard_maximum=50 * GIB)
    assert item.status is StorageEvidenceStatus.BOUNDED
    assert item.operational_available_bytes == 8 * GIB
    assert item.native_source == "administrator"

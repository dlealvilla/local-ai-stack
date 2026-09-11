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


def test_five_percent_apart_uses_specialist() -> None:
    native = 1000
    probe = 950
    item = _evidence(native_available=native, probe_available=probe)
    assert disagreement_ratio(native, probe) == 0.05
    assert item.status is StorageEvidenceStatus.CORROBORATED
    assert item.operational_available_bytes == probe


def test_exactly_ten_percent_is_corroborated() -> None:
    native = 1000
    probe = 900
    assert disagreement_ratio(native, probe) == 0.10
    item = _evidence(native_available=native, probe_available=probe)
    assert item.status is StorageEvidenceStatus.CORROBORATED
    assert item.operational_available_bytes == probe


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


def test_trusted_local_below_anomaly_authorizes() -> None:
    item = _evidence(native_available=180 * GIB)
    assert item.status is StorageEvidenceStatus.AUTHORITATIVE
    assert item.operational_available_bytes == 180 * GIB


def test_absurd_statvfs_without_probe_does_not_authorize() -> None:
    item = _evidence(
        reported_available=186 * 1024**4,
        native_available=186 * 1024**4,
        native_source="posix-statvfs",
    )
    assert item.status is StorageEvidenceStatus.UNRESOLVED
    assert not is_resolved(item.authorizing_available_bytes)
    assert item.declared_available_bytes == 186 * 1024**4


def test_specialist_beats_huge_native() -> None:
    item = _evidence(
        native_available=180 * 1024**4,
        probe_available=50 * GIB,
        native_source="posix-statvfs",
    )
    assert item.status is StorageEvidenceStatus.CONTRADICTED
    assert item.operational_available_bytes == 50 * GIB


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


def test_exactly_anomaly_threshold_still_authorizes() -> None:
    from kultrun.storage.limits import NATIVE_ANOMALY_TRIGGER_BYTES

    item = _evidence(native_available=NATIVE_ANOMALY_TRIGGER_BYTES)
    assert item.status is StorageEvidenceStatus.AUTHORITATIVE


def test_just_above_anomaly_without_probe_is_unresolved() -> None:
    from kultrun.storage.limits import NATIVE_ANOMALY_TRIGGER_BYTES

    item = _evidence(native_available=NATIVE_ANOMALY_TRIGGER_BYTES + 1)
    assert item.status is StorageEvidenceStatus.UNRESOLVED
    assert not is_resolved(item.authorizing_available_bytes)


def test_sonar_always_requested_when_specialist_settled() -> None:
    from kultrun.storage.contracts import ProbeReport
    from kultrun.storage.evidence import needs_empirical_fallback

    reports = (
        ProbeReport(
            probe_name="moosefs-quota",
            technology="moosefs",
            compatible=True,
            available=True,
            executed=True,
            available_bytes=50 * GIB,
        ),
    )
    evidence = _evidence(
        native_available=180 * 1024**4,
        probe_available=50 * GIB,
        native_trusted=False,
    )
    assert (
        needs_empirical_fallback(
            family="fuse",
            credible_family=False,
            reports=reports,
            evidence=evidence,
        )
        is True
    )


def test_sonar_runs_for_unresolved_anomaly() -> None:
    from kultrun.storage.contracts import ProbeReport
    from kultrun.storage.evidence import needs_empirical_fallback

    reports = (
        ProbeReport(
            probe_name="linux-quota",
            technology="linux-quota",
            compatible=True,
            available=False,
            executed=False,
        ),
    )
    evidence = _evidence(native_available=12 * 1024**4)
    assert (
        needs_empirical_fallback(
            family="ext4",
            credible_family=True,
            reports=reports,
            evidence=evidence,
        )
        is True
    )


def test_fuse_identify_without_bytes_is_not_settlement() -> None:
    from kultrun.storage.contracts import ProbeReport
    from kultrun.storage.evidence import needs_empirical_fallback

    reports = (
        ProbeReport(
            probe_name="fuse-identify",
            technology="fuse",
            compatible=True,
            available=True,
            executed=True,
            detail="identified fuse",
        ),
    )
    evidence = _evidence(
        native_available=80 * GIB,
        native_trusted=False,
    )
    assert (
        needs_empirical_fallback(
            family="fuse",
            credible_family=False,
            reports=reports,
            evidence=evidence,
        )
        is True
    )


def _empirical(
    *,
    lower: int,
    upper: object = NOT_PROVIDED,
    ceiling: bool = False,
) -> object:
    from kultrun.evidence.contracts import Confidence, Provenance
    from kultrun.kernel.ids import Name
    from kultrun.storage.contracts import EmpiricalProbeEvidence
    from kultrun.storage.limits import POLICY_VERSION

    return EmpiricalProbeEvidence(
        host_id=HOST,
        mount_point="/workspace",
        target_path="/workspace",
        max_probe_bytes=lower,
        bytes_physically_written=0,
        search_granularity_bytes=1,
        probe_ceiling_reached=ceiling,
        confidence=Confidence.MEDIUM,
        provenance=Provenance(
            producer=Name("test"),
            producer_version=NOT_PROVIDED,
            observed_at=INSTANT,
            policy_version=POLICY_VERSION,
        ),
        cleanup_success=True,
        verified_lower_bound_bytes=lower,
        observed_failure_upper_bytes=upper,
    )


def test_sonar_confirms_specialist_within_ten_percent() -> None:
    empirical = _empirical(lower=48 * GIB)
    item = arbitrate(
        host_id=HOST,
        mount_point="/workspace",
        quota_identity="fuse:x:/workspace",
        pool_fingerprint="fp",
        clock=CLOCK,
        native_available=180 * 1024**4,
        probe_available=50 * GIB,
        empirical=empirical,
        native_trusted=False,
        probe_name="moosefs-quota",
        probe_compatible=True,
        probe_executed=True,
    )
    assert item.operational_available_bytes == 50 * GIB
    assert "sonar confirmed" in item.selected_reason
    assert item.probe_name == "moosefs-quota"


def test_sonar_replaces_specialist_when_they_disagree() -> None:
    empirical = _empirical(lower=32 * GIB)
    item = arbitrate(
        host_id=HOST,
        mount_point="/workspace",
        quota_identity="fuse:x:/workspace",
        pool_fingerprint="fp",
        clock=CLOCK,
        native_available=180 * 1024**4,
        probe_available=50 * GIB,
        empirical=empirical,
        native_trusted=False,
        probe_name="moosefs-quota",
        probe_compatible=True,
        probe_executed=True,
    )
    assert item.operational_available_bytes == 32 * GIB
    assert item.probe_name == "empirical-fallback"


def test_sonar_miss_keeps_specialist() -> None:
    from kultrun.evidence.contracts import Confidence, Provenance
    from kultrun.kernel.ids import Name
    from kultrun.storage.contracts import EmpiricalProbeEvidence
    from kultrun.storage.limits import POLICY_VERSION

    empirical = EmpiricalProbeEvidence(
        host_id=HOST,
        mount_point="/workspace",
        target_path="/workspace",
        max_probe_bytes=1,
        bytes_physically_written=0,
        search_granularity_bytes=1,
        probe_ceiling_reached=False,
        confidence=Confidence.LOW,
        provenance=Provenance(
            producer=Name("test"),
            producer_version=NOT_PROVIDED,
            observed_at=INSTANT,
            policy_version=POLICY_VERSION,
        ),
        cleanup_success=True,
        interrupted=True,
    )
    item = arbitrate(
        host_id=HOST,
        mount_point="/workspace",
        quota_identity="fuse:x:/workspace",
        pool_fingerprint="fp",
        clock=CLOCK,
        native_available=180 * 1024**4,
        probe_available=50 * GIB,
        empirical=empirical,
        native_trusted=False,
        probe_name="moosefs-quota",
        probe_compatible=True,
        probe_executed=True,
    )
    assert item.operational_available_bytes == 50 * GIB
    assert item.probe_name == "moosefs-quota"

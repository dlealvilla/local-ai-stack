"""Low-space policy: Step 0 first, no large stack, admin guidance."""

from __future__ import annotations

from pathlib import Path

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.kernel.clock import FixedClock
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.cleanup import step0_cleanup
from kultrun.storage.contracts import (
    CleanupPolicy,
    LifecycleState,
    ManagedResourceType,
)
from kultrun.storage.limits import LOW_SPACE_THRESHOLD_BYTES
from kultrun.storage.ownership import OwnershipService
from kultrun.storage.probes import ProbeRegistry
from tests.test_capacity import INSTANT, host, mount
from tests.test_storage_ownership import HOST


def test_step0_runs_and_unrelated_data_survives(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    customer = state / "customer-weights"
    customer.mkdir()
    (customer / "keep.bin").write_bytes(b"x" * 100)
    ownership = OwnershipService(
        FileStore(tmp_path / "records"), FixedClock(INSTANT), state
    )
    disposable = state / "tmp" / "failed"
    ownership.assert_owned(
        disposable,
        HOST,
        ManagedResourceType.TEMP,
        lifecycle=LifecycleState.FAILED,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    report = step0_cleanup(ownership, HOST)
    assert report.removed == 1
    assert (customer / "keep.bin").read_bytes() == b"x" * 100
    assert report.rediscovery_required is True


def test_characterization_reports_low_space(tmp_path: Path) -> None:
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry(()),
        low_space_bytes=LOW_SPACE_THRESHOLD_BYTES,
    )
    tiny = 2 * 1024**3
    subject = host(
        mounts=(mount("/kultrun-no-such-mount", "ext4", free=tiny, total=tiny),)
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=False)
    assert result.low_space
    assert result.low_space[0].rediscovery_required is True
    assert "Unrelated files will not be removed" in result.low_space[0].message

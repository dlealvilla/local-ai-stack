"""Stage 1.6L — CurrentCapacitySnapshot: SAFE minus ACTIVE commitments."""

from __future__ import annotations

from pathlib import Path

from kultrun.kernel.unresolved import is_resolved
from kultrun.resource.contracts import ReservationState
from kultrun.resource.snapshot import SNAPSHOT_VERSION, current_capacity_snapshot
from tests.test_resource_admission import (
    GIB,
    INSTANT,
    _artifact,
    _envelope,
    _manager,
    _request,
)


class TestCapacitySnapshotLayers:
    def test_physical_safe_and_available_stay_distinct(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(ram_safe=48 * GIB, devices=((0, 30 * GIB),))
        snapshot = manager.snapshot(envelope)
        assert snapshot.safe_ram_bytes == 48 * GIB
        assert snapshot.available_ram_bytes == 48 * GIB
        gpu = snapshot.accelerators[0]
        assert gpu.safe_bytes == 30 * GIB
        assert gpu.available_bytes == 30 * GIB
        assert gpu.reserved_bytes == 0
        assert snapshot.snapshot_version == SNAPSHOT_VERSION
        assert envelope.memory.reported_bytes != snapshot.available_ram_bytes
        assert envelope.accelerators[0].memory.reported_bytes != gpu.available_bytes

    def test_no_reservations_available_equals_safe(self, tmp_path: Path) -> None:
        snapshot = _manager(tmp_path).snapshot(
            _envelope(ram_safe=40 * GIB, devices=((0, 24 * GIB),))
        )
        assert snapshot.available_ram_bytes == snapshot.safe_ram_bytes
        gpu = snapshot.accelerators[0]
        assert gpu.available_bytes == gpu.safe_bytes
        assert snapshot.active_count == 0
        assert snapshot.active_reservation_ids == ()

    def test_active_vram_reservation_reduces_available_vram(
        self, tmp_path: Path
    ) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(devices=((0, 30 * GIB),))
        artifact = _artifact()
        admitted = manager.admit(
            _request(artifact, envelope, ram=4 * GIB, vram=12 * GIB),
            envelope,
            artifact,
        )
        assert admitted.reservation is not None
        snapshot = manager.snapshot(envelope)
        gpu = snapshot.accelerators[0]
        assert gpu.reserved_bytes == 12 * GIB
        assert gpu.available_bytes == 18 * GIB
        assert gpu.safe_bytes == 30 * GIB
        assert snapshot.available_ram_bytes == envelope.memory.safe_bytes - 4 * GIB
        assert (
            admitted.reservation.reservation_id.value in snapshot.active_reservation_ids
        )

    def test_ram_and_vram_remain_separate_pools(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(ram_safe=48 * GIB, devices=((0, 30 * GIB),))
        artifact = _artifact()
        manager.admit(
            _request(artifact, envelope, ram=8 * GIB, vram=12 * GIB),
            envelope,
            artifact,
        )
        snapshot = manager.snapshot(envelope)
        assert snapshot.reserved_ram_bytes == 8 * GIB
        assert snapshot.accelerators[0].reserved_bytes == 12 * GIB
        assert snapshot.available_ram_bytes != snapshot.accelerators[0].available_bytes

    def test_release_restores_availability(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(devices=((0, 30 * GIB),))
        artifact = _artifact()
        admitted = manager.admit(
            _request(artifact, envelope, vram=12 * GIB), envelope, artifact
        )
        assert admitted.reservation is not None
        before = manager.snapshot(envelope).snapshot_basis
        manager.release(admitted.reservation.reservation_id)
        after = manager.snapshot(envelope)
        assert after.accelerators[0].available_bytes == 30 * GIB
        assert after.active_count == 0
        assert after.snapshot_basis != before

    def test_own_reservation_exclusion_avoids_double_subtraction(
        self, tmp_path: Path
    ) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(devices=((0, 30 * GIB),))
        before = manager.snapshot(envelope)
        artifact = _artifact()
        admitted = manager.admit(
            _request(artifact, envelope, vram=12 * GIB), envelope, artifact
        )
        assert admitted.reservation is not None
        excluded = manager.snapshot(
            envelope, exclude_reservation_id=admitted.reservation.reservation_id
        )
        full = manager.snapshot(envelope)
        assert excluded.accelerators[0].available_bytes == 30 * GIB
        assert full.accelerators[0].available_bytes == 18 * GIB
        assert (
            excluded.excluded_reservation_id
            == admitted.reservation.reservation_id.value
        )
        assert excluded.snapshot_basis != full.snapshot_basis
        assert excluded.snapshot_basis == before.snapshot_basis
        matched = manager.active_reservation_for_plan("test-plan")
        assert matched is not None
        assert matched.reservation_id == admitted.reservation.reservation_id
        assert manager.active_reservation_for_plan("other-plan") is None

    def test_snapshot_is_derived_not_persisted_as_truth(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(devices=((0, 30 * GIB),))
        first = manager.snapshot(envelope)
        artifact = _artifact()
        manager.admit(_request(artifact, envelope, vram=12 * GIB), envelope, artifact)
        second = manager.snapshot(envelope)
        assert first.observed_at == INSTANT
        assert not hasattr(first, "captured_at")
        assert not hasattr(first, "derived_at")
        assert second.accelerators[0].available_bytes == 18 * GIB
        assert first.snapshot_basis != second.snapshot_basis
        reread = manager.snapshot(envelope)
        assert reread.snapshot_basis == second.snapshot_basis
        assert reread.accelerators[0].available_bytes == 18 * GIB

    def test_storage_is_not_combined_with_vram(self, tmp_path: Path) -> None:
        snapshot = current_capacity_snapshot(_envelope(devices=((0, 30 * GIB),)), ())
        assert is_resolved(snapshot.available_storage_bytes)
        assert (
            snapshot.available_storage_bytes != snapshot.accelerators[0].available_bytes
        )
        assert snapshot.reserved_incremental_storage_bytes == 0

    def test_stored_artifact_bytes_are_not_vram(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        envelope = _envelope(devices=((0, 30 * GIB),))
        artifact = _artifact()
        assert artifact.installed_bytes == 20 * GIB
        snapshot = manager.snapshot(envelope)
        assert snapshot.accelerators[0].reserved_bytes == 0
        assert snapshot.accelerators[0].available_bytes == 30 * GIB
        released = [
            item
            for item in manager.reservations(include_released=True)
            if item.state is ReservationState.RELEASED
        ]
        assert released == []

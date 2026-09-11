"""Foundation storage fit uses SAFE, the same figure ResourceManager spends."""

from __future__ import annotations

from kultrun.storage.feasibility import (
    requirement_fits,
    reservable_bytes,
    withhold_storage,
)
from kultrun.storage.footprint import runtime_provisioning_requirement
from kultrun.storage.limits import STORAGE_RESERVE_FLOOR_BYTES
from tests.test_capacity_first_storage import _evidence
from tests.test_contracts import host_capabilities

GIB = 1024**3


def test_twenty_five_gib_authorizing_is_not_enough_for_vllm_peak() -> None:
    host = host_capabilities()
    evidence = _evidence(host.host_id, 25 * GIB)
    requirement = runtime_provisioning_requirement()
    assert reservable_bytes(evidence) == 20 * GIB
    assert requirement_fits(requirement, evidence) is False


def test_thirty_two_gib_authorizing_can_admit_current_vllm_peak() -> None:
    host = host_capabilities()
    evidence = _evidence(host.host_id, 32 * GIB)
    requirement = runtime_provisioning_requirement()
    safe = reservable_bytes(evidence)
    assert safe is not None
    assert safe == 32 * GIB - STORAGE_RESERVE_FLOOR_BYTES
    assert requirement_fits(requirement, evidence) is True


def test_twenty_four_gib_authorizing_safe_is_nineteen() -> None:
    assert withhold_storage(24 * GIB) == 19 * GIB


def test_sixty_four_gib_authorizing_safe_is_fifty_seven_point_six() -> None:
    assert withhold_storage(64 * GIB) == 64 * GIB - int(64 * GIB * 0.10)


def test_storage_and_capacity_reserve_constants_match() -> None:
    from kultrun.capacity import policy as capacity_policy
    from kultrun.storage import limits as storage_limits

    assert (
        storage_limits.STORAGE_RESERVE_FRACTION
        == capacity_policy.STORAGE_RESERVE_FRACTION
    )
    assert (
        storage_limits.STORAGE_RESERVE_FLOOR_BYTES
        == capacity_policy.STORAGE_RESERVE_FLOOR_BYTES
    )

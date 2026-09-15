"""Machi architecture boundary tests through 2.3."""

from __future__ import annotations

from tests.machi.architecture import (
    binder_ownership_violations,
    discover_boundary_violations,
    identity_boundary_violations,
    journal_port_violations,
    kernel_policy_violations,
    kernel_technology_violations,
    marker_boundary_violations,
    package_import_violations,
    registry_boundary_violations,
    run_boundary_violations,
    scan,
    source_root,
    store_boundary_violations,
    unassigned_packages,
    violations,
)


def test_machi_does_not_import_kultrun() -> None:
    problems = [item for item in violations(scan(source_root())) if "kultrun" in item]
    assert problems == []


def test_tier_import_law_holds() -> None:
    assert violations(scan(source_root())) == []


def test_machi_packages_are_assigned_to_tiers() -> None:
    assert unassigned_packages(source_root()) == []


def test_kernel_does_not_own_state_root_or_ownership_policy() -> None:
    assert kernel_policy_violations(source_root()) == []


def test_state_root_binder_does_not_write_ownership_markers() -> None:
    assert binder_ownership_violations(source_root()) == []


def test_self_ownership_marker_stays_inside_local_evidence() -> None:
    assert marker_boundary_violations(source_root()) == []


def test_kernel_store_does_not_own_install_or_journal() -> None:
    assert store_boundary_violations(source_root()) == []


def test_registry_seed_stays_inside_control_plane_evidence() -> None:
    assert registry_boundary_violations(source_root()) == []


def test_install_identity_stays_inside_install_record() -> None:
    assert identity_boundary_violations(source_root()) == []


def test_install_run_store_stays_inside_install_run() -> None:
    assert run_boundary_violations(source_root()) == []


def test_os_arch_adapter_stays_inside_observation() -> None:
    assert discover_boundary_violations(source_root()) == []


def test_memory_observer_stays_inside_observation() -> None:
    assert discover_boundary_violations(source_root()) == []


def test_accelerator_observer_stays_inside_observation() -> None:
    assert discover_boundary_violations(source_root()) == []


def test_kernel_does_not_name_platform_or_vendor_primitives() -> None:
    assert kernel_technology_violations(source_root()) == []


def test_journal_port_is_not_the_jsonl_adapter() -> None:
    assert journal_port_violations(source_root()) == []


def test_base_package_import_does_not_load_providers() -> None:
    assert package_import_violations(source_root()) == []

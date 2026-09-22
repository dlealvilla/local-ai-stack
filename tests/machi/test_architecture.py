"""Machi architecture boundary tests through 2.4.1."""

from __future__ import annotations

from tests.machi.architecture import (
    binder_ownership_violations,
    capacity_boundary_violations,
    discover_boundary_violations,
    foundation_boundary_violations,
    identity_boundary_violations,
    journal_port_violations,
    kernel_policy_violations,
    kernel_technology_violations,
    marker_boundary_violations,
    package_import_violations,
    prerequisite_boundary_violations,
    registry_boundary_violations,
    run_boundary_violations,
    scan,
    source_root,
    steward_boundary_violations,
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


def test_capacity_derives_envelopes_without_admission() -> None:
    assert capacity_boundary_violations(source_root()) == []


def test_foundation_verifies_vllm_without_serving() -> None:
    assert foundation_boundary_violations(source_root()) == []


def test_steward_classifies_without_deletion_or_admission() -> None:
    assert steward_boundary_violations(source_root()) == []


def test_mount_observer_stays_inside_observation() -> None:
    assert discover_boundary_violations(source_root()) == []


def test_kernel_does_not_name_platform_or_vendor_primitives() -> None:
    assert kernel_technology_violations(source_root()) == []


def test_journal_port_is_not_the_jsonl_adapter() -> None:
    assert journal_port_violations(source_root()) == []


def test_base_package_import_does_not_load_providers() -> None:
    assert package_import_violations(source_root()) == []


def test_prerequisite_readiness_stays_outside_discover_and_admission() -> None:
    assert prerequisite_boundary_violations(source_root()) == []


def test_intel_provider_is_absent_from_composition() -> None:
    root = source_root()
    assert not (root / "adapters" / "discover" / "intel_accelerator.py").exists()
    native = (root / "adapters" / "discover" / "native_accelerator.py").read_text(
        encoding="utf-8"
    )
    tree = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert "IntelAcceleratorProvider" not in native
    assert "intel_provider" not in native
    assert "xpu-smi" not in tree
    assert "xpumcli" not in tree
    assert "tools.acceptance_lab" not in tree

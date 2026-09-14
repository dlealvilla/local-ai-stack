"""Machi architecture boundary tests (M0 Kernel + 1.2.1 Install)."""

from __future__ import annotations

from tests.machi.architecture import (
    kernel_policy_violations,
    scan,
    source_root,
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


def test_kernel_does_not_own_state_root_policy() -> None:
    assert kernel_policy_violations(source_root()) == []

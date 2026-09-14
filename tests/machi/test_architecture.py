"""Machi M0 architecture boundary tests."""

from __future__ import annotations

from tests.machi.architecture import scan, source_root, unassigned_packages, violations


def test_machi_does_not_import_kultrun() -> None:
    problems = [item for item in violations(scan(source_root())) if "kultrun" in item]
    assert problems == []


def test_kernel_does_not_import_adapters_or_future_blocks() -> None:
    assert violations(scan(source_root())) == []


def test_machi_packages_are_assigned_to_m0_tiers() -> None:
    assert unassigned_packages(source_root()) == []

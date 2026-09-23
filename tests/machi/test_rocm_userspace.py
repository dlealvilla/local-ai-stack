"""Managed ROCm prefix and verified-host shortcut. Fixtures only."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import replace
from pathlib import Path

from tests.machi.test_foundation import GIB, _capacity, _gpu, _os, _Runner

from machi.adapters.foundation.provision import ManagedVllmProvisioner
from machi.adapters.foundation.rocm_userspace import (
    AmdHostDevices,
    ComponentRecord,
    RealizedEnvironment,
    UserspacePlan,
    assess,
    driver_compatible,
    generation_process_env,
    minimum_components,
    realize,
    remove_owned_environment,
    unrelated_process_env,
)
from machi.discover.contracts import AcceleratorVendor, OSFamily
from machi.foundation.contracts import FailureCode, ProvisionMode, SupportState
from machi.foundation.policy import ROCM700_LIBS, default_foundation_settings
from machi.foundation.recipe import HostRuntimeFacts
from machi.foundation.resolve import resolve_candidate
from machi.kernel.clock import FixedClock

FIXED = dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.UTC)
SOURCE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "machi"
    / "adapters"
    / "foundation"
    / "rocm_userspace.py"
)
DEVICES = AmdHostDevices(
    kernel_module=True,
    gpu_device=True,
    kfd=True,
    dri=True,
)


def _host(**overrides: object) -> HostRuntimeFacts:
    fields: dict[str, object] = {
        "glibc_version": "2.39",
        "accelerator_architecture": "gfx942",
        "driver_line": "6.3.1",
        "rocm_version": None,
        "present_libraries": frozenset(),
    }
    fields.update(overrides)
    return HostRuntimeFacts(**fields)  # type: ignore[arg-type]


def _sized() -> tuple[ComponentRecord, ...]:
    return tuple(replace(item, size_bytes=32) for item in minimum_components())


def _write(prefix: Path, components: tuple[ComponentRecord, ...]) -> None:
    lib = prefix / "lib"
    lib.mkdir()
    for item in components:
        (lib / item.soname).write_bytes(b"fixture")


def test_compatible_driver_without_userspace_is_managed() -> None:
    plan = assess(_host(driver_line="6.4.2"), DEVICES)
    assert plan.disposition == "managed"


def test_driver_61_refuses_managed_userspace() -> None:
    assert driver_compatible("6.1.0") is False
    assert driver_compatible("6.2.4") is True
    assert driver_compatible("30.10.1") is True
    plan = assess(_host(driver_line="6.1.0"), DEVICES)
    assert plan.disposition == "refused"
    assert plan.failure == "driver_or_backend_incompatible"


def test_verified_existing_userspace_matches_the_recipe() -> None:
    plan = assess(
        _host(
            driver_line="6.2.0",
            rocm_version="7.0.2",
            present_libraries=frozenset(ROCM700_LIBS),
            library_prefix="/fixture/lib",
        ),
        DEVICES,
    )
    assert plan.disposition == "verified"


def test_missing_soname_fails_verification() -> None:
    missing = ROCM700_LIBS[0]
    present = frozenset(name for name in ROCM700_LIBS if name != missing)
    plan = assess(
        _host(
            rocm_version="7.0.0",
            present_libraries=present,
        ),
        DEVICES,
    )
    assert plan.disposition == "refused"
    assert missing in plan.reason


def test_customer_tree_is_not_overwritten_and_prefix_is_isolated(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "customer"
    customer.mkdir()
    sentinel = customer / "version"
    sentinel.write_text("customer", encoding="utf-8")
    before = dict(os.environ)
    state = tmp_path / "state"
    result = realize(
        state,
        _host(),
        DEVICES,
        _sized(),
        recipe_id="vllm-0.18.0-rocm700",
        safe_bytes=10_000,
        writer=_write,
    )
    assert isinstance(result, RealizedEnvironment)
    manifest = (result.manifest_path).read_text(encoding="utf-8")
    assert '"owned": true' in manifest
    assert '"owner": "machi"' in manifest
    assert sentinel.read_text(encoding="utf-8") == "customer"
    generation = generation_process_env(result.prefix)
    assert str(result.prefix / "lib") in generation["LD_LIBRARY_PATH"]
    assert "LD_LIBRARY_PATH" not in unrelated_process_env()
    assert os.environ == before
    sibling = state / "foundation" / "environments" / "keep.txt"
    sibling.write_text("keep", encoding="utf-8")
    remove_owned_environment(state, result.environment_id)
    assert not result.prefix.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"
    assert sentinel.read_text(encoding="utf-8") == "customer"


def test_unknown_license_is_not_classified_green(tmp_path: Path) -> None:
    components = _sized()
    blocked = replace(
        components[0], license_name="unknown", classification="green"
    )
    result = realize(
        tmp_path,
        _host(),
        DEVICES,
        (blocked, *components[1:]),
        recipe_id="vllm-0.18.0-rocm700",
        safe_bytes=10_000,
        writer=_write,
    )
    assert isinstance(result, UserspacePlan)
    assert result.disposition == "refused"
    assert not (tmp_path / "foundation" / "environments").exists()


def test_unmeasured_prefix_does_not_install(tmp_path: Path) -> None:
    result = realize(
        tmp_path,
        _host(),
        DEVICES,
        minimum_components(),
        recipe_id="vllm-0.18.0-rocm700",
        safe_bytes=12 * GIB,
        writer=_write,
    )
    assert isinstance(result, UserspacePlan)
    assert result.reason == "prefix footprint is unmeasured"


def test_realize_candidate_does_not_install_before_a_prefix(tmp_path: Path) -> None:
    runner = _Runner()
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.AMD, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="rocm",
        prerequisite_ready=True,
        host_runtime=_host(driver_line="6.4.0"),
    )
    assert candidate.support is SupportState.SUPPORTED
    assert candidate.native_status == "realize"
    result = ManagedVllmProvisioner(runner, clock=FixedClock(FIXED)).apply(
        state_root=tmp_path,
        candidate=candidate,
        settings=default_foundation_settings(mode=ProvisionMode.PROVISION),
        capacity_evidence_id="cap_foundation",
    )
    assert runner.calls == []
    assert result.selection.failure is FailureCode.PREREQUISITE_BLOCKED


def test_provider_does_not_mutate_the_global_loader() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "ldconfig" not in text
    assert "ContainerExecutor" not in text
    assert "docker" not in text.lower()

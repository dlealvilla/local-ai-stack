"""Apple accelerator provider (MACHI 2.3)."""

from __future__ import annotations

import datetime as dt
import json
import platform
import subprocess

import pytest

from machi.adapters.discover.apple_accelerator import (
    AppleAcceleratorProvider,
    parse_apple_displays_json,
)
from machi.adapters.discover.command import CommandOutcome
from machi.adapters.discover.native_accelerator import NativeAcceleratorObserver
from machi.discover.contracts import (
    AcceleratorDeviceType,
    AcceleratorMemoryTopology,
    AcceleratorSource,
    AcceleratorVendor,
    ObservationStatus,
    ProviderInspectionStatus,
)
from machi.discover.normalize import normalize_os_architecture
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import is_resolved

FIXED = dt.datetime(2026, 9, 15, 15, 0, tzinfo=dt.UTC)

APPLE_M1 = json.dumps(
    {
        "SPDisplaysDataType": [
            {
                "_name": "kHW_AppleM1Item",
                "sppci_bus": "spdisplays_builtin",
                "sppci_cores": "7",
                "sppci_device_type": "spdisplays_gpu",
                "sppci_model": "Apple M1",
                "spdisplays_vendor": "sppci_vendor_Apple",
            }
        ]
    }
)
INTEL_MAC = json.dumps(
    {
        "SPDisplaysDataType": [
            {
                "sppci_bus": "spdisplays_builtin",
                "sppci_device_type": "spdisplays_gpu",
                "sppci_model": "Intel UHD Graphics 630",
                "spdisplays_vendor": "sppci_vendor_Intel",
            }
        ]
    }
)
TWO_APPLE = json.dumps(
    {
        "SPDisplaysDataType": [
            {
                "sppci_bus": "spdisplays_builtin",
                "sppci_device_type": "spdisplays_gpu",
                "sppci_model": "Apple M1",
                "spdisplays_vendor": "sppci_vendor_Apple",
            },
            {
                "sppci_bus": "spdisplays_builtin",
                "sppci_device_type": "spdisplays_gpu",
                "sppci_model": "Apple M1",
                "spdisplays_vendor": "sppci_vendor_Apple",
            },
        ]
    }
)


def test_apple_silicon_fixture_is_unified_without_fake_vram() -> None:
    devices = parse_apple_displays_json(APPLE_M1)
    assert len(devices) == 1
    device = devices[0]
    assert device.vendor is AcceleratorVendor.APPLE
    assert device.model_name == "Apple M1"
    assert device.device_type is AcceleratorDeviceType.INTEGRATED_GPU
    assert device.memory_topology is AcceleratorMemoryTopology.UNIFIED
    assert device.memory_total_status is ObservationStatus.UNOBSERVED
    assert not is_resolved(device.memory_total_bytes)
    assert device.identity == "apple-m1"
    assert device.source is AcceleratorSource.APPLE_DISPLAYS
    assert "8589934592" not in device.raw
    assert "physical_memory" not in device.raw


def test_non_apple_macos_gpu_is_observed_zero_apple_devices() -> None:
    devices = parse_apple_displays_json(INTEL_MAC)
    assert devices == ()
    result = AppleAcceleratorProvider(displays_json=INTEL_MAC).inspect()
    assert result.report.status is ProviderInspectionStatus.OBSERVED
    assert result.report.device_count == 0


def test_duplicate_apple_models_keep_distinct_identities() -> None:
    devices = parse_apple_displays_json(TWO_APPLE)
    assert [device.identity for device in devices] == ["apple-m1", "apple-m1-1"]


def test_malformed_json_fails() -> None:
    with pytest.raises(ValidationError, match="malformed"):
        parse_apple_displays_json("{not-json")


def test_missing_expected_key_fails() -> None:
    with pytest.raises(ValidationError, match="SPDisplaysDataType is missing"):
        parse_apple_displays_json("{}")


def test_inspect_malformed_is_failed_not_zero() -> None:
    result = AppleAcceleratorProvider(displays_json="{not-json").inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED
    assert result.devices == ()
    assert not is_resolved(result.report.device_count)


def test_missing_command_is_unavailable() -> None:
    def missing(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=False, timed_out=False, returncode=None, stdout="", stderr=""
        )

    result = AppleAcceleratorProvider(runner=missing).inspect()
    assert result.report.status is ProviderInspectionStatus.UNAVAILABLE
    assert not is_resolved(result.report.device_count)


def test_not_applicable_on_linux() -> None:
    linux = normalize_os_architecture("Linux", "x86_64", observed_at=FIXED)
    provider = AppleAcceleratorProvider(displays_json=APPLE_M1)
    assert provider.applicable(linux) is False


def test_not_applicable_when_os_unobserved() -> None:
    unobserved = normalize_os_architecture("", "arm64", observed_at=FIXED)
    provider = AppleAcceleratorProvider(displays_json=APPLE_M1)
    assert unobserved.os_status is ObservationStatus.UNOBSERVED
    assert provider.applicable(unobserved) is False


def test_applicable_on_macos() -> None:
    darwin = normalize_os_architecture("Darwin", "arm64", observed_at=FIXED)
    assert AppleAcceleratorProvider().applicable(darwin) is True


@pytest.mark.skipif(platform.system() != "Darwin", reason="Apple host evidence")
def test_real_host_apple_observation_matches_system_profiler() -> None:
    observed = NativeAcceleratorObserver(clock=FixedClock(FIXED)).observe()
    apple = next(report for report in observed.providers if report.provider == "apple")
    nvidia = next(
        report for report in observed.providers if report.provider == "nvidia"
    )
    assert apple.status is ProviderInspectionStatus.OBSERVED
    assert isinstance(apple.device_count, int)
    assert apple.device_count >= 1
    device = next(
        item for item in observed.devices if item.vendor is AcceleratorVendor.APPLE
    )
    assert device.memory_topology is AcceleratorMemoryTopology.UNIFIED
    assert not is_resolved(device.memory_total_bytes)
    assert device.source is AcceleratorSource.APPLE_DISPLAYS
    raw = subprocess.check_output(
        ["system_profiler", "SPDisplaysDataType", "-json"],
        text=True,
        timeout=60,
    )
    independent = json.loads(raw)["SPDisplaysDataType"]
    apple_models = [
        str(item.get("sppci_model", ""))
        for item in independent
        if "apple" in str(item.get("spdisplays_vendor", "")).lower()
        or str(item.get("sppci_model", "")).lower().startswith("apple")
    ]
    assert device.model_name in apple_models
    if nvidia.status is ProviderInspectionStatus.UNAVAILABLE:
        assert all(
            item.vendor is not AcceleratorVendor.NVIDIA for item in observed.devices
        )
        assert not is_resolved(nvidia.device_count)
    assert observed.status is ObservationStatus.NORMALIZED
    assert observed.observer == "native"
    amd = next(report for report in observed.providers if report.provider == "amd")
    assert amd.status is ProviderInspectionStatus.NOT_APPLICABLE
    assert not is_resolved(amd.device_count)

"""NVIDIA accelerator provider (MACHI 2.3)."""

from __future__ import annotations

import datetime as dt

import pytest

from machi.adapters.discover.command import CommandOutcome
from machi.adapters.discover.native_accelerator import NativeAcceleratorObserver
from machi.adapters.discover.nvidia_accelerator import (
    NvidiaAcceleratorProvider,
    parse_nvidia_smi_csv,
)
from machi.discover.contracts import (
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

SINGLE = "0, GPU-11111111-1111-1111-1111-111111111111, NVIDIA GeForce RTX 4090, 24576\n"
QUOTED = (
    "1, GPU-22222222-2222-2222-2222-222222222222, "
    '"NVIDIA RTX PRO 4500 Blackwell 32GB", 32768\n'
)
WHITESPACE = (
    "  0  ,  GPU-33333333-3333-3333-3333-333333333333  ,  Tesla T4  ,  15360  \n"
)
SMALL = "0, GPU-44444444-4444-4444-4444-444444444444, NVIDIA GeForce GT 1030, 2048\n"
MULTI = (
    "0, GPU-aaaaaaa1-1111-1111-1111-111111111111, NVIDIA A100-SXM4-40GB, 40960\n"
    "1, GPU-aaaaaaa2-2222-2222-2222-222222222222, NVIDIA A100-SXM4-80GB, 81920\n"
    "2, GPU-aaaaaaa3-3333-3333-3333-333333333333, NVIDIA L40S, 46068\n"
    "3, GPU-aaaaaaa4-4444-4444-4444-444444444444, NVIDIA H100 80GB HBM3, 81559\n"
)
MISSING_MEMORY = (
    "0, GPU-55555555-5555-5555-5555-555555555555, NVIDIA GeForce RTX 4090, [N/A]\n"
)
MALFORMED_MEMORY = (
    "0, GPU-11111111-1111-1111-1111-111111111111, NVIDIA GeForce RTX 4090, lots\n"
)
MISSING_UUID = "0, [N/A], NVIDIA GeForce RTX 4090, 24576\n"


def test_single_gpu_converts_mib_to_bytes() -> None:
    devices = parse_nvidia_smi_csv(SINGLE)
    assert len(devices) == 1
    device = devices[0]
    assert device.vendor is AcceleratorVendor.NVIDIA
    assert device.model_name == "NVIDIA GeForce RTX 4090"
    assert device.memory_topology is AcceleratorMemoryTopology.DISCRETE
    assert device.memory_total_bytes == 24576 * 1024 * 1024
    assert device.memory_total_status is ObservationStatus.NORMALIZED
    assert device.identity == "GPU-11111111-1111-1111-1111-111111111111"
    assert device.source is AcceleratorSource.NVIDIA_SMI
    assert device.ordinal == 0


def test_csv_quoting_preserves_model_name() -> None:
    devices = parse_nvidia_smi_csv(QUOTED)
    assert devices[0].model_name == "NVIDIA RTX PRO 4500 Blackwell 32GB"
    assert devices[0].memory_total_bytes == 32768 * 1024 * 1024
    assert devices[0].ordinal == 0


def test_whitespace_is_stripped() -> None:
    devices = parse_nvidia_smi_csv(WHITESPACE)
    assert devices[0].model_name == "Tesla T4"
    assert devices[0].memory_total_bytes == 15360 * 1024 * 1024


def test_small_and_large_memory_values() -> None:
    small = parse_nvidia_smi_csv(SMALL)[0]
    large = parse_nvidia_smi_csv(MULTI)[1]
    assert small.memory_total_bytes == 2048 * 1024 * 1024
    assert large.memory_total_bytes == 81920 * 1024 * 1024


def test_four_gpus_are_emitted_individually() -> None:
    devices = parse_nvidia_smi_csv(MULTI)
    assert len(devices) == 4
    assert [device.ordinal for device in devices] == [0, 1, 2, 3]
    names = [device.model_name for device in devices]
    assert names[0] == "NVIDIA A100-SXM4-40GB"
    assert names[3] == "NVIDIA H100 80GB HBM3"
    totals = [
        device.memory_total_bytes
        for device in devices
        if isinstance(device.memory_total_bytes, int)
    ]
    assert totals == [
        40960 * 1024 * 1024,
        81920 * 1024 * 1024,
        46068 * 1024 * 1024,
        81559 * 1024 * 1024,
    ]


def test_missing_memory_is_unresolved_not_zero() -> None:
    device = parse_nvidia_smi_csv(MISSING_MEMORY)[0]
    assert not is_resolved(device.memory_total_bytes)
    assert device.memory_total_status is ObservationStatus.UNOBSERVED
    assert device.memory_topology is AcceleratorMemoryTopology.DISCRETE


def test_missing_uuid_falls_back_to_index_identity() -> None:
    device = parse_nvidia_smi_csv(MISSING_UUID)[0]
    assert device.identity == "nvidia-index-0"


def test_empty_successful_csv_is_zero_devices() -> None:
    assert parse_nvidia_smi_csv("") == ()
    assert parse_nvidia_smi_csv("   \n") == ()


def test_malformed_numeric_memory_fails() -> None:
    with pytest.raises(ValidationError, match="not an integer"):
        parse_nvidia_smi_csv(MALFORMED_MEMORY)


def test_missing_fields_fail() -> None:
    with pytest.raises(ValidationError, match="wrong number of fields"):
        parse_nvidia_smi_csv("0, NVIDIA GeForce RTX 4090, 24576\n")


def test_zero_memory_fails_closed() -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        parse_nvidia_smi_csv(
            "0, GPU-11111111-1111-1111-1111-111111111111, NVIDIA GeForce RTX 4090, 0\n"
        )


def test_inspect_malformed_csv_is_failed_not_zero() -> None:
    result = NvidiaAcceleratorProvider(csv_text=MALFORMED_MEMORY).inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED
    assert result.devices == ()
    assert not is_resolved(result.report.device_count)


def test_inspect_empty_csv_is_observed_zero() -> None:
    result = NvidiaAcceleratorProvider(csv_text="").inspect()
    assert result.report.status is ProviderInspectionStatus.OBSERVED
    assert result.report.device_count == 0
    assert result.devices == ()


def test_missing_command_is_unavailable_not_zero() -> None:
    def missing(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=False, timed_out=False, returncode=None, stdout="", stderr=""
        )

    result = NvidiaAcceleratorProvider(runner=missing).inspect()
    assert result.report.status is ProviderInspectionStatus.UNAVAILABLE
    assert result.devices == ()
    assert not is_resolved(result.report.device_count)
    assert "not found" in result.report.detail


def test_nonzero_exit_is_failed() -> None:
    def failed(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=True,
            timed_out=False,
            returncode=1,
            stdout="",
            stderr="couldn't communicate with the NVIDIA driver",
        )

    result = NvidiaAcceleratorProvider(runner=failed).inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED
    assert result.devices == ()


def test_timeout_is_failed() -> None:
    def timed_out(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=True, timed_out=True, returncode=None, stdout="", stderr=""
        )

    result = NvidiaAcceleratorProvider(runner=timed_out).inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED
    assert "timed out" in result.report.detail


def test_stderr_paths_are_not_leaked() -> None:
    def failed(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=True,
            timed_out=False,
            returncode=127,
            stdout="",
            stderr="/usr/bin/nvidia-smi: failed",
        )

    result = NvidiaAcceleratorProvider(runner=failed).inspect()
    assert "/" not in result.report.detail
    assert "\\" not in result.report.detail


def test_applicable_on_linux_macos_windows() -> None:
    provider = NvidiaAcceleratorProvider(csv_text="")
    linux = normalize_os_architecture("Linux", "x86_64", observed_at=FIXED)
    darwin = normalize_os_architecture("Darwin", "arm64", observed_at=FIXED)
    windows = normalize_os_architecture("Windows", "AMD64", observed_at=FIXED)
    assert provider.applicable(linux)
    assert provider.applicable(darwin)
    assert provider.applicable(windows)


def test_local_negative_path_is_not_measured_zero_nvidia_gpus() -> None:
    observed = NativeAcceleratorObserver(clock=FixedClock(FIXED)).observe()
    nvidia = next(
        report for report in observed.providers if report.provider == "nvidia"
    )
    assert [report.provider for report in observed.providers] == [
        "nvidia",
        "amd",
        "intel",
        "apple",
    ]
    nvidia_devices = [
        device
        for device in observed.devices
        if device.vendor is AcceleratorVendor.NVIDIA
    ]
    if nvidia.status is ProviderInspectionStatus.UNAVAILABLE:
        assert nvidia_devices == []
        assert not is_resolved(nvidia.device_count)
        return
    if nvidia.status is ProviderInspectionStatus.OBSERVED:
        assert nvidia.device_count == len(nvidia_devices)
        return
    pytest.fail(f"unexpected NVIDIA provider status {nvidia.status.value}")

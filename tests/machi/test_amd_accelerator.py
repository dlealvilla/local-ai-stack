"""AMD accelerator provider (MACHI 2.3)."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence

import pytest

from machi.adapters.discover.amd_accelerator import (
    AmdAcceleratorProvider,
    parse_amd_smi_json,
)
from machi.adapters.discover.command import CommandOutcome
from machi.discover.contracts import (
    AcceleratorDeviceType,
    AcceleratorMemoryTopology,
    AcceleratorSource,
    AcceleratorVendor,
    ObservationStatus,
    ProviderInspectionStatus,
)
from machi.discover.normalize import normalize_os_architecture
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import is_resolved

FIXED = dt.datetime(2026, 9, 15, 15, 0, tzinfo=dt.UTC)

MI300X_LIST = json.dumps(
    [
        {
            "gpu": 0,
            "bdf": "0000:05:00.0",
            "uuid": "afff74a1-0000-1000-8054-e92b0a5d57c8",
            "partition_id": 0,
        }
    ]
)
MI300X_STATIC = json.dumps(
    [
        {
            "gpu": 0,
            "asic": {"market_name": "MI300X-O", "vendor_id": "0x1002"},
            "bus": {"bdf": "0000:05:00.0"},
            "vram": {"type": "HBM", "size": {"value": 196592, "unit": "MB"}},
        }
    ]
)
MULTI_LIST = json.dumps(
    [
        {
            "gpu": 0,
            "bdf": "0000:05:00.0",
            "uuid": "afff74a1-0000-1000-8054-e92b0a5d57c8",
        },
        {
            "gpu": 1,
            "bdf": "0000:26:00.0",
            "uuid": "0aff74a1-0000-1000-805b-ce698de95724",
        },
    ]
)
MULTI_STATIC = json.dumps(
    [
        {
            "gpu": 0,
            "asic": {"market_name": "MI300X-O"},
            "vram": {"type": "HBM", "size": {"value": 196592, "unit": "MB"}},
        },
        {
            "gpu": 1,
            "asic": {"market_name": "MI300X-O"},
            "vram": {"type": "HBM", "size": {"value": 196592, "unit": "MB"}},
        },
    ]
)
MI300A_LIST = json.dumps(
    [{"gpu": 0, "bdf": "0000:01:00.0", "uuid": "aaaaaaaa-0000-1000-8000-aaaaaaaaaaaa"}]
)
MI300A_STATIC = json.dumps(
    [
        {
            "gpu": 0,
            "asic": {"market_name": "AMD Instinct MI300A"},
            "board": {"product_name": "Aqua Vanjaram [Instinct MI300A]"},
            "vram": {"type": "HBM", "size": {"value": 96432, "unit": "MB"}},
        }
    ]
)
CPU_AND_GPU = json.dumps(
    [
        {"cpu": 0, "uuid": "cpu-uuid-should-be-ignored"},
        {
            "gpu": 0,
            "bdf": "0000:05:00.0",
            "uuid": "afff74a1-0000-1000-8054-e92b0a5d57c8",
        },
    ]
)
MISSING_VRAM = json.dumps(
    [
        {
            "gpu": 0,
            "asic": {"market_name": "MI300X-O"},
            "vram": {"type": "HBM", "size": "N/A"},
        }
    ]
)
DUPLICATE = json.dumps(
    [
        {
            "gpu": 0,
            "uuid": "afff74a1-0000-1000-8054-e92b0a5d57c8",
            "bdf": "0000:05:00.0",
        },
        {
            "gpu": 1,
            "uuid": "afff74a1-0000-1000-8054-e92b0a5d57c8",
            "bdf": "0000:26:00.0",
        },
    ]
)


def test_discrete_instinct_converts_mb_to_bytes() -> None:
    devices = parse_amd_smi_json(MI300X_LIST, MI300X_STATIC)
    assert len(devices) == 1
    device = devices[0]
    assert device.vendor is AcceleratorVendor.AMD
    assert device.model_name == "MI300X-O"
    assert device.device_type is AcceleratorDeviceType.DISCRETE_GPU
    assert device.memory_topology is AcceleratorMemoryTopology.DISCRETE
    assert device.memory_total_bytes == 196592 * 1024 * 1024
    assert device.identity == "afff74a1-0000-1000-8054-e92b0a5d57c8"
    assert device.source is AcceleratorSource.AMD_SMI
    assert "0000:05:00.0" in device.raw


def test_multi_gpu_is_not_reduced() -> None:
    devices = parse_amd_smi_json(MULTI_LIST, MULTI_STATIC)
    assert len(devices) == 2
    assert [device.ordinal for device in devices] == [0, 1]
    assert devices[0].identity != devices[1].identity
    assert devices[0].memory_total_bytes == devices[1].memory_total_bytes
    assert isinstance(devices[0].memory_total_bytes, int)


def test_mi300a_is_unified_without_dedicated_total() -> None:
    devices = parse_amd_smi_json(MI300A_LIST, MI300A_STATIC)
    device = devices[0]
    assert device.device_type is AcceleratorDeviceType.INTEGRATED_GPU
    assert device.memory_topology is AcceleratorMemoryTopology.UNIFIED
    assert device.memory_total_status is ObservationStatus.UNOBSERVED
    assert not is_resolved(device.memory_total_bytes)
    assert "96432" not in str(device.memory_total_bytes)


def test_cpu_entries_are_ignored() -> None:
    devices = parse_amd_smi_json(CPU_AND_GPU, MI300X_STATIC)
    assert len(devices) == 1
    assert devices[0].vendor is AcceleratorVendor.AMD
    assert devices[0].identity == "afff74a1-0000-1000-8054-e92b0a5d57c8"


def test_missing_vram_is_unresolved_not_zero() -> None:
    listed = json.dumps(
        [
            {
                "gpu": 0,
                "uuid": "afff74a1-0000-1000-8054-e92b0a5d57c8",
                "bdf": "0000:05:00.0",
            }
        ]
    )
    device = parse_amd_smi_json(listed, MISSING_VRAM)[0]
    assert not is_resolved(device.memory_total_bytes)
    assert device.memory_topology is AcceleratorMemoryTopology.DISCRETE


def test_empty_list_is_zero_devices() -> None:
    assert parse_amd_smi_json("[]") == ()
    assert parse_amd_smi_json(json.dumps([{"cpu": 0}])) == ()


def test_missing_uuid_falls_back_to_index() -> None:
    listed = json.dumps([{"gpu": 3, "bdf": "0000:05:00.0"}])
    static = json.dumps(
        [
            {
                "gpu": 3,
                "asic": {"market_name": "MI300X-O"},
                "vram": {"type": "HBM", "size": {"value": 1, "unit": "MB"}},
            }
        ]
    )
    device = parse_amd_smi_json(listed, static)[0]
    assert device.identity == "amd-index-3"


def test_malformed_json_fails() -> None:
    with pytest.raises(ValidationError, match="malformed"):
        parse_amd_smi_json("{not-json")


def test_wrong_field_type_fails() -> None:
    with pytest.raises(ValidationError, match="wrong type"):
        parse_amd_smi_json(
            json.dumps([{"gpu": "zero", "uuid": "abc", "bdf": "0000:00:00.0"}])
        )


def test_duplicate_identity_fails() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        parse_amd_smi_json(DUPLICATE)


def test_unknown_vram_unit_fails() -> None:
    static = json.dumps(
        [
            {
                "gpu": 0,
                "asic": {"market_name": "MI300X-O"},
                "vram": {"type": "HBM", "size": {"value": 16, "unit": "KB"}},
            }
        ]
    )
    listed = json.dumps(
        [
            {
                "gpu": 0,
                "uuid": "afff74a1-0000-1000-8054-e92b0a5d57c8",
                "bdf": "0000:05:00.0",
            }
        ]
    )
    with pytest.raises(ValidationError, match="unit"):
        parse_amd_smi_json(listed, static)


def test_zero_vram_fails_closed() -> None:
    static = json.dumps(
        [
            {
                "gpu": 0,
                "asic": {"market_name": "MI300X-O"},
                "vram": {"type": "HBM", "size": {"value": 0, "unit": "MB"}},
            }
        ]
    )
    listed = json.dumps(
        [
            {
                "gpu": 0,
                "uuid": "afff74a1-0000-1000-8054-e92b0a5d57c8",
                "bdf": "0000:05:00.0",
            }
        ]
    )
    with pytest.raises(ValidationError, match="greater than zero"):
        parse_amd_smi_json(listed, static)


def test_inspect_malformed_is_failed_not_zero() -> None:
    result = AmdAcceleratorProvider(list_json="{not-json").inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED
    assert result.devices == ()
    assert not is_resolved(result.report.device_count)


def test_inspect_empty_is_observed_zero() -> None:
    result = AmdAcceleratorProvider(list_json="[]").inspect()
    assert result.report.status is ProviderInspectionStatus.OBSERVED
    assert result.report.device_count == 0


def test_missing_command_is_unavailable() -> None:
    def missing(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=False, timed_out=False, returncode=None, stdout="", stderr=""
        )

    result = AmdAcceleratorProvider(runner=missing).inspect()
    assert result.report.status is ProviderInspectionStatus.UNAVAILABLE
    assert "not found" in result.report.detail


def test_timeout_is_failed() -> None:
    def timed_out(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=True, timed_out=True, returncode=None, stdout="", stderr=""
        )

    result = AmdAcceleratorProvider(runner=timed_out).inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED
    assert "timed out" in result.report.detail


def test_nonzero_exit_is_failed() -> None:
    def failed(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=True,
            timed_out=False,
            returncode=1,
            stdout="",
            stderr="Permission denied talking to KFD",
        )

    result = AmdAcceleratorProvider(runner=failed).inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED
    assert result.devices == ()


def test_stderr_paths_are_not_leaked() -> None:
    def failed(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=True,
            timed_out=False,
            returncode=127,
            stdout="",
            stderr="/opt/rocm/bin/amd-smi: failed",
        )

    result = AmdAcceleratorProvider(runner=failed).inspect()
    assert "/" not in result.report.detail


def test_applicable_on_linux_only() -> None:
    provider = AmdAcceleratorProvider(list_json="[]")
    linux = normalize_os_architecture("Linux", "x86_64", observed_at=FIXED)
    darwin = normalize_os_architecture("Darwin", "arm64", observed_at=FIXED)
    windows = normalize_os_architecture("Windows", "AMD64", observed_at=FIXED)
    assert provider.applicable(linux) is True
    assert provider.applicable(darwin) is False
    assert provider.applicable(windows) is False


def test_static_failure_keeps_list_devices() -> None:
    def runner(argv: Sequence[str], _timeout: float) -> CommandOutcome:
        if argv[1] == "list":
            return CommandOutcome(
                found=True,
                timed_out=False,
                returncode=0,
                stdout=MI300X_LIST,
                stderr="",
            )
        return CommandOutcome(
            found=True, timed_out=True, returncode=None, stdout="", stderr=""
        )

    result = AmdAcceleratorProvider(runner=runner).inspect()
    assert result.report.status is ProviderInspectionStatus.OBSERVED
    assert result.report.device_count == 1
    assert not is_resolved(result.devices[0].memory_total_bytes)

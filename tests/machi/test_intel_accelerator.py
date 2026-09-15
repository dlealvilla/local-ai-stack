"""Intel accelerator provider (MACHI 2.3)."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence

import pytest

from machi.adapters.discover.command import CommandOutcome
from machi.adapters.discover.intel_accelerator import (
    IntelAcceleratorProvider,
    parse_intel_discovery_json,
)
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

ONE = json.dumps(
    {
        "device_list": [
            {
                "device_id": 0,
                "device_name": "Intel(R) Data Center GPU Max 1550",
                "device_type": "GPU",
                "pci_bdf_address": "0000:4d:00.0",
                "uuid": "01000000-0000-004d-0000-000856c08086",
                "vendor_name": "Intel(R) Corporation",
                "memory_physical_size": 32768.00,
                "max_mem_alloc_size": 4095.99,
                "number_of_tiles": 2,
            }
        ]
    }
)
MULTI = json.dumps(
    {
        "device_list": [
            {
                "device_id": 0,
                "device_name": "Intel(R) Data Center GPU Flex Series 170",
                "device_type": "GPU",
                "uuid": "01000000-0000-004d-0000-000856c08086",
                "memory_physical_size": 16384,
            },
            {
                "device_id": 1,
                "device_name": "Intel(R) Data Center GPU Flex Series 170",
                "device_type": "GPU",
                "uuid": "02000000-0000-004e-0000-000856c08086",
                "memory_physical_size": 16384,
            },
        ]
    }
)
EMPTY = json.dumps({"device_list": []})
MISSING_MEMORY = json.dumps(
    {
        "device_list": [
            {
                "device_id": 0,
                "device_name": "Intel(R) Data Center GPU Max 1550",
                "device_type": "GPU",
                "uuid": "01000000-0000-004d-0000-000856c08086",
                "max_mem_alloc_size": 4095.99,
            }
        ]
    }
)
DUMP_CSV = (
    "0,Intel(R) Data Center GPU Max 1550,"
    "01000000-0000-004d-0000-000856c08086,32768.00\n"
)


def test_discrete_gpu_uses_physical_size_not_alloc_cap() -> None:
    devices = parse_intel_discovery_json(ONE)
    assert len(devices) == 1
    device = devices[0]
    assert device.vendor is AcceleratorVendor.INTEL
    assert device.model_name == "Intel(R) Data Center GPU Max 1550"
    assert device.device_type is AcceleratorDeviceType.DISCRETE_GPU
    assert device.memory_topology is AcceleratorMemoryTopology.DISCRETE
    assert device.memory_total_bytes == 32768 * 1024 * 1024
    assert device.identity == "01000000-0000-004d-0000-000856c08086"
    assert device.source is AcceleratorSource.XPU_SMI
    assert device.raw.find("tiles=2") >= 0


def test_two_tiles_remain_one_device() -> None:
    devices = parse_intel_discovery_json(ONE)
    assert len(devices) == 1
    assert devices[0].ordinal == 0


def test_multi_gpu_is_not_reduced() -> None:
    devices = parse_intel_discovery_json(MULTI)
    assert len(devices) == 2
    assert devices[0].identity != devices[1].identity
    assert devices[0].memory_total_bytes == 16384 * 1024 * 1024


def test_empty_device_list_is_observed_zero() -> None:
    assert parse_intel_discovery_json(EMPTY) == ()
    result = IntelAcceleratorProvider(discovery_json=EMPTY).inspect()
    assert result.report.status is ProviderInspectionStatus.OBSERVED
    assert result.report.device_count == 0


def test_alloc_size_is_not_used_as_total() -> None:
    device = parse_intel_discovery_json(MISSING_MEMORY)[0]
    assert not is_resolved(device.memory_total_bytes)
    assert device.memory_total_status is ObservationStatus.UNOBSERVED


def test_dump_csv_supplies_physical_size() -> None:
    listed = json.dumps(
        {
            "device_list": [
                {
                    "device_id": 0,
                    "device_name": "Intel(R) Data Center GPU Max 1550",
                    "device_type": "GPU",
                    "uuid": "01000000-0000-004d-0000-000856c08086",
                }
            ]
        }
    )
    device = parse_intel_discovery_json(listed, DUMP_CSV)[0]
    assert device.memory_total_bytes == 32768 * 1024 * 1024


def test_missing_uuid_falls_back_to_index() -> None:
    payload = json.dumps(
        {
            "device_list": [
                {
                    "device_id": 4,
                    "device_name": "Intel(R) Data Center GPU Max 1550",
                    "device_type": "GPU",
                    "memory_physical_size": 1024,
                }
            ]
        }
    )
    device = parse_intel_discovery_json(payload)[0]
    assert device.identity == "intel-index-4"


def test_malformed_json_fails() -> None:
    with pytest.raises(ValidationError, match="malformed"):
        parse_intel_discovery_json("{not-json")


def test_duplicate_identity_fails() -> None:
    payload = json.dumps(
        {
            "device_list": [
                {
                    "device_id": 0,
                    "device_name": "Intel(R) Data Center GPU Max 1550",
                    "device_type": "GPU",
                    "uuid": "01000000-0000-004d-0000-000856c08086",
                    "memory_physical_size": 1024,
                },
                {
                    "device_id": 1,
                    "device_name": "Intel(R) Data Center GPU Max 1550",
                    "device_type": "GPU",
                    "uuid": "01000000-0000-004d-0000-000856c08086",
                    "memory_physical_size": 1024,
                },
            ]
        }
    )
    with pytest.raises(ValidationError, match="duplicate"):
        parse_intel_discovery_json(payload)


def test_inspect_malformed_is_failed() -> None:
    result = IntelAcceleratorProvider(discovery_json="{not-json").inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED
    assert result.devices == ()


def test_missing_command_is_unavailable() -> None:
    def missing(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=False, timed_out=False, returncode=None, stdout="", stderr=""
        )

    result = IntelAcceleratorProvider(runner=missing).inspect()
    assert result.report.status is ProviderInspectionStatus.UNAVAILABLE
    assert "not found" in result.report.detail


def test_timeout_is_failed() -> None:
    def timed_out(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=True, timed_out=True, returncode=None, stdout="", stderr=""
        )

    result = IntelAcceleratorProvider(runner=timed_out).inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED


def test_nonzero_exit_is_failed() -> None:
    def failed(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=True,
            timed_out=False,
            returncode=2,
            stdout="",
            stderr="failed to initialize Level Zero",
        )

    result = IntelAcceleratorProvider(runner=failed).inspect()
    assert result.report.status is ProviderInspectionStatus.FAILED


def test_xpumcli_is_used_only_when_xpu_smi_is_missing() -> None:
    seen: list[str] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandOutcome:
        executable = argv[0]
        seen.append(executable)
        if executable == "xpu-smi":
            return CommandOutcome(
                found=False, timed_out=False, returncode=None, stdout="", stderr=""
            )
        if len(argv) >= 3 and argv[1] == "discovery" and argv[2] == "-j":
            return CommandOutcome(
                found=True, timed_out=False, returncode=0, stdout=ONE, stderr=""
            )
        raise AssertionError(argv)

    result = IntelAcceleratorProvider(runner=runner).inspect()
    assert result.report.status is ProviderInspectionStatus.OBSERVED
    assert result.report.device_count == 1
    assert seen[0] == "xpu-smi"
    assert "xpumcli" in seen


def test_does_not_run_xpumcli_when_xpu_smi_exists() -> None:
    seen: list[str] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandOutcome:
        executable = argv[0]
        seen.append(executable)
        if executable == "xpumcli":
            raise AssertionError("xpumcli must not run when xpu-smi exists")
        if len(argv) >= 3 and argv[1] == "discovery" and argv[2] == "-j":
            return CommandOutcome(
                found=True, timed_out=False, returncode=0, stdout=EMPTY, stderr=""
            )
        raise AssertionError(argv)

    result = IntelAcceleratorProvider(runner=runner).inspect()
    assert result.report.status is ProviderInspectionStatus.OBSERVED
    assert result.report.device_count == 0
    assert "xpumcli" not in seen


def test_applicable_on_linux_only() -> None:
    provider = IntelAcceleratorProvider(discovery_json=EMPTY)
    linux = normalize_os_architecture("Linux", "x86_64", observed_at=FIXED)
    darwin = normalize_os_architecture("Darwin", "arm64", observed_at=FIXED)
    windows = normalize_os_architecture("Windows", "AMD64", observed_at=FIXED)
    assert provider.applicable(linux) is True
    assert provider.applicable(darwin) is False
    assert provider.applicable(windows) is False


def test_wrong_field_type_fails() -> None:
    payload = json.dumps(
        {
            "device_list": [
                {
                    "device_id": "zero",
                    "device_name": "Intel(R) Data Center GPU Max 1550",
                    "device_type": "GPU",
                    "uuid": "01000000-0000-004d-0000-000856c08086",
                    "memory_physical_size": 1024,
                }
            ]
        }
    )
    with pytest.raises(ValidationError, match="wrong type"):
        parse_intel_discovery_json(payload)


def test_malformed_dump_does_not_drop_valid_discovery() -> None:
    devices = parse_intel_discovery_json(ONE, "{not-json")
    assert len(devices) == 1
    assert devices[0].memory_total_bytes == 32768 * 1024 * 1024

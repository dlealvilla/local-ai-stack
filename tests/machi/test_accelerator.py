"""Accelerator observer orchestration (MACHI 2.3)."""

from __future__ import annotations

import datetime as dt
import json
import socket
from pathlib import Path

import pytest

from machi.adapters.discover.accelerator_provider import ProviderInspectResult
from machi.adapters.discover.amd_accelerator import AmdAcceleratorProvider
from machi.adapters.discover.apple_accelerator import AppleAcceleratorProvider
from machi.adapters.discover.command import CommandOutcome
from machi.adapters.discover.intel_accelerator import IntelAcceleratorProvider
from machi.adapters.discover.native_accelerator import NativeAcceleratorObserver
from machi.adapters.discover.nvidia_accelerator import NvidiaAcceleratorProvider
from machi.discover.accelerator import (
    non_observed_provider_report,
    observed_provider_report,
)
from machi.discover.contracts import (
    AcceleratorDevice,
    AcceleratorDeviceType,
    AcceleratorMemoryTopology,
    AcceleratorObservation,
    AcceleratorSource,
    AcceleratorVendor,
    ObservationStatus,
    OSArchitectureObservation,
    ProviderInspectionStatus,
)
from machi.discover.events import ACCELERATOR_OBSERVED_TYPE, accelerator_observed
from machi.discover.normalize import normalize_os_architecture
from machi.discover.ports import AcceleratorObserver
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict, unresolved_fields
from machi.kernel.unresolved import is_resolved
from machi.main import main

FIXED = dt.datetime(2026, 9, 15, 15, 0, tzinfo=dt.UTC)

NVIDIA_ONE = (
    "0, GPU-11111111-1111-1111-1111-111111111111, NVIDIA GeForce RTX 4090, 24576\n"
)
NVIDIA_TWO = (
    "0, GPU-aaaaaaa1-1111-1111-1111-111111111111, NVIDIA A100-SXM4-40GB, 40960\n"
    "1, GPU-aaaaaaa2-2222-2222-2222-222222222222, NVIDIA A100-SXM4-80GB, 81920\n"
)
APPLE_M1 = json.dumps(
    {
        "SPDisplaysDataType": [
            {
                "_name": "kHW_AppleM1Item",
                "sppci_bus": "spdisplays_builtin",
                "sppci_device_type": "spdisplays_gpu",
                "sppci_model": "Apple M1",
                "spdisplays_vendor": "sppci_vendor_Apple",
            }
        ]
    }
)


class _FixedOS:
    def __init__(self, raw_os: str, raw_arch: str = "arm64") -> None:
        self._raw_os = raw_os
        self._raw_arch = raw_arch

    def observe(self) -> OSArchitectureObservation:
        return normalize_os_architecture(
            self._raw_os, self._raw_arch, observed_at=FIXED
        )


class _FakeProvider:
    def __init__(
        self,
        provider_id: str,
        *,
        applicable: bool,
        result: ProviderInspectResult,
    ) -> None:
        self.provider_id = provider_id
        self._applicable = applicable
        self._result = result

    def applicable(self, os_observation: OSArchitectureObservation) -> bool:
        del os_observation
        return self._applicable

    def inspect(self) -> ProviderInspectResult:
        return self._result


def _missing_command(_argv: object, _timeout: float) -> CommandOutcome:
    return CommandOutcome(
        found=False, timed_out=False, returncode=None, stdout="", stderr=""
    )


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


def test_native_observer_satisfies_the_port(clock: FixedClock) -> None:
    observer = NativeAcceleratorObserver(clock=clock)
    assert isinstance(observer, AcceleratorObserver)


def test_unified_topology_refuses_fake_dedicated_bytes() -> None:
    with pytest.raises(ValidationError, match="unified accelerator memory"):
        AcceleratorDevice(
            ordinal=0,
            vendor=AcceleratorVendor.APPLE,
            vendor_status=ObservationStatus.NORMALIZED,
            model_name="Apple M1",
            model_status=ObservationStatus.NORMALIZED,
            device_type=AcceleratorDeviceType.INTEGRATED_GPU,
            device_type_status=ObservationStatus.NORMALIZED,
            memory_topology=AcceleratorMemoryTopology.UNIFIED,
            memory_topology_status=ObservationStatus.NORMALIZED,
            memory_total_bytes=8 * 1024 * 1024 * 1024,
            memory_total_status=ObservationStatus.NORMALIZED,
            identity="apple-m1",
            source=AcceleratorSource.APPLE_DISPLAYS,
            raw="sppci_model=Apple M1",
        )


def test_unknown_memory_is_not_zero() -> None:
    with pytest.raises(ValidationError, match="positive integer"):
        AcceleratorDevice(
            ordinal=0,
            vendor=AcceleratorVendor.NVIDIA,
            vendor_status=ObservationStatus.NORMALIZED,
            model_name="NVIDIA GeForce RTX 4090",
            model_status=ObservationStatus.NORMALIZED,
            device_type=AcceleratorDeviceType.DISCRETE_GPU,
            device_type_status=ObservationStatus.NORMALIZED,
            memory_topology=AcceleratorMemoryTopology.DISCRETE,
            memory_topology_status=ObservationStatus.NORMALIZED,
            memory_total_bytes=0,
            memory_total_status=ObservationStatus.NORMALIZED,
            identity="nvidia-index-0",
            source=AcceleratorSource.NVIDIA_SMI,
            raw="index=0;memory.total=0",
        )


def test_no_providers_applicable_is_unobserved_not_zero(
    clock: FixedClock,
) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        providers=(AppleAcceleratorProvider(displays_json=APPLE_M1),),
        clock=clock,
    ).observe()
    assert observed.status is ObservationStatus.UNOBSERVED
    assert observed.devices == ()
    assert observed.providers[0].status is ProviderInspectionStatus.NOT_APPLICABLE
    assert not is_resolved(observed.providers[0].device_count)


def test_empty_successful_nvidia_inspection_is_observed_zero(
    clock: FixedClock,
) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=""),
        amd_provider=AmdAcceleratorProvider(runner=_missing_command),
        intel_provider=IntelAcceleratorProvider(runner=_missing_command),
        apple_provider=AppleAcceleratorProvider(displays_json=APPLE_M1),
        clock=clock,
    ).observe()
    nvidia = next(
        report for report in observed.providers if report.provider == "nvidia"
    )
    apple = next(report for report in observed.providers if report.provider == "apple")
    assert nvidia.status is ProviderInspectionStatus.OBSERVED
    assert nvidia.device_count == 0
    assert apple.status is ProviderInspectionStatus.NOT_APPLICABLE
    assert observed.status is ObservationStatus.NORMALIZED
    assert observed.devices == ()


def test_multi_device_nvidia_is_not_reduced_to_primary(
    clock: FixedClock,
) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_TWO),
        amd_provider=AmdAcceleratorProvider(runner=_missing_command),
        intel_provider=IntelAcceleratorProvider(runner=_missing_command),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    assert len(observed.devices) == 2
    assert [device.ordinal for device in observed.devices] == [0, 1]
    assert observed.devices[0].model_name == "NVIDIA A100-SXM4-40GB"
    assert observed.devices[1].model_name == "NVIDIA A100-SXM4-80GB"
    assert observed.devices[0].memory_total_bytes == 40960 * 1024 * 1024
    assert observed.devices[1].memory_total_bytes == 81920 * 1024 * 1024
    assert (
        observed.devices[0].memory_total_bytes != observed.devices[1].memory_total_bytes
    )


def test_heterogeneous_providers_keep_separate_devices(
    clock: FixedClock,
) -> None:
    nvidia_devices = NvidiaAcceleratorProvider(csv_text=NVIDIA_ONE).inspect().devices
    apple_devices = AppleAcceleratorProvider(displays_json=APPLE_M1).inspect().devices
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Darwin"),
        providers=(
            _FakeProvider(
                "nvidia",
                applicable=True,
                result=ProviderInspectResult(
                    observed_provider_report("nvidia", len(nvidia_devices)),
                    nvidia_devices,
                ),
            ),
            _FakeProvider(
                "apple",
                applicable=True,
                result=ProviderInspectResult(
                    observed_provider_report("apple", len(apple_devices)),
                    apple_devices,
                ),
            ),
        ),
        clock=clock,
    ).observe()
    assert observed.status is ObservationStatus.NORMALIZED
    assert len(observed.devices) == 2
    assert observed.devices[0].vendor is AcceleratorVendor.NVIDIA
    assert observed.devices[1].vendor is AcceleratorVendor.APPLE
    assert observed.devices[0].memory_topology is AcceleratorMemoryTopology.DISCRETE
    assert observed.devices[1].memory_topology is AcceleratorMemoryTopology.UNIFIED
    assert not is_resolved(observed.devices[1].memory_total_bytes)
    assert [device.ordinal for device in observed.devices] == [0, 1]


def test_provider_failure_is_not_swallowed_as_zero_devices(
    clock: FixedClock,
) -> None:
    apple_devices = AppleAcceleratorProvider(displays_json=APPLE_M1).inspect().devices
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Darwin"),
        providers=(
            _FakeProvider(
                "nvidia",
                applicable=True,
                result=ProviderInspectResult(
                    non_observed_provider_report(
                        "nvidia",
                        ProviderInspectionStatus.FAILED,
                        detail="nvidia-smi exited non-zero",
                    )
                ),
            ),
            _FakeProvider(
                "apple",
                applicable=True,
                result=ProviderInspectResult(
                    observed_provider_report("apple", len(apple_devices)),
                    apple_devices,
                ),
            ),
        ),
        clock=clock,
    ).observe()
    nvidia = next(
        report for report in observed.providers if report.provider == "nvidia"
    )
    assert nvidia.status is ProviderInspectionStatus.FAILED
    assert not is_resolved(nvidia.device_count)
    assert len(observed.devices) == 1
    assert observed.devices[0].vendor is AcceleratorVendor.APPLE
    assert observed.status is ObservationStatus.NORMALIZED


def test_amd_and_intel_vendors_and_sources_exist() -> None:
    assert AcceleratorVendor.AMD.value == "amd"
    assert AcceleratorVendor.INTEL.value == "intel"
    assert AcceleratorVendor.NVIDIA.value == "nvidia"
    assert AcceleratorVendor.APPLE.value == "apple"
    assert AcceleratorSource.AMD_SMI.value == "amd_smi"
    assert AcceleratorSource.XPU_SMI.value == "xpu_smi"
    assert AcceleratorSource.NVIDIA_SMI.value == "nvidia_smi"
    assert AcceleratorSource.APPLE_DISPLAYS.value == "apple_displays"


def test_event_is_generic_and_unresolved_host(clock: FixedClock) -> None:
    observation = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_TWO),
        amd_provider=AmdAcceleratorProvider(runner=_missing_command),
        intel_provider=IntelAcceleratorProvider(runner=_missing_command),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    event = accelerator_observed(
        observation,
        install_id=InstallId.generate(),
        install_run_id=InstallRunId.generate(),
    )
    assert event.event_type.value == ACCELERATOR_OBSERVED_TYPE
    assert event.component_id.value == "2.3.1"
    assert event.privacy is PrivacyClass.PUBLIC_OPS
    assert is_resolved(event.install_id)
    assert is_resolved(event.install_run_id)
    assert not is_resolved(event.host_id)
    payload = to_dict(event)["payload"]
    assert payload["kind"] == "discover.accelerator.observed"
    assert len(payload["devices"]) == 2
    blob = json.dumps(to_dict(event))
    assert "hostname" not in blob
    assert "/" not in json.dumps(payload)
    assert "host_id" in unresolved_fields(event)
    assert "install_id" not in unresolved_fields(event)
    assert "install_run_id" not in unresolved_fields(event)


def test_observation_is_not_a_store_entity() -> None:
    assert AcceleratorObservation.kind == "accelerator_observation"


def test_cli_observes_and_correlates_after_m1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "installation-a"
    control = tmp_path / "control-plane"
    assert (
        main(
            [
                "install",
                "establish-run",
                "--state-root",
                str(root),
                "--store-dir",
                str(control),
            ]
        )
        == 0
    )
    first = capsys.readouterr().out
    install_id = next(
        line for line in first.splitlines() if line.startswith("install  ")
    ).split()[1]
    run_id = next(
        line for line in first.splitlines() if line.startswith("run      ")
    ).split()[1]
    assert (
        main(
            [
                "discover",
                "os-arch",
                "--state-root",
                str(root),
                "--store-dir",
                str(control),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "discover",
                "memory",
                "--state-root",
                str(root),
                "--store-dir",
                str(control),
            ]
        )
        == 0
    )
    capsys.readouterr()
    os_arch = next(
        json.loads(line)
        for line in (root / "journal" / "events.jsonl").read_text().splitlines()
        if json.loads(line).get("event_type") == "discover.os_arch.observed"
    )
    memory = next(
        json.loads(line)
        for line in (root / "journal" / "events.jsonl").read_text().splitlines()
        if json.loads(line).get("event_type") == "discover.memory.observed"
    )
    bound = next(
        json.loads(line)
        for line in (root / "journal" / "events.jsonl").read_text().splitlines()
        if json.loads(line).get("event_type") == "install.bound"
    )
    assert (
        main(
            [
                "discover",
                "accelerator",
                "--state-root",
                str(root),
                "--store-dir",
                str(control),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert '"event_type": "discover.accelerator.observed"' in out
    assert '"privacy": "public_ops"' in out
    assert f"install  {install_id}" in out
    assert f"run      {run_id}" in out
    assert "host     unresolved(not_provided)" in out
    assert '"kind": "accelerator_observation"' in out
    assert "primary" not in out.lower()
    event_at = out.find('"kind": "event_record"')
    assert event_at >= 0
    event_blob = out[event_at:]
    assert str(root.resolve()) not in event_blob
    assert str(control.resolve()) not in event_blob
    assert socket.gethostname() not in event_blob
    later = [
        json.loads(line)
        for line in (root / "journal" / "events.jsonl").read_text().splitlines()
    ]
    still_os = next(item for item in later if item["event_id"] == os_arch["event_id"])
    still_memory = next(
        item for item in later if item["event_id"] == memory["event_id"]
    )
    still_bound = next(item for item in later if item["event_id"] == bound["event_id"])
    assert still_os == os_arch
    assert still_memory == memory
    assert still_bound == bound
    discovered = next(
        item
        for item in later
        if item.get("event_type") == "discover.accelerator.observed"
    )
    assert discovered["install_id"] == install_id
    assert discovered["install_run_id"] == run_id
    assert "$unresolved" in json.dumps(discovered["host_id"])
    assert not (control / "accelerator_observation").exists()
    assert not (root / "accelerator_observation").exists()


def test_cli_without_install_context_does_not_mint_host_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    assert main(["discover", "accelerator", "--journal-dir", str(journal)]) == 0
    out = capsys.readouterr().out
    assert "host     unresolved(not_provided)" in out
    assert "install  unresolved(not_provided)" in out
    event = next(
        json.loads(line)
        for line in (journal / "events.jsonl").read_text().splitlines()
        if json.loads(line).get("event_type") == "discover.accelerator.observed"
    )
    assert "$unresolved" in json.dumps(event["host_id"])


AMD_ONE_LIST = json.dumps(
    [
        {
            "gpu": 0,
            "bdf": "0000:05:00.0",
            "uuid": "afff74a1-0000-1000-8054-e92b0a5d57c8",
        }
    ]
)
AMD_ONE_STATIC = json.dumps(
    [
        {
            "gpu": 0,
            "asic": {"market_name": "MI300X-O"},
            "vram": {"type": "HBM", "size": {"value": 196592, "unit": "MB"}},
        }
    ]
)
AMD_TWO_LIST = json.dumps(
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
AMD_TWO_STATIC = json.dumps(
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
INTEL_ONE = json.dumps(
    {
        "device_list": [
            {
                "device_id": 0,
                "device_name": "Intel(R) Data Center GPU Max 1550",
                "device_type": "GPU",
                "uuid": "01000000-0000-004d-0000-000856c08086",
                "memory_physical_size": 32768,
            }
        ]
    }
)
INTEL_TWO = json.dumps(
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
INTEL_EMPTY = json.dumps({"device_list": []})


class _BoomProvider:
    provider_id = "amd"

    def applicable(self, os_observation: OSArchitectureObservation) -> bool:
        del os_observation
        return True

    def inspect(self) -> ProviderInspectResult:
        raise RuntimeError("parser exploded /tmp/secret")


def _statuses(observed: AcceleratorObservation) -> dict[str, str]:
    return {report.provider: report.status.value for report in observed.providers}


def test_case_a_all_linux_providers_and_apple_not_applicable(
    clock: FixedClock,
) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_TWO),
        amd_provider=AmdAcceleratorProvider(
            list_json=AMD_ONE_LIST, static_json=AMD_ONE_STATIC
        ),
        intel_provider=IntelAcceleratorProvider(discovery_json=INTEL_ONE),
        apple_provider=AppleAcceleratorProvider(displays_json=APPLE_M1),
        clock=clock,
    ).observe()
    assert [report.provider for report in observed.providers] == [
        "nvidia",
        "amd",
        "intel",
        "apple",
    ]
    assert _statuses(observed) == {
        "nvidia": "observed",
        "amd": "observed",
        "intel": "observed",
        "apple": "not_applicable",
    }
    assert len(observed.devices) == 4
    assert [device.ordinal for device in observed.devices] == [0, 1, 2, 3]
    vendors = [device.vendor for device in observed.devices]
    assert vendors == [
        AcceleratorVendor.NVIDIA,
        AcceleratorVendor.NVIDIA,
        AcceleratorVendor.AMD,
        AcceleratorVendor.INTEL,
    ]
    totals = [
        device.memory_total_bytes
        for device in observed.devices
        if isinstance(device.memory_total_bytes, int)
    ]
    assert sum(totals) != totals[0]
    blob = json.dumps(to_dict(observed))
    assert "primary" not in blob.lower()


def test_case_b_amd_unavailable_intel_zero(clock: FixedClock) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_ONE),
        amd_provider=AmdAcceleratorProvider(runner=_missing_command),
        intel_provider=IntelAcceleratorProvider(discovery_json=INTEL_EMPTY),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    assert _statuses(observed) == {
        "nvidia": "observed",
        "amd": "unavailable",
        "intel": "observed",
        "apple": "not_applicable",
    }
    assert len(observed.devices) == 1
    intel = next(report for report in observed.providers if report.provider == "intel")
    assert intel.device_count == 0


def test_case_c_nvidia_failed_does_not_erase_amd_intel(clock: FixedClock) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text="0, bad\n"),
        amd_provider=AmdAcceleratorProvider(
            list_json=AMD_ONE_LIST, static_json=AMD_ONE_STATIC
        ),
        intel_provider=IntelAcceleratorProvider(discovery_json=INTEL_ONE),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    assert _statuses(observed)["nvidia"] == "failed"
    assert _statuses(observed)["amd"] == "observed"
    assert _statuses(observed)["intel"] == "observed"
    assert len(observed.devices) == 2
    assert observed.devices[0].vendor is AcceleratorVendor.AMD
    assert observed.devices[1].vendor is AcceleratorVendor.INTEL


def test_case_d_macos_apple_observed_amd_intel_not_applicable(
    clock: FixedClock,
) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Darwin", "arm64"),
        nvidia_provider=NvidiaAcceleratorProvider(runner=_missing_command),
        amd_provider=AmdAcceleratorProvider(
            list_json=AMD_ONE_LIST, static_json=AMD_ONE_STATIC
        ),
        intel_provider=IntelAcceleratorProvider(discovery_json=INTEL_ONE),
        apple_provider=AppleAcceleratorProvider(displays_json=APPLE_M1),
        clock=clock,
    ).observe()
    assert _statuses(observed) == {
        "nvidia": "unavailable",
        "amd": "not_applicable",
        "intel": "not_applicable",
        "apple": "observed",
    }
    assert len(observed.devices) == 1
    assert observed.devices[0].vendor is AcceleratorVendor.APPLE
    assert not is_resolved(observed.devices[0].memory_total_bytes)


def test_case_e_multi_vendor_multi_device_ordinals(clock: FixedClock) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_TWO),
        amd_provider=AmdAcceleratorProvider(
            list_json=AMD_TWO_LIST, static_json=AMD_TWO_STATIC
        ),
        intel_provider=IntelAcceleratorProvider(discovery_json=INTEL_TWO),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    assert len(observed.devices) == 6
    assert [device.ordinal for device in observed.devices] == [0, 1, 2, 3, 4, 5]
    assert [device.source.value for device in observed.devices] == [
        "nvidia_smi",
        "nvidia_smi",
        "amd_smi",
        "amd_smi",
        "xpu_smi",
        "xpu_smi",
    ]
    nvidia_bytes = observed.devices[0].memory_total_bytes
    amd_bytes = observed.devices[2].memory_total_bytes
    intel_bytes = observed.devices[4].memory_total_bytes
    assert nvidia_bytes != amd_bytes
    assert amd_bytes != intel_bytes


def test_provider_exception_is_isolated(clock: FixedClock) -> None:
    nvidia_devices = NvidiaAcceleratorProvider(csv_text=NVIDIA_TWO).inspect().devices
    intel_devices = IntelAcceleratorProvider(discovery_json=INTEL_ONE).inspect().devices
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        providers=(
            _FakeProvider(
                "nvidia",
                applicable=True,
                result=ProviderInspectResult(
                    observed_provider_report("nvidia", len(nvidia_devices)),
                    nvidia_devices,
                ),
            ),
            _BoomProvider(),
            _FakeProvider(
                "intel",
                applicable=True,
                result=ProviderInspectResult(
                    observed_provider_report("intel", len(intel_devices)),
                    intel_devices,
                ),
            ),
            _FakeProvider(
                "apple",
                applicable=False,
                result=ProviderInspectResult(
                    non_observed_provider_report(
                        "apple", ProviderInspectionStatus.NOT_APPLICABLE
                    )
                ),
            ),
        ),
        clock=clock,
    ).observe()
    assert _statuses(observed)["nvidia"] == "observed"
    assert _statuses(observed)["amd"] == "failed"
    assert _statuses(observed)["intel"] == "observed"
    assert _statuses(observed)["apple"] == "not_applicable"
    assert len(observed.devices) == 3
    amd = next(report for report in observed.providers if report.provider == "amd")
    assert "/" not in amd.detail
    assert "\\" not in amd.detail


def test_four_provider_event_stays_generic(clock: FixedClock) -> None:
    observation = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_ONE),
        amd_provider=AmdAcceleratorProvider(
            list_json=AMD_ONE_LIST, static_json=AMD_ONE_STATIC
        ),
        intel_provider=IntelAcceleratorProvider(discovery_json=INTEL_ONE),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    event = accelerator_observed(
        observation,
        install_id=InstallId.generate(),
        install_run_id=InstallRunId.generate(),
    )
    payload = to_dict(event)["payload"]
    assert payload["kind"] == "discover.accelerator.observed"
    assert event.component_id.value == "2.3.1"
    providers = [item["provider"] for item in payload["providers"]]
    assert providers == ["nvidia", "amd", "intel", "apple"]
    blob = json.dumps(to_dict(event))
    assert "hostname" not in blob
    assert "/" not in json.dumps(payload)

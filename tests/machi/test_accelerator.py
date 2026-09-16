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
        amd_provider=AmdAcceleratorProvider(list_json="[]"),
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
        amd_provider=AmdAcceleratorProvider(list_json="[]"),
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


def test_amd_vendor_is_implemented_and_intel_remains_vocabulary() -> None:
    assert AcceleratorVendor.AMD.value == "amd"
    assert AcceleratorVendor.INTEL.value == "intel"
    assert AcceleratorSource.AMD_SMI.value == "amd_smi"
    observer = NativeAcceleratorObserver(clock=FixedClock(FIXED))
    assert [provider.provider_id for provider in observer._providers] == [
        "nvidia",
        "amd",
        "apple",
    ]
    assert "intel" not in {provider.provider_id for provider in observer._providers}


def test_event_is_generic_and_unresolved_host(clock: FixedClock) -> None:
    observation = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_TWO),
        amd_provider=AmdAcceleratorProvider(list_json="[]"),
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


def test_linux_nvidia_only_keeps_amd_unavailable_or_zero(clock: FixedClock) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_ONE),
        amd_provider=AmdAcceleratorProvider(list_json="[]"),
        apple_provider=AppleAcceleratorProvider(displays_json=APPLE_M1),
        clock=clock,
    ).observe()
    by_id = {report.provider: report for report in observed.providers}
    assert by_id["nvidia"].status is ProviderInspectionStatus.OBSERVED
    assert by_id["nvidia"].device_count == 1
    assert by_id["amd"].status is ProviderInspectionStatus.OBSERVED
    assert by_id["amd"].device_count == 0
    assert by_id["apple"].status is ProviderInspectionStatus.NOT_APPLICABLE
    assert [device.vendor for device in observed.devices] == [AcceleratorVendor.NVIDIA]


def test_linux_amd_only_keeps_nvidia_unavailable(clock: FixedClock) -> None:
    def missing(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=False, timed_out=False, returncode=None, stdout="", stderr=""
        )

    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(runner=missing),
        amd_provider=AmdAcceleratorProvider(
            list_json=AMD_ONE_LIST, static_json=AMD_ONE_STATIC
        ),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    by_id = {report.provider: report for report in observed.providers}
    assert by_id["nvidia"].status is ProviderInspectionStatus.UNAVAILABLE
    assert by_id["amd"].status is ProviderInspectionStatus.OBSERVED
    assert by_id["amd"].device_count == 1
    assert by_id["apple"].status is ProviderInspectionStatus.NOT_APPLICABLE
    assert [device.vendor for device in observed.devices] == [AcceleratorVendor.AMD]
    assert observed.devices[0].ordinal == 0


def test_linux_nvidia_and_amd_keep_both_devices_in_provider_order(
    clock: FixedClock,
) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_ONE),
        amd_provider=AmdAcceleratorProvider(
            list_json=AMD_ONE_LIST, static_json=AMD_ONE_STATIC
        ),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    assert [device.vendor for device in observed.devices] == [
        AcceleratorVendor.NVIDIA,
        AcceleratorVendor.AMD,
    ]
    assert [device.ordinal for device in observed.devices] == [0, 1]
    assert observed.devices[0].identity.startswith("GPU-")
    assert observed.devices[1].identity == "afff74a1-0000-1000-8054-e92b0a5d57c8"


def test_amd_failure_does_not_destroy_nvidia(clock: FixedClock) -> None:
    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(csv_text=NVIDIA_ONE),
        amd_provider=AmdAcceleratorProvider(list_json="{not-json"),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    by_id = {report.provider: report for report in observed.providers}
    assert by_id["nvidia"].status is ProviderInspectionStatus.OBSERVED
    assert by_id["nvidia"].device_count == 1
    assert by_id["amd"].status is ProviderInspectionStatus.FAILED
    assert by_id["apple"].status is ProviderInspectionStatus.NOT_APPLICABLE
    assert len(observed.devices) == 1
    assert observed.devices[0].vendor is AcceleratorVendor.NVIDIA


def test_nvidia_failure_does_not_destroy_amd(clock: FixedClock) -> None:
    def failed(_argv: object, _timeout: float) -> CommandOutcome:
        return CommandOutcome(
            found=True,
            timed_out=False,
            returncode=1,
            stdout="",
            stderr="nvidia-smi failed",
        )

    observed = NativeAcceleratorObserver(
        os_observer=_FixedOS("Linux", "x86_64"),
        nvidia_provider=NvidiaAcceleratorProvider(runner=failed),
        amd_provider=AmdAcceleratorProvider(
            list_json=AMD_ONE_LIST, static_json=AMD_ONE_STATIC
        ),
        apple_provider=AppleAcceleratorProvider(),
        clock=clock,
    ).observe()
    by_id = {report.provider: report for report in observed.providers}
    assert by_id["nvidia"].status is ProviderInspectionStatus.FAILED
    assert by_id["amd"].status is ProviderInspectionStatus.OBSERVED
    assert by_id["amd"].device_count == 1
    assert len(observed.devices) == 1
    assert observed.devices[0].vendor is AcceleratorVendor.AMD


class _ExplodingProvider:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id

    def applicable(self, os_observation: OSArchitectureObservation) -> bool:
        del os_observation
        return True

    def inspect(self) -> ProviderInspectResult:
        raise RuntimeError("provider inspect exploded")


def test_unexpected_provider_exception_is_isolated(clock: FixedClock) -> None:
    nvidia_devices = NvidiaAcceleratorProvider(csv_text=NVIDIA_ONE).inspect().devices
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
            _ExplodingProvider("amd"),
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
    by_id = {report.provider: report for report in observed.providers}
    assert by_id["nvidia"].status is ProviderInspectionStatus.OBSERVED
    assert by_id["amd"].status is ProviderInspectionStatus.FAILED
    assert "exploded" in by_id["amd"].detail
    assert by_id["apple"].status is ProviderInspectionStatus.NOT_APPLICABLE
    assert len(observed.devices) == 1
    assert observed.devices[0].vendor is AcceleratorVendor.NVIDIA


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

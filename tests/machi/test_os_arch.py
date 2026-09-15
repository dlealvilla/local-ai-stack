"""OS/architecture observer (MACHI 2.1.1)."""

from __future__ import annotations

import datetime as dt
import json
import platform
import socket
from pathlib import Path

import pytest

from machi.adapters.discover.native_os_arch import NativeOSArchitectureObserver
from machi.discover.contracts import (
    CpuArchitecture,
    ObservationStatus,
    OSFamily,
)
from machi.discover.events import OS_ARCH_OBSERVED_TYPE, os_arch_observed
from machi.discover.normalize import normalize_os_architecture
from machi.discover.ports import OSArchitectureObserver
from machi.kernel.clock import FixedClock
from machi.kernel.errors import InternalError, ValidationError
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict, unresolved_fields
from machi.kernel.unresolved import UnresolvedReason, is_resolved
from machi.main import main

FIXED = dt.datetime(2026, 9, 15, 3, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


def test_native_observer_satisfies_the_port(clock: FixedClock) -> None:
    observer = NativeOSArchitectureObserver(clock=clock)
    assert isinstance(observer, OSArchitectureObserver)


def test_native_adapter_observes_the_current_host(clock: FixedClock) -> None:
    observed = NativeOSArchitectureObserver(clock=clock).observe()
    expected = normalize_os_architecture(
        platform.system(),
        platform.machine(),
        observed_at=FIXED,
    )
    assert observed.raw_os == platform.system()
    assert observed.raw_architecture == platform.machine()
    assert observed.os_family == expected.os_family
    assert observed.architecture == expected.architecture
    assert observed.os_status == expected.os_status
    assert observed.architecture_status == expected.architecture_status
    assert observed.observer == "native"
    assert observed.observed_at == FIXED


def test_repeated_native_observation_is_semantically_stable() -> None:
    first = NativeOSArchitectureObserver().observe()
    second = NativeOSArchitectureObserver().observe()
    assert first.os_family == second.os_family
    assert first.architecture == second.architecture
    assert first.raw_os == second.raw_os
    assert first.raw_architecture == second.raw_architecture
    assert first.os_status == second.os_status
    assert first.architecture_status == second.architecture_status


@pytest.mark.parametrize(
    ("raw_os", "raw_arch", "os_family", "architecture"),
    [
        ("Linux", "x86_64", OSFamily.LINUX, CpuArchitecture.X86_64),
        ("linux", "AMD64", OSFamily.LINUX, CpuArchitecture.X86_64),
        ("Windows", "AMD64", OSFamily.WINDOWS, CpuArchitecture.X86_64),
        ("WINDOWS", "x64", OSFamily.WINDOWS, CpuArchitecture.X86_64),
        ("win32", "amd64", OSFamily.WINDOWS, CpuArchitecture.X86_64),
        ("Darwin", "arm64", OSFamily.MACOS, CpuArchitecture.ARM64),
        ("macOS", "aarch64", OSFamily.MACOS, CpuArchitecture.ARM64),
        ("Linux", "aarch64", OSFamily.LINUX, CpuArchitecture.ARM64),
        ("Linux", "ARM64", OSFamily.LINUX, CpuArchitecture.ARM64),
    ],
)
def test_common_aliases_normalize(
    raw_os: str,
    raw_arch: str,
    os_family: OSFamily,
    architecture: CpuArchitecture,
    clock: FixedClock,
) -> None:
    observed = normalize_os_architecture(
        raw_os, raw_arch, observed_at=FIXED, clock=clock
    )
    assert observed.os_family is os_family
    assert observed.architecture is architecture
    assert observed.os_status is ObservationStatus.NORMALIZED
    assert observed.architecture_status is ObservationStatus.NORMALIZED
    assert observed.raw_os == raw_os
    assert observed.raw_architecture == raw_arch


def test_unknown_os_is_not_defaulted(clock: FixedClock) -> None:
    observed = normalize_os_architecture("Solaris", "x86_64", clock=clock)
    assert not is_resolved(observed.os_family)
    assert observed.os_status is ObservationStatus.UNRECOGNIZED
    assert observed.os_family.reason is UnresolvedReason.UNSUPPORTED  # type: ignore[union-attr]
    assert observed.raw_os == "Solaris"
    assert observed.architecture is CpuArchitecture.X86_64
    assert observed.os_family is not OSFamily.LINUX


def test_unknown_architecture_is_not_defaulted(clock: FixedClock) -> None:
    observed = normalize_os_architecture("Linux", "riscv64", clock=clock)
    assert observed.os_family is OSFamily.LINUX
    assert not is_resolved(observed.architecture)
    assert observed.architecture_status is ObservationStatus.UNRECOGNIZED
    assert observed.architecture.reason is UnresolvedReason.UNSUPPORTED  # type: ignore[union-attr]
    assert observed.raw_architecture == "riscv64"
    assert observed.architecture is not CpuArchitecture.X86_64
    assert observed.architecture is not CpuArchitecture.ARM64


def test_empty_raw_values_are_unobserved_not_normalized(clock: FixedClock) -> None:
    observed = normalize_os_architecture("", "", clock=clock)
    assert observed.os_status is ObservationStatus.UNOBSERVED
    assert observed.architecture_status is ObservationStatus.UNOBSERVED
    assert not is_resolved(observed.os_family)
    assert not is_resolved(observed.architecture)
    assert observed.os_family.reason is UnresolvedReason.NOT_MEASURED  # type: ignore[union-attr]
    assert observed.raw_os == ""
    assert observed.raw_architecture == ""


def test_event_is_public_ops_and_keeps_host_unresolved(clock: FixedClock) -> None:
    observed = normalize_os_architecture("Linux", "x86_64", clock=clock)
    event = os_arch_observed(
        observed,
        install_id=InstallId.generate(),
        install_run_id=InstallRunId.generate(),
    )
    assert event.event_type.value == OS_ARCH_OBSERVED_TYPE
    assert event.component_id.value == "2.1.1"
    assert event.privacy is PrivacyClass.PUBLIC_OPS
    assert is_resolved(event.install_id)
    assert is_resolved(event.install_run_id)
    assert "host_id" in unresolved_fields(event)
    blob = json.dumps(to_dict(event))
    assert socket.gethostname() not in blob
    assert "prompt" not in blob
    assert "/" not in observed.raw_os


def test_event_without_install_context_leaves_install_unresolved(
    clock: FixedClock,
) -> None:
    observed = normalize_os_architecture("Darwin", "arm64", clock=clock)
    event = os_arch_observed(observed)
    assert "install_id" in unresolved_fields(event)
    assert "install_run_id" in unresolved_fields(event)
    assert "host_id" in unresolved_fields(event)


def test_native_platform_failure_is_typed(
    monkeypatch: pytest.MonkeyPatch, clock: FixedClock
) -> None:
    def boom() -> str:
        raise OSError("platform unavailable")

    monkeypatch.setattr(platform, "system", boom)
    with pytest.raises(InternalError, match="failed to observe"):
        NativeOSArchitectureObserver(clock=clock).observe()


def test_native_non_string_platform_value_fails_closed(
    monkeypatch: pytest.MonkeyPatch, clock: FixedClock
) -> None:
    monkeypatch.setattr(platform, "system", lambda: 12)
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    with pytest.raises(ValidationError, match="did not return strings"):
        NativeOSArchitectureObserver(clock=clock).observe()


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
    bound = next(
        json.loads(line)
        for line in (root / "journal" / "events.jsonl").read_text().splitlines()
        if json.loads(line).get("event_type") == "install.bound"
    )
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
    out = capsys.readouterr().out
    assert '"event_type": "discover.os_arch.observed"' in out
    assert '"privacy": "public_ops"' in out
    assert f"install  {install_id}" in out
    assert f"run      {run_id}" in out
    assert "host     unresolved(not_provided)" in out
    assert '"kind": "os_architecture_observation"' in out
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
    still_bound = next(item for item in later if item["event_id"] == bound["event_id"])
    assert still_bound == bound
    discovered = next(
        item for item in later if item.get("event_type") == "discover.os_arch.observed"
    )
    assert discovered["install_id"] == install_id
    assert discovered["install_run_id"] == run_id
    assert "$unresolved" in json.dumps(discovered["host_id"])
    assert not (control / "os_architecture_observation").exists()
    assert not (root / "os_architecture_observation").exists()


def test_cli_without_install_context_does_not_mint_host_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    assert main(["discover", "os-arch", "--journal-dir", str(journal)]) == 0
    out = capsys.readouterr().out
    assert "install  unresolved(not_provided)" in out
    assert "run      unresolved(not_provided)" in out
    assert "host     unresolved(not_provided)" in out
    assert '"privacy": "public_ops"' in out
    rows = [
        json.loads(line)
        for line in (journal / "events.jsonl").read_text().splitlines()
        if line
    ]
    assert len(rows) == 1
    assert rows[0]["event_type"] == "discover.os_arch.observed"


def test_cli_repeat_normalizes_the_same_facts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["discover", "os-arch"]) == 0
    first = capsys.readouterr().out
    assert main(["discover", "os-arch"]) == 0
    second = capsys.readouterr().out
    first_os = next(line for line in first.splitlines() if line.startswith("os       "))
    second_os = next(
        line for line in second.splitlines() if line.startswith("os       ")
    )
    first_arch = next(
        line for line in first.splitlines() if line.startswith("arch     ")
    )
    second_arch = next(
        line for line in second.splitlines() if line.startswith("arch     ")
    )
    assert first_os == second_os
    assert first_arch == second_arch

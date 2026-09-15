"""Memory observer (MACHI 2.2.1)."""

from __future__ import annotations

import datetime as dt
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from machi.adapters.discover.linux_proc_memory import (
    LinuxProcMemoryProvider,
    parse_linux_memory_table,
)
from machi.adapters.discover.macos_sysconf_memory import (
    physical_total_from_page_counts,
)
from machi.adapters.discover.native_memory import NativeMemoryObserver
from machi.discover.contracts import (
    MemoryObservation,
    MemorySource,
    ObservationStatus,
    OSArchitectureObservation,
)
from machi.discover.events import MEMORY_OBSERVED_TYPE, memory_observed
from machi.discover.normalize import normalize_os_architecture
from machi.discover.ports import MemoryObserver
from machi.kernel.clock import FixedClock
from machi.kernel.errors import InternalError, ValidationError
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict, unresolved_fields
from machi.kernel.unresolved import UnresolvedReason, is_resolved
from machi.main import main

FIXED = dt.datetime(2026, 9, 15, 4, 0, tzinfo=dt.UTC)
LINUX_TABLE = (
    "MemTotal:       16384000 kB\n"
    "MemFree:         4096000 kB\n"
    "MemAvailable:    8192000 kB\n"
    "SwapTotal:             0 kB\n"
)


class _FixedOS:
    def __init__(self, raw_os: str, raw_arch: str = "x86_64") -> None:
        self._raw_os = raw_os
        self._raw_arch = raw_arch

    def observe(self) -> OSArchitectureObservation:
        return normalize_os_architecture(
            self._raw_os, self._raw_arch, observed_at=FIXED
        )


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


def test_native_observer_satisfies_the_port(clock: FixedClock) -> None:
    observer = NativeMemoryObserver(clock=clock)
    assert isinstance(observer, MemoryObserver)


def test_native_adapter_observes_the_current_host(clock: FixedClock) -> None:
    observed = NativeMemoryObserver(clock=clock).observe()
    assert observed.observer == "native"
    assert observed.observed_at == FIXED
    assert is_resolved(observed.physical_total_bytes)
    assert isinstance(observed.physical_total_bytes, int)
    assert observed.physical_total_bytes > 0
    assert observed.physical_total_status is ObservationStatus.NORMALIZED
    assert "/" not in observed.raw_total
    host = __import__("platform").system()
    if host == "Darwin":
        assert observed.source is MemorySource.SYSCONF
        assert "SC_PHYS_PAGES=" in observed.raw_total
        independent = int(
            subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        )
        assert observed.physical_total_bytes == independent
        assert observed.physical_total_bytes == os.sysconf(
            "SC_PHYS_PAGES"
        ) * os.sysconf("SC_PAGE_SIZE")
        return
    if host == "Linux":
        assert observed.source is MemorySource.LINUX_PROC
        table = Path("/proc/meminfo").read_text(encoding="utf-8")
        expected, _raw = parse_linux_memory_table(table)
        assert observed.physical_total_bytes == expected
        return
    pytest.fail(f"native memory test has no harness truth for {host}")


def test_repeated_native_observation_is_semantically_stable() -> None:
    first = NativeMemoryObserver().observe()
    second = NativeMemoryObserver().observe()
    assert first.physical_total_bytes == second.physical_total_bytes
    assert first.physical_total_status == second.physical_total_status
    assert first.source == second.source
    assert first.observer == second.observer
    assert first.raw_total == second.raw_total


def test_linux_memtotal_converts_kib_to_bytes(clock: FixedClock) -> None:
    total, raw = parse_linux_memory_table(LINUX_TABLE)
    assert total == 16384000 * 1024
    assert raw == "MemTotal: 16384000 kB"
    observed = NativeMemoryObserver(
        os_observer=_FixedOS("Linux"),
        linux_memory_text=LINUX_TABLE,
        clock=clock,
    ).observe()
    assert observed.physical_total_bytes == total
    assert observed.source is MemorySource.LINUX_PROC
    assert observed.physical_total_status is ObservationStatus.NORMALIZED
    assert observed.raw_total == raw


def test_linux_provider_is_callable_without_the_orchestrator(clock: FixedClock) -> None:
    observed = LinuxProcMemoryProvider(
        memory_text=LINUX_TABLE,
        clock=clock,
    ).observe(FIXED)
    assert observed.physical_total_bytes == 16384000 * 1024
    assert observed.source is MemorySource.LINUX_PROC
    assert observed.observer == "native"


def test_linux_one_kib_is_1024_bytes() -> None:
    total, raw = parse_linux_memory_table("MemTotal: 1 kB\n")
    assert total == 1024
    assert raw == "MemTotal: 1 kB"


def test_linux_missing_memtotal_fails() -> None:
    with pytest.raises(ValidationError, match="MemTotal is missing"):
        parse_linux_memory_table("MemAvailable: 100 kB\n")


def test_linux_malformed_memtotal_fails() -> None:
    with pytest.raises(ValidationError, match="not an integer"):
        parse_linux_memory_table("MemTotal: twelve kB\n")


def test_linux_unknown_unit_fails() -> None:
    with pytest.raises(ValidationError, match="unit is not kB"):
        parse_linux_memory_table("MemTotal: 16384000 MB\n")


def test_linux_zero_memtotal_fails() -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        parse_linux_memory_table("MemTotal: 0 kB\n")


def test_linux_missing_file_is_unobserved(tmp_path: Path, clock: FixedClock) -> None:
    observed = NativeMemoryObserver(
        os_observer=_FixedOS("Linux"),
        linux_memory_path=tmp_path / "absent",
        clock=clock,
    ).observe()
    assert observed.physical_total_status is ObservationStatus.UNOBSERVED
    assert observed.source is MemorySource.UNOBSERVED
    assert not is_resolved(observed.physical_total_bytes)
    assert observed.physical_total_bytes.reason is UnresolvedReason.NOT_MEASURED  # type: ignore[union-attr]
    assert observed.raw_total == ""


def test_macos_sysconf_seam(clock: FixedClock) -> None:
    def sysconf(name: str) -> int:
        return {"SC_PHYS_PAGES": 2, "SC_PAGE_SIZE": 4096}[name]

    observed = NativeMemoryObserver(
        os_observer=_FixedOS("Darwin", "arm64"),
        sysconf=sysconf,
        clock=clock,
    ).observe()
    assert observed.physical_total_bytes == 8192
    assert observed.source is MemorySource.SYSCONF
    assert observed.raw_total == "SC_PHYS_PAGES=2;SC_PAGE_SIZE=4096"


def test_sysconf_rejects_non_positive_pages() -> None:
    with pytest.raises(ValidationError, match="not positive"):
        physical_total_from_page_counts(0, 4096)


def test_windows_is_unsupported_not_zero(clock: FixedClock) -> None:
    observed = NativeMemoryObserver(
        os_observer=_FixedOS("Windows", "AMD64"),
        clock=clock,
    ).observe()
    assert observed.physical_total_status is ObservationStatus.UNOBSERVED
    assert observed.source is MemorySource.UNSUPPORTED
    assert not is_resolved(observed.physical_total_bytes)
    assert observed.physical_total_bytes.reason is UnresolvedReason.UNSUPPORTED  # type: ignore[union-attr]
    assert observed.physical_total_bytes != 0
    assert observed.raw_total == ""


def test_unknown_os_is_unsupported_not_linux_fallback(clock: FixedClock) -> None:
    observed = NativeMemoryObserver(
        os_observer=_FixedOS("Solaris"),
        linux_memory_text=LINUX_TABLE,
        clock=clock,
    ).observe()
    assert observed.source is MemorySource.UNSUPPORTED
    assert not is_resolved(observed.physical_total_bytes)


def test_event_is_public_ops_and_keeps_host_unresolved(clock: FixedClock) -> None:
    observed = NativeMemoryObserver(
        os_observer=_FixedOS("Linux"),
        linux_memory_text=LINUX_TABLE,
        clock=clock,
    ).observe()
    event = memory_observed(
        observed,
        install_id=InstallId.generate(),
        install_run_id=InstallRunId.generate(),
    )
    assert event.event_type.value == MEMORY_OBSERVED_TYPE
    assert event.component_id.value == "2.2.1"
    assert event.privacy is PrivacyClass.PUBLIC_OPS
    assert is_resolved(event.install_id)
    assert is_resolved(event.install_run_id)
    assert "host_id" in unresolved_fields(event)
    blob = json.dumps(to_dict(event))
    assert socket.gethostname() not in blob
    assert "/proc/" not in blob
    assert "safe_" not in blob
    assert "prompt" not in blob


def test_event_without_install_context_leaves_install_unresolved(
    clock: FixedClock,
) -> None:
    observed = NativeMemoryObserver(clock=clock).observe()
    event = memory_observed(observed)
    assert "install_id" in unresolved_fields(event)
    assert "install_run_id" in unresolved_fields(event)
    assert "host_id" in unresolved_fields(event)


def test_sysconf_failure_is_typed(clock: FixedClock) -> None:
    def boom(_name: str) -> int:
        raise OSError("sysconf unavailable")

    with pytest.raises(InternalError, match="failed to observe"):
        NativeMemoryObserver(
            os_observer=_FixedOS("Darwin"),
            sysconf=boom,
            clock=clock,
        ).observe()


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
    os_arch = next(
        json.loads(line)
        for line in (root / "journal" / "events.jsonl").read_text().splitlines()
        if json.loads(line).get("event_type") == "discover.os_arch.observed"
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
                "memory",
                "--state-root",
                str(root),
                "--store-dir",
                str(control),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert '"event_type": "discover.memory.observed"' in out
    assert '"privacy": "public_ops"' in out
    assert f"install  {install_id}" in out
    assert f"run      {run_id}" in out
    assert "host     unresolved(not_provided)" in out
    assert '"kind": "memory_observation"' in out
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
    still_bound = next(item for item in later if item["event_id"] == bound["event_id"])
    assert still_os == os_arch
    assert still_bound == bound
    discovered = next(
        item for item in later if item.get("event_type") == "discover.memory.observed"
    )
    assert discovered["install_id"] == install_id
    assert discovered["install_run_id"] == run_id
    assert "$unresolved" in json.dumps(discovered["host_id"])
    assert not (control / "memory_observation").exists()
    assert not (root / "memory_observation").exists()


def test_cli_without_install_context_does_not_mint_host_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    assert main(["discover", "memory", "--journal-dir", str(journal)]) == 0
    out = capsys.readouterr().out
    assert "host     unresolved(not_provided)" in out
    assert "install  unresolved(not_provided)" in out
    event = next(
        json.loads(line)
        for line in (journal / "events.jsonl").read_text().splitlines()
        if json.loads(line).get("event_type") == "discover.memory.observed"
    )
    assert "$unresolved" in json.dumps(event["host_id"])


def test_cli_repeat_keeps_total_stable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["discover", "memory"]) == 0
    first = capsys.readouterr().out
    assert main(["discover", "memory"]) == 0
    second = capsys.readouterr().out
    total_one = next(
        line for line in first.splitlines() if line.startswith("total    ")
    )
    total_two = next(
        line for line in second.splitlines() if line.startswith("total    ")
    )
    assert total_one == total_two
    status_one = next(
        line for line in first.splitlines() if line.startswith("status   ")
    )
    status_two = next(
        line for line in second.splitlines() if line.startswith("status   ")
    )
    assert status_one == status_two


def test_observation_is_immutable(clock: FixedClock) -> None:
    observed = NativeMemoryObserver(clock=clock).observe()
    assert isinstance(observed, MemoryObservation)
    with pytest.raises(AttributeError):
        observed.physical_total_bytes = 1  # type: ignore[misc]

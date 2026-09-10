"""Probe registry: compatible probes run; none is explicit."""

from __future__ import annotations

from kultrun.adapters.storage.fuse_identify import FuseIdentifyProbe
from kultrun.adapters.storage.macos import MacosCapacityProbe
from kultrun.adapters.storage.moosefs import MooseFSQuotaProbe
from kultrun.adapters.storage.windows import WindowsCapacityProbe
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.storage.ports import (
    CapacityProbeResult,
    StorageEnvironment,
)
from kultrun.storage.probes import ProbeRegistry


class _Always:
    name = "always"
    technology = "test"

    def supports(self, environment: StorageEnvironment) -> bool:
        return True

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        del environment
        return CapacityProbeResult(
            available_bytes=123,
            executed=True,
            available=True,
            detail="ran",
        )


class _Never:
    name = "never"
    technology = "other"

    def supports(self, environment: StorageEnvironment) -> bool:
        return False

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        raise AssertionError("incompatible probe must not run")


def _env(
    *,
    os_name: str = "linux",
    architecture: str = "x86_64",
    mount_point: str = "/workspace",
    filesystem_type: Maybe[str] = "fuse",
    device: Maybe[str] = "mfs#x",
) -> StorageEnvironment:
    return StorageEnvironment(
        os_name=os_name,
        architecture=architecture,
        mount_point=mount_point,
        filesystem_type=filesystem_type,
        device=device,
    )


def test_compatible_probe_is_always_run() -> None:
    registry = ProbeRegistry((_Never(), _Always()))
    reports = registry.run(_env())
    assert len(reports) == 1
    assert reports[0].executed is True
    assert reports[0].available_bytes == 123


def test_no_compatible_probe_is_explicit() -> None:
    reports = ProbeRegistry((_Never(),)).run(_env())
    assert reports[0].probe_name == "none"
    assert reports[0].compatible is False
    assert reports[0].executed is False


def test_fuse_and_moosefs_match_fuse_mfs() -> None:
    env = _env(filesystem_type="fuse", device="mfs#host:9421")
    assert FuseIdentifyProbe().supports(env)
    assert MooseFSQuotaProbe().supports(env)
    moose = MooseFSQuotaProbe().probe(env)
    assert moose.executed is False
    assert moose.available is False


def test_windows_and_macos_contracts() -> None:
    win = WindowsCapacityProbe()
    mac = MacosCapacityProbe()
    assert win.supports(_env(os_name="windows", filesystem_type="ntfs"))
    assert mac.supports(_env(os_name="darwin", filesystem_type="apfs"))
    assert win.probe(_env(os_name="windows")).executed is False
    assert mac.probe(_env(os_name="darwin")).executed is False
    assert not FuseIdentifyProbe().supports(
        _env(os_name="windows", filesystem_type="ntfs", device=NOT_PROVIDED)
    )

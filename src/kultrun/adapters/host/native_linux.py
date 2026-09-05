"""Native Linux facts that no topology or vendor tool reports.

**Why it exists.** The Stage 1.1 spike found hwloc reports no
operating-system release and no filesystem mounts, and the vendor interface
reports only its own devices. Stage 1.2 needs mount identity with sizes, and
the deployment profile needs the distribution. Nothing mature fills that gap
that a few lines of standard-library reading would not do better, so this is
the one place Kultrun reads the operating system directly.

That is not the commodity enumeration Part IX forbids building. It is
reading `/etc/os-release`, `/proc/meminfo` and the mount table through
`os.statvfs` — documented interfaces with no library worth a dependency.

**On the storage it reports.** These are *reported* values and may not
authorize anything. The reference host mounts a network filesystem
advertising 2.15 PB with 560 TB free; the previous attempt met the same
shape as "239 TB free" and correctly refused a 6.70 GiB install for want of
verified evidence. Interpretation is Stage 1.2's and credibility is
Milestone 2's.

Single-file bind mounts are filtered out. A container image binds individual
files such as `/etc/hosts` from the host's disks, and reporting those as
storage pools would invent capacity out of plumbing.
"""

from __future__ import annotations

import os
import platform
import socket
from pathlib import Path
from typing import Final

from kultrun.evidence.contracts import Confidence, Derivation
from kultrun.host.contracts import Observation, ProviderReport, ProviderStatus
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED

PROVIDER: Final = Name("native-linux")

#: Pseudo-filesystems that describe kernel interfaces rather than storage.
_IGNORED_TYPES: Final = frozenset(
    {
        "proc", "sysfs", "devpts", "cgroup", "cgroup2", "devtmpfs", "mqueue",
        "debugfs", "tracefs", "securityfs", "pstore", "bpf", "configfs",
        "fusectl", "hugetlbfs", "autofs", "binfmt_misc", "rpc_pipefs",
        "nsfs", "ramfs", "efivarfs",
    }
)

#: Mount points beneath these are kernel interfaces, runtime state or
#: container plumbing rather than places data can be kept.
#:
#: Measured, not assumed. The reference host mounts a tmpfs at
#: `/run/nvidia-ctk-hook<random-uuid>`, and that UUID changes on every
#: container start. Because a mount point is a host **fingerprint** input,
#: reporting it would have made the fingerprint unstable across restarts —
#: and the fingerprint is the key by which Milestone 2 judges cached evidence
#: reusable, so nothing would ever have been reused. Free space was the
#: obvious volatility trap; mount identity was the one that nearly landed.
_NON_STORAGE_PREFIXES: Final = ("/proc", "/sys", "/dev", "/run")

#: Architecture strings normalized onto the platform's vocabulary.
_ARCHITECTURES: Final = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "arm64",
    "arm64": "arm64",
}


class NativeLinuxProvider:
    """Observes OS release, memory availability, mounts and occupied ports."""

    provider = PROVIDER

    def __init__(
        self,
        clock: Clock | None = None,
        *,
        root: Path | None = None,
        capture: dict[str, object] | None = None,
    ) -> None:
        self._clock = clock or SystemClock()
        self._root = root or Path("/")
        self._capture = capture  # supplied when replaying a captured fixture

    @property
    def reports_accelerator_assignment(self) -> bool:
        """False: this provider observes no accelerators at all."""
        return False

    def observe(self) -> ProviderReport:
        if self._capture is not None:
            return ProviderReport(
                provider=PROVIDER,
                status=ProviderStatus.PARTIAL,
                observed_at=self._clock.now(),
                provider_version=NOT_PROVIDED,
                observations=tuple(_from_capture(self._capture)),
                detail="replayed from a captured observation",
            )
        if not (self._root / "proc").is_dir():
            return ProviderReport(
                provider=PROVIDER,
                status=ProviderStatus.UNAVAILABLE,
                observed_at=self._clock.now(),
                detail="no /proc; this provider observes Linux hosts only",
            )
        return ProviderReport(
            provider=PROVIDER,
            status=ProviderStatus.PARTIAL,
            observed_at=self._clock.now(),
            provider_version=NOT_PROVIDED,
            observations=tuple(_from_capture(self.capture())),
            detail="OS release, available memory, mounts and occupied ports",
        )

    def capture(self) -> dict[str, object]:
        """The raw reading, as the provider fixture records it.

        Captured as a structure rather than as free text so the fixture can
        be replayed through exactly this provider's normalization path.
        """
        return {
            "os_release": _read_os_release(self._root),
            "architecture": platform.machine(),
            "kernel_version": platform.release(),
            "hostname": _hostname(),
            "meminfo": _read_meminfo(self._root),
            "mounts": _read_mounts(self._root),
            "occupied_ports": _read_ports(self._root),
            "container": (self._root / ".dockerenv").exists(),
        }


def _from_capture(capture: dict[str, object]) -> list[Observation]:
    found: list[Observation] = []

    def add(path: str, value: object, derivation: Derivation) -> None:
        found.append(
            Observation(
                path=path,
                value=value,  # type: ignore[arg-type]
                derivation=derivation,
                confidence=Confidence.HIGH,
            )
        )

    # The family, not the distribution. This provider only runs where /proc
    # exists, so the family is known; reporting "ubuntu" here would collide
    # with a topology provider reporting "linux" for the same field and look
    # like a disagreement rather than two different facts.
    add("operating_environment.os_name", "linux", Derivation.DERIVED)

    release = capture.get("os_release")
    if isinstance(release, dict):
        name = release.get("ID") or release.get("NAME")
        if isinstance(name, str) and name:
            add(
                "operating_environment.distribution",
                name.strip('"').lower(),
                Derivation.REPORTED_BY_SOURCE,
            )
        version = release.get("VERSION_ID") or release.get("VERSION")
        if isinstance(version, str) and version:
            add(
                "operating_environment.os_version",
                version.strip('"'),
                Derivation.REPORTED_BY_SOURCE,
            )

    machine = capture.get("architecture")
    if isinstance(machine, str) and machine:
        add(
            "operating_environment.architecture",
            _ARCHITECTURES.get(machine.lower(), "unknown"),
            Derivation.MEASURED,
        )
    kernel = capture.get("kernel_version")
    if isinstance(kernel, str) and kernel:
        add("operating_environment.kernel_version", kernel, Derivation.MEASURED)
    hostname = capture.get("hostname")
    if isinstance(hostname, str) and hostname:
        add("network.hostname", hostname, Derivation.MEASURED)

    container = capture.get("container")
    if isinstance(container, bool):
        # Containerized counts as virtualized for capability purposes: the
        # platform does not see the whole machine either way.
        add("operating_environment.virtualized", container, Derivation.DERIVED)

    meminfo = capture.get("meminfo")
    if isinstance(meminfo, dict):
        total = meminfo.get("MemTotal")
        available = meminfo.get("MemAvailable")
        if isinstance(total, int):
            add("memory.total_bytes", total, Derivation.MEASURED)
        if isinstance(available, int):
            add("memory.available_bytes", available, Derivation.MEASURED)

    mounts = capture.get("mounts")
    if isinstance(mounts, list):
        for mount in mounts:
            if not isinstance(mount, dict):
                continue
            point = mount.get("mount_point")
            if not isinstance(point, str) or not point:
                continue
            add(f"mount.{point}.mount_point", point, Derivation.MEASURED)
            for field, derivation in (
                ("device", Derivation.REPORTED_BY_SOURCE),
                ("filesystem_type", Derivation.REPORTED_BY_SOURCE),
                ("total_bytes", Derivation.MEASURED),
                ("free_bytes", Derivation.MEASURED),
            ):
                value = mount.get(field)
                if value is not None:
                    add(f"mount.{point}.{field}", value, derivation)

    ports = capture.get("occupied_ports")
    if isinstance(ports, list) and ports:
        add("network.occupied_ports", sorted(set(ports)), Derivation.MEASURED)
    return found


def _read_os_release(root: Path) -> dict[str, str]:
    path = root / "etc" / "os-release"
    if not path.is_file():
        return {}
    parsed: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        parsed[key.strip()] = value.strip().strip('"')
    return parsed


def _read_meminfo(root: Path) -> dict[str, int]:
    path = root / "proc" / "meminfo"
    if not path.is_file():
        return {}
    parsed: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, _, rest = line.partition(":")
        fields = rest.split()
        if len(fields) >= 2 and fields[0].isdigit() and fields[1] == "kB":
            parsed[key.strip()] = int(fields[0]) * 1024
    return parsed


def _read_mounts(root: Path) -> list[dict[str, object]]:
    path = root / "proc" / "mounts"
    if not path.is_file():
        return []
    seen: set[str] = set()
    mounts: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        device, point, fstype = fields[0], fields[1].replace("\\040", " "), fields[2]
        if fstype in _IGNORED_TYPES or point in seen:
            continue
        if not _could_hold_data(point):
            continue
        target = Path(point)
        if not target.is_dir():
            # A single-file bind mount is container plumbing, not storage.
            continue
        try:
            stat = os.statvfs(point)
        except OSError:
            continue
        seen.add(point)
        mounts.append(
            {
                "mount_point": point,
                "device": device,
                "filesystem_type": fstype,
                "total_bytes": stat.f_blocks * stat.f_frsize,
                "free_bytes": stat.f_bavail * stat.f_frsize,
            }
        )
    return mounts


def _could_hold_data(point: str) -> bool:
    """Whether a mount point is somewhere the platform could keep data."""
    if point == "/":
        return True
    return not any(
        point == prefix or point.startswith(f"{prefix}/")
        for prefix in _NON_STORAGE_PREFIXES
    )


def _read_ports(root: Path) -> list[int]:
    """Occupied TCP ports, read from /proc rather than by shelling out."""
    ports: set[int] = set()
    for name in ("tcp", "tcp6"):
        path = root / "proc" / "net" / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A":  # 0A = LISTEN
                continue
            _, _, port = fields[1].rpartition(":")
            try:
                ports.add(int(port, 16))
            except ValueError:
                continue
    return sorted(ports)


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return ""


def build(clock: Clock | None = None) -> NativeLinuxProvider:
    """Factory for the adapter registry."""
    return NativeLinuxProvider(clock)


def replay(
    capture: dict[str, object], clock: Clock | None = None
) -> NativeLinuxProvider:
    """Replay a captured provider fixture through the real parsing path."""
    return NativeLinuxProvider(clock, capture=capture)

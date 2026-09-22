"""Machine-readable Machi dependency law.

Machi production code must not import Kultrun. Kernel must not import
adapters, Install, Discover, or the composition root. Install may import
Kernel and must not import adapters, Discover, or later Blocks. Discover
may import Kernel and must not import adapters, Install, or later Blocks.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TIERS: dict[str, int] = {
    "kernel": 0,
    "install": 1,
    "discover": 2,
    "prerequisites": 2,
    "steward": 2,
    "capacity": 2,
    "foundation": 2,
    "model": 2,
    "adapters": 3,
    "main": 4,
}

CROSS_IMPORT_FORBIDDEN: frozenset[tuple[str, str]] = frozenset(
    {
        ("discover", "prerequisites"),
        ("prerequisites", "discover"),
        ("prerequisites", "install"),
        ("install", "prerequisites"),
        ("kernel", "prerequisites"),
        ("discover", "steward"),
        ("install", "steward"),
        ("kernel", "steward"),
        ("prerequisites", "steward"),
        ("steward", "prerequisites"),
        ("discover", "capacity"),
        ("steward", "capacity"),
        ("kernel", "capacity"),
        ("install", "capacity"),
        ("prerequisites", "capacity"),
        ("capacity", "prerequisites"),
        ("capacity", "foundation"),
        ("discover", "foundation"),
        ("steward", "foundation"),
        ("kernel", "foundation"),
        ("install", "foundation"),
        ("prerequisites", "foundation"),
        ("foundation", "prerequisites"),
        ("foundation", "model"),
        ("capacity", "model"),
        ("discover", "model"),
        ("steward", "model"),
        ("kernel", "model"),
        ("install", "model"),
        ("prerequisites", "model"),
        ("model", "prerequisites"),
    }
)

FORBIDDEN_TOP_LEVEL = frozenset({"kultrun"})

FUTURE_PACKAGES = frozenset(
    {
        "plan",
        "admit",
        "serve",
    }
)

KERNEL_POLICY_TOKENS = (
    "MACHI_STATE_ROOT",
    ".local/state/machi",
    "StateRootBinder",
    "KULTRUN_STATE_ROOT",
    "SelfOwnershipMarker",
    ".machi-owner.json",
    "local_marker_present",
)


@dataclass(frozen=True, slots=True)
class ImportEdge:
    source_module: str
    source_package: str
    target_module: str
    line: int

    def describe(self) -> str:
        return f"{self.source_module}:{self.line} imports {self.target_module}"


def source_root() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "machi"


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root.parent)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_of(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) < 2:
        return None
    if parts[0] != "machi":
        return None
    if len(parts) == 2 and parts[1] in {"main", "__main__"}:
        return "main"
    return parts[1]


def scan(root: Path) -> list[ImportEdge]:
    edges: list[ImportEdge] = []
    for path in sorted(root.rglob("*.py")):
        source_module = _module_name(path, root)
        source_package = _package_of(source_module)
        if source_package is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append(
                        ImportEdge(
                            source_module=source_module,
                            source_package=source_package,
                            target_module=alias.name,
                            line=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                edges.append(
                    ImportEdge(
                        source_module=source_module,
                        source_package=source_package,
                        target_module=node.module,
                        line=node.lineno,
                    )
                )
    return edges


def violations(edges: Iterable[ImportEdge]) -> list[str]:
    found: list[str] = []
    for edge in edges:
        top = edge.target_module.split(".", 1)[0]
        if top in FORBIDDEN_TOP_LEVEL:
            found.append(
                f"{edge.describe()} (production Machi must not import kultrun)"
            )
            continue
        if top != "machi":
            continue
        parts = edge.target_module.split(".")
        if len(parts) >= 2 and parts[1] in FUTURE_PACKAGES:
            found.append(f"{edge.describe()} (future Block is not implemented)")
            continue
        target_package = _package_of(edge.target_module)
        if target_package is None:
            continue
        if edge.source_package not in TIERS:
            found.append(f"{edge.source_module} is in no Machi tier")
            continue
        if target_package not in TIERS:
            found.append(f"{edge.describe()} targets an unassigned Machi package")
            continue
        if (edge.source_package, target_package) in CROSS_IMPORT_FORBIDDEN:
            found.append(
                f"{edge.describe()} "
                f"({edge.source_package} may not import {target_package})"
            )
            continue
        if TIERS[target_package] < TIERS[edge.source_package]:
            continue
        if TIERS[target_package] == TIERS[edge.source_package]:
            continue
        found.append(
            f"{edge.describe()} "
            f"(tier {edge.source_package} may not import {target_package})"
        )
    return found


def unassigned_packages(root: Path) -> list[str]:
    found = {
        child.name
        for child in root.iterdir()
        if child.is_dir() and not child.name.startswith(("_", "."))
    }
    assigned = set(TIERS) - {"main"}
    return sorted(found - assigned)


def kernel_policy_violations(root: Path) -> list[str]:
    """Kernel must not encode Install state-root policy."""
    kernel = root / "kernel"
    found: list[str] = []
    for path in sorted(kernel.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in KERNEL_POLICY_TOKENS:
            if token in text:
                found.append(f"{path.name} contains Install policy token {token!r}")
    return found


def binder_ownership_violations(root: Path) -> list[str]:
    """StateRootBinder must not write the local ownership marker."""
    binder = root / "install" / "binder.py"
    text = binder.read_text(encoding="utf-8")
    if ".machi-owner.json" in text or "SelfOwnershipMarker" in text:
        return [f"{binder.name} must not create local ownership evidence"]
    return []


MARKER_FORBIDDEN_TOKENS = (
    "StateRootBinder",
    "shutil.rmtree",
    "rglob",
    "OwnershipRecord",
    "InstallId",
    "InstallRunId",
    "HostId",
    "delete_owned",
    "reclaim",
    "steward",
)


def marker_boundary_violations(root: Path) -> list[str]:
    """1.3.1 consumes a binding; it does not re-bind, register, or destroy."""
    marker = root / "install" / "marker.py"
    text = marker.read_text(encoding="utf-8")
    found: list[str] = []
    for token in MARKER_FORBIDDEN_TOKENS:
        if token in text:
            found.append(f"{marker.name} must not contain {token!r}")
    if "def establish(self, binding: StateRootBinding)" not in text:
        found.append("SelfOwnershipMarker.establish must consume StateRootBinding")
    return found


STORE_PORT_FORBIDDEN = (
    "MACHI_STATE_ROOT",
    "StateRootBinder",
    "SelfOwnershipMarker",
    ".machi-owner.json",
    "RegistrySeed",
    "InstallIdentity",
    "InstallRunStore",
    "EventRecord",
    "JsonlJournal",
    "FileStore",
    "os.environ",
    "os.link",
)

STORE_ADAPTER_FORBIDDEN = (
    "MACHI_STATE_ROOT",
    "StateRootBinder",
    "SelfOwnershipMarker",
    ".machi-owner.json",
    "RegistrySeed",
    "InstallIdentity",
    "InstallRunStore",
    "EventRecord",
    "JsonlJournal",
    "os.environ",
    "shutil.rmtree",
    "machi.install",
)


def store_boundary_violations(root: Path) -> list[str]:
    """0.4.1 Store stays a Kernel mechanism with an injected root."""
    found: list[str] = []
    port = root / "kernel" / "store.py"
    port_text = port.read_text(encoding="utf-8")
    for token in STORE_PORT_FORBIDDEN:
        if token in port_text:
            found.append(f"{port.name} must not contain {token!r}")
    adapter = root / "adapters" / "persistence" / "file_store.py"
    adapter_text = adapter.read_text(encoding="utf-8")
    for token in STORE_ADAPTER_FORBIDDEN:
        if token in adapter_text:
            found.append(f"{adapter.name} must not contain {token!r}")
    journal = (root / "kernel" / "journal.py").read_text(encoding="utf-8")
    if "FileStore" in journal or "validate_record_key" in journal:
        found.append("journal.py must not depend on Store")
    return found


REGISTRY_FORBIDDEN_TOKENS = (
    "FileStore",
    "MACHI_STATE_ROOT",
    "os.environ",
    "os.link",
    "shutil.rmtree",
    "rglob",
    "OwnershipRecord",
    "InstallId",
    "InstallRunId",
    "HostId",
    "delete_owned",
    "reclaim",
    "steward",
    "kernel.store.proved",
    "StateRootBinder",
    "SelfOwnershipMarker",
    ".machi-owner.json",
    "/proc/",
    "nvidia",
    "docker",
    "runpod",
)


def registry_boundary_violations(root: Path) -> list[str]:
    """1.3.2 consumes binding + local evidence and an injected Store port."""
    path = root / "install" / "registry.py"
    text = path.read_text(encoding="utf-8")
    found: list[str] = []
    for token in REGISTRY_FORBIDDEN_TOKENS:
        if token in text:
            found.append(f"{path.name} must not contain {token!r}")
    if "def seed(" not in text:
        found.append("RegistrySeed.seed must be defined")
    if "binding: StateRootBinding" not in text:
        found.append("RegistrySeed.seed must consume StateRootBinding")
    if "establishment: LocalOwnershipEstablishment" not in text:
        found.append("RegistrySeed.seed must consume LocalOwnershipEstablishment")
    if "store: Store" not in text:
        found.append("RegistrySeed.seed must consume the Store port")
    if "from machi.kernel.store import Store" not in text:
        found.append("RegistrySeed must consume the Kernel Store port")
    if "from machi.adapters" in text:
        found.append("RegistrySeed must not import adapters")
    store_port = (root / "kernel" / "store.py").read_text(encoding="utf-8")
    if "RegistrySeed" in store_port:
        found.append("kernel Store must not import RegistrySeed")
    return found


IDENTITY_FORBIDDEN_TOKENS = (
    "FileStore",
    "MACHI_STATE_ROOT",
    "os.environ",
    "os.link",
    "shutil.rmtree",
    "rglob",
    "OwnershipRecord",
    "InstallRunId",
    "HostId",
    "delete_owned",
    "reclaim",
    "steward",
    "kernel.store.proved",
    "StateRootBinder",
    "SelfOwnershipMarker",
    "from machi.install.registry",
    ".machi-owner.json",
    "identity()",
    "/proc/",
    "nvidia",
    "docker",
    "runpod",
)


def identity_boundary_violations(root: Path) -> list[str]:
    """1.1.1 consumes contracts and an injected Store; it does not invent runs."""
    path = root / "install" / "identity.py"
    text = path.read_text(encoding="utf-8")
    found: list[str] = []
    for token in IDENTITY_FORBIDDEN_TOKENS:
        if token in text:
            found.append(f"{path.name} must not contain {token!r}")
    if "def establish(" not in text:
        found.append("InstallIdentity.establish must be defined")
    if "binding: StateRootBinding" not in text:
        found.append("InstallIdentity.establish must consume StateRootBinding")
    if "establishment: LocalOwnershipEstablishment" not in text:
        found.append(
            "InstallIdentity.establish must consume LocalOwnershipEstablishment"
        )
    if "registry: LocalOwnershipRegistryEstablishment" not in text:
        found.append(
            "InstallIdentity.establish must consume LocalOwnershipRegistryEstablishment"
        )
    if "store: Store" not in text:
        found.append("InstallIdentity.establish must consume the Store port")
    if "build: BuildIdentity" not in text:
        found.append("InstallIdentity.establish must consume BuildIdentity")
    if "from machi.kernel.store import Store" not in text:
        found.append("InstallIdentity must consume the Kernel Store port")
    if "from machi.adapters" in text:
        found.append("InstallIdentity must not import adapters")
    store_port = (root / "kernel" / "store.py").read_text(encoding="utf-8")
    if "InstallIdentity" in store_port:
        found.append("kernel Store must not import InstallIdentity")
    return found


RUN_FORBIDDEN_TOKENS = (
    "FileStore",
    "MACHI_STATE_ROOT",
    "os.environ",
    "os.link",
    "shutil.rmtree",
    "rglob",
    "OwnershipRecord",
    "HostId",
    "delete_owned",
    "reclaim",
    "steward",
    "discover",
    "kernel.store.proved",
    "StateRootBinder",
    "SelfOwnershipMarker",
    "from machi.install.registry",
    "from machi.install.identity",
    ".machi-owner.json",
    "identity()",
    "/proc/",
    "nvidia",
    "docker",
    "runpod",
)


def run_boundary_violations(root: Path) -> list[str]:
    """1.4.1 consumes InstallRecord and an injected Store; it does not re-own."""
    path = root / "install" / "run.py"
    text = path.read_text(encoding="utf-8")
    found: list[str] = []
    for token in RUN_FORBIDDEN_TOKENS:
        if token in text:
            found.append(f"{path.name} must not contain {token!r}")
    if "def establish(" not in text:
        found.append("InstallRunStore.establish must be defined")
    if "record: InstallRecord" not in text:
        found.append("InstallRunStore.establish must consume InstallRecord")
    if "store: Store" not in text:
        found.append("InstallRunStore.establish must consume the Store port")
    if "build: BuildIdentity" not in text:
        found.append("InstallRunStore.establish must consume BuildIdentity")
    if "from machi.kernel.store import Store" not in text:
        found.append("InstallRunStore must consume the Kernel Store port")
    if "from machi.adapters" in text:
        found.append("InstallRunStore must not import adapters")
    if "InstallId.generate" in text:
        found.append("InstallRunStore must not mint InstallId")
    store_port = (root / "kernel" / "store.py").read_text(encoding="utf-8")
    if "InstallRunStore" in store_port:
        found.append("kernel Store must not import InstallRunStore")
    kernel_text = "\n".join(
        p.read_text(encoding="utf-8") for p in (root / "kernel").rglob("*.py")
    )
    if "InstallRunStore" in kernel_text:
        found.append("Kernel must not import InstallRunStore")
    return found


DISCOVER_DOMAIN_FORBIDDEN = (
    "platform.system",
    "platform.machine",
    "/etc/os-release",
    "subprocess",
    "nvidia-smi",
    "amd-smi",
    "rocm-smi",
    "xpu-smi",
    "xpumcli",
    "HostId.generate",
    "FileStore",
    "MACHI_STATE_ROOT",
    "meminfo",
    "shutil.rmtree",
    "from machi.install",
    "from machi.adapters",
    "from machi.prerequisites",
    "PrerequisiteReadiness",
    "cuda",
    "nvml",
    "pynvml",
    "system_profiler",
    "SPDisplaysDataType",
    "ioreg",
    "psutil",
    "cgroup",
    "safe_bytes",
    "safe_memory",
    "/proc/",
    "parse_linux_memory_table",
    "SC_PHYS_PAGES",
    "linux_proc_memory",
    "macos_sysconf_memory",
    "nvidia_accelerator",
    "amd_accelerator",
    "apple_accelerator",
    "intel_accelerator",
    "parse_nvidia_smi_csv",
    "parse_amd_smi_json",
    "parse_apple_displays_json",
    "parse_linux_mountinfo",
    "getfsstat",
    "LinuxMountProvider",
    "MacOSMountProvider",
    "linux_mount",
    "macos_mount",
    "umount",
    "os.walk",
    "SAFE_STORAGE_BYTES",
    "ResourceManager",
    "ServingConfiguration",
    "OccupancyMap",
    "OwnershipRecord",
)

NATIVE_OS_ARCH_FORBIDDEN = (
    "subprocess",
    "nvidia",
    "HostId.generate",
    "FileStore",
    "meminfo",
    "/proc/",
    "shutil",
    "os.system",
    "from machi.install",
    "os-release",
)

NATIVE_MEMORY_FORBIDDEN = (
    "subprocess",
    "nvidia",
    "HostId.generate",
    "FileStore",
    "shutil",
    "os.system",
    "from machi.install",
    "psutil",
    "safe_bytes",
    "safe_memory",
    "ctypes",
    "cgroup",
    "/proc/meminfo",
    "os.sysconf",
)

MEMORY_PROVIDER_FORBIDDEN = (
    "subprocess",
    "nvidia",
    "HostId.generate",
    "FileStore",
    "shutil",
    "os.system",
    "from machi.install",
    "psutil",
    "safe_bytes",
    "safe_memory",
    "cgroup",
    "cuda",
    "docker",
    "runpod",
)

NATIVE_ACCELERATOR_FORBIDDEN = (
    "subprocess",
    "nvidia-smi",
    "amd-smi",
    "rocm-smi",
    "xpu-smi",
    "xpumcli",
    "system_profiler",
    "IntelAcceleratorProvider",
    "intel_accelerator",
    "HostId.generate",
    "FileStore",
    "from machi.install",
    "psutil",
    "safe_bytes",
    "safe_memory",
    "pynvml",
    "torch",
    "cuda",
    "MemoryObservation",
    "physical_total_bytes",
)

NVIDIA_PROVIDER_FORBIDDEN = (
    "system_profiler",
    "SPDisplaysDataType",
    "ioreg",
    "amd-smi",
    "rocm-smi",
    "xpu-smi",
    "xpumcli",
    "HostId.generate",
    "FileStore",
    "from machi.install",
    "psutil",
    "safe_bytes",
    "safe_memory",
    "pynvml",
    "torch",
    "cuda",
    "docker",
    "runpod",
    "shell=True",
    "physical_memory",
    "hw.memsize",
)

AMD_PROVIDER_FORBIDDEN = (
    "nvidia-smi",
    "query-gpu",
    "system_profiler",
    "SPDisplaysDataType",
    "ioreg",
    "xpu-smi",
    "xpumcli",
    "from amdsmi",
    "import amdsmi",
    "HostId.generate",
    "FileStore",
    "from machi.install",
    "psutil",
    "safe_bytes",
    "safe_memory",
    "pynvml",
    "torch",
    "cuda",
    "docker",
    "runpod",
    "shell=True",
    "physical_memory",
    "hw.memsize",
    "rocm-smi",
)

APPLE_PROVIDER_FORBIDDEN = (
    "nvidia-smi",
    "query-gpu",
    "amd-smi",
    "rocm-smi",
    "xpu-smi",
    "xpumcli",
    "HostId.generate",
    "FileStore",
    "from machi.install",
    "psutil",
    "safe_bytes",
    "safe_memory",
    "pynvml",
    "torch",
    "cuda",
    "docker",
    "runpod",
    "shell=True",
    "physical_memory",
    "hw.memsize",
    "SC_PHYS_PAGES",
)

NATIVE_MOUNT_FORBIDDEN = (
    "subprocess",
    "nvidia-smi",
    "amd-smi",
    "parse_linux_mountinfo",
    "getfsstat",
    "HostId.generate",
    "FileStore",
    "from machi.install",
    "from machi.prerequisites",
    "psutil",
    "SAFE_STORAGE_BYTES",
    "umount",
    "os.walk",
    "shutil.rmtree",
    "ResourceManager",
    "ServingConfiguration",
    "OccupancyMap",
)

LINUX_MOUNT_FORBIDDEN = (
    "subprocess",
    "shell=True",
    "nvidia-smi",
    "HostId.generate",
    "FileStore",
    "from machi.install",
    "from machi.prerequisites",
    "psutil",
    "SAFE_STORAGE_BYTES",
    "umount",
    "os.walk",
    "shutil.rmtree",
    "ResourceManager",
    "ServingConfiguration",
    "os.system",
)

MACOS_MOUNT_FORBIDDEN = (
    "/proc/self/mountinfo",
    "subprocess",
    "shell=True",
    "nvidia-smi",
    "HostId.generate",
    "FileStore",
    "from machi.install",
    "SAFE_STORAGE_BYTES",
    "umount",
    "os.walk",
    "shutil.rmtree",
    "ResourceManager",
    "ServingConfiguration",
)

MOUNT_PROBE_FORBIDDEN = (
    "os.walk",
    "rglob(",
    "umount",
    "SAFE_STORAGE_BYTES",
    "ENOSPC",
    "EDQUOT",
    "shutil.rmtree",
    "ResourceManager",
)


def discover_boundary_violations(root: Path) -> list[str]:
    """Discover domain owns contracts; native adapters own host I/O."""
    found: list[str] = []
    domain = root / "discover"
    for path in sorted(domain.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in DISCOVER_DOMAIN_FORBIDDEN:
            if token in text:
                found.append(f"{path.name} must not contain {token!r}")
    adapter = root / "adapters" / "discover" / "native_os_arch.py"
    adapter_text = adapter.read_text(encoding="utf-8")
    for token in NATIVE_OS_ARCH_FORBIDDEN:
        if token in adapter_text:
            found.append(f"{adapter.name} must not contain {token!r}")
    if "import platform" not in adapter_text:
        found.append("native OS/arch adapter must import platform")
    if "platform.system()" not in adapter_text:
        found.append("native OS/arch adapter must call platform.system()")
    if "platform.machine()" not in adapter_text:
        found.append("native OS/arch adapter must call platform.machine()")
    if "normalize_os_architecture" not in adapter_text:
        found.append("native OS/arch adapter must call pure normalization")
    memory_adapter = root / "adapters" / "discover" / "native_memory.py"
    memory_text = memory_adapter.read_text(encoding="utf-8")
    for token in NATIVE_MEMORY_FORBIDDEN:
        if token in memory_text:
            found.append(f"{memory_adapter.name} must not contain {token!r}")
    if "LinuxProcMemoryProvider" not in memory_text:
        found.append("native memory observer must compose LinuxProcMemoryProvider")
    if "MacOSSysconfMemoryProvider" not in memory_text:
        found.append("native memory observer must compose MacOSSysconfMemoryProvider")
    linux_provider = root / "adapters" / "discover" / "linux_proc_memory.py"
    linux_text = linux_provider.read_text(encoding="utf-8")
    for token in MEMORY_PROVIDER_FORBIDDEN:
        if token in linux_text:
            found.append(f"{linux_provider.name} must not contain {token!r}")
    if "/proc/meminfo" not in linux_text:
        found.append("Linux memory provider must read /proc/meminfo")
    if "parse_linux_memory_table" not in linux_text:
        found.append("Linux memory provider must own Linux table parsing")
    macos_provider = root / "adapters" / "discover" / "macos_sysconf_memory.py"
    macos_text = macos_provider.read_text(encoding="utf-8")
    for token in MEMORY_PROVIDER_FORBIDDEN:
        if token in macos_text:
            found.append(f"{macos_provider.name} must not contain {token!r}")
    if "os.sysconf" not in macos_text:
        found.append("macOS memory provider must use os.sysconf")
    if "/proc/meminfo" in macos_text:
        found.append("macOS memory provider must not read /proc/meminfo")
    accelerator_adapter = root / "adapters" / "discover" / "native_accelerator.py"
    accelerator_text = accelerator_adapter.read_text(encoding="utf-8")
    for token in NATIVE_ACCELERATOR_FORBIDDEN:
        if token in accelerator_text:
            found.append(f"{accelerator_adapter.name} must not contain {token!r}")
    if "NvidiaAcceleratorProvider" not in accelerator_text:
        found.append(
            "native accelerator observer must compose NvidiaAcceleratorProvider"
        )
    if "AmdAcceleratorProvider" not in accelerator_text:
        found.append("native accelerator observer must compose AmdAcceleratorProvider")
    if "AppleAcceleratorProvider" not in accelerator_text:
        found.append(
            "native accelerator observer must compose AppleAcceleratorProvider"
        )
    if "intel_provider" in accelerator_text:
        found.append("native accelerator observer must not wire an Intel provider")
    intel_module = root / "adapters" / "discover" / "intel_accelerator.py"
    if intel_module.exists():
        found.append("Intel accelerator provider must not exist in this composition")
    nvidia_provider = root / "adapters" / "discover" / "nvidia_accelerator.py"
    nvidia_text = nvidia_provider.read_text(encoding="utf-8")
    for token in NVIDIA_PROVIDER_FORBIDDEN:
        if token in nvidia_text:
            found.append(f"{nvidia_provider.name} must not contain {token!r}")
    if "nvidia-smi" not in nvidia_text:
        found.append("NVIDIA provider must use nvidia-smi")
    if "--query-gpu=" not in nvidia_text:
        found.append("NVIDIA provider must use machine-readable query mode")
    if "csv,noheader,nounits" not in nvidia_text:
        found.append("NVIDIA provider must request csv,noheader,nounits")
    if "parse_nvidia_smi_csv" not in nvidia_text:
        found.append("NVIDIA provider must own CSV parsing")
    amd_provider = root / "adapters" / "discover" / "amd_accelerator.py"
    amd_text = amd_provider.read_text(encoding="utf-8")
    for token in AMD_PROVIDER_FORBIDDEN:
        if token in amd_text:
            found.append(f"{amd_provider.name} must not contain {token!r}")
    if "amd-smi" not in amd_text:
        found.append("AMD provider must use amd-smi")
    if "parse_amd_smi_json" not in amd_text:
        found.append("AMD provider must own JSON parsing")
    if "--json" not in amd_text:
        found.append("AMD provider must request structured JSON")
    apple_provider = root / "adapters" / "discover" / "apple_accelerator.py"
    apple_text = apple_provider.read_text(encoding="utf-8")
    for token in APPLE_PROVIDER_FORBIDDEN:
        if token in apple_text:
            found.append(f"{apple_provider.name} must not contain {token!r}")
    if "system_profiler" not in apple_text:
        found.append("Apple provider must use system_profiler")
    if "SPDisplaysDataType" not in apple_text:
        found.append("Apple provider must read SPDisplaysDataType")
    if "parse_apple_displays_json" not in apple_text:
        found.append("Apple provider must own JSON parsing")
    if "UNIFIED" not in apple_text:
        found.append("Apple provider must represent unified memory topology")
    mount_adapter = root / "adapters" / "discover" / "native_mount.py"
    if not mount_adapter.exists():
        found.append("native mount observer is missing")
    else:
        mount_text = mount_adapter.read_text(encoding="utf-8")
        for token in NATIVE_MOUNT_FORBIDDEN:
            if token in mount_text:
                found.append(f"{mount_adapter.name} must not contain {token!r}")
        if "LinuxMountProvider" not in mount_text:
            found.append("native mount observer must compose LinuxMountProvider")
        if "MacOSMountProvider" not in mount_text:
            found.append("native mount observer must compose MacOSMountProvider")
        if "parse_linux_mountinfo" in mount_text:
            found.append("native mount observer must not parse the Linux mount table")
    linux_mount = root / "adapters" / "discover" / "linux_mount.py"
    if not linux_mount.exists():
        found.append("Linux mount provider is missing")
    else:
        linux_mount_text = linux_mount.read_text(encoding="utf-8")
        for token in LINUX_MOUNT_FORBIDDEN:
            if token in linux_mount_text:
                found.append(f"{linux_mount.name} must not contain {token!r}")
        if "/proc/self/mountinfo" not in linux_mount_text:
            found.append("Linux mount provider must read the process mount table")
        if "parse_linux_mountinfo" not in linux_mount_text:
            found.append("Linux mount provider must own mount-table parsing")
        if "classify_linux_filesystem" not in linux_mount_text:
            found.append("Linux mount provider must own filesystem classification")
    macos_mount = root / "adapters" / "discover" / "macos_mount.py"
    if not macos_mount.exists():
        found.append("macOS mount provider is missing")
    else:
        macos_mount_text = macos_mount.read_text(encoding="utf-8")
        for token in MACOS_MOUNT_FORBIDDEN:
            if token in macos_mount_text:
                found.append(f"{macos_mount.name} must not contain {token!r}")
        if "getfsstat" not in macos_mount_text:
            found.append("macOS mount provider must use native mount statistics")
        if "classify_darwin_filesystem" not in macos_mount_text:
            found.append("macOS mount provider must own filesystem classification")
    mount_probe = root / "adapters" / "discover" / "mount_probe.py"
    if not mount_probe.exists():
        found.append("bounded mount probe helper is missing")
    else:
        probe_text = mount_probe.read_text(encoding="utf-8")
        for token in MOUNT_PROBE_FORBIDDEN:
            if token in probe_text:
                found.append(f"{mount_probe.name} must not contain {token!r}")
        if "O_EXCL" not in probe_text:
            found.append("bounded write probe must create an exclusive temp file")
        if ".machi-mount-probe-" not in probe_text:
            found.append("bounded write probe must use a Machi-owned temp name")
    kernel_text = "\n".join(
        p.read_text(encoding="utf-8") for p in (root / "kernel").rglob("*.py")
    )
    if "machi.discover" in kernel_text or "OSArchitectureObservation" in kernel_text:
        found.append("Kernel must not import Discover")
    if "MemoryObservation" in kernel_text:
        found.append("Kernel must not import MemoryObservation")
    if "AcceleratorObservation" in kernel_text:
        found.append("Kernel must not import AcceleratorObservation")
    if "MountObservation" in kernel_text:
        found.append("Kernel must not import MountObservation")
    install_text = "\n".join(
        p.read_text(encoding="utf-8") for p in (root / "install").rglob("*.py")
    )
    if "machi.discover" in install_text:
        found.append("Install must not import Discover")
    main_text = (root / "main.py").read_text(encoding="utf-8")
    if "LinuxProcMemoryProvider" in main_text:
        found.append(
            "composition must wire NativeMemoryObserver, not LinuxProcMemoryProvider"
        )
    if "MacOSSysconfMemoryProvider" in main_text:
        found.append(
            "composition must wire NativeMemoryObserver, not MacOSSysconfMemoryProvider"
        )
    if "NativeAcceleratorObserver" not in main_text:
        found.append("composition must wire NativeAcceleratorObserver")
    if "NativeMountObserver" not in main_text:
        found.append("composition must wire NativeMountObserver")
    if "LinuxMountProvider" in main_text:
        found.append(
            "composition must wire NativeMountObserver, not LinuxMountProvider"
        )
    if "MacOSMountProvider" in main_text:
        found.append(
            "composition must wire NativeMountObserver, not MacOSMountProvider"
        )
    if "NvidiaAcceleratorProvider" in main_text:
        found.append(
            "composition must wire NativeAcceleratorObserver, "
            "not NvidiaAcceleratorProvider"
        )
    if "AppleAcceleratorProvider" in main_text:
        found.append(
            "composition must wire NativeAcceleratorObserver, "
            "not AppleAcceleratorProvider"
        )
    if "AmdAcceleratorProvider" in main_text:
        found.append(
            "composition must wire NativeAcceleratorObserver, "
            "not AmdAcceleratorProvider"
        )
    if "IntelAcceleratorProvider" in main_text:
        found.append("composition must not wire IntelAcceleratorProvider")
    for token in (
        "nvidia-smi",
        "amd-smi",
        "rocm-smi",
        "xpu-smi",
        "xpumcli",
        "cuda",
        "nvml",
        "pynvml",
        "system_profiler",
        "runpod",
        "docker",
    ):
        if token in main_text.lower():
            found.append(f"composition root must not name {token}")
    store_port = (root / "kernel" / "store.py").read_text(encoding="utf-8")
    file_store = (root / "adapters" / "persistence" / "file_store.py").read_text(
        encoding="utf-8"
    )
    if "os.link" not in file_store:
        found.append("FileStore must own the exclusive-publish primitive")
    if "os.link" in store_port:
        found.append("Store port must not require os.link")
    return found


KERNEL_TECHNOLOGY_TOKENS = (
    "os.link",
    "/proc/",
    "/proc/meminfo",
    "nvidia",
    "amd-smi",
    "rocm-smi",
    "cuda",
    "nvml",
    "docker",
    "runpod",
    "platform.system",
    "platform.machine",
)

JOURNAL_PORT_FORBIDDEN = (
    "os.link",
    "os.fsync",
    "FileStore",
    "/proc",
    "nvidia",
    "docker",
    "runpod",
)


def kernel_technology_violations(root: Path) -> list[str]:
    """Kernel must not name OS, vendor, or filesystem publication primitives."""
    kernel = root / "kernel"
    found: list[str] = []
    for path in sorted(kernel.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in KERNEL_TECHNOLOGY_TOKENS:
            if token in text:
                found.append(f"{path.name} contains platform token {token!r}")
    return found


def journal_port_violations(root: Path) -> list[str]:
    """Journal port is generic; JSONL and fsync belong to the adapter."""
    found: list[str] = []
    port = root / "kernel" / "journal.py"
    text = port.read_text(encoding="utf-8")
    for token in JOURNAL_PORT_FORBIDDEN:
        if token in text:
            found.append(f"{port.name} must not contain {token!r}")
    adapter = root / "adapters" / "journal" / "jsonl.py"
    adapter_text = adapter.read_text(encoding="utf-8")
    if "class JsonlJournal" not in adapter_text:
        found.append("JsonlJournal adapter must exist")
    if "os.fsync" not in adapter_text:
        found.append("JsonlJournal adapter must own fsync")
    return found


def package_import_violations(root: Path) -> list[str]:
    """Importing machi must not load concrete providers."""
    text = (root / "__init__.py").read_text(encoding="utf-8")
    found: list[str] = []
    for token in ("machi.adapters", "from machi.adapters", "LinuxProc", "nvidia"):
        if token in text:
            found.append(f"machi/__init__.py must not contain {token!r}")
    return found


PREREQUISITE_DOMAIN_FORBIDDEN = (
    "subprocess",
    "shell=True",
    "amd-smi",
    "nvidia-smi",
    "rocm-smi",
    "from machi.adapters",
    "from machi.discover",
    "from machi.install",
    "ResourceManager",
    "DeploymentPlan",
    "DeploymentConfiguration",
    "ServingConfiguration",
    "OptimizerProvider",
    "GlobalOptimizer",
    "MetaOptimizer",
    "pip install",
)

PREREQUISITE_ADAPTER_FORBIDDEN = (
    "from machi.discover",
    "from machi.install",
    "ResourceManager",
    "DeploymentPlan",
    "OptimizerProvider",
    "shell=True",
    "nvidia-smi",
    "from amdsmi",
    "import amdsmi",
    "pynvml",
    "torch",
)


def prerequisite_boundary_violations(root: Path) -> list[str]:
    """2.5.1 domain orchestrates; adapters own host I/O; Discover stays read-only."""
    found: list[str] = []
    domain = root / "prerequisites"
    if not domain.exists():
        return ["prerequisites package is missing"]
    for path in sorted(domain.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in PREREQUISITE_DOMAIN_FORBIDDEN:
            if token in text:
                found.append(f"{path.name} must not contain {token!r}")
    adapter_root = root / "adapters" / "prerequisites"
    if not adapter_root.exists():
        found.append("prerequisite adapters package is missing")
        return found
    for path in sorted(adapter_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in PREREQUISITE_ADAPTER_FORBIDDEN:
            if token in text:
                found.append(f"{path.name} must not contain {token!r}")
    amd = adapter_root / "amd_smi.py"
    if not amd.exists():
        found.append("AMD vendor CLI prerequisite adapter is missing")
    else:
        amd_text = amd.read_text(encoding="utf-8")
        if "amd-smi" not in amd_text:
            found.append("AMD prerequisite adapter must inspect amd-smi")
        if "PyYAML" not in amd_text:
            found.append("AMD allowlist must include the first known pin")
        if "missing_module_name" not in amd_text:
            found.append("AMD adapter must use generic missing-module diagnosis")
    for path in sorted((root / "adapters" / "discover").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "machi.prerequisites" in text or "PrerequisiteReadiness" in text:
            found.append(f"{path.name} must not import PrerequisiteReadiness")
        if "pip" in text and "install" in text:
            found.append(f"{path.name} must not remediate packages")
    domain_init = (domain / "__init__.py").read_text(encoding="utf-8")
    if "machi.adapters" in domain_init:
        found.append("prerequisites package must not import adapters")
    main_text = (root / "main.py").read_text(encoding="utf-8")
    if "AmdSmiPrerequisiteAdapter" not in main_text:
        found.append("composition must wire AmdSmiPrerequisiteAdapter")
    if "PrerequisiteReadiness" not in main_text:
        found.append("composition must wire PrerequisiteReadiness")
    if "AmdAcceleratorProvider" in main_text:
        found.append("composition must not wire AmdAcceleratorProvider directly")
    kernel_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (root / "kernel").rglob("*.py")
    )
    if "machi.prerequisites" in kernel_text:
        found.append("Kernel must not import prerequisites")
    return found


CAPACITY_DOMAIN_FORBIDDEN = (
    "vllm",
    "ResourceManager",
    "DeploymentConfiguration",
    "shutil.rmtree",
    "0.8",
    "from machi.adapters",
    "from machi.prerequisites",
)

CAPACITY_SONAR_FORBIDDEN = (
    "shutil.rmtree",
    "vllm",
    "ResourceManager",
)


def capacity_boundary_violations(root: Path) -> list[str]:
    """Capacity derives envelopes. It does not admit, tune, or delete trees."""
    found: list[str] = []
    domain = root / "capacity"
    if not domain.is_dir():
        return ["capacity domain is missing"]
    for path in sorted(domain.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for token in CAPACITY_DOMAIN_FORBIDDEN:
            if token.lower() in text:
                found.append(f"{path.name} must not contain {token!r}")
    sonar = root / "adapters" / "capacity" / "sonar_file.py"
    if not sonar.is_file():
        found.append("capacity sonar file writer is missing")
    else:
        text = sonar.read_text(encoding="utf-8")
        for token in CAPACITY_SONAR_FORBIDDEN:
            if token in text:
                found.append(f"{sonar.name} must not contain {token!r}")
        if "O_EXCL" not in text:
            found.append("sonar writer must create an exclusive probe file")
        if ".machi-capacity-sonar-" not in text:
            found.append("sonar writer must use a Machi-owned probe name")
    main_text = (root / "main.py").read_text(encoding="utf-8")
    if "NativeCapacity" not in main_text:
        found.append("composition must wire NativeCapacity")
    return found


FOUNDATION_DOMAIN_FORBIDDEN = (
    "docker",
    "ollama",
    "huggingface",
    "subprocess",
    "resourcemanager",
    "from machi.adapters",
    "from machi.prerequisites",
)


def foundation_boundary_violations(root: Path) -> list[str]:
    """Foundation resolves and verifies vLLM. It does not serve or download models."""
    found: list[str] = []
    domain = root / "foundation"
    if not domain.is_dir():
        return ["foundation domain is missing"]
    for path in sorted(domain.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for token in FOUNDATION_DOMAIN_FORBIDDEN:
            if token in text:
                found.append(f"{path.name} must not contain {token!r}")
    process = root / "adapters" / "foundation" / "process.py"
    if "subprocess" not in process.read_text(encoding="utf-8"):
        found.append("native process runner must own subprocess")
    if "shell=True" in process.read_text(encoding="utf-8"):
        found.append("native process runner must not use a shell")
    provision_path = root / "adapters" / "foundation" / "provision.py"
    provision = provision_path.read_text(encoding="utf-8")
    if "api_server" in provision and "entrypoints" not in provision:
        found.append("verification must not launch a server")
    if "NativeProcessRunner" not in provision:
        found.append("provisioning must use the native process runner")
    main_text = (root / "main.py").read_text(encoding="utf-8")
    if "def inspect_foundation" not in main_text:
        found.append("composition must expose foundation inspection")
    return found


MODEL_DOMAIN_FORBIDDEN = (
    "huggingface",
    "subprocess",
    "docker",
    "from machi.adapters",
    "from machi.plan",
    "from machi.serve",
    "resourcemanager",
    "trust_remote_code=true",
)


def model_boundary_violations(root: Path) -> list[str]:
    """Model stores artifacts. It does not load weights or serve."""
    found: list[str] = []
    domain = root / "model"
    if not domain.is_dir():
        return ["model domain is missing"]
    for path in sorted(domain.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for token in MODEL_DOMAIN_FORBIDDEN:
            if token in text:
                found.append(f"{path.name} must not contain {token!r}")
    hub = root / "adapters" / "model" / "hub.py"
    if not hub.is_file():
        found.append("hub adapter is missing")
    else:
        hub_text = hub.read_text(encoding="utf-8")
        if "huggingface_hub" not in hub_text:
            found.append("hub adapter must own the hub client")
    local = root / "adapters" / "model" / "local.py"
    if "is_symlink" not in local.read_text(encoding="utf-8"):
        found.append("local import must reject symlinks")
    main_text = (root / "main.py").read_text(encoding="utf-8")
    if "def inspect_model" not in main_text:
        found.append("composition must expose model inspection")
    return found


STEWARD_DOMAIN_FORBIDDEN = (
    "shutil.rmtree",
    "os.walk",
    "os.unlink",
    "os.remove",
    "SAFE_STORAGE_BYTES",
    "ResourceManager",
    "DeploymentConfiguration",
    "ServingConfiguration",
    "from machi.adapters",
    "from machi.prerequisites",
    "NativeMountObserver",
    "umount",
)

STEWARD_ADAPTER_FORBIDDEN = (
    "shutil.rmtree",
    "os.unlink",
    "os.remove",
    "SAFE_STORAGE_BYTES",
    "ResourceManager",
    "DeploymentConfiguration",
    "umount",
    "from machi.prerequisites",
)


def steward_boundary_violations(root: Path) -> list[str]:
    """Steward classifies known roots. It does not delete or admit."""
    found: list[str] = []
    domain = root / "steward"
    if not domain.is_dir():
        return ["steward domain is missing"]
    for path in sorted(domain.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in STEWARD_DOMAIN_FORBIDDEN:
            if token in text:
                found.append(f"{path.name} must not contain {token!r}")
    adapter = root / "adapters" / "steward"
    if not adapter.is_dir():
        return [*found, "steward adapter is missing"]
    for path in sorted(adapter.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in STEWARD_ADAPTER_FORBIDDEN:
            if token in text:
                found.append(f"{path.name} must not contain {token!r}")
    native = (adapter / "native.py").read_text(encoding="utf-8")
    if "measure_owned_tree" not in native:
        found.append("native steward must measure only through the bounded helper")
    if "read_ownership" not in native:
        found.append("native steward must read Install evidence")
    main_text = (root / "main.py").read_text(encoding="utf-8")
    if "NativeSteward" not in main_text:
        found.append("composition must wire NativeSteward")
    if "def assess_steward" not in main_text:
        found.append("composition must expose steward assessment")
    return found

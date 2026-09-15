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
    "adapters": 3,
    "main": 4,
}

FORBIDDEN_TOP_LEVEL = frozenset({"kultrun"})

FUTURE_PACKAGES = frozenset(
    {
        "steward",
        "capacity",
        "foundation",
        "model",
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
    "HostId.generate",
    "FileStore",
    "MACHI_STATE_ROOT",
    "meminfo",
    "shutil.rmtree",
    "from machi.install",
    "from machi.adapters",
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
    "apple_accelerator",
    "parse_nvidia_smi_csv",
    "parse_apple_displays_json",
    "parse_amd_smi_json",
    "parse_intel_discovery_json",
    "amd-smi",
    "rocm-smi",
    "xpu-smi",
    "xpumcli",
    "amd_accelerator",
    "intel_accelerator",
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
    "system_profiler",
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

AMD_PROVIDER_FORBIDDEN = (
    "nvidia-smi",
    "query-gpu",
    "system_profiler",
    "SPDisplaysDataType",
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
    "import amdsmi",
    "from amdsmi",
    "/sys/class/drm",
    "rocm-smi",
)

INTEL_PROVIDER_FORBIDDEN = (
    "nvidia-smi",
    "query-gpu",
    "system_profiler",
    "SPDisplaysDataType",
    "amd-smi",
    "rocm-smi",
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
    "sycl-ls",
    "level_zero",
    "/sys/class/drm",
    "import ze",
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
    if "AppleAcceleratorProvider" not in accelerator_text:
        found.append(
            "native accelerator observer must compose AppleAcceleratorProvider"
        )
    if "AmdAcceleratorProvider" not in accelerator_text:
        found.append("native accelerator observer must compose AmdAcceleratorProvider")
    if "IntelAcceleratorProvider" not in accelerator_text:
        found.append(
            "native accelerator observer must compose IntelAcceleratorProvider"
        )
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
    amd_provider = root / "adapters" / "discover" / "amd_accelerator.py"
    amd_text = amd_provider.read_text(encoding="utf-8")
    for token in AMD_PROVIDER_FORBIDDEN:
        if token in amd_text:
            found.append(f"{amd_provider.name} must not contain {token!r}")
    if "amd-smi" not in amd_text:
        found.append("AMD provider must use amd-smi")
    if "--json" not in amd_text:
        found.append("AMD provider must request JSON")
    if "parse_amd_smi_json" not in amd_text:
        found.append("AMD provider must own JSON parsing")
    if "LIST_ARGV" not in amd_text or "STATIC_ARGV" not in amd_text:
        found.append("AMD provider must declare read-only argv constants")
    intel_provider = root / "adapters" / "discover" / "intel_accelerator.py"
    intel_text = intel_provider.read_text(encoding="utf-8")
    for token in INTEL_PROVIDER_FORBIDDEN:
        if token in intel_text:
            found.append(f"{intel_provider.name} must not contain {token!r}")
    if "xpu-smi" not in intel_text:
        found.append("Intel provider must use xpu-smi")
    if "xpumcli" not in intel_text:
        found.append("Intel provider must allow xpumcli as alternate executable")
    if "parse_intel_discovery_json" not in intel_text:
        found.append("Intel provider must own JSON parsing")
    if "max_mem" not in intel_text:
        found.append("Intel provider must name Max Mem Alloc Size so it can ignore it")
    kernel_text = "\n".join(
        p.read_text(encoding="utf-8") for p in (root / "kernel").rglob("*.py")
    )
    if "machi.discover" in kernel_text or "OSArchitectureObservation" in kernel_text:
        found.append("Kernel must not import Discover")
    if "MemoryObservation" in kernel_text:
        found.append("Kernel must not import MemoryObservation")
    if "AcceleratorObservation" in kernel_text:
        found.append("Kernel must not import AcceleratorObservation")
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
        found.append(
            "composition must wire NativeAcceleratorObserver, "
            "not IntelAcceleratorProvider"
        )
    for token in (
        "nvidia-smi",
        "cuda",
        "nvml",
        "pynvml",
        "system_profiler",
        "amd-smi",
        "rocm-smi",
        "xpu-smi",
        "xpumcli",
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

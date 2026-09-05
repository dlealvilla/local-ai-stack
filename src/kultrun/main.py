"""The composition root.

The only module that names a concrete adapter alongside a core type.
Everything above it depends on ports; this is where ports meet
implementations, which is what makes "core owns concepts, adapters own
implementations" an arrangement rather than an aspiration.

Until Stage 0.3 this job was done by the test suite, which was the honest
way to prove the seams were real before there was a program to run.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from kultrun.adapters.host import hwloc, native_linux, nvidia
from kultrun.adapters.install import apt
from kultrun.adapters.persistence import file_store

# Contract registration is a side effect of import, so the catalogue the
# Platform API serves would otherwise list only whatever the control plane
# happened to reach. The composition root is the right place to import the
# whole set: assembling the platform includes establishing what shapes it
# speaks in.
from kultrun.analytics import contracts as _analytics_contracts  # noqa: F401
from kultrun.api.contracts import ApiRequest, ApiResponse
from kultrun.api.router import Router
from kultrun.api.routes import ControlPlane, register
from kultrun.audit import contracts as _audit_contracts  # noqa: F401
from kultrun.capacity import contracts as _capacity_contracts  # noqa: F401
from kultrun.components.contracts import ComponentNecessity, ComponentRequirement
from kultrun.entitlement import contracts as _entitlement_contracts  # noqa: F401
from kultrun.evidence import contracts as _evidence_contracts  # noqa: F401
from kultrun.host import contracts as _host_contracts  # noqa: F401
from kultrun.host.discovery import HostDiscoveryService
from kultrun.host.inventory import HostInventory
from kultrun.host.ports import HostDiscoveryProvider
from kultrun.inference import contracts as _inference_contracts  # noqa: F401
from kultrun.install.preparation import ComponentProvisioner, Preparation
from kultrun.kernel.build import identity as build_identity
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.config import ConfigSchema, Configuration
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.kernel.registry import AdapterRegistry
from kultrun.kernel.schema import validate_registry
from kultrun.knowledge import contracts as _knowledge_contracts  # noqa: F401
from kultrun.model import contracts as _model_contracts  # noqa: F401
from kultrun.platform.approval import ApprovalLog
from kultrun.platform.contracts import (
    ComponentHealth,
    HealthStatus,
    PhaseReport,
    PlatformSettings,
    StartupReport,
)
from kultrun.platform.health import HealthAggregator
from kultrun.platform.startup import Startup, StoreReconcilePhase
from kultrun.platform.state import PlatformStateStore
from kultrun.policy import contracts as _policy_contracts  # noqa: F401
from kultrun.resource import contracts as _resource_contracts  # noqa: F401
from kultrun.storage import contracts as _storage_contracts  # noqa: F401
from kultrun.training import contracts as _training_contracts  # noqa: F401

PLATFORM_VERSION = "0.1.0"


#: The one component Stage 1.1 requires. Stated here, in the composition
#: root, because which discovery tooling Kultrun prefers is a build-time
#: choice rather than something `host` should know: the domain reports that a
#: provider was unavailable and never asks for it to be installed.
HWLOC_REQUIREMENT = ComponentRequirement(
    component=Name("hwloc"),
    necessity=ComponentNecessity.REQUIRED,
    purpose=(
        "general host topology discovery: CPU, cores, NUMA, memory and the "
        "PCI tree. Preferred initial provider; not a core dependency"
    ),
    minimum_version="2.0",
    probe_command="hwloc-info",
)


class _HostDiscoveryPhase:
    """Adapts `host` to the control plane's startup port.

    `platform` declares `ReconcilePhase` at tier 8, so a tier-2 domain cannot
    implement it directly without importing upward. The domain therefore
    reports facts and this adapter grades them — which is where grading
    belongs anyway, since "degraded" depends on the whole platform's state
    rather than on one subsystem's view of itself.
    """

    phase = Name("host-discovery")
    component = Name("host-discovery")

    def __init__(self, inventory: HostInventory) -> None:
        self._inventory = inventory

    def reconcile(self) -> PhaseReport:
        try:
            outcome = self._inventory.establish()
        except Exception as error:
            return PhaseReport(
                phase=self.phase,
                succeeded=False,
                detail=f"host discovery failed: {error}",
            )
        # As with preparation: the phase ran. A host that could not be
        # observed is a defect and a degraded health report, not a refusal
        # to start — the Platform API is the only surface an administrator
        # has for finding out why.
        return PhaseReport(
            phase=self.phase,
            succeeded=True,
            detail=f"{outcome.change.value}: {outcome.detail}",
            defects=self._inventory.defects(),
        )

    def check_health(self) -> ComponentHealth:
        if not self._inventory.is_loaded:
            return ComponentHealth(
                component=self.component,
                status=HealthStatus.UNKNOWN,
                detail="host discovery has not run",
            )
        unavailable = self._inventory.unavailable_providers()
        if unavailable:
            return ComponentHealth(
                component=self.component,
                status=HealthStatus.DEGRADED,
                detail=f"providers unavailable: {', '.join(unavailable)}",
            )
        return ComponentHealth(component=self.component, status=HealthStatus.HEALTHY)


@dataclass(frozen=True, slots=True)
class Platform:
    """An assembled, started platform."""

    router: Router
    plane: ControlPlane
    settings: PlatformSettings
    startup_report: StartupReport
    hosts: HostInventory
    preparation: Preparation

    def call(self, request: ApiRequest) -> ApiResponse:
        """Invoke the Platform API without a transport."""
        return self.router.handle(request)


def config_schema() -> ConfigSchema:
    """The configuration sections the platform recognises."""
    schema = ConfigSchema()
    schema.register("platform", PlatformSettings)
    return schema


def store_registry() -> AdapterRegistry[Store]:
    """The record-store implementations available to this build."""
    registry: AdapterRegistry[Store] = AdapterRegistry("kernel.persistence.Store")
    registry.register("file", file_store.build)
    return registry


def build(
    configuration: Configuration | None = None,
    *,
    clock: Clock | None = None,
    store_adapter: str = "file",
    providers: Sequence[HostDiscoveryProvider] | None = None,
    requirements: Sequence[ComponentRequirement] | None = None,
    provisioners: Sequence[ComponentProvisioner] | None = None,
) -> Platform:
    """Assemble the platform and run its startup path.

    Startup runs here rather than lazily, because a platform that has not
    reconciled has not established what it owns, and answering an API call
    before that would be answering from a state nobody has verified.
    """
    validate_registry(module_prefix="kultrun.")

    resolved_clock = clock or SystemClock()
    resolved_config = configuration or config_schema().load({})
    settings = resolved_config.section(PlatformSettings)

    store = store_registry().create(store_adapter, Path(settings.state_root))

    state = PlatformStateStore(store, resolved_clock, PLATFORM_VERSION)
    approvals = ApprovalLog(store, resolved_clock)

    # Preparation runs before discovery, never after: `host` observes what is
    # present and never asks for anything to be installed.
    preparation = Preparation(
        [HWLOC_REQUIREMENT] if requirements is None else requirements,
        [apt.build()] if provisioners is None else provisioners,
        clock=resolved_clock,
        may_provision=settings.may_provision_components,
    )
    discovery = HostDiscoveryService(
        [
            hwloc.build(resolved_clock),
            nvidia.build(resolved_clock),
            native_linux.build(resolved_clock),
        ]
        if providers is None
        else providers,
        clock=resolved_clock,
    )
    hosts = HostInventory(discovery, store)
    host_phase = _HostDiscoveryPhase(hosts)

    startup = Startup(resolved_clock)
    startup.register(StoreReconcilePhase(store))
    startup.register(state)
    startup.register(preparation)
    startup.register(host_phase)

    health = HealthAggregator(resolved_clock)
    health.register(state)
    health.register(approvals)
    health.register(preparation)
    health.register(host_phase)

    report = startup.run(state=state)

    plane = ControlPlane(
        state=state,
        startup=startup,
        health=health,
        approvals=approvals,
        configuration=resolved_config,
        hosts=hosts,
    )
    return Platform(
        router=register(Router(), plane),
        plane=plane,
        settings=settings,
        startup_report=report,
        hosts=hosts,
        preparation=preparation,
    )


def serve() -> int:  # pragma: no cover - exercised by hand, not by L1 tests
    """Start the control plane and serve until interrupted."""
    from kultrun.adapters.http.server import serving

    platform = build()
    with serving(
        platform.router,
        address=platform.settings.api_address,
        port=platform.settings.api_port,
    ) as server:
        print(
            f"Kultrun control plane on http://{server.address}:{server.port}"
            f"{platform.router.prefix}/health"
        )
        try:
            while True:
                import time

                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return 0


def show_version() -> int:
    """Report which build this is.

    The first thing to run on a deployment target, and the reason the
    workflow can trust a remote observation: it names the source commit the
    running code came from, or says plainly that it came from a checkout and
    therefore cannot carry acceptance evidence.
    """
    identity = build_identity()
    print(identity.describe())
    print(f"  origin        {identity.origin.value}")
    print(f"  version       {identity.version}")
    print(f"  source commit {identity.source_commit or '-'}")
    print(f"  build id      {identity.build_id or '-'}")
    print(f"  built at      {identity.built_at or '-'}")
    standing = "acceptable" if identity.acceptable_as_evidence else "development only"
    print(f"  evidence      {standing}")
    return 0


def show_host() -> int:
    """Describe this host through the accepted Stage 1.1 discovery path.

    Product-owned inspection rather than a test script. Because source
    cannot be patched on a deployment target, the product has to be
    diagnosable from outside — so what an acceptance run needs to see is a
    command the product ships, not a harness copied alongside it.
    """
    platform = build()
    identity = build_identity()
    host = platform.hosts.current
    preparation = platform.preparation.last_outcome

    print(identity.describe())
    print(f"\nhost {host.host_id.value}  fingerprint {host.fingerprint}")
    print(f"  profile      {host.profile.value}")
    environment = host.operating_environment
    print(
        f"  system       {environment.os_name} {environment.os_version} "
        f"({environment.distribution or '-'}) {environment.architecture.value}"
    )
    print(f"  cpu          {host.cpu.model_name}")
    print(
        f"               {host.cpu.physical_cores} cores / "
        f"{host.cpu.logical_cores} threads"
    )
    print(f"  memory       {_bytes(host.memory.total_bytes)} total")
    for accelerator in host.accelerators:
        print(
            f"  accelerator  [{accelerator.index}] {accelerator.vendor.value} "
            f"{accelerator.model_name} "
            f"{_bytes(accelerator.memory_total_bytes)} "
            f"driver {accelerator.driver_version}"
        )
    if not host.accelerators:
        print("  accelerator  none detected")
    for mount in host.mounts:
        print(
            f"  mount        {mount.mount_point} {mount.filesystem_type} "
            f"{_bytes(mount.total_bytes)} total (reported; authorizes nothing)"
        )

    print("\ncomponents")
    for resolution in preparation.resolutions if preparation else ():
        print(
            f"  {resolution.component.value:12} {resolution.outcome.value:16} "
            f"version {resolution.resolved_version} from {resolution.source}"
        )

    print("\nproviders")
    for report in host.provider_reports:
        print(
            f"  {report.provider.value:14} {report.status.value:12} "
            f"{len(report.observations):3} observations"
        )
    for conflict in host.conflicts:
        settled = "resolved" if conflict.resolution else "UNRESOLVED"
        print(
            f"\nconflict at {conflict.path}: {settled} "
            f"({len(conflict.observations)} competing observations)"
        )
    return 0


def _bytes(value: object) -> str:
    """Bytes at a readable scale, or the unresolved marker.

    Scaled because the reference host reports a 2.15 PB network mount, and
    printing that as "2002393.6 GiB" invites a misreading in the one place
    an operator goes to understand what the platform thinks it has. Never
    invents a number: unresolved stays unknown.
    """
    if not isinstance(value, int):
        return "unknown"
    for unit, size in (
        ("PiB", 2**50),
        ("TiB", 2**40),
        ("GiB", 2**30),
        ("MiB", 2**20),
    ):
        if value >= size:
            return f"{value / size:.1f} {unit}"
    return f"{value} B"


COMMANDS: dict[str, Callable[[], int]] = {
    "version": show_version,
    "host": show_host,
    "serve": serve,
}


def main(argv: Sequence[str] | None = None) -> int:
    """The `kultrun` command.

    Deliberately three subcommands and no framework. Each exists because the
    workflow needs it: `version` identifies a deployed build, `host` lets a
    real-host run be observed without shipping a script beside the product,
    and `serve` is what the platform does.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in ("-h", "--help", "help"):
        print("usage: kultrun {" + ",".join(COMMANDS) + "}")
        return 0 if arguments else 2
    command = COMMANDS.get(arguments[0])
    if command is None:
        print(f"kultrun: unknown command {arguments[0]!r}", file=sys.stderr)
        print("usage: kultrun {" + ",".join(COMMANDS) + "}", file=sys.stderr)
        return 2
    return command()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""The composition root.

The only module that names a concrete adapter alongside a core type.
Everything above it depends on ports; this is where ports meet
implementations, which is what makes "core owns concepts, adapters own
implementations" an arrangement rather than an aspiration.

Until Stage 0.3 this job was done by the test suite, which was the honest
way to prove the seams were real before there was a program to run.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from kultrun.adapters.host import fixtures, hwloc, native_linux, nvidia
from kultrun.adapters.install import apt
from kultrun.adapters.persistence import file_store
from kultrun.adapters.storage import posix_reservation, replayed

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
from kultrun.capacity.envelope import CapacityService
from kultrun.components.contracts import ComponentNecessity, ComponentRequirement
from kultrun.entitlement import contracts as _entitlement_contracts  # noqa: F401
from kultrun.evidence import contracts as _evidence_contracts  # noqa: F401
from kultrun.host import contracts as _host_contracts  # noqa: F401
from kultrun.host.contracts import HostCapabilities, MountFacts
from kultrun.host.discovery import HostDiscoveryService
from kultrun.host.inventory import HostInventory
from kultrun.host.ports import HostDiscoveryProvider
from kultrun.inference import contracts as _inference_contracts  # noqa: F401
from kultrun.install.preparation import ComponentProvisioner, Preparation
from kultrun.kernel.build import identity as build_identity
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.config import ConfigSchema, Configuration
from kultrun.kernel.errors import ConfigError
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
from kultrun.storage.contracts import StorageSanityEvidence
from kultrun.storage.sanity import StorageSanityService
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
    #: Absolute, resolved once at startup. Absolute because a relative root
    #: would follow the working directory, and durable state that moves when
    #: an operator changes directory is state that will eventually be lost.
    capacity: CapacityService
    sanity: StorageSanityService
    #: Whether the facts came from this machine or from captured evidence.
    evidence_mode: EvidenceMode
    #: The captured shape being replayed, when one is.
    fixture_shape: str | None
    state_root: Path
    #: Whether the root was chosen rather than defaulted. An installed
    #: artifact that defaulted is warned about; it must not be silent.
    state_root_configured: bool

    def call(self, request: ApiRequest) -> ApiResponse:
        """Invoke the Platform API without a transport."""
        return self.router.handle(request)


#: Where a deployed instance is told to keep its records.
#:
#: One variable, not a configuration framework. `docs/DEBT.md` K-20 records
#: why: the installed artifact resolved `state_root` against the working
#: directory, so two invocations from different directories built two
#: unrelated state stores, and an environment variable set on the command
#: line silently did nothing. A general `KULTRUN_<SECTION>__<KEY>` overlay
#: would have to settle type coercion, nested tables and unknown-key
#: behaviour, which is a design decision rather than a fix — recorded as
#: K-22 and deliberately deferred.
STATE_ROOT_VARIABLE = "KULTRUN_STATE_ROOT"

#: Names a captured host shape to replay instead of inspecting this machine.
#:
#: The default development mode, and the reason a rented GPU host is a
#: laboratory rather than a home: the real parsers, normalization, capacity
#: policy and sanity controller all run, against evidence captured from a
#: machine that once existed. `docs/DEVELOPMENT_WORKFLOW.md`.
FIXTURE_VARIABLE = "KULTRUN_FIXTURE"


class EvidenceMode(StrEnum):
    """Where the platform's facts are coming from.

    Reported everywhere, because replayed evidence must never be mistaken
    for a live machine. Evidence captured in September, describing a host
    that has since been released, says nothing about anything running now.
    """

    LIVE_HOST = "live_host"
    FIXTURE_REPLAY = "fixture_replay"


def resolve_fixture(environment: Mapping[str, str] | None = None) -> str | None:
    """Which captured shape to replay, if any. None means inspect this host."""
    source = os.environ if environment is None else environment
    named = source.get(FIXTURE_VARIABLE, "").strip()
    if not named:
        return None
    if named in ("1", "true", "yes", "default"):
        return fixtures.DEFAULT_SHAPE
    return named


def resolve_configuration(
    environment: Mapping[str, str] | None = None,
) -> Configuration:
    """Build configuration from the deployment environment.

    Precedence is: an explicit `configuration` passed to :func:`build` wins,
    then this environment override, then the declared defaults. Resolution
    happens **here, in the composition root**, and the resolved value is
    handed down. No domain reads the environment for itself: a subsystem
    that consults `os.environ` cannot be tested or reasoned about, and its
    behaviour would depend on how the process happened to be launched.
    """
    source = os.environ if environment is None else environment
    configured = source.get(STATE_ROOT_VARIABLE, "").strip()
    overrides = {"state_root": configured} if configured else {}
    return config_schema().load({"platform": overrides} if overrides else {})


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
    fixture: str | None = None,
) -> Platform:
    """Assemble the platform and run its startup path.

    Startup runs here rather than lazily, because a platform that has not
    reconciled has not established what it owns, and answering an API call
    before that would be answering from a state nobody has verified.
    """
    validate_registry(module_prefix="kultrun.")

    resolved_clock = clock or SystemClock()
    resolved_config = configuration or resolve_configuration()
    settings = resolved_config.section(PlatformSettings)

    state_root = Path(settings.state_root).expanduser().resolve()
    store = store_registry().create(store_adapter, state_root)

    state = PlatformStateStore(store, resolved_clock, PLATFORM_VERSION)
    approvals = ApprovalLog(store, resolved_clock)

    # Preparation runs before discovery, never after: `host` observes what is
    # present and never asks for anything to be installed.
    shape = fixture if fixture is not None else resolve_fixture()
    if shape is not None and shape not in fixtures.available():
        raise ConfigError(
            "no such captured host shape",
            requested=shape,
            available=list(fixtures.available()),
        )
    mode = (
        EvidenceMode.FIXTURE_REPLAY if shape else EvidenceMode.LIVE_HOST
    )

    if providers is not None:
        resolved_providers: Sequence[HostDiscoveryProvider] = providers
    elif shape is not None:
        # The real parsers and the real normalization, against captured
        # observations. Only the source of evidence is substituted.
        resolved_providers = [
            hwloc.replay(fixtures.hwloc_xml(shape), resolved_clock),
            nvidia.replay(fixtures.nvidia_csv(shape), resolved_clock),
            native_linux.replay(fixtures.native_capture(shape), resolved_clock),
        ]
    else:
        resolved_providers = [
            hwloc.build(resolved_clock),
            nvidia.build(resolved_clock),
            native_linux.build(resolved_clock),
        ]

    # Replaying a shape must not provision anything on the machine doing the
    # replaying: the component requirement belongs to the captured host.
    preparation = Preparation(
        ([] if shape else [HWLOC_REQUIREMENT])
        if requirements is None
        else requirements,
        ([] if shape else [apt.build()]) if provisioners is None else provisioners,
        clock=resolved_clock,
        may_provision=settings.may_provision_components and shape is None,
    )
    discovery = HostDiscoveryService(resolved_providers, clock=resolved_clock)
    hosts = HostInventory(discovery, store)
    host_phase = _HostDiscoveryPhase(hosts)
    # Derived from host facts on every read, never stored: a persisted
    # envelope invites a stale number authorizing a present decision.
    capacity = CapacityService(clock=resolved_clock)
    # The probe is wired in but never invoked by a read. Whether to spend
    # real time and real bytes is an explicit action.
    # Fixture replay never reserves real space. The ladder, budgets, stop
    # reasons and interpretation are all the real implementation; only the
    # reservation primitive is replaced.
    sanity = StorageSanityService(
        replayed.build() if shape else posix_reservation.build(resolved_clock),
        store,
        clock=resolved_clock,
    )

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
        capacity=capacity,
        sanity=sanity,
        stored_sanity=lambda host: _stored_sanity_with(sanity, host),
        pool_fingerprint=lambda point: _fingerprint_of(hosts, point),
        evidence_mode=mode.value,
        fixture_shape=shape,
        fixture_description=_describe_fixture(shape),
        available_fixtures=fixtures.available(),
    )
    return Platform(
        router=register(Router(), plane),
        plane=plane,
        settings=settings,
        startup_report=report,
        hosts=hosts,
        preparation=preparation,
        capacity=capacity,
        sanity=sanity,
        evidence_mode=mode,
        fixture_shape=shape,
        state_root=state_root,
        state_root_configured=(
            settings.state_root != PlatformSettings().state_root
        ),
    )


def serve() -> int:  # pragma: no cover - exercised by hand, not by L1 tests
    """Start the control plane and serve until interrupted."""
    from kultrun.adapters.http.server import serving

    platform = build()
    _warn_if_state_root_defaulted(platform)
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


def _warn_if_state_root_defaulted(platform: Platform) -> None:
    """An installed artifact must not keep durable state silently under cwd.

    `docs/DEVELOPMENT_WORKFLOW.md` requires acceptance evidence to state
    which state root was used. Running from a source checkout is ordinary
    development and stays quiet; an installed artifact that fell back to a
    working-directory-relative default is told so, by name, with the fix.
    """
    if platform.state_root_configured or not build_identity().is_artifact:
        return
    print(
        f"warning: no state root configured; using {platform.state_root}\n"
        f"         set {STATE_ROOT_VARIABLE} to keep durable state in a "
        f"fixed location",
        file=sys.stderr,
    )


def show_host() -> int:
    """Describe this host through the accepted Stage 1.1 discovery path.

    Product-owned inspection rather than a test script. Because source
    cannot be patched on a deployment target, the product has to be
    diagnosable from outside — so what an acceptance run needs to see is a
    command the product ships, not a harness copied alongside it.
    """
    platform = build()
    _warn_if_state_root_defaulted(platform)
    identity = build_identity()
    host = platform.hosts.current
    preparation = platform.preparation.last_outcome

    print(identity.describe())
    chosen = "configured" if platform.state_root_configured else "default"
    print(f"  state root    {platform.state_root} ({chosen})")
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

    envelope = platform.capacity.compute(host, _stored_sanity(platform, host))
    print(f"\ncapacity  policy {envelope.policy_version}")
    print(
        f"  memory       reported {_bytes(envelope.memory.reported_bytes)} | "
        f"effective {_bytes(envelope.memory.effective_bytes)} | "
        f"safe {_bytes(envelope.memory.safe_bytes)}"
    )
    if envelope.memory_note:
        print(f"               {envelope.memory_note}")
    for entry in envelope.accelerators:
        print(
            f"  accel [{entry.index}]  reported "
            f"{_bytes(entry.memory.reported_bytes)} | "
            f"effective {_bytes(entry.memory.effective_bytes)} | "
            f"safe {_bytes(entry.memory.safe_bytes)}"
        )
    for pool in envelope.pools:
        print(
            f"  pool {pool.mount_point:11} reported "
            f"{_bytes(pool.space.reported_bytes)} | "
            f"effective {_bytes(pool.space.effective_bytes)} | "
            f"safe {_bytes(pool.space.safe_bytes)}  [{pool.requirement.value}]"
        )
    for defect in envelope.defects:
        print(f"  ! {defect}")

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


def _describe_fixture(shape_id: str | None) -> dict[str, str] | None:
    """What is honest to say about a replayed shape.

    Flattened here rather than passed as an adapter type, so the API layer
    reports it without importing an adapter.
    """
    if shape_id is None:
        return None
    shape = fixtures.SHAPES[shape_id]
    return {
        "shape_id": shape.shape_id,
        "description": shape.description,
        "captured": shape.captured,
        "evidence_level": shape.evidence_level,
        "deployment_profile": shape.deployment_profile,
        "note": shape.note,
    }


def _fingerprint_of(hosts: HostInventory, mount_point: str) -> str | None:
    """The pool fingerprint for a mount point, or None if it is not one."""
    mount = next(
        (m for m in hosts.current.mounts if m.mount_point == mount_point), None
    )
    return None if mount is None else _pool_fingerprint(mount)


def _stored_sanity_with(
    sanity: StorageSanityService, host: HostCapabilities
) -> dict[str, StorageSanityEvidence]:
    """Evidence already gathered, keyed by mount point. A lookup, never a probe."""
    found: dict[str, StorageSanityEvidence] = {}
    for mount in host.mounts:
        evidence = sanity.evidence_for(
            mount.mount_point,
            host_fingerprint=host.fingerprint,
            pool_fingerprint=_pool_fingerprint(mount),
        )
        if evidence is not None:
            found[mount.mount_point] = evidence
    return found


def _stored_sanity(
    platform: Platform, host: HostCapabilities
) -> dict[str, StorageSanityEvidence]:
    """Evidence already gathered, keyed by mount point.

    A lookup, never a probe. Reading capacity must not be able to cause
    filesystem work: the previous implementation put a search behind an
    innocent-looking read and spent 48 minutes there.
    """
    return _stored_sanity_with(platform.sanity, host)


def _pool_fingerprint(mount: MountFacts) -> str:
    """Enough pool identity to stop evidence being reused for another pool.

    Filesystem type and reported size: if either changes materially the
    thing underneath the mount point is not what was measured.
    """
    total = mount.total_bytes if isinstance(mount.total_bytes, int) else 0
    family = mount.filesystem_type if isinstance(mount.filesystem_type, str) else "?"
    return f"{family}:{total}"


def check_storage_sanity(arguments: Sequence[str]) -> int:
    """Run a bounded storage sanity check on one pool.

    Explicit by design. This reserves real space, and Kultrun has no
    execution or job lifecycle yet — making it automatic would mean running
    a long filesystem operation on a background thread, which is precisely
    how the previous implementation orphaned a 42,990 MiB probe file. Stage
    1.3 builds the seam that makes scheduling it safe.
    """
    if not arguments:
        print("usage: kultrun storage sanity-check <mount-point>", file=sys.stderr)
        return 2
    mount_point = arguments[0]

    platform = build()
    _warn_if_state_root_defaulted(platform)
    host = platform.hosts.current
    envelope = platform.capacity.compute(host, _stored_sanity(platform, host))
    pool = next(
        (p for p in envelope.pools if p.mount_point == mount_point), None
    )
    if pool is None:
        known = ", ".join(p.mount_point for p in envelope.pools) or "none"
        print(
            f"kultrun: {mount_point!r} is not a candidate storage pool "
            f"(known: {known})",
            file=sys.stderr,
        )
        return 2

    target = pool.space.effective_bytes
    if not isinstance(target, int) or target <= 0:
        print(
            f"kultrun: {mount_point} has no effective capacity to verify",
            file=sys.stderr,
        )
        return 2

    mount = next(m for m in host.mounts if m.mount_point == mount_point)
    print(
        f"reserving up to {_bytes(target)} on {mount_point} in "
        f"{_bytes(platform.sanity.policy.chunk_bytes)} units; this performs "
        f"real storage work"
    )
    evidence = platform.sanity.check(
        mount_point,
        policy_target_bytes=target,
        host_fingerprint=host.fingerprint,
        pool_fingerprint=_pool_fingerprint(mount),
    )
    print(f"\nstatus         {evidence.status.value}")
    print(f"stopped        {evidence.stop_reason.value}")
    print(f"policy target  {_bytes(evidence.policy_target_bytes)}")
    print(f"verified up to {_bytes(evidence.verified_lower_bound_bytes)}")
    print(f"failed at      {_bytes(evidence.observed_failure_upper_bytes)}")
    print(f"reserved total {_bytes(evidence.total_reserved_bytes)}")
    print(f"elapsed        {evidence.elapsed_seconds:.1f}s")
    cleaned = "verified" if evidence.cleanup_verified else "NOT VERIFIED"
    print(f"cleanup        {cleaned}")
    print(f"orphans        {evidence.orphans_removed} removed before starting")
    for attempt in evidence.attempts:
        print(
            f"  {_bytes(attempt.target_bytes):>10}  {attempt.outcome.value:16} "
            f"{attempt.duration_seconds:6.2f}s  {attempt.detail or ''}"
        )
    return 0


def _storage(arguments: Sequence[str]) -> int:
    """The `storage` command group."""
    if not arguments or arguments[0] != "sanity-check":
        print("usage: kultrun storage sanity-check <mount-point>", file=sys.stderr)
        return 2
    return check_storage_sanity(arguments[1:])


COMMANDS: dict[str, Callable[[Sequence[str]], int]] = {
    "version": lambda _: show_version(),
    "host": lambda _: show_host(),
    "storage": _storage,
    "serve": lambda _: serve(),
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
    return command(arguments[1:])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

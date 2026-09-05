"""The composition root.

The only module that names a concrete adapter alongside a core type.
Everything above it depends on ports; this is where ports meet
implementations, which is what makes "core owns concepts, adapters own
implementations" an arrangement rather than an aspiration.

Until Stage 0.3 this job was done by the test suite, which was the honest
way to prove the seams were real before there was a program to run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from kultrun.entitlement import contracts as _entitlement_contracts  # noqa: F401
from kultrun.evidence import contracts as _evidence_contracts  # noqa: F401
from kultrun.host import contracts as _host_contracts  # noqa: F401
from kultrun.inference import contracts as _inference_contracts  # noqa: F401
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.config import ConfigSchema, Configuration
from kultrun.kernel.persistence import Store
from kultrun.kernel.registry import AdapterRegistry
from kultrun.kernel.schema import validate_registry
from kultrun.knowledge import contracts as _knowledge_contracts  # noqa: F401
from kultrun.model import contracts as _model_contracts  # noqa: F401
from kultrun.platform.approval import ApprovalLog
from kultrun.platform.contracts import PlatformSettings, StartupReport
from kultrun.platform.health import HealthAggregator
from kultrun.platform.startup import Startup, StoreReconcilePhase
from kultrun.platform.state import PlatformStateStore
from kultrun.policy import contracts as _policy_contracts  # noqa: F401
from kultrun.resource import contracts as _resource_contracts  # noqa: F401
from kultrun.storage import contracts as _storage_contracts  # noqa: F401
from kultrun.training import contracts as _training_contracts  # noqa: F401

PLATFORM_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class Platform:
    """An assembled, started platform."""

    router: Router
    plane: ControlPlane
    settings: PlatformSettings
    startup_report: StartupReport

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

    startup = Startup(resolved_clock)
    startup.register(StoreReconcilePhase(store))
    startup.register(state)

    health = HealthAggregator(resolved_clock)
    health.register(state)
    health.register(approvals)

    report = startup.run(state=state)

    plane = ControlPlane(
        state=state,
        startup=startup,
        health=health,
        approvals=approvals,
        configuration=resolved_config,
    )
    return Platform(
        router=register(Router(), plane),
        plane=plane,
        settings=settings,
        startup_report=report,
    )


def main() -> None:  # pragma: no cover - exercised by hand, not by L1 tests
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


if __name__ == "__main__":  # pragma: no cover
    main()

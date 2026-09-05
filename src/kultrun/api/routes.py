"""The Stage 0.3 endpoints.

All read-only. The Milestone 0 gate says the Platform API answers from
platform state, and at this stage there is nothing to mutate.

This module is where every later stage adds its surface, which is the point
of building it now. `docs/ROADMAP.md` Part II §4.6 makes an API surface part
of the definition of done for every stage, and that is only affordable if
adding one costs a handful of lines against a table that already exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from kultrun.api.contracts import ApiRequest
from kultrun.api.router import Router
from kultrun.kernel.config import Configuration
from kultrun.kernel.errors import NotFoundError, PreconditionFailedError
from kultrun.kernel.schema import registered_contracts
from kultrun.platform.approval import ApprovalLog
from kultrun.platform.contracts import HealthReport, PlatformState, StartupReport
from kultrun.platform.health import HealthAggregator
from kultrun.platform.startup import Startup
from kultrun.platform.state import PlatformStateStore


@dataclass(frozen=True, slots=True)
class ControlPlane:
    """Everything the Platform API reads from.

    Assembled by the composition root. Holding it as one value rather than
    threading five arguments through every handler keeps the route table
    readable as the surface grows.
    """

    state: PlatformStateStore
    startup: Startup
    health: HealthAggregator
    approvals: ApprovalLog
    configuration: Configuration


def register(router: Router, plane: ControlPlane) -> Router:
    """Add the Stage 0.3 endpoints to a router."""

    def health(_: ApiRequest) -> HealthReport:
        return plane.health.report()

    def platform(_: ApiRequest) -> PlatformState:
        return plane.state.current

    def contracts(_: ApiRequest) -> list[dict[str, object]]:
        """The contract catalogue, straight from the kind registry.

        The Admin surface and the Admin Agent both need to know what shapes
        the platform speaks in, and deriving it from the registry means the
        answer cannot drift from the code.
        """
        return [
            {
                "kind": kind,
                "schema_version": version,
                "module": contract_type.__module__,
            }
            for (kind, version), contract_type in sorted(
                registered_contracts().items()
            )
            if contract_type.__module__.startswith("kultrun.")
        ]

    def configuration(_: ApiRequest) -> dict[str, object]:
        """Effective configuration, so an administrator sees what is in force.

        Not the file. The file is one input, and a setting that was defaulted
        looks identical to one that was set until provenance arrives at
        Stage 6.1.
        """
        return plane.configuration.effective()

    def startup(_: ApiRequest) -> StartupReport:
        report = plane.startup.last_report
        if report is None:
            raise PreconditionFailedError("startup has not run")
        return report

    def approvals(request: ApiRequest) -> object:
        approval_id = request.query.get("approval_id")
        if approval_id is None:
            return list(plane.approvals.all())
        found = plane.approvals.get(approval_id)
        if found is None:
            raise NotFoundError("no such approval", approval_id=approval_id)
        return found

    router.get("/health", health)
    router.get("/platform", platform)
    router.get("/contracts", contracts)
    router.get("/config", configuration)
    router.get("/startup", startup)
    router.get("/approvals", approvals)
    return router

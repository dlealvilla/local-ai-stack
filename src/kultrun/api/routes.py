"""The Stage 0.3 endpoints.

All read-only. The Milestone 0 gate says the Platform API answers from
platform state, and at this stage there is nothing to mutate.

This module is where every later stage adds its surface, which is the point
of building it now. `docs/ROADMAP.md` Part II §4.6 makes an API surface part
of the definition of done for every stage, and that is only affordable if
adding one costs a handful of lines against a table that already exists.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from kultrun.api.contracts import ApiRequest
from kultrun.api.router import Router
from kultrun.capacity.contracts import CapacityEnvelope, HeadroomPolicy
from kultrun.capacity.envelope import CapacityService
from kultrun.host.contracts import DeploymentProfile, HostCapabilities
from kultrun.host.inventory import HostInventory
from kultrun.host.profile import shape_of
from kultrun.kernel.build import identity as build_identity
from kultrun.kernel.config import Configuration
from kultrun.kernel.errors import (
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.schema import registered_contracts
from kultrun.platform.approval import ApprovalLog
from kultrun.platform.contracts import HealthReport, PlatformState, StartupReport
from kultrun.platform.health import HealthAggregator
from kultrun.platform.startup import Startup
from kultrun.platform.state import PlatformStateStore
from kultrun.storage.contracts import StorageSanityEvidence
from kultrun.storage.sanity import StorageSanityService, summarize


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
    hosts: HostInventory
    capacity: CapacityService
    sanity: StorageSanityService
    #: How the control plane turns host mounts into stored sanity evidence.
    #: Injected rather than computed here so `api` does not acquire storage
    #: logic; the composition root owns the wiring.
    stored_sanity: Callable[[HostCapabilities], dict[str, StorageSanityEvidence]]
    pool_fingerprint: Callable[[str], str | None]
    #: Whether the facts came from this machine or from captured evidence.
    evidence_mode: str
    #: The captured shape being replayed, when one is.
    fixture_shape: str | None
    #: What is honest to say about that shape. Injected by the composition
    #: root: only `main` may import an adapter, and which shapes exist is an
    #: adapter's knowledge rather than the API's.
    fixture_description: Mapping[str, str] | None
    available_fixtures: tuple[str, ...]


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

    def host(_: ApiRequest) -> HostCapabilities:
        return plane.hosts.current

    def host_profile(_: ApiRequest) -> dict[str, object]:
        """The profile and the reason for it.

        The reason matters more than the tier. An administrator on unusual
        hardware needs to know what is and is not validated, and a bare
        label does not say.
        """
        current = plane.hosts.current
        return {
            "profile": current.profile.value,
            "shape": shape_of(current).describe(),
            "fingerprint": current.fingerprint,
            "earned_by": (
                "L2 real-host discovery on this shape"
                if current.profile is not DeploymentProfile.EXPERIMENTAL
                else "no acceptance evidence for this shape"
            ),
        }

    def host_providers(_: ApiRequest) -> list[dict[str, object]]:
        """Which providers were consulted, and how each fared.

        This is what turns "the GPU is missing" into "the vendor tool did not
        load", which is the difference between a support ticket and a fix.
        """
        return [
            {
                "provider": report.provider.value,
                "status": report.status.value,
                "observations": len(report.observations),
                "detail": report.detail,
            }
            for report in plane.hosts.current.provider_reports
        ]

    def version(_: ApiRequest) -> dict[str, object]:
        """Which build is answering.

        On the API too, not only the CLI: when a result arrives over HTTP,
        the surface that produced it is the one that has to identify itself.
        """
        identity = build_identity()
        return {
            "version": identity.version,
            "origin": identity.origin.value,
            "source_commit": identity.source_commit,
            "build_id": identity.build_id,
            "built_at": identity.built_at,
            "acceptable_as_evidence": identity.acceptable_as_evidence,
        }

    def mode(_: ApiRequest) -> dict[str, object]:
        """Where this instance's facts come from.

        The console shows this prominently, and it is the reason it can:
        replayed evidence describes a machine that has since been released,
        so presenting it as live would be a lie the product told itself
        first. Every consumer gets the same answer from the same place.
        """
        replaying = plane.fixture_shape is not None
        return {
            "evidence_mode": plane.evidence_mode,
            "physical_host_connected": not replaying,
            "storage_evidence_kind": (
                "replayed_test_evidence"
                if replaying
                else "live_empirical_verification"
            ),
            "fixture": dict(plane.fixture_description)
            if plane.fixture_description
            else None,
            "available_fixtures": list(plane.available_fixtures),
        }

    def storage_sanity(_: ApiRequest) -> dict[str, object]:
        """Empirical storage evidence, and the probe policy behind it.

        A read. It reports what has been established and never establishes
        anything: a capacity read that allocated storage is the previous
        implementation's mistake with a new name.
        """
        policy = plane.sanity.policy
        return {
            "evidence": summarize(plane.sanity.all_evidence()),
            "policy": {
                "version": policy.version,
                "first_checkpoint_bytes": policy.first_checkpoint_bytes,
                "growth_factor": policy.growth_factor,
                "max_checkpoints": policy.max_checkpoints,
                "chunk_bytes": policy.chunk_bytes,
                "time_budget_seconds": policy.time_budget_seconds,
                "work_budget_bytes": policy.work_budget_bytes,
            },
            "method": "explicit action only; never triggered by a read",
            "evidence_kind": (
                "replayed_test_evidence"
                if plane.fixture_shape is not None
                else "live_empirical_verification"
            ),
        }

    def run_storage_sanity(request: ApiRequest) -> StorageSanityEvidence:
        """Run a bounded sanity check on one pool. **POST only.**

        The one mutation the console offers. It reserves real space, so it
        is unreachable by GET and therefore cannot be triggered by loading
        or refreshing a page.
        """
        mount_point = request.query.get("mount_point", "").strip()
        if not mount_point:
            raise ValidationError(
                "a mount point is required", parameter="mount_point"
            )
        host = plane.hosts.current
        envelope = plane.capacity.compute(host, plane.stored_sanity(host))
        pool = next(
            (p for p in envelope.pools if p.mount_point == mount_point), None
        )
        if pool is None:
            raise NotFoundError(
                "no such candidate storage pool",
                mount_point=mount_point,
                known=[p.mount_point for p in envelope.pools],
            )
        target = pool.space.effective_bytes
        fingerprint = plane.pool_fingerprint(mount_point)
        if not isinstance(target, int) or target <= 0 or fingerprint is None:
            raise ValidationError(
                "this pool has no effective capacity to verify",
                mount_point=mount_point,
            )
        return plane.sanity.check(
            mount_point,
            policy_target_bytes=target,
            host_fingerprint=host.fingerprint,
            pool_fingerprint=fingerprint,
        )

    def capacity(_: ApiRequest) -> CapacityEnvelope:
        """What this host can safely give, with all three layers visible.

        All three deliberately, not just the safe figure. An administrator
        asking why a model will not run needs to see that a pool reports
        two petabytes while only a bounded amount is treated as effective —
        a single number would hide exactly the distinction that keeps the
        platform safe.
        """
        host = plane.hosts.current
        return plane.capacity.compute(host, plane.stored_sanity(host))

    def capacity_policy(_: ApiRequest) -> HeadroomPolicy:
        """The headroom policy in force, so a decision stays explicable."""
        return plane.capacity.policy

    router.get("/capacity", capacity)
    router.get("/storage/sanity", storage_sanity)
    router.post("/storage/sanity-check", run_storage_sanity)
    router.get("/capacity/policy", capacity_policy)
    router.get("/mode", mode)
    router.get("/version", version)
    router.get("/health", health)
    router.get("/host", host)
    router.get("/host/profile", host_profile)
    router.get("/host/providers", host_providers)
    router.get("/platform", platform)
    router.get("/contracts", contracts)
    router.get("/config", configuration)
    router.get("/startup", startup)
    router.get("/approvals", approvals)
    return router

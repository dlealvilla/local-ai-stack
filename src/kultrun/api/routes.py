"""The Platform API endpoints.

Reads answer from platform state. Mutations that exist are explicit POST
routes and never run on GET, so a page load cannot start a process or
reserve storage.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from kultrun.api.contracts import ApiRequest
from kultrun.api.router import Router
from kultrun.capacity.contracts import CapacityEnvelope, HeadroomPolicy
from kultrun.capacity.envelope import CapacityService
from kultrun.execution.contracts import ExecutionId, ExecutorCapabilityProfile
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import DeploymentProfile, HostCapabilities
from kultrun.host.inventory import HostInventory
from kultrun.host.profile import shape_of
from kultrun.inference.contracts import InstanceId, ObservedState
from kultrun.inference.service import InstanceService
from kultrun.kernel.build import identity as build_identity
from kultrun.kernel.config import Configuration
from kultrun.kernel.errors import (
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import registered_contracts
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.model.acquisition import AcquisitionService, request_from_entry
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import ArtifactId
from kultrun.model.inventory import ModelInventory
from kultrun.planning.contracts import CompatibilityVerdict
from kultrun.planning.service import SelectionService
from kultrun.platform.admission import AdmissionService
from kultrun.platform.approval import ApprovalLog
from kultrun.platform.contracts import HealthReport, PlatformState, StartupReport
from kultrun.platform.deployment_plan import (
    DeploymentPlanningService,
    DeploymentPlanOverview,
)
from kultrun.platform.deployment_prepare import DeploymentPreparationService
from kultrun.platform.eligibility import catalog_facts, runtime_compatibility
from kultrun.platform.health import HealthAggregator
from kultrun.platform.launch import executor_spec_from
from kultrun.platform.model_selection import ModelSelectionService
from kultrun.platform.requirement import (
    RequirementAssessment,
    assess_catalog,
    assessment_payload,
)
from kultrun.platform.startup import Startup
from kultrun.platform.state import PlatformStateStore
from kultrun.resource.contracts import RequestId, ReservationId
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.catalogue import RuntimeCatalogue
from kultrun.runtime.contracts import (
    EligibleModelView,
    RuntimeInstallationId,
    RuntimePolicy,
    RuntimeProvisioningPlanId,
    RuntimeResolverMode,
)
from kultrun.runtime.eligibility import ModelEligibilityService, view_payload
from kultrun.runtime.provision import ProvisioningService
from kultrun.runtime.resolve import path_presence, resolve
from kultrun.runtime.selection import FoundationSelectionService
from kultrun.runtime.verify import VerificationService
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
    executions: ExecutionService
    runtimes: RuntimeCatalogue
    models: ModelCatalogue
    selection: SelectionService
    inventory: ModelInventory
    acquisition: AcquisitionService
    resources: ResourceManager
    admission: AdmissionService
    instances: InstanceService
    provisioning: ProvisioningService
    verification: VerificationService
    foundation: FoundationSelectionService
    eligibility: ModelEligibilityService
    model_selection: ModelSelectionService
    deployment_plan: DeploymentPlanningService
    deployment_prepare: DeploymentPreparationService
    #: Adapter identity, e.g. native-process. A string so the API does not
    #: import an adapter module.
    executor_identity: str
    #: Capability probe for the container executor. Composition-owned.
    container_capability: Callable[[HostCapabilities], ExecutorCapabilityProfile]
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
            for (kind, version), contract_type in sorted(registered_contracts().items())
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
                "replayed_test_evidence" if replaying else "live_empirical_verification"
            ),
            "process_evidence_kind": "live_local_process",
            "host_evidence_kind": ("fixture_replay" if replaying else "live_host"),
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
            raise ValidationError("a mount point is required", parameter="mount_point")
        host = plane.hosts.current
        envelope = plane.capacity.compute(host, plane.stored_sanity(host))
        pool = next((p for p in envelope.pools if p.mount_point == mount_point), None)
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

    def runtime(_: ApiRequest) -> dict[str, object]:
        """Runtime profiles and every execution, observed now.

        Host/capacity evidence may be a fixture replay. Process evidence is
        always this machine: NativeProcessExecutor runs here. The two are
        not one "LIVE" flag.
        """
        return {
            "executor": {
                "identity": plane.executor_identity,
                "kind": (
                    "container"
                    if plane.executor_identity == "container-docker"
                    else "native_process"
                ),
            },
            "executor_capability": plane.executions.capabilities(plane.hosts.current),
            "container_executor_capability": plane.container_capability(
                plane.hosts.current
            ),
            "profiles": list(plane.runtimes.profiles()),
            "support": list(plane.runtimes.descriptors()),
            "executions": list(plane.executions.list()),
            "workload": "kultrun.adapters.runtime.reference_workload",
            "process_evidence": {
                "kind": "live_local_process",
                "summary": (
                    "NativeProcessExecutor ran on this machine. "
                    "Host and capacity evidence is independent."
                ),
            },
            "host_evidence_mode": plane.evidence_mode,
            "controls": {
                "start_reference": True,
                "stop": True,
                "arbitrary_command": False,
            },
        }

    def runtime_candidates(request: ApiRequest) -> dict[str, object]:
        """Declared support, current host, and current executors. Read-only."""
        host = plane.hosts.current
        requested = (request.query.get("runtime") or "").strip()
        allow_test = (request.query.get("allow_test_only") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        allow_reference = (request.query.get("allow_reference") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        policy = RuntimePolicy(
            mode=(
                RuntimeResolverMode.EXPLICIT if requested else RuntimeResolverMode.AUTO
            ),
            requested_runtime=requested if requested else NOT_PROVIDED,
            allow_test_only=allow_test,
            allow_reference_runtimes=allow_reference,
        )
        descriptors = plane.runtimes.descriptors()
        required = [
            component.value
            for descriptor in descriptors
            for component in descriptor.required_components
        ]
        resolution = resolve(
            host,
            (
                plane.executions.capabilities(host),
                plane.container_capability(host),
            ),
            descriptors,
            policy,
            components=path_presence(required),
        )
        foundation = plane.foundation.view(
            host,
            _executors(host),
            descriptors,
            policy,
            components=path_presence(required),
        )
        return {
            "host_id": host.host_id.value,
            "host_fingerprint": host.fingerprint,
            "policy": {
                "mode": policy.mode.value,
                "requested_runtime": requested or None,
            },
            "resolution": resolution,
            "foundation": {
                "selection_mode": foundation.selection.selection_mode.value,
                "resolver_mode": policy.mode.value,
                "recommended_candidate_id": (
                    foundation.selection.recommended_candidate_id
                    if isinstance(foundation.selection.recommended_candidate_id, str)
                    else None
                ),
                "selected_candidate_id": (
                    foundation.selection.selected_candidate_id
                    if isinstance(foundation.selection.selected_candidate_id, str)
                    else None
                ),
                "downstream_stale": foundation.selection.downstream_stale,
            },
            "mutations": False,
            "provision": False,
            "verify": False,
            "install": False,
        }

    def _executors(
        host: HostCapabilities,
    ) -> tuple[ExecutorCapabilityProfile, ExecutorCapabilityProfile]:
        return (
            plane.executions.capabilities(host),
            plane.container_capability(host),
        )

    def _components() -> dict[str, str]:
        required = [
            component.value
            for descriptor in plane.runtimes.descriptors()
            for component in descriptor.required_components
        ]
        return path_presence(required)

    def _eligible_view(host: HostCapabilities) -> EligibleModelView:
        return plane.eligibility.evaluate(
            host,
            _executors(host),
            plane.runtimes.descriptors(),
            catalog_facts(plane.models),
            RuntimePolicy(),
            components=_components(),
        )

    def _runtime_compat(
        host: HostCapabilities,
    ) -> tuple[EligibleModelView, dict[str, CompatibilityVerdict]]:
        view = _eligible_view(host)
        mapping = runtime_compatibility(
            view,
            [entry.metadata.model_id.value for entry in plane.models.entries()],
        )
        return view, mapping

    def _assessments(
        host: HostCapabilities,
    ) -> tuple[EligibleModelView, CapacityEnvelope, tuple[RequirementAssessment, ...]]:
        view = _eligible_view(host)
        envelope = plane.capacity.compute(host, plane.stored_sanity(host))
        rows = assess_catalog(
            view,
            plane.models,
            envelope,
            plane.selection.estimator,
            plane.selection.policy,
        )
        return view, envelope, rows

    def _selected_runtime(view: EligibleModelView) -> str:
        token = view.runtime
        return token if isinstance(token, str) and token.strip() else ""

    def _selected_version(view: EligibleModelView) -> Maybe[str]:
        token = view.runtime_version
        return token if isinstance(token, str) else NOT_PROVIDED

    def create_provisioning_plan(request: ApiRequest) -> object:
        """Create an exact install plan. Does not install."""
        candidate_id = (request.query.get("candidate_id") or "").strip()
        if not candidate_id:
            raise ValidationError(
                "a candidate id is required", parameter="candidate_id"
            )
        host = plane.hosts.current
        return plane.provisioning.create_plan(
            candidate_id,
            host,
            _executors(host),
            plane.runtimes.descriptors(),
            RuntimePolicy(),
            components=_components(),
        )

    def provision_runtime(request: ApiRequest) -> object:
        """Install a persisted plan. Does not verify the engine."""
        plan_id = (request.query.get("plan_id") or "").strip()
        if not plan_id:
            raise ValidationError("a plan id is required", parameter="plan_id")
        retry = (request.query.get("retry") or "").lower() in {"1", "true", "yes"}
        host = plane.hosts.current
        return plane.provisioning.provision(
            RuntimeProvisioningPlanId.parse(plan_id),
            host,
            _executors(host),
            plane.runtimes.descriptors(),
            components=_components(),
            retry=retry,
        )

    def list_provisioning_plans(_: ApiRequest) -> dict[str, object]:
        items = plane.provisioning.plans()
        return {
            "plans": list(items),
            "count": len(items),
            "mutations": False,
            "verify": False,
        }

    def list_installations(_: ApiRequest) -> dict[str, object]:
        items = plane.provisioning.installations()
        return {
            "installations": list(items),
            "count": len(items),
            "verify_on_get": False,
            "mutations": False,
        }

    def verify_runtime(request: ApiRequest) -> object:
        """Probe an exact installation. Does not provision or load a model."""
        installation_id = (request.query.get("installation_id") or "").strip()
        if not installation_id:
            raise ValidationError(
                "an installation id is required", parameter="installation_id"
            )
        host = plane.hosts.current
        return plane.verification.verify(
            RuntimeInstallationId.parse(installation_id),
            host,
            _executors(host),
        )

    def list_capability_profiles(_: ApiRequest) -> dict[str, object]:
        host = plane.hosts.current
        items = plane.verification.profiles(host, _executors(host))
        return {
            "profiles": list(items),
            "count": len(items),
            "mutations": False,
            "verify_on_get": False,
        }

    def get_capability_profile(request: ApiRequest) -> object:
        installation_id = (request.query.get("installation_id") or "").strip()
        if not installation_id:
            raise ValidationError(
                "an installation id is required", parameter="installation_id"
            )
        host = plane.hosts.current
        profile = plane.verification.profile_for(
            RuntimeInstallationId.parse(installation_id),
            host,
            _executors(host),
        )
        if profile is None:
            raise NotFoundError(
                "no capability profile for this installation",
                installation_id=installation_id,
            )
        return profile

    def _foundation_policy(request: ApiRequest) -> RuntimePolicy:
        requested = (request.query.get("runtime") or "").strip()
        allow_test = (request.query.get("allow_test_only") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        allow_reference = (request.query.get("allow_reference") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        return RuntimePolicy(
            mode=(
                RuntimeResolverMode.EXPLICIT if requested else RuntimeResolverMode.AUTO
            ),
            requested_runtime=requested if requested else NOT_PROVIDED,
            allow_test_only=allow_test,
            allow_reference_runtimes=allow_reference,
        )

    def runtime_foundation(request: ApiRequest) -> dict[str, object]:
        """Recommended versus selected foundation. GET does not realize."""
        host = plane.hosts.current
        policy = _foundation_policy(request)
        overview = plane.foundation.view(
            host,
            _executors(host),
            plane.runtimes.descriptors(),
            policy,
            components=_components(),
        )
        payload = overview.payload()
        payload["host_id"] = host.host_id.value
        return payload

    def select_foundation(request: ApiRequest) -> dict[str, object]:
        """Persist AUTO or MANUAL selection. Does not provision or verify."""
        mode = (request.query.get("mode") or "").strip().lower()
        candidate_id = (request.query.get("candidate_id") or "").strip()
        host = plane.hosts.current
        policy = _foundation_policy(request)
        args = (
            host,
            _executors(host),
            plane.runtimes.descriptors(),
            policy,
        )
        if mode == "auto":
            overview = plane.foundation.select_auto(*args, components=_components())
        elif mode == "manual":
            overview = plane.foundation.select_manual(
                candidate_id, *args, components=_components()
            )
        else:
            raise ValidationError("mode must be auto or manual", parameter="mode")
        payload = overview.payload()
        payload["host_id"] = host.host_id.value
        payload["mutations"] = True
        return payload

    def realize_foundation(request: ApiRequest) -> object:
        """Provision the selected candidate. Does not verify or switch."""
        retry = (request.query.get("retry") or "").lower() in {"1", "true", "yes"}
        host = plane.hosts.current
        return plane.foundation.realize_selected(
            host,
            _executors(host),
            plane.runtimes.descriptors(),
            RuntimePolicy(),
            components=_components(),
            retry=retry,
        )

    def verify_selected_foundation(_: ApiRequest) -> object:
        """Verify the selected installation. Does not switch foundation."""
        host = plane.hosts.current
        return plane.foundation.verify_selected(
            host,
            _executors(host),
            plane.runtimes.descriptors(),
            RuntimePolicy(),
            components=_components(),
        )

    def models(_: ApiRequest) -> dict[str, object]:
        """The curated candidate catalog. Read-only. No ranking, no download."""
        return {
            "source": {
                "identity": plane.models.source_identity.value,
                "kind": "huggingface_hub_identity",
                "live_fetch": False,
            },
            "candidates": list(plane.models.entries()),
            "ranking": False,
            "selection": False,
            "download": False,
        }

    def models_selection(_: ApiRequest) -> dict[str, object]:
        """Current feasible set, recommendation, and AUTO|MANUAL selection."""
        host = plane.hosts.current
        view, envelope, rows = _assessments(host)
        overview = plane.model_selection.view(host, view, envelope, rows)
        payload = overview.payload()
        stored = plane.foundation.stored(host)
        payload["foundation_stale"] = (
            stored.downstream_stale if stored is not None else False
        )
        payload["foundation_selection_mode"] = (
            stored.selection_mode.value if stored is not None else None
        )
        return payload

    def select_model(request: ApiRequest) -> dict[str, object]:
        """Persist AUTO or MANUAL model selection. Does not acquire or admit."""
        mode = (request.query.get("mode") or "").strip().lower()
        token = (
            request.query.get("model") or request.query.get("model_id") or ""
        ).strip()
        host = plane.hosts.current
        view, envelope, rows = _assessments(host)
        if mode == "auto" and not token:
            overview = plane.model_selection.select_auto(host, view, envelope, rows)
        elif mode == "manual" or (token and mode != "auto"):
            overview = plane.model_selection.select_manual(
                token, host, view, envelope, rows
            )
        else:
            raise ValidationError("mode must be auto or manual", parameter="mode")
        payload = overview.payload()
        stored = plane.foundation.stored(host)
        payload["foundation_stale"] = (
            stored.downstream_stale if stored is not None else False
        )
        payload["foundation_selection_mode"] = (
            stored.selection_mode.value if stored is not None else None
        )
        payload["mutations"] = True
        return payload

    def _plan_overview(
        host: HostCapabilities, *, persist: bool
    ) -> DeploymentPlanOverview:
        view, envelope, rows = _assessments(host)
        selection = plane.model_selection.view(host, view, envelope, rows)
        foundation = plane.foundation.stored(host)
        if persist:
            return plane.deployment_plan.refresh(
                host, view, envelope, rows, selection, foundation
            )
        return plane.deployment_plan.view(
            host, view, envelope, rows, selection, foundation
        )

    def deployments_plan(_: ApiRequest) -> dict[str, object]:
        """Authoritative current deployment plan. GET does not persist."""
        payload = _plan_overview(plane.hosts.current, persist=False).payload()
        payload["mutations"] = False
        return payload

    def refresh_deployments_plan(_: ApiRequest) -> dict[str, object]:
        """Persist the current plan from upstream state. Does not execute."""
        payload = _plan_overview(plane.hosts.current, persist=True).payload()
        payload["mutations"] = True
        return payload

    def acquire_deployment_plan(_: ApiRequest) -> dict[str, object]:
        """Acquire or reuse the CURRENT plan's exact artifact. Does not admit."""
        return plane.deployment_prepare.acquire(plane.hosts.current).payload()

    def admit_deployment_plan(request: ApiRequest) -> dict[str, object]:
        """Admit the CURRENT plan against a matching stored artifact. No instance."""
        raw = (request.query.get("artifact_id") or "").strip()
        artifact_id = ArtifactId.parse(raw) if raw else None
        return plane.deployment_prepare.admit(
            plane.hosts.current, artifact_id
        ).payload()

    def prepare_deployment_plan(_: ApiRequest) -> dict[str, object]:
        """Acquire/reuse then admit the CURRENT plan. Does not launch inference."""
        return plane.deployment_prepare.prepare(plane.hosts.current).payload()

    def models_requirements(_: ApiRequest) -> dict[str, object]:
        """Derived requirements and capacity. GET does not admit or acquire."""
        host = plane.hosts.current
        view, _envelope, rows = _assessments(host)
        return {
            "mutations": False,
            "acquire": False,
            "admit": False,
            "view_status": view.status.value,
            "selected_runtime": _selected_runtime(view) or None,
            "selected_runtime_version": (
                view.runtime_version if isinstance(view.runtime_version, str) else None
            ),
            "profile_id": view.profile_id if isinstance(view.profile_id, str) else None,
            "counts": {
                "ready": sum(
                    1 for item in rows if item.requirement_status.value == "ready"
                ),
                "refused": sum(
                    1 for item in rows if item.requirement_status.value == "refused"
                ),
                "unresolved": sum(
                    1 for item in rows if item.requirement_status.value == "unresolved"
                ),
                "stale": sum(
                    1 for item in rows if item.requirement_status.value == "stale"
                ),
                "unavailable": sum(
                    1 for item in rows if item.requirement_status.value == "unavailable"
                ),
                "feasible": sum(
                    1 for item in rows if item.capacity_verdict == "feasible"
                ),
                "infeasible": sum(
                    1 for item in rows if item.capacity_verdict == "infeasible"
                ),
                "not_assessed": sum(
                    1 for item in rows if item.capacity_verdict == "not_assessed"
                ),
            },
            "assessments": [assessment_payload(item) for item in rows],
        }

    def models_eligible(_: ApiRequest) -> dict[str, object]:
        """Runtime-aware eligible models. GET does not acquire or mutate."""
        host = plane.hosts.current
        payload = view_payload(_eligible_view(host))
        payload["host_id"] = host.host_id.value
        return payload

    def models_inventory(_: ApiRequest) -> dict[str, object]:
        """Plural stored artifacts. Stored is not running."""
        artifacts = list(plane.inventory.artifacts())
        extras = plane.models.extras()
        acceptance = None
        if extras:
            meta = extras[0].metadata
            acceptance = {
                "logical_name": meta.logical_name.value,
                "source_ref": meta.source_ref,
                "note": "bounded provider proof; not a recommendation",
            }
        return {
            "artifacts": artifacts,
            "count": len(artifacts),
            "running": [],
            "inference_instances": [],
            "stored_implies_running": False,
            "serving": False,
            "acceptance_target": acceptance,
            "provider": {
                "identity": plane.acquisition.provider_identity,
                "version": plane.acquisition.provider_version,
            },
            "catalog_candidates": [
                entry.metadata.logical_name.value for entry in plane.models.entries()
            ],
        }

    def acquire_model(request: ApiRequest) -> object:
        """Acquire a known candidate. No arbitrary URL or destination path."""
        _reject_arbitrary_destination(request)
        candidate = (request.query.get("candidate") or "").strip()
        recommended = (request.query.get("recommended") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if recommended and not candidate:
            return plane.deployment_prepare.acquire(plane.hosts.current).payload()
        if not candidate:
            raise ValidationError(
                "a known candidate is required", parameter="candidate"
            )
        entry = plane.models.acquirable(candidate)
        if entry is None:
            raise NotFoundError("no such candidate", candidate=candidate)
        host = plane.hosts.current
        envelope = plane.capacity.compute(host, plane.stored_sanity(host))
        return plane.acquisition.acquire(
            request_from_entry(entry), envelope, host.host_id
        )

    def delete_artifact(request: ApiRequest) -> object:
        """Delete one stored artifact. Not stop or unload."""
        _reject_arbitrary_destination(request)
        raw = (request.query.get("artifact_id") or "").strip()
        if not raw:
            raise ValidationError("an artifact id is required", parameter="artifact_id")
        return plane.acquisition.delete(
            ArtifactId.parse(raw), plane.hosts.current.host_id
        )

    def start_reference(request: ApiRequest) -> object:
        """Start the bounded reference workload. Empty body only."""
        _reject_arbitrary_command(request)
        launch = plane.runtimes.launch(Name("reference-process"))
        spec = executor_spec_from(launch)
        return plane.executions.start(plane.hosts.current.host_id, spec)

    def stop_execution(request: ApiRequest) -> object:
        """Stop one owned execution, or every owned running execution."""
        _reject_arbitrary_command(request)
        raw_id = (request.query.get("execution_id") or "").strip()
        if raw_id:
            return plane.executions.stop(ExecutionId.parse(raw_id))
        return list(plane.executions.stop_all_running())

    router.get("/capacity", capacity)
    router.get("/storage/sanity", storage_sanity)
    router.post("/storage/sanity-check", run_storage_sanity)
    router.get("/capacity/policy", capacity_policy)
    router.get("/runtime", runtime)
    router.get("/runtimes/candidates", runtime_candidates)
    router.post("/runtimes/provisioning-plans", create_provisioning_plan)
    router.post("/runtimes/provision", provision_runtime)
    router.get("/runtimes/provisioning-plans", list_provisioning_plans)
    router.get("/runtimes/installations", list_installations)
    router.post("/runtimes/verify", verify_runtime)
    router.get("/runtimes/capability-profiles", list_capability_profiles)
    router.get("/runtimes/capability-profile", get_capability_profile)
    router.get("/runtimes/foundation", runtime_foundation)
    router.post("/runtimes/foundation/select", select_foundation)
    router.post("/runtimes/foundation/realize", realize_foundation)
    router.post("/runtimes/foundation/verify", verify_selected_foundation)
    router.post("/runtime/execution", start_reference)
    router.post("/runtime/execution/stop", stop_execution)
    router.get("/models", models)
    router.get("/models/selection", models_selection)
    router.post("/models/selection", select_model)
    router.get("/deployments/plan", deployments_plan)
    router.post("/deployments/plan", refresh_deployments_plan)
    router.post("/deployments/plan/acquire", acquire_deployment_plan)
    router.post("/deployments/plan/admit", admit_deployment_plan)
    router.post("/deployments/plan/prepare", prepare_deployment_plan)
    router.get("/models/eligible", models_eligible)
    router.get("/models/requirements", models_requirements)

    def resources_summary(_: ApiRequest) -> object:
        """SAFE / RESERVED / AVAILABLE. Reserved is not running."""
        host = plane.hosts.current
        envelope = plane.capacity.compute(host, plane.stored_sanity(host))
        summary = plane.resources.summary(envelope)
        items = plane.instances.list()
        running = _running(items)
        return {
            "summary": summary,
            "instances": items,
            "serving": running > 0,
            "running_instances": running,
            "stored_implies_reserved": False,
            "reserved_implies_running": False,
            "fixed_stored_active_partition": False,
        }

    def list_reservations(request: ApiRequest) -> object:
        include = (request.query.get("include_released") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        items = plane.resources.reservations(include_released=include)
        live = {
            item.reservation_id.value
            for item in plane.instances.list()
            if item.reservation_id is not None
            and item.observed_state
            in {
                ObservedState.STARTING,
                ObservedState.RUNNING,
                ObservedState.STOPPING,
                ObservedState.UNKNOWN,
            }
        }
        return {
            "reservations": items,
            "count": len(items),
            "in_use_reservation_ids": sorted(live),
            "serving": bool(live),
            "running_instances": _running(plane.instances.list()),
            "reserved_implies_running": False,
            "fixed_stored_active_partition": False,
        }

    def reserve(request: ApiRequest) -> object:
        """Admit a STORED artifact. Client amounts are not authoritative."""
        _reject_arbitrary_destination(request)
        _reject_client_quantities(request)
        raw = (request.query.get("artifact_id") or "").strip()
        if not raw:
            raise ValidationError(
                "a stored artifact id is required", parameter="artifact_id"
            )
        token = (request.query.get("request_id") or "").strip()
        request_id = RequestId.parse(token) if token else None
        host = plane.hosts.current
        view, mapping = _runtime_compat(host)
        return plane.admission.reserve(
            ArtifactId.parse(raw),
            host,
            plane.stored_sanity(host),
            mapping,
            runtime=_selected_runtime(view) or "unresolved",
            runtime_version=_selected_version(view),
            request_id=request_id,
        )

    def release_reservation(request: ApiRequest) -> object:
        """Release a platform reservation. Not delete-model or stop."""
        _reject_arbitrary_destination(request)
        raw = (request.query.get("reservation_id") or "").strip()
        if not raw:
            raise ValidationError(
                "a reservation id is required", parameter="reservation_id"
            )
        return plane.admission.release(ReservationId.parse(raw))

    def list_instances(_: ApiRequest) -> object:
        items = plane.instances.list()
        return {
            "instances": items,
            "count": len(items),
            "fixed_stored_active_partition": False,
        }

    def create_instance(request: ApiRequest) -> object:
        """Create from a reservation. Clients do not invent argv or amounts."""
        _reject_arbitrary_command(request)
        _reject_arbitrary_destination(request)
        _reject_client_quantities(request)
        raw = (request.query.get("reservation_id") or "").strip()
        if not raw:
            raise ValidationError(
                "a reservation id is required", parameter="reservation_id"
            )
        reservation = plane.resources.get(ReservationId.parse(raw))
        if reservation is None:
            raise NotFoundError("no such reservation", reservation_id=raw)
        if reservation.artifact_id is None:
            raise PreconditionFailedError("reservation has no artifact")
        artifact = plane.inventory.get(reservation.artifact_id)
        if artifact is None:
            raise NotFoundError(
                "reservation artifact is missing",
                artifact_id=reservation.artifact_id.value,
            )
        return plane.instances.create(artifact, reservation)

    def start_instance(request: ApiRequest) -> object:
        _reject_arbitrary_command(request)
        _reject_arbitrary_destination(request)
        _reject_client_quantities(request)
        raw = (request.query.get("instance_id") or "").strip()
        if not raw:
            raise ValidationError("an instance id is required", parameter="instance_id")
        if request.query.get("serving_mode"):
            raise ValidationError("serving_mode is not a product parameter")
        host = plane.hosts.current
        envelope = plane.capacity.compute(host, plane.stored_sanity(host))
        return plane.instances.start(
            InstanceId.parse(raw),
            ledger_health=plane.resources.summary(envelope).health,
        )

    def stop_instance(request: ApiRequest) -> object:
        _reject_arbitrary_command(request)
        raw = (request.query.get("instance_id") or "").strip()
        if not raw:
            raise ValidationError("an instance id is required", parameter="instance_id")
        return plane.instances.stop(InstanceId.parse(raw))

    router.get("/models/inventory", models_inventory)
    router.post("/models/acquire", acquire_model)
    router.delete("/models/artifact", delete_artifact)
    router.get("/resources", resources_summary)
    router.get("/resources/reservations", list_reservations)
    router.post("/resources/reservations", reserve)
    router.delete("/resources/reservations", release_reservation)
    router.get("/inference/instances", list_instances)
    router.post("/inference/instances", create_instance)
    router.post("/inference/instances/start", start_instance)
    router.post("/inference/instances/stop", stop_instance)
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


_CLIENT_QUANTITY_KEYS = frozenset(
    {
        "ram_bytes",
        "vram_bytes",
        "accelerator_bytes",
        "unified_bytes",
        "admitted_ram_bytes",
        "admitted_vram_bytes",
        "cpu",
        "incremental_storage_bytes",
        "accelerator_index",
    }
)


def _reject_client_quantities(request: ApiRequest) -> None:
    """Callers identify a workload. They do not set authoritative amounts."""
    payload = request.body or {}
    keys = set(request.query) | {str(key) for key in payload}
    refused = sorted(keys & _CLIENT_QUANTITY_KEYS)
    if refused:
        raise ValidationError(
            "client resource quantities are not authoritative",
            refused=refused,
        )


_ARBITRARY_DESTINATION_KEYS = frozenset(
    {
        "path",
        "dest",
        "destination",
        "target",
        "url",
        "repo",
        "local_dir",
        "directory",
        "output",
        "output_dir",
    }
)


def _reject_arbitrary_destination(request: ApiRequest) -> None:
    """Ordinary product callers may not choose a URL or filesystem path."""
    payload = request.body or {}
    keys = set(request.query) | {str(key) for key in payload}
    refused = sorted(keys & _ARBITRARY_DESTINATION_KEYS)
    if refused:
        raise ValidationError(
            "arbitrary URLs and destination paths are not accepted",
            refused=refused,
        )


_ARBITRARY_COMMAND_KEYS = frozenset(
    {
        "executable",
        "command",
        "args",
        "arguments",
        "shell",
        "argv",
        "cmd",
    }
)


def _reject_arbitrary_command(request: ApiRequest) -> None:
    """The API starts one product-controlled workload, never a caller argv."""
    payload = request.body or {}
    keys = set(request.query) | {str(key) for key in payload}
    refused = sorted(keys & _ARBITRARY_COMMAND_KEYS)
    if refused:
        raise ValidationError(
            "arbitrary commands are not accepted; "
            "only the reference workload may be started",
            refused=refused,
        )


def _running(items: tuple[object, ...]) -> int:
    return sum(
        1
        for item in items
        if getattr(item, "observed_state", None) is ObservedState.RUNNING
    )

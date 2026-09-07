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
from kultrun.execution.contracts import ExecutionId
from kultrun.execution.service import ExecutionService
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
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import registered_contracts
from kultrun.model.acquisition import AcquisitionService, request_from_entry
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import ArtifactId
from kultrun.model.inventory import ModelInventory
from kultrun.planning.service import SelectionService, plan_from
from kultrun.platform.admission import AdmissionService
from kultrun.platform.approval import ApprovalLog
from kultrun.platform.contracts import HealthReport, PlatformState, StartupReport
from kultrun.platform.health import HealthAggregator
from kultrun.platform.launch import executor_spec_from
from kultrun.platform.startup import Startup
from kultrun.platform.state import PlatformStateStore
from kultrun.resource.contracts import RequestId, ReservationId
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.catalogue import RuntimeCatalogue
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
    #: Adapter identity, e.g. native-process. A string so the API does not
    #: import an adapter module.
    executor_identity: str
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
            "process_evidence_kind": "live_local_process",
            "host_evidence_kind": (
                "fixture_replay" if replaying else "live_host"
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

    def runtime(_: ApiRequest) -> dict[str, object]:
        """Runtime profiles and every execution, observed now.

        Host/capacity evidence may be a fixture replay. Process evidence is
        always this machine: NativeProcessExecutor runs here. The two are
        not one "LIVE" flag.
        """
        return {
            "executor": {
                "identity": plane.executor_identity,
                "kind": "native_process",
            },
            "profiles": list(plane.runtimes.profiles()),
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
        """Active-estimator selection. No dual estimates. No download."""
        host = plane.hosts.current
        envelope = plane.capacity.compute(host, plane.stored_sanity(host))
        recommendation = plane.selection.recommend(
            envelope=envelope,
            candidates=plane.models.entries(),
            available_runtimes=_inference_runtime_names(plane),
        )
        planned = plan_from(recommendation)
        return {
            "download": False,
            "estimator_mode": recommendation.estimator_mode,
            "estimator_provider": recommendation.estimator_provider,
            "estimator_version": recommendation.estimator_version,
            "requested_primary": recommendation.requested_primary,
            "fallback_used": recommendation.fallback_used,
            "fallback_reason": recommendation.fallback_reason,
            "policy_version": recommendation.policy_version,
            "outcome": recommendation.outcome.value,
            "recommendation": recommendation,
            "plan": planned,
        }

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
            host = plane.hosts.current
            envelope = plane.capacity.compute(host, plane.stored_sanity(host))
            recommendation = plane.selection.recommend(
                envelope=envelope,
                candidates=plane.models.entries(),
                available_runtimes=_inference_runtime_names(plane),
            )
            if recommendation.primary is None:
                raise PreconditionFailedError("no recommended candidate to acquire")
            candidate = recommendation.primary.logical_name.value
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
            raise ValidationError(
                "an artifact id is required", parameter="artifact_id"
            )
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
    router.post("/runtime/execution", start_reference)
    router.post("/runtime/execution/stop", stop_execution)
    router.get("/models", models)
    router.get("/models/selection", models_selection)
    def resources_summary(_: ApiRequest) -> object:
        """SAFE / RESERVED / AVAILABLE. Reserved is not running."""
        host = plane.hosts.current
        envelope = plane.capacity.compute(host, plane.stored_sanity(host))
        summary = plane.resources.summary(envelope)
        return {
            "summary": summary,
            "serving": False,
            "running_instances": 0,
            "stored_implies_reserved": False,
            "reserved_implies_running": False,
        }

    def list_reservations(request: ApiRequest) -> object:
        include = (request.query.get("include_released") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        items = plane.resources.reservations(include_released=include)
        return {
            "reservations": items,
            "count": len(items),
            "serving": False,
            "running_instances": 0,
            "reserved_implies_running": False,
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
        return plane.admission.reserve(
            ArtifactId.parse(raw),
            host,
            plane.stored_sanity(host),
            _inference_runtime_names(plane),
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

    router.get("/models/inventory", models_inventory)
    router.post("/models/acquire", acquire_model)
    router.delete("/models/artifact", delete_artifact)
    router.get("/resources", resources_summary)
    router.get("/resources/reservations", list_reservations)
    router.post("/resources/reservations", reserve)
    router.delete("/resources/reservations", release_reservation)
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


def _inference_runtime_names(plane: ControlPlane) -> tuple[str, ...]:
    """Runtime identities that can serve a model. The Stage 1.3 harness is not one."""
    return tuple(
        profile.runtime.value
        for profile in plane.runtimes.profiles()
        if profile.runtime.value != "reference-process"
    )

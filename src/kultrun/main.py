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

from kultrun.adapters.acquisition import fixture as fixture_acquisition
from kultrun.adapters.acquisition import huggingface as huggingface_acquisition
from kultrun.adapters.container.docker import DockerCliEngine
from kultrun.adapters.estimators import kultrun as kultrun_estimator
from kultrun.adapters.estimators import llmfit as llmfit_estimator
from kultrun.adapters.execution.container import ContainerExecutor
from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.host import fixtures, hwloc, native_linux, nvidia
from kultrun.adapters.install import apt
from kultrun.adapters.model_source.accelerate_fit import AccelerateStructuralProvider
from kultrun.adapters.model_source.candidates import acceptance_candidate
from kultrun.adapters.model_source.huggingface import HuggingFaceSource, hub_list_models
from kultrun.adapters.model_source.safetensors import (
    SafetensorsWeightEvidenceProvider,
    huggingface_safetensors_payload,
)
from kultrun.adapters.persistence import file_store
from kultrun.adapters.provisioning.fixture import FixtureRuntimeProvisioner
from kultrun.adapters.provisioning.vllm_native import VllmNativeProvisioner
from kultrun.adapters.runtime.reference import ReferenceProcessRuntime
from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.adapters.runtime.vllm import VllmModelCompatibility, VllmRuntimeSupport
from kultrun.adapters.runtime.vllm_memory import VllmMemoryInterpreter
from kultrun.adapters.storage import default_probe_registry, posix_reservation, replayed
from kultrun.adapters.storage.empirical_write import RealWritePort
from kultrun.adapters.verification.fixture import (
    FixtureProbeRunner,
    FixtureRuntimeVerifier,
)
from kultrun.adapters.verification.vllm_native import VllmNativeVerifier

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
from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.capacity.envelope import CapacityService
from kultrun.components.contracts import ComponentNecessity, ComponentRequirement
from kultrun.entitlement import contracts as _entitlement_contracts  # noqa: F401
from kultrun.evidence import contracts as _evidence_contracts  # noqa: F401
from kultrun.execution import contracts as _execution_contracts  # noqa: F401
from kultrun.execution.contracts import (
    ContainerExecutionConfig,
    ExecutionId,
    ExecutionState,
    ExecutorCapabilityProfile,
    ExecutorHandle,
)
from kultrun.execution.ports import Executor
from kultrun.execution.service import ExecutionService
from kultrun.host import contracts as _host_contracts  # noqa: F401
from kultrun.host.contracts import HostCapabilities, MountFacts
from kultrun.host.discovery import HostDiscoveryService
from kultrun.host.inventory import HostInventory
from kultrun.host.ports import HostDiscoveryProvider
from kultrun.inference import contracts as _inference_contracts  # noqa: F401
from kultrun.inference.contracts import ObservedState
from kultrun.inference.service import InstanceService
from kultrun.install.preparation import ComponentProvisioner, Preparation
from kultrun.kernel.build import identity as build_identity
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.config import ConfigSchema, Configuration
from kultrun.kernel.errors import ConfigError, PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.kernel.registry import AdapterRegistry
from kultrun.kernel.schema import validate_registry
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.knowledge import contracts as _knowledge_contracts  # noqa: F401
from kultrun.model import contracts as _model_contracts  # noqa: F401
from kultrun.model.acquisition import AcquisitionService
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.estimator_router import EstimatorRouter
from kultrun.model.inventory import ModelInventory
from kultrun.model.ports import ModelAcquisitionProvider, ModelRequirementEstimator
from kultrun.model.store import ModelArtifactStore
from kultrun.planning import contracts as _planning_contracts  # noqa: F401
from kultrun.planning.contracts import CompatibilityVerdict, DeploymentCapacity
from kultrun.planning.service import SelectionService
from kultrun.platform.admission import AdmissionService
from kultrun.platform.approval import ApprovalLog
from kultrun.platform.available_models import (
    AvailableModelsLock,
    AvailableModelsService,
    FunnelPass,
    format_available_models,
    format_funnel,
)
from kultrun.platform.capacity_snapshot import (
    planning_capacity,
    revalidation_plan_basis,
)
from kultrun.platform.contracts import (
    ComponentHealth,
    HealthStatus,
    PhaseReport,
    PlatformSettings,
    StartupReport,
)
from kultrun.platform.deployment_instance import DeploymentInstanceService
from kultrun.platform.deployment_plan import (
    DeploymentPlanLock,
    DeploymentPlanningService,
    DeploymentPlanOverview,
)
from kultrun.platform.deployment_prepare import DeploymentPreparationService
from kultrun.platform.eligibility import catalog_facts, runtime_compatibility
from kultrun.platform.foundation_realize import FoundationRealizeService
from kultrun.platform.health import HealthAggregator
from kultrun.platform.launch import executor_spec_from
from kultrun.platform.model_selection import (
    ModelSelectionLock,
    ModelSelectionOverview,
    ModelSelectionService,
)
from kultrun.platform.probe_run import ExecutorProbeRunner
from kultrun.platform.requirement import (
    RequirementAssessment,
)
from kultrun.platform.runtime_memory import (
    RuntimeMemoryCalibrationService,
    format_estimated_feasible,
    format_runtime_validation,
)
from kultrun.platform.startup import Startup, StoreReconcilePhase
from kultrun.platform.state import PlatformStateStore
from kultrun.platform.storage_acquire import StorageAwareAcquisition
from kultrun.policy import contracts as _policy_contracts  # noqa: F401
from kultrun.resource import contracts as _resource_contracts  # noqa: F401
from kultrun.resource.contracts import LedgerHealth
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.manager import ResourceManager
from kultrun.runtime import contracts as _runtime_contracts  # noqa: F401
from kultrun.runtime.catalogue import RuntimeCatalogue
from kultrun.runtime.contracts import (
    EligibleModelView,
    RuntimeInstallationId,
    RuntimePolicy,
    RuntimeProvisioningPlanId,
    RuntimeResolverMode,
    RuntimeSupportDescriptor,
    VerificationStatus,
)
from kultrun.runtime.eligibility import ModelEligibilityService
from kultrun.runtime.lock import ProvisioningLock, SelectionLock, VerificationLock
from kultrun.runtime.ports import RuntimeProvisioner, RuntimeVerifier
from kultrun.runtime.provision import ProvisioningService
from kultrun.runtime.resolve import path_presence, resolve
from kultrun.runtime.selection import FoundationSelectionService
from kultrun.runtime.verify import VerificationService
from kultrun.storage import contracts as _storage_contracts  # noqa: F401
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.contracts import StorageSanityEvidence
from kultrun.storage.index import StorageEvidenceIndex
from kultrun.storage.ownership import OwnershipService
from kultrun.storage.sanity import StorageSanityService
from kultrun.storage.sonar import EmpiricalStorageProbe
from kultrun.storage.topology import mount_for_path
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


class _ExecutionPhase:
    """Adapts `execution` to the control plane's startup and health ports.

    The domain reports facts (unverified leftover PIDs) and never grades
    them. Grading belongs here because "degraded" is a platform judgement.
    """

    phase = Name("execution")
    component = Name("execution")

    def __init__(self, executions: ExecutionService) -> None:
        self._executions = executions

    def reconcile(self) -> PhaseReport:
        try:
            detail = self._executions.reconcile()
        except Exception as error:
            return PhaseReport(
                phase=self.phase,
                succeeded=False,
                detail=f"execution reconcile failed: {error}",
            )
        leftovers = self._executions.unverified_count()
        return PhaseReport(
            phase=self.phase,
            succeeded=True,
            detail=detail,
            defects=() if leftovers == 0 else (detail,),
        )

    def check_health(self) -> ComponentHealth:
        leftovers = self._executions.unverified_count()
        if leftovers:
            return ComponentHealth(
                component=self.component,
                status=HealthStatus.DEGRADED,
                detail=f"{leftovers} unverified process(es) left unclaimed",
            )
        return ComponentHealth(
            component=self.component,
            status=HealthStatus.HEALTHY,
            detail="no unverified processes",
        )


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
    available_models: AvailableModelsService
    deployment_plan: DeploymentPlanningService
    deployment_prepare: DeploymentPreparationService
    deployment_instance: DeploymentInstanceService
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
ESTIMATOR_VARIABLE = "KULTRUN_MODEL_REQUIREMENT_ESTIMATOR"
ESTIMATOR_MODES = ("auto", "llmfit", "kultrun")
ACQUISITION_VARIABLE = "KULTRUN_MODEL_ACQUISITION_PROVIDER"
ACQUISITION_MODES = ("huggingface", "fixture")
SOURCE_MODE_VARIABLE = "KULTRUN_MODEL_SOURCE_MODE"
SOURCE_MODES = ("offline", "live")
EXECUTOR_VARIABLE = "KULTRUN_EXECUTOR"
PROVISIONER_VARIABLE = "KULTRUN_RUNTIME_PROVISIONER"
VERIFIER_VARIABLE = "KULTRUN_RUNTIME_VERIFIER"
CONTAINER_IMAGE_VARIABLE = "KULTRUN_CONTAINER_IMAGE"
LIVE_EXECUTORS = ("native-process", "container-docker")
REFERENCE_CONTAINER_IMAGE = "kultrun-reference-serving:stage-16a"


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
    estimator = source.get(ESTIMATOR_VARIABLE, "").strip()
    acquisition = source.get(ACQUISITION_VARIABLE, "").strip()
    source_mode = source.get(SOURCE_MODE_VARIABLE, "").strip()
    overrides: dict[str, object] = {}
    if configured:
        overrides["state_root"] = configured
    if estimator:
        overrides["model_requirement_estimator"] = estimator
    if acquisition:
        overrides["model_acquisition_provider"] = acquisition
    if source_mode:
        overrides["model_source_mode"] = source_mode
    return config_schema().load({"platform": overrides} if overrides else {})


def resolve_live_executor(
    environment: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """Which Executor the composition root wires as the live path."""
    source = os.environ if environment is None else environment
    named = source.get(EXECUTOR_VARIABLE, "native-process").strip() or "native-process"
    if named not in LIVE_EXECUTORS:
        raise ConfigError(
            "unknown executor",
            requested=named,
            known=list(LIVE_EXECUTORS),
        )
    image = source.get(CONTAINER_IMAGE_VARIABLE, "").strip()
    if named == "container-docker" and not image:
        raise ConfigError(
            "container executor requires an explicit image",
            variable=CONTAINER_IMAGE_VARIABLE,
        )
    return named, image or REFERENCE_CONTAINER_IMAGE


def config_schema() -> ConfigSchema:
    """The configuration sections the platform recognises."""
    schema = ConfigSchema()
    schema.register("platform", PlatformSettings)
    return schema


def estimator_registry() -> AdapterRegistry[ModelRequirementEstimator]:
    """Named requirement estimators. Composition picks the chain."""
    registry: AdapterRegistry[ModelRequirementEstimator] = AdapterRegistry(
        "model.ModelRequirementEstimator"
    )
    registry.register("kultrun", kultrun_estimator.build)
    registry.register("llmfit", llmfit_estimator.build)
    return registry


def acquisition_registry() -> AdapterRegistry[ModelAcquisitionProvider]:
    """Named acquisition providers. Composition picks the adapter."""
    registry: AdapterRegistry[ModelAcquisitionProvider] = AdapterRegistry(
        "model.ModelAcquisitionProvider"
    )
    registry.register("fixture", fixture_acquisition.build)
    registry.register("huggingface", huggingface_acquisition.build)
    return registry


def resolve_model_source(
    mode: str,
) -> tuple[
    HuggingFaceSource, SafetensorsWeightEvidenceProvider, AccelerateStructuralProvider
]:
    """Offline catalog, or optional live Hub/Accelerate extras. Not a plugin bus."""
    if mode not in SOURCE_MODES:
        raise ConfigError(
            "unknown model source mode",
            requested=mode,
            registered=list(SOURCE_MODES),
        )
    if mode == "live":
        return (
            HuggingFaceSource(list_models=hub_list_models),
            SafetensorsWeightEvidenceProvider(fetch=huggingface_safetensors_payload),
            AccelerateStructuralProvider(enabled=True),
        )
    return (
        HuggingFaceSource(),
        SafetensorsWeightEvidenceProvider(),
        AccelerateStructuralProvider(),
    )


def resolve_acquisition(name: str) -> ModelAcquisitionProvider:
    if name not in ACQUISITION_MODES:
        raise ConfigError(
            "unknown model acquisition provider",
            requested=name,
            registered=list(ACQUISITION_MODES),
        )
    return acquisition_registry().create(name)


def resolve_runtime_provisioner(
    name: str | None, *, fixture_host: bool
) -> RuntimeProvisioner:
    """Fixture on captured hosts; native vLLM on live hosts unless overridden."""
    chosen = (name or os.environ.get(PROVISIONER_VARIABLE) or "").strip()
    if not chosen:
        chosen = "fixture" if fixture_host else "vllm-native"
    if chosen == "fixture":
        return FixtureRuntimeProvisioner()
    if chosen in {"vllm-native", "vllm"}:
        return VllmNativeProvisioner()
    raise ConfigError(
        "unknown runtime provisioner",
        requested=chosen,
        registered=["fixture", "vllm-native"],
    )


def resolve_runtime_verifier(
    name: str | None, *, fixture_host: bool
) -> RuntimeVerifier:
    """Fixture on captured hosts; native vLLM on live hosts unless overridden."""
    chosen = (name or os.environ.get(VERIFIER_VARIABLE) or "").strip()
    if not chosen:
        chosen = "fixture" if fixture_host else "vllm-native"
    if chosen == "fixture":
        return FixtureRuntimeVerifier()
    if chosen in {"vllm-native", "vllm"}:
        return VllmNativeVerifier()
    raise ConfigError(
        "unknown runtime verifier",
        requested=chosen,
        registered=["fixture", "vllm-native"],
    )


def resolve_estimator(mode: str) -> ModelRequirementEstimator:
    """auto → llmfit then Kultrun; llmfit/kultrun stay strict."""
    if mode not in ESTIMATOR_MODES:
        raise ConfigError(
            "unknown model requirement estimator",
            requested=mode,
            registered=list(ESTIMATOR_MODES),
        )
    estimators = estimator_registry()
    if mode == "auto":
        return EstimatorRouter(
            mode="auto",
            providers=(estimators.create("llmfit"), estimators.create("kultrun")),
            allow_fallback=True,
        )
    return EstimatorRouter(
        mode=mode,
        providers=(estimators.create(mode),),
        allow_fallback=False,
    )


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
    acquisition_adapter: str | None = None,
    runtime_provisioner: str | None = None,
    runtime_verifier: str | None = None,
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
    ownership = OwnershipService(store, resolved_clock, state_root)
    storage_index = StorageEvidenceIndex(store)

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
    mode = EvidenceMode.FIXTURE_REPLAY if shape else EvidenceMode.LIVE_HOST

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
    empirical = (
        None
        if shape is not None
        else EmpiricalStorageProbe(
            RealWritePort(),
            resolved_clock,
            ownership,
        )
    )
    characterization = StorageCharacterizationService(
        resolved_clock,
        default_probe_registry(),
        ownership,
        empirical,
        use_live_native=shape is None,
    )
    chosen_executor, container_image = resolve_live_executor()
    container_executor = ContainerExecutor(
        DockerCliEngine(),
        ContainerExecutionConfig(image=container_image),
        resolved_clock,
    )
    live_executor: Executor
    if chosen_executor == "container-docker":
        live_executor = container_executor
    else:
        live_executor = NativeProcessExecutor(resolved_clock)
    executions = ExecutionService(live_executor, store)
    runtimes = RuntimeCatalogue(
        (
            ReferenceProcessRuntime(hold=True),
            ReferenceServingRuntime(),
            VllmRuntimeSupport(),
        )
    )
    source, weight_evidence, structural_evidence = resolve_model_source(
        settings.model_source_mode
    )
    models = ModelCatalogue(source, extras=(acceptance_candidate(),))
    selection = SelectionService(
        resolve_estimator(settings.model_requirement_estimator),
        resolved_clock,
    )
    artifact_store = ModelArtifactStore(state_root)
    inventory = ModelInventory(store, artifact_store)
    acquisition = AcquisitionService(
        resolve_acquisition(acquisition_adapter or settings.model_acquisition_provider),
        inventory,
        artifact_store,
        resolved_clock,
    )
    execution_phase = _ExecutionPhase(executions)

    startup = Startup(resolved_clock)
    startup.register(StoreReconcilePhase(store))
    startup.register(state)
    startup.register(preparation)
    startup.register(host_phase)
    startup.register(execution_phase)

    health = HealthAggregator(resolved_clock)
    health.register(state)
    health.register(approvals)
    health.register(preparation)
    health.register(host_phase)
    health.register(execution_phase)

    report = startup.run(state=state)
    discovered = hosts.current
    ownership.ensure_platform_roots(discovered.host_id)
    cheap = characterization.characterize(
        discovered,
        run_cleanup=True,
        run_empirical=False,
        probe_workspace=state_root,
    )
    storage_index.put_many(cheap.evidence)
    resources = ResourceManager(store, resolved_clock, AdmissionLock(state_root))
    try:
        actor_id = state.current.administrator_id
    except PreconditionFailedError:
        from kultrun.identity.contracts import SubjectId

        actor_id = SubjectId.generate()
    instances = InstanceService(
        store,
        resolved_clock,
        inventory,
        resources,
        executions,
        runtimes,
        live_executor=live_executor.identity.value,
    )
    instances.reconcile()
    runtime_installer = resolve_runtime_provisioner(
        runtime_provisioner, fixture_host=shape is not None
    )
    provisioning = ProvisioningService(
        store,
        resolved_clock,
        runtime_installer,
        state_root,
        ProvisioningLock(state_root),
    )
    provisioning.reconcile()
    runtime_checker = resolve_runtime_verifier(
        runtime_verifier, fixture_host=shape is not None
    )
    probe_runner = (
        FixtureProbeRunner()
        if isinstance(runtime_checker, FixtureRuntimeVerifier)
        else ExecutorProbeRunner(executions)
    )
    verification = VerificationService(
        store,
        resolved_clock,
        runtime_checker,
        probe_runner,
        state_root,
        VerificationLock(state_root),
    )
    current_host = hosts.current
    verification.reconcile(
        current_host,
        (
            executions.capabilities(current_host),
            container_executor.capabilities(current_host),
        ),
    )
    foundation = FoundationSelectionService(
        store,
        resolved_clock,
        provisioning,
        verification,
        SelectionLock(state_root),
        runtime_root=state_root / "runtimes",
    )
    foundation_realize = FoundationRealizeService(
        foundation,
        characterization,
        resources,
        capacity,
        state_root,
        storage_index,
        allow_empirical=shape is None,
    )
    storage_acquire = StorageAwareAcquisition(
        acquisition,
        resources,
        capacity,
        characterization,
        storage_index,
        state_root,
        allow_empirical=shape is None,
    )
    eligibility = ModelEligibilityService(
        resolved_clock,
        foundation,
        provisioning,
        verification,
        interpreters=(VllmModelCompatibility(),),
    )
    model_selection = ModelSelectionService(
        store,
        resolved_clock,
        selection,
        models,
        ModelSelectionLock(state_root),
    )

    def refresh_capacity(
        host: HostCapabilities,
    ) -> tuple[CapacityEnvelope, DeploymentCapacity]:
        live = capacity.compute(
            host, _stored_sanity_with(sanity, host), storage_index.for_host(host)
        )
        return live, planning_capacity(
            resources,
            live,
            host,
            storage_mount=mount_for_path(state_root / "models", host),
        )

    available_models = AvailableModelsService(
        store,
        resolved_clock,
        models,
        selection.estimator,
        selection.policy,
        AvailableModelsLock(state_root),
        weights=weight_evidence,
        structural=structural_evidence,
        inventory=inventory,
        calibrator=RuntimeMemoryCalibrationService(
            store,
            resolved_clock,
            VllmMemoryInterpreter(),
            acquisition=acquisition,
            inventory=inventory,
            resources=resources,
            executions=executions,
            runtime=runtimes.get(Name("vllm")),
            provisioning=provisioning,
            state_root=state_root,
        ),
        refresh_capacity=refresh_capacity,
    )
    deployment_plan = DeploymentPlanningService(
        store,
        resolved_clock,
        DeploymentPlanLock(state_root),
        live_executor.identity.value,
        selection.policy.policy_version,
    )
    admission = AdmissionService(
        resources,
        inventory,
        models,
        selection,
        capacity,
        store,
        resolved_clock,
        actor_id,
        reservation_in_use=instances.blocks_release,
        stored_storage=storage_index.for_host,
    )

    def _plan_overview_live(host: HostCapabilities) -> DeploymentPlanOverview:
        descriptors = runtimes.descriptors()
        view = eligibility.evaluate(
            host,
            (
                executions.capabilities(host),
                container_executor.capabilities(host),
            ),
            descriptors,
            catalog_facts(models),
            RuntimePolicy(),
            components=path_presence(
                [
                    component.value
                    for descriptor in descriptors
                    for component in descriptor.required_components
                ]
            ),
        )
        envelope = capacity.compute(
            host, _stored_sanity_with(sanity, host), storage_index.for_host(host)
        )
        stored_plan = deployment_plan.stored(host)
        bound = planning_capacity(
            resources,
            envelope,
            host,
            plan_basis=revalidation_plan_basis(
                stored_plan, model_selection.stored(host)
            ),
            storage_mount=mount_for_path(state_root / "models", host),
        )
        funnel = available_models.evaluate(host, view, envelope, bound, persist=False)
        chosen = model_selection.view(
            host, view, envelope, funnel.assessments, funnel.available
        )
        return deployment_plan.view(
            host, view, envelope, funnel.assessments, chosen, foundation.stored(host)
        )

    deployment_prepare = DeploymentPreparationService(
        _plan_overview_live,
        models,
        acquisition,
        inventory,
        admission,
        capacity,
        lambda host: _stored_sanity_with(sanity, host),
        resolved_clock,
        storage_acquire=storage_acquire,
    )
    deployment_instance = DeploymentInstanceService(
        _plan_overview_live,
        inventory,
        resources,
        instances,
        provisioning,
        state_root,
    )

    plane = ControlPlane(
        state=state,
        startup=startup,
        health=health,
        approvals=approvals,
        configuration=resolved_config,
        hosts=hosts,
        capacity=capacity,
        sanity=sanity,
        executions=executions,
        runtimes=runtimes,
        models=models,
        selection=selection,
        inventory=inventory,
        acquisition=acquisition,
        resources=resources,
        admission=admission,
        instances=instances,
        provisioning=provisioning,
        verification=verification,
        foundation=foundation,
        eligibility=eligibility,
        model_selection=model_selection,
        available_models=available_models,
        deployment_plan=deployment_plan,
        deployment_prepare=deployment_prepare,
        deployment_instance=deployment_instance,
        foundation_realize=foundation_realize,
        storage_acquire=storage_acquire,
        state_root=state_root,
        executor_identity=live_executor.identity.value,
        container_capability=container_executor.capabilities,
        stored_sanity=lambda host: _stored_sanity_with(sanity, host),
        stored_storage=storage_index.for_host,
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
        executions=executions,
        runtimes=runtimes,
        models=models,
        selection=selection,
        inventory=inventory,
        acquisition=acquisition,
        resources=resources,
        admission=admission,
        instances=instances,
        provisioning=provisioning,
        verification=verification,
        foundation=foundation,
        eligibility=eligibility,
        model_selection=model_selection,
        available_models=available_models,
        deployment_plan=deployment_plan,
        deployment_prepare=deployment_prepare,
        deployment_instance=deployment_instance,
        evidence_mode=mode,
        fixture_shape=shape,
        state_root=state_root,
        state_root_configured=(settings.state_root != PlatformSettings().state_root),
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

    envelope = platform.capacity.compute(
        host,
        _stored_sanity(platform, host),
        platform.plane.stored_storage(host),
    )
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
    envelope = platform.capacity.compute(
        host,
        _stored_sanity(platform, host),
        platform.plane.stored_storage(host),
    )
    pool = next((p for p in envelope.pools if p.mount_point == mount_point), None)
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


def start_reference_workload(platform: Platform, *, hold: bool) -> ExecutorHandle:
    """Compose the reference recipe and start it. Lives here, not in either domain."""
    launch = ReferenceProcessRuntime(hold=hold).launch_spec()
    spec = executor_spec_from(launch)
    return platform.executions.start(platform.hosts.current.host_id, spec)


def _runtime(arguments: Sequence[str]) -> int:
    """The `runtime` command group: start, status, stop the reference workload."""
    if not arguments or arguments[0] in ("-h", "--help"):
        print("usage: kultrun runtime {start,status,stop}", file=sys.stderr)
        return 0 if arguments else 2
    command = arguments[0]
    rest = list(arguments[1:])
    if command == "start":
        return _runtime_start(rest)
    if command == "status":
        return _runtime_status()
    if command == "stop":
        return _runtime_stop(rest)
    print(f"kultrun: unknown runtime command {command!r}", file=sys.stderr)
    print("usage: kultrun runtime {start,status,stop}", file=sys.stderr)
    return 2


def _runtimes(arguments: Sequence[str]) -> int:
    """Runtime candidates, selection, and provisioning. GET never installs."""
    if not arguments or arguments[0] in ("-h", "--help"):
        print(
            "usage: kultrun runtimes "
            "{candidates,foundation,select,plan,provision,realize,"
            "installations,verify,capabilities} [...]",
            file=sys.stderr,
        )
        return 0 if arguments else 2
    command = arguments[0]
    rest = list(arguments[1:])
    if command == "candidates":
        return show_runtime_candidates(rest)
    if command == "foundation":
        return show_foundation(rest)
    if command == "select":
        return select_foundation(rest)
    if command == "plan":
        return plan_runtime(rest)
    if command == "provision":
        return provision_runtime(rest)
    if command == "realize":
        return realize_foundation(rest)
    if command == "installations":
        return show_runtime_installations()
    if command == "verify":
        return verify_runtime(rest)
    if command == "capabilities":
        return show_runtime_capabilities()
    print(f"kultrun: unknown runtimes command {command!r}", file=sys.stderr)
    print(
        "usage: kultrun runtimes "
        "{candidates,foundation,select,plan,provision,realize,"
        "installations,verify,capabilities}",
        file=sys.stderr,
    )
    return 2


def show_runtime_candidates(arguments: Sequence[str]) -> int:
    """Print AUTO or EXPLICIT resolution from current host and executors."""
    requested: str | None = None
    allow_test = False
    allow_reference = False
    rest = list(arguments)
    index = 0
    while index < len(rest):
        token = rest[index]
        if token == "--runtime":
            if index + 1 >= len(rest):
                print("kultrun: --runtime needs a family name", file=sys.stderr)
                return 2
            requested = rest[index + 1]
            index += 2
            continue
        if token == "--allow-test-only":
            allow_test = True
            index += 1
            continue
        if token == "--allow-reference":
            allow_reference = True
            index += 1
            continue
        print(f"kultrun: unknown argument {token!r}", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host = platform.hosts.current
    executors = (
        platform.executions.capabilities(host),
        platform.plane.container_capability(host),
    )
    descriptors = platform.runtimes.descriptors()
    policy = RuntimePolicy(
        mode=(RuntimeResolverMode.EXPLICIT if requested else RuntimeResolverMode.AUTO),
        requested_runtime=requested if requested else NOT_PROVIDED,
        allow_test_only=allow_test,
        allow_reference_runtimes=allow_reference,
    )
    required = [
        component.value
        for descriptor in descriptors
        for component in descriptor.required_components
    ]
    resolution = resolve(
        host,
        executors,
        descriptors,
        policy,
        components=path_presence(required),
    )
    preferred = (
        resolution.preferred_candidate_id
        if is_resolved(resolution.preferred_candidate_id)
        else None
    )
    print(
        f"mode {policy.mode.value}  host {host.host_id.value}  "
        f"preferred {preferred or '-'}"
    )
    rows = (
        *resolution.candidates,
        *resolution.unresolved,
        *resolution.unsupported,
    )
    if not rows:
        print("no runtime candidates")
        for note in resolution.notes:
            print(f"  note {note}")
        return 0
    for item in rows:
        mark = "*" if preferred == item.candidate_id.value else "-"
        print(
            f"{mark} {item.candidate_id.value} {item.runtime.value:16} "
            f"{item.executor.value:18} {item.compatibility.value:12} "
            f"{item.support_tier.value:10} {item.reason}"
        )
    return 0


def _runtime_inputs(
    platform: Platform,
) -> tuple[
    HostCapabilities,
    tuple[ExecutorCapabilityProfile, ExecutorCapabilityProfile],
    tuple[RuntimeSupportDescriptor, ...],
    dict[str, str],
]:
    host = platform.hosts.current
    executors = (
        platform.executions.capabilities(host),
        platform.plane.container_capability(host),
    )
    descriptors = platform.runtimes.descriptors()
    components = path_presence(
        [
            component.value
            for descriptor in descriptors
            for component in descriptor.required_components
        ]
    )
    return host, executors, descriptors, components


def _eligible_view(platform: Platform) -> EligibleModelView:
    host, executors, descriptors, components = _runtime_inputs(platform)
    return platform.eligibility.evaluate(
        host,
        executors,
        descriptors,
        catalog_facts(platform.models),
        components=components,
    )


def _runtime_compat(platform: Platform) -> Mapping[str, CompatibilityVerdict]:
    view = _eligible_view(platform)
    return runtime_compatibility(
        view,
        [entry.metadata.model_id.value for entry in platform.models.entries()],
    )


def _funnel(
    platform: Platform,
    *,
    persist: bool = False,
    pending_model: str | None = None,
) -> FunnelPass:
    view = _eligible_view(platform)
    host = platform.hosts.current
    envelope = platform.capacity.compute(
        host,
        _stored_sanity(platform, host),
        platform.plane.stored_storage(host),
    )
    stored_plan = platform.deployment_plan.stored(host)
    return platform.available_models.evaluate(
        host,
        view,
        envelope,
        planning_capacity(
            platform.resources,
            envelope,
            host,
            plan_basis=revalidation_plan_basis(
                stored_plan,
                platform.model_selection.stored(host),
                pending_model=pending_model,
            ),
            storage_mount=mount_for_path(platform.plane.state_root / "models", host),
        ),
        persist=persist,
    )


def _assessments(
    platform: Platform,
    *,
    pending_model: str | None = None,
) -> tuple[EligibleModelView, CapacityEnvelope, tuple[RequirementAssessment, ...]]:
    result = _funnel(platform, pending_model=pending_model)
    return result.eligible, result.envelope, result.assessments


def _model_overview(platform: Platform) -> ModelSelectionOverview:
    host = platform.hosts.current
    result = _funnel(platform)
    return platform.model_selection.view(
        host, result.eligible, result.envelope, result.assessments, result.available
    )


def _deployment_overview(
    platform: Platform, *, persist: bool = False
) -> DeploymentPlanOverview:
    host = platform.hosts.current
    result = _funnel(platform)
    selection = platform.model_selection.view(
        host, result.eligible, result.envelope, result.assessments, result.available
    )
    foundation = platform.foundation.stored(host)
    if persist:
        return platform.deployment_plan.refresh(
            host,
            result.eligible,
            result.envelope,
            result.assessments,
            selection,
            foundation,
        )
    return platform.deployment_plan.view(
        host,
        result.eligible,
        result.envelope,
        result.assessments,
        selection,
        foundation,
    )


def _selected_runtime(view: EligibleModelView) -> str:
    token = view.runtime
    return token if isinstance(token, str) and token.strip() else ""


def show_foundation(arguments: Sequence[str]) -> int:
    """Print recommended versus selected foundation. Does not realize."""
    del arguments
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host, executors, descriptors, components = _runtime_inputs(platform)
    overview = platform.foundation.view(
        host,
        executors,
        descriptors,
        components=components,
        storage_evidence=platform.plane.stored_storage(host),
        require_storage=True,
    )
    selection = overview.selection
    recommended = (
        selection.recommended_candidate_id
        if isinstance(selection.recommended_candidate_id, str)
        else "-"
    )
    selected = (
        selection.selected_candidate_id
        if isinstance(selection.selected_candidate_id, str)
        else "-"
    )
    print(
        f"selection {selection.selection_mode.value}  "
        f"resolver {overview.resolution.policy.mode.value}  "
        f"recommended {recommended}  selected {selected}  "
        f"stale {str(selection.downstream_stale).lower()}"
    )
    if not overview.candidates:
        print("no foundation candidates")
        return 0
    for item in overview.candidates:
        mark = "*" if item.selected else "-"
        print(
            f"{mark} {item.candidate_id} {item.role:24} "
            f"{item.confidence.value:20} "
            f"{item.profile_status or 'unverified'}"
        )
    return 0


def select_foundation(arguments: Sequence[str]) -> int:
    """Persist AUTO or MANUAL selection. Does not provision."""
    mode = "auto"
    candidate: str | None = None
    rest = list(arguments)
    index = 0
    while index < len(rest):
        token = rest[index]
        if token == "--auto":
            mode = "auto"
            index += 1
            continue
        if token == "--candidate":
            if index + 1 >= len(rest):
                print("kultrun: --candidate needs an id", file=sys.stderr)
                return 2
            mode = "manual"
            candidate = rest[index + 1]
            index += 2
            continue
        print(f"kultrun: unknown argument {token!r}", file=sys.stderr)
        return 2
    if mode == "manual" and not candidate:
        print("usage: kultrun runtimes select --auto|--candidate <id>", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host, executors, descriptors, components = _runtime_inputs(platform)
    if mode == "auto":
        overview = platform.foundation.select_auto(
            host,
            executors,
            descriptors,
            components=components,
            storage_evidence=platform.plane.stored_storage(host),
            require_storage=True,
        )
    else:
        overview = platform.foundation.select_manual(
            candidate or "",
            host,
            executors,
            descriptors,
            components=components,
            storage_evidence=platform.plane.stored_storage(host),
            require_storage=True,
        )
    selected = (
        overview.selection.selected_candidate_id
        if isinstance(overview.selection.selected_candidate_id, str)
        else "-"
    )
    print(
        f"selection {overview.selection.selection_mode.value}  "
        f"selected {selected}  "
        f"generation {overview.selection.generation}"
    )
    return 0


def realize_foundation(arguments: Sequence[str]) -> int:
    """Provision the selected foundation. Does not verify or switch."""
    retry = "--retry" in arguments
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host, executors, descriptors, components = _runtime_inputs(platform)
    installation = platform.plane.foundation_realize.realize(
        host,
        executors,
        descriptors,
        components=components,
        retry=retry,
    )
    print(
        f"installation {installation.installation_id.value}  "
        f"{installation.status.value}  "
        f"{installation.runtime.value}=={installation.runtime_version}  "
        f"attempts {installation.attempt_count}"
    )
    if installation.status.value == "failed":
        return 1
    return 0


def plan_runtime(arguments: Sequence[str]) -> int:
    """Persist an exact provisioning plan for one candidate."""
    if not arguments:
        print("usage: kultrun runtimes plan <candidate-id>", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host = platform.hosts.current
    plan = platform.provisioning.create_plan(
        arguments[0],
        host,
        (
            platform.executions.capabilities(host),
            platform.plane.container_capability(host),
        ),
        platform.runtimes.descriptors(),
        RuntimePolicy(),
        components=path_presence(
            [
                component.value
                for descriptor in platform.runtimes.descriptors()
                for component in descriptor.required_components
            ]
        ),
    )
    print(
        f"plan {plan.plan_id.value}  {plan.runtime.value}=={plan.runtime_version}  "
        f"{plan.executor.value}  {plan.installation_root}"
    )
    return 0


def provision_runtime(arguments: Sequence[str]) -> int:
    """Install a plan into an isolated environment. Not verification."""
    retry = False
    rest = [token for token in arguments if token != "--retry"]
    if "--retry" in arguments:
        retry = True
    if not rest:
        print(
            "usage: kultrun runtimes provision <plan-id> [--retry]",
            file=sys.stderr,
        )
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host = platform.hosts.current
    installation = platform.provisioning.provision(
        RuntimeProvisioningPlanId.parse(rest[0]),
        host,
        (
            platform.executions.capabilities(host),
            platform.plane.container_capability(host),
        ),
        platform.runtimes.descriptors(),
        components=path_presence(
            [
                component.value
                for descriptor in platform.runtimes.descriptors()
                for component in descriptor.required_components
            ]
        ),
        retry=retry,
    )
    print(
        f"installation {installation.installation_id.value}  "
        f"{installation.status.value}  "
        f"{installation.runtime.value}=={installation.runtime_version}  "
        f"attempts {installation.attempt_count}"
    )
    if installation.status.value == "failed":
        code = (
            installation.last_failure_code
            if isinstance(installation.last_failure_code, str)
            else "-"
        )
        print(f"failure {code}")
        return 1
    return 0


def show_runtime_installations() -> int:
    """List persisted installations with effective verification status."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    items = platform.provisioning.installations()
    if not items:
        print("no runtime installations")
        return 0
    host = platform.hosts.current
    executors = (
        platform.executions.capabilities(host),
        platform.plane.container_capability(host),
    )
    for item in items:
        profile = platform.verification.profile_for(
            item.installation_id, host, executors
        )
        status = profile.status.value if profile is not None else "unverified"
        print(
            f"{item.installation_id.value}  {item.status.value}  "
            f"{item.runtime.value}=={item.runtime_version}  "
            f"{item.executor.value}  verified {status}"
        )
    return 0


def verify_runtime(arguments: Sequence[str]) -> int:
    """Verify an exact installed runtime. Does not provision or load a model."""
    if not arguments:
        print(
            "usage: kultrun runtimes verify <installation-id>|--selected",
            file=sys.stderr,
        )
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host, executors, descriptors, components = _runtime_inputs(platform)
    if arguments[0] == "--selected":
        profile = platform.foundation.verify_selected(
            host, executors, descriptors, components=components
        )
    else:
        profile = platform.verification.verify(
            RuntimeInstallationId.parse(arguments[0]),
            host,
            executors,
        )
    print(
        f"profile {profile.profile_id.value}  {profile.status.value}  "
        f"{profile.runtime.value}=={profile.runtime_version}  "
        f"{profile.executor.value}  attempts {profile.attempt_count}"
    )
    if profile.status is not VerificationStatus.VERIFIED:
        codes = ",".join(code.value for code in profile.reason_codes) or "-"
        print(f"failure {codes}")
        return 1
    return 0


def show_runtime_capabilities() -> int:
    """List persisted capability profiles. GET does not probe."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host = platform.hosts.current
    executors = (
        platform.executions.capabilities(host),
        platform.plane.container_capability(host),
    )
    items = platform.verification.profiles(host, executors)
    if not items:
        print("no runtime capability profiles")
        return 0
    for item in items:
        print(
            f"{item.profile_id.value}  {item.status.value}  "
            f"{item.runtime.value}=={item.runtime_version}  "
            f"{item.executor.value}  "
            f"installation {item.installation_id.value}"
        )
        if item.reason_codes:
            print("  " + ",".join(code.value for code in item.reason_codes))
    return 0


def _runtime_start(arguments: Sequence[str]) -> int:
    once = "--once" in arguments
    hold_flag = "--hold" in arguments
    if once and hold_flag:
        print("kultrun: choose --once or --hold, not both", file=sys.stderr)
        return 2
    hold = not once
    platform = build()
    _warn_if_state_root_defaulted(platform)
    handle = start_reference_workload(platform, hold=hold)
    _print_execution(handle)
    if not hold:
        handle = _wait_until_terminal(platform, handle)
        _print_execution(handle)
        code = handle.exit_code
        if handle.observed_state.value == "exited" and code == 0:
            return 0
        return 1
    print("running; interrupt to stop", file=sys.stderr)
    try:
        handle = _wait_until_terminal(platform, handle)
    except KeyboardInterrupt:
        handle = platform.executions.stop(handle.execution_id)
    _print_execution(handle)
    return 0


def _runtime_status() -> int:
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host = platform.hosts.current
    live = platform.executions.capabilities(host)
    container = platform.plane.container_capability(host)
    print(f"executor {live.executor.value} {live.availability.value}")
    print(
        f"container-docker {container.availability.value}"
        + (f" {container.reason}" if is_resolved(container.reason) else "")
    )
    handles = platform.executions.list()
    if not handles:
        print("no executions")
        return 0
    for handle in handles:
        _print_execution(handle)
    return 0


def _runtime_stop(arguments: Sequence[str]) -> int:
    platform = build()
    _warn_if_state_root_defaulted(platform)
    if arguments:
        handle = platform.executions.stop(ExecutionId.parse(arguments[0]))
        _print_execution(handle)
        return 0
    stopped = platform.executions.stop_all_running()
    if not stopped:
        print("no owned running executions to stop")
        return 0
    for handle in stopped:
        _print_execution(handle)
    return 0


def _wait_until_terminal(platform: Platform, handle: ExecutorHandle) -> ExecutorHandle:
    import time

    current = handle
    deadline = time.monotonic() + 30
    while current.observed_state in (
        ExecutionState.PENDING,
        ExecutionState.STARTING,
        ExecutionState.RUNNING,
        ExecutionState.STOPPING,
    ):
        if time.monotonic() > deadline:
            return current
        time.sleep(0.05)
        current = platform.executions.observe(current.execution_id)
    return current


def _print_execution(handle: ExecutorHandle) -> None:
    pid = handle.pid if is_resolved(handle.pid) else "-"
    exit_code = handle.exit_code if is_resolved(handle.exit_code) else "-"
    external = (
        handle.external_identity if is_resolved(handle.external_identity) else "-"
    )
    print(
        f"{handle.execution_id.value}  {handle.observed_state.value}  "
        f"executor {handle.executor.value}  "
        f"pid {pid}  external {external}  exit {exit_code}  "
        f"ownership {handle.ownership.value}"
    )
    if handle.stdout:
        print("--- stdout ---")
        print(handle.stdout, end="" if handle.stdout.endswith("\n") else "\n")
    if handle.stderr:
        print("--- stderr ---")
        print(handle.stderr, end="" if handle.stderr.endswith("\n") else "\n")


def show_models() -> int:
    """List the curated catalog. Does not rank, download or recommend."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    print(f"source {platform.models.source_identity.value}  live-fetch no")
    print("selection no  ranking no  download no")
    for entry in platform.models.entries():
        meta = entry.metadata
        req = entry.requirement
        display = (
            meta.display_name if is_resolved(meta.display_name) else meta.logical_name
        )
        quant = meta.quantization if is_resolved(meta.quantization) else "unknown"
        params = (
            f"{meta.parameter_count / 1_000_000_000:.1f}B"
            if is_resolved(meta.parameter_count)
            else "unknown"
        )
        context = (
            str(meta.context_length_tokens)
            if is_resolved(meta.context_length_tokens)
            else "unknown"
        )
        print(f"\n{display}")
        print(f"  {meta.logical_name}  {meta.source_ref}")
        print(
            f"  params {params}  quant {quant}  context {context}  "
            f"confidence {req.confidence.value}"
        )
        print(
            f"  artifact {_bytes(req.storage_bytes)}  "
            f"peak {_bytes(req.peak_additional_bytes)}  "
            f"RAM {_bytes(req.ram_bytes)}  "
            f"VRAM {_bytes(req.estimated_vram_bytes)}"
        )
        method = (
            req.estimation_method if is_resolved(req.estimation_method) else "unknown"
        )
        print(
            f"  runtimes {', '.join(meta.supported_runtimes) or 'unstated'}  "
            f"method {method}"
        )
    return 0


def _models(arguments: Sequence[str]) -> int:
    if not arguments:
        return show_models()
    command = arguments[0]
    if command == "available":
        return show_available_models()
    if command == "recommend":
        return show_recommendation()
    if command == "selection":
        return show_model_selection()
    if command == "select":
        return select_named_model(arguments[1:])
    if command == "eligible":
        return show_eligible_models()
    if command == "requirements":
        return show_requirements()
    if command == "inventory":
        return show_inventory()
    if command == "acquire":
        return acquire_named(arguments[1:])
    if command == "delete":
        return delete_named(arguments[1:])
    print(
        "usage: kultrun models ["
        "available|recommend|selection|select|eligible|requirements|"
        "inventory|acquire|delete]",
        file=sys.stderr,
    )
    return 2


def _deployments(arguments: Sequence[str]) -> int:
    if not arguments or arguments[0] in {"plan", "--refresh"}:
        return show_deployment_plan(refresh="--refresh" in arguments)
    command = arguments[0]
    if command == "acquire":
        return acquire_deployment()
    if command == "admit":
        return admit_deployment()
    if command == "prepare":
        return prepare_deployment()
    print(
        "usage: kultrun deployments {plan [--refresh]|acquire|admit|prepare}",
        file=sys.stderr,
    )
    return 2


def show_deployment_plan(*, refresh: bool) -> int:
    """Print the authoritative deployment plan. Does not execute."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    overview = _deployment_overview(platform, persist=refresh)
    plan = overview.plan
    print(f"Deployment Plan: {overview.status.value.upper()}")
    if overview.reasons:
        print(f"reasons {'; '.join(overview.reasons)}")
    if plan is None:
        print("no persisted plan")
        return 0
    runtime = plan.runtime if isinstance(plan.runtime, str) else "-"
    version = plan.runtime_version if isinstance(plan.runtime_version, str) else "-"
    print(f"plan {plan.plan_id if isinstance(plan.plan_id, str) else '-'}")
    print(f"Runtime:\n  {runtime} {version}")
    print(f"Model:\n  {plan.logical_name.value}")
    mode = (
        plan.model_selection_mode if isinstance(plan.model_selection_mode, str) else "-"
    )
    print(f"Selection:\n  {mode.upper() if mode != '-' else mode}")
    verdict = (
        plan.capacity_verdict.upper() if isinstance(plan.capacity_verdict, str) else "-"
    )
    print(f"Capacity:\n  {verdict}")
    print("Resources:")
    print(f"  RAM: {_bytes(plan.expected_ram_bytes)}")
    print(f"  VRAM: {_bytes(plan.expected_vram_bytes)}")
    executor = plan.executor_kind if isinstance(plan.executor_kind, str) else "-"
    print(f"Execution:\n  {executor}")
    return 0


def acquire_deployment() -> int:
    """Acquire or reuse the CURRENT plan's exact artifact. Does not admit."""
    from kultrun.kernel.errors import KultrunError

    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        result = platform.deployment_prepare.acquire(platform.hosts.current)
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    _print_acquisition(result.payload())
    return 0


def admit_deployment() -> int:
    """Admit the CURRENT plan against a matching stored artifact."""
    from kultrun.kernel.errors import KultrunError

    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        result = platform.deployment_prepare.admit(platform.hosts.current)
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    payload = result.payload()
    _print_acquisition(payload)
    return _print_admission(payload)


def prepare_deployment() -> int:
    """Acquire/reuse then admit the CURRENT plan. Does not start inference."""
    from kultrun.kernel.errors import KultrunError

    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        result = platform.deployment_prepare.prepare(platform.hosts.current)
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    payload = result.payload()
    _print_acquisition(payload)
    return _print_admission(payload)


def _print_acquisition(payload: Mapping[str, object]) -> None:
    status = str(payload.get("plan_status") or "unavailable").upper()
    print(f"Plan: {status}")
    print(f"Model: {payload.get('selected_model') or '-'}")
    acquisition = payload.get("acquisition")
    details = acquisition if isinstance(acquisition, Mapping) else {}
    reused = bool(details.get("reused"))
    print(f"Artifact: {'reused' if reused else 'acquired'}")
    print(f"Artifact ID: {payload.get('artifact_id') or '-'}")


def _print_admission(payload: Mapping[str, object]) -> int:
    admission = payload.get("admission")
    details = admission if isinstance(admission, Mapping) else {}
    verdict = str(details.get("verdict") or "unresolved").upper()
    print(f"Admission: {verdict}")
    reservation = details.get("reservation_id") or "-"
    print(f"Reservation ID: {reservation}")
    reasons = details.get("reasons")
    if isinstance(reasons, list):
        for line in reasons:
            print(f"  {line}")
    return 0 if verdict == "ADMITTED" else 1


def show_inventory() -> int:
    """List stored artifacts. Stored is not running."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    artifacts = platform.inventory.artifacts()
    print(
        f"provider {platform.acquisition.provider_identity}  "
        f"artifacts {len(artifacts)}  serving no"
    )
    print("stored is not running")
    if not artifacts:
        print("empty inventory")
        return 0
    for artifact in artifacts:
        name = artifact.logical_name if is_resolved(artifact.logical_name) else "-"
        revision = artifact.revision if is_resolved(artifact.revision) else "-"
        quant = artifact.quantization if is_resolved(artifact.quantization) else "-"
        print(
            f"\n{artifact.artifact_id.value}  {name}  "
            f"{artifact.state.value}  serving no"
        )
        print(
            f"  revision {revision}  quant {quant}  "
            f"bytes {_bytes(artifact.installed_bytes)}  "
            f"verify {artifact.verification_state.value}"
        )
        source = artifact.source_ref if is_resolved(artifact.source_ref) else "-"
        print(f"  source {source}  provider {artifact.acquisition_provider}")
    return 0


def acquire_named(arguments: Sequence[str]) -> int:
    """Acquire a known candidate. Selection remains read-only."""
    from kultrun.kernel.errors import KultrunError
    from kultrun.model.acquisition import request_from_entry

    recommended = "--recommended" in arguments
    names = [item for item in arguments if not item.startswith("-")]
    if recommended and not names:
        return acquire_deployment()
    if len(names) != 1:
        print(
            "usage: kultrun models acquire <candidate-id> | --recommended",
            file=sys.stderr,
        )
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    entry = platform.models.acquirable(names[0])
    if entry is None:
        print(f"kultrun: no such candidate {names[0]!r}", file=sys.stderr)
        return 2
    host = platform.hosts.current
    try:
        receipt = platform.plane.storage_acquire.acquire(
            request_from_entry(entry),
            host,
            _stored_sanity(platform, host),
        )
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    print(
        f"{receipt.outcome}  {receipt.artifact_id.value}  "
        f"{receipt.state.value}  serving no"
    )
    if is_resolved(receipt.resolved_revision):
        print(f"  revision {receipt.resolved_revision}")
    if is_resolved(receipt.failure_reason):
        print(f"  failure {receipt.failure_reason}")
    return 0 if receipt.outcome != "failed" else 1


def delete_named(arguments: Sequence[str]) -> int:
    from kultrun.kernel.errors import KultrunError
    from kultrun.model.contracts import ArtifactId

    if len(arguments) != 1:
        print("usage: kultrun models delete <artifact-id>", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        artifact = platform.acquisition.delete(
            ArtifactId.parse(arguments[0]), platform.hosts.current.host_id
        )
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    print(f"deleted  {artifact.artifact_id.value}  serving no")
    return 0


def _print_availability_report(result: FunnelPass) -> None:
    print(format_funnel(result.available))
    print()
    print(format_estimated_feasible(result.estimated_feasible))
    if result.validation is not None:
        print(format_runtime_validation(result.validation))
        print()
    print(format_available_models(result.available))


def show_available_models() -> int:
    """Print Available Models. Does not recommend or select."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    result = _funnel(platform, persist=True)
    _print_availability_report(result)
    return 0


def show_recommendation() -> int:
    """Select using the configured estimator. Does not download or reserve."""
    from kultrun.planning.service import plan_from

    platform = build()
    _warn_if_state_root_defaulted(platform)
    result = _funnel(platform, persist=True)
    _print_availability_report(result)
    print()
    overview = platform.model_selection.view(
        platform.hosts.current,
        result.eligible,
        result.envelope,
        result.assessments,
        result.available,
    )
    recommendation = overview.recommendation
    recommendation_mode = recommendation.estimator_mode
    fallback = (
        f"  fallback {recommendation.fallback_reason}"
        if recommendation.fallback_used and is_resolved(recommendation.fallback_reason)
        else "  fallback no"
    )
    runtime = _selected_runtime(overview.view) or "-"
    version = (
        overview.view.runtime_version
        if isinstance(overview.view.runtime_version, str)
        else "-"
    )
    rec = overview.selection.recommended_logical_name
    sel = overview.selection.selected_logical_name
    print(
        f"selection {overview.selection.selection_mode.value}  "
        f"status {overview.status.value}  "
        f"recommended {rec if isinstance(rec, str) else '-'}  "
        f"selected {sel if isinstance(sel, str) else '-'}"
    )
    print(
        f"mode {recommendation_mode}  "
        f"effective {recommendation.estimator_provider}  "
        f"version {recommendation.estimator_version}  "
        f"outcome {recommendation.outcome.value}"
        f"{fallback}"
    )
    print(
        f"runtime {runtime}  runtime-version {version}  "
        f"eligibility {overview.view.status.value}"
    )
    print(f"policy {recommendation.policy_version}")
    for line in recommendation.rationale:
        print(f"  {line}")
    if recommendation.primary is not None:
        winner = recommendation.primary
        ratio = winner.utilization.ratio
        used = f"{float(ratio):.1%}" if is_resolved(ratio) else "unknown"
        print(
            f"primary {winner.logical_name.value}  {winner.capacity_fit.value}  {used}"
        )
        assessed = next(
            (
                item
                for item in overview.assessments
                if item.model_id == winner.model_id.value
            ),
            None,
        )
        if assessed is not None:
            print(
                f"requirement {assessed.requirement_status.value}  "
                f"capacity {assessed.capacity_verdict}"
            )
    planned = plan_from(recommendation)
    if planned is not None:
        print(
            f"plan {planned.logical_name.value}  "
            f"placement {planned.placement.value}  "
            f"runtime {planned.runtime if is_resolved(planned.runtime) else '-'}  "
            f"authoritative no"
        )
    print()
    print("RECOMMENDED MODEL:")
    print(rec if isinstance(rec, str) else "none")
    print("SELECTED MODEL:")
    print(sel if isinstance(sel, str) else "none")
    print("MODE:")
    print(overview.selection.selection_mode.value.upper())
    return 0


def show_model_selection() -> int:
    """Current AUTO|MANUAL model selection and feasible alternatives."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    overview = _model_overview(platform)
    rec = overview.selection.recommended_logical_name
    sel = overview.selection.selected_logical_name
    print(
        f"mode {overview.selection.selection_mode.value}  "
        f"status {overview.status.value}"
    )
    print(f"recommended {rec if isinstance(rec, str) else '-'}")
    print(f"selected {sel if isinstance(sel, str) else '-'}")
    if overview.feasible:
        print("feasible")
        for item in overview.feasible:
            mark = (
                "selected"
                if item.model_id
                == (
                    overview.selection.selected_model_id
                    if isinstance(overview.selection.selected_model_id, str)
                    else ""
                )
                else "ok"
            )
            print(f"  {mark:8} {item.logical_name}  {item.capacity_fit}")
    else:
        print("feasible none")
    return 0


def select_named_model(arguments: Sequence[str]) -> int:
    """Persist AUTO or a currently feasible MANUAL model."""
    from kultrun.kernel.errors import KultrunError

    auto = "--auto" in arguments
    names = [item for item in arguments if not item.startswith("-")]
    if auto and names:
        print("usage: kultrun models select <model> | --auto", file=sys.stderr)
        return 2
    if not auto and len(names) != 1:
        print("usage: kultrun models select <model> | --auto", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host = platform.hosts.current
    result = _funnel(platform, persist=True, pending_model=None if auto else names[0])
    _print_availability_report(result)
    print()
    try:
        if auto:
            overview = platform.model_selection.select_auto(
                host,
                result.eligible,
                result.envelope,
                result.assessments,
                result.available,
            )
        else:
            overview = platform.model_selection.select_manual(
                names[0],
                host,
                result.eligible,
                result.envelope,
                result.assessments,
                result.available,
            )
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    rec = overview.selection.recommended_logical_name
    sel = overview.selection.selected_logical_name
    print(
        f"{overview.selection.selection_mode.value}  "
        f"{overview.status.value}  "
        f"recommended {rec if isinstance(rec, str) else '-'}  "
        f"selected {sel if isinstance(sel, str) else '-'}"
    )
    print()
    print("RECOMMENDED MODEL:")
    print(rec if isinstance(rec, str) else "none")
    print("SELECTED MODEL:")
    print(sel if isinstance(sel, str) else "none")
    print("MODE:")
    print(overview.selection.selection_mode.value.upper())
    return 0


def show_requirements() -> int:
    """Derived requirements and capacity for the selected foundation."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    view, _envelope, rows = _assessments(platform)
    runtime = _selected_runtime(view) or "-"
    version = view.runtime_version if isinstance(view.runtime_version, str) else "-"
    print(
        f"runtime {runtime}  version {version}  "
        f"view {view.status.value}  profile "
        f"{view.profile_status if isinstance(view.profile_status, str) else '-'}"
    )
    if not rows:
        print("no requirement assessments")
        return 0
    for item in rows:
        eligibility = item.eligibility_status or "-"
        print(
            f"{item.requirement_status.value:12} {item.capacity_verdict:16} "
            f"{item.logical_name:32} eligibility {eligibility}  "
            f"vram {_bytes(item.required_vram_bytes)}/"
            f"{_bytes(item.available_vram_bytes)}"
        )
    return 0


def show_eligible_models() -> int:
    """Runtime-aware eligible models for the selected verified foundation."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    view = _eligible_view(platform)
    runtime = view.runtime if isinstance(view.runtime, str) else "-"
    version = view.runtime_version if isinstance(view.runtime_version, str) else "-"
    selected = (
        view.selected_candidate_id
        if isinstance(view.selected_candidate_id, str)
        else "-"
    )
    profile = view.profile_status if isinstance(view.profile_status, str) else "-"
    print(
        f"selected {selected}  runtime {runtime}  version {version}  "
        f"profile {profile}  view {view.status.value}"
    )
    print(
        f"eligible {view.eligible_count}  blocked {view.blocked_count}  "
        f"unresolved {view.unresolved_count}  "
        f"authoritative {str(view.status.value == 'current').lower()}"
    )
    if view.reason_codes:
        print("reasons " + ",".join(item.value for item in view.reason_codes))
    if not view.candidates:
        print("no eligible-model candidates")
        return 0
    for item in view.candidates:
        extra = ",".join(code.value for code in item.reason_codes) or "-"
        print(f"{item.status.value:10} {item.logical_name:32} {extra}")
    return 0


def _resources(arguments: Sequence[str]) -> int:
    if not arguments:
        return show_resource_summary()
    command = arguments[0]
    if command == "reservations":
        return show_reservations()
    if command == "reserve":
        return reserve_named(arguments[1:])
    if command == "release":
        return release_named(arguments[1:])
    print(
        "usage: kultrun resources [reservations|reserve|release]",
        file=sys.stderr,
    )
    return 2


def show_resource_summary() -> int:
    """SAFE / RESERVED / AVAILABLE. Reserved is not running."""
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host = platform.hosts.current
    envelope = platform.capacity.compute(
        host,
        _stored_sanity(platform, host),
        platform.plane.stored_storage(host),
    )
    summary = platform.resources.summary(envelope)
    running = _running_count(platform)
    print(
        f"health {summary.health.value}  active {summary.active_count}  "
        f"serving {'yes' if running else 'no'}  running {running}"
    )
    print("reserved is not running")
    print(
        f"ram  safe {_bytes(summary.safe_ram_bytes)}  "
        f"reserved {_bytes(summary.reserved_ram_bytes)}  "
        f"available {_bytes(summary.available_ram_bytes)}"
    )
    for device in summary.accelerators:
        print(
            f"gpu {device.index}  safe {_bytes(device.safe_bytes)}  "
            f"reserved {_bytes(device.reserved_bytes)}  "
            f"available {_bytes(device.available_bytes)}"
        )
    return 0


def show_reservations() -> int:
    platform = build()
    _warn_if_state_root_defaulted(platform)
    items = platform.resources.reservations()
    print(f"reservations {len(items)}  serving no")
    if not items:
        print("no active reservations")
        return 0
    for item in items:
        name = item.logical_name if is_resolved(item.logical_name) else "-"
        print(
            f"{item.reservation_id.value}  {name}  {item.state.value}  "
            f"ram {_bytes(item.admitted_ram_bytes)}  "
            f"accel {_bytes(item.admitted_vram_bytes)}"
        )
    return 0


def reserve_named(arguments: Sequence[str]) -> int:
    from kultrun.kernel.errors import KultrunError
    from kultrun.model.contracts import ArtifactId

    if len(arguments) != 1:
        print("usage: kultrun resources reserve <artifact-id>", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    host = platform.hosts.current
    view = _eligible_view(platform)
    try:
        decision = platform.admission.reserve(
            ArtifactId.parse(arguments[0]),
            host,
            _stored_sanity(platform, host),
            _runtime_compat(platform),
            runtime=_selected_runtime(view) or "unresolved",
            runtime_version=(
                view.runtime_version
                if isinstance(view.runtime_version, str)
                else NOT_PROVIDED
            ),
        )
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    granted = (
        decision.reservation.reservation_id.value
        if decision.reservation is not None
        else "-"
    )
    print(f"{decision.verdict.value}  {granted}  serving no")
    for line in decision.reasons:
        print(f"  {line}")
    return 0 if decision.verdict.value == "admitted" else 1


def release_named(arguments: Sequence[str]) -> int:
    from kultrun.kernel.errors import KultrunError
    from kultrun.resource.contracts import ReservationId

    if len(arguments) != 1:
        print(
            "usage: kultrun resources release <reservation-id>",
            file=sys.stderr,
        )
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        released = platform.admission.release(ReservationId.parse(arguments[0]))
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    print(f"released  {released.reservation_id.value}  serving no")
    return 0


def _running_count(platform: Platform) -> int:
    return sum(
        1
        for item in platform.instances.list()
        if item.observed_state is ObservedState.RUNNING
    )


def _ledger_health_of(platform: Platform) -> LedgerHealth:
    host = platform.hosts.current
    envelope = platform.capacity.compute(
        host,
        _stored_sanity(platform, host),
        platform.plane.stored_storage(host),
    )
    return platform.resources.summary(envelope).health


def _instances(arguments: Sequence[str]) -> int:
    if not arguments:
        return show_instances()
    command = arguments[0]
    if command == "create":
        return create_named_instance(arguments[1:])
    if command == "start":
        return start_named_instance(arguments[1:])
    if command == "stop":
        return stop_named_instance(arguments[1:])
    if command == "inspect":
        return inspect_named_instance(arguments[1:])
    if command == "infer":
        return infer_named_instance(arguments[1:])
    print(
        "usage: kultrun instances [create|start|stop|inspect|infer]",
        file=sys.stderr,
    )
    return 2


def show_instances() -> int:
    platform = build()
    _warn_if_state_root_defaulted(platform)
    views = platform.deployment_instance.list(platform.hosts.current)
    print(f"instances {len(views)}  running {_running_count(platform)}")
    if not views:
        print("no inference instances")
        return 0
    for view in views:
        item = view.instance
        endpoint = "-"
        if item.endpoint is not None:
            endpoint = f"{item.endpoint.address}:{item.endpoint.port}"
        pid = item.pid if is_resolved(item.pid) else "-"
        current = (
            "CURRENT"
            if view.configuration_current
            else ("STALE" if view.plan_status else "-")
        )
        print(
            f"{item.instance_id.value}  {item.observed_state.value}  "
            f"desired {item.desired_state.value}  pid {pid}  {endpoint}  "
            f"configuration {current}"
        )
    return 0


def create_named_instance(arguments: Sequence[str]) -> int:
    from kultrun.kernel.errors import KultrunError
    from kultrun.resource.contracts import ReservationId

    if len(arguments) != 1:
        print("usage: kultrun instances create <reservation-id>", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        view = platform.deployment_instance.create(
            platform.hosts.current,
            reservation_id=ReservationId.parse(arguments[0]),
        )
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    item = view.instance
    print(f"Plan: {_token_or_dash(item.plan_id)}")
    print(f"Model: {_token_or_dash(item.logical_name)}")
    print(f"Artifact: {_id_or_dash(item.artifact_id)}")
    print(f"Reservation: {_id_or_dash(item.reservation_id)}")
    print(f"Runtime: {item.runtime.value}")
    print(f"Executor: {item.executor.value}")
    print(f"Instance: {item.instance_id.value}  {item.observed_state.value.upper()}")
    current = "CURRENT" if view.configuration_current else (view.plan_status or "-")
    print(f"Configuration: {current.upper() if current != '-' else current}")
    return 0


def start_named_instance(arguments: Sequence[str]) -> int:
    from kultrun.inference.contracts import InstanceId
    from kultrun.kernel.errors import KultrunError

    if len(arguments) != 1:
        print("usage: kultrun instances start <instance-id>", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        view = platform.deployment_instance.start(
            InstanceId.parse(arguments[0]),
            platform.hosts.current,
            ledger_health=_ledger_health_of(platform),
        )
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    instance = view.instance
    endpoint = "-"
    if instance.endpoint is not None:
        endpoint = f"{instance.endpoint.address}:{instance.endpoint.port}"
    pid = instance.pid if is_resolved(instance.pid) else "-"
    print(
        f"{instance.instance_id.value}  {instance.observed_state.value}  "
        f"pid {pid}  {endpoint}"
    )
    return 0


def stop_named_instance(arguments: Sequence[str]) -> int:
    from kultrun.inference.contracts import InstanceId
    from kultrun.kernel.errors import KultrunError

    if len(arguments) != 1:
        print("usage: kultrun instances stop <instance-id>", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        view = platform.deployment_instance.stop(
            InstanceId.parse(arguments[0]), platform.hosts.current
        )
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    print(
        f"{view.instance.instance_id.value}  {view.instance.observed_state.value}  "
        f"reservation held"
    )
    return 0


def inspect_named_instance(arguments: Sequence[str]) -> int:
    from kultrun.inference.contracts import InstanceId
    from kultrun.kernel.errors import KultrunError

    if len(arguments) != 1:
        print("usage: kultrun instances inspect <instance-id>", file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        view = platform.deployment_instance.get(
            InstanceId.parse(arguments[0]), platform.hosts.current
        )
    except KultrunError:
        print("kultrun: no such instance", file=sys.stderr)
        return 1
    instance = view.instance
    endpoint = "-"
    if instance.endpoint is not None:
        endpoint = (
            f"{instance.endpoint.scheme}://{instance.endpoint.address}"
            f":{instance.endpoint.port}"
        )
    current = "CURRENT" if view.configuration_current else (view.plan_status or "-")
    print(f"instance {instance.instance_id.value}")
    print(f"plan {_token_or_dash(instance.plan_id)}")
    print(f"plan basis {_token_or_dash(instance.plan_basis)}")
    print(f"configuration {current}")
    print(f"model {_token_or_dash(instance.logical_name)}")
    print(f"artifact {instance.artifact_id}")
    print(f"reservation {instance.reservation_id}")
    print(f"desired {instance.desired_state.value}")
    print(f"observed {instance.observed_state.value}")
    print(f"runtime {instance.runtime.value}")
    print(f"executor {instance.executor.value}")
    print(
        "execution "
        f"{instance.execution_id.value if instance.execution_id is not None else '-'}"
    )
    print(f"pid {instance.pid if is_resolved(instance.pid) else '-'}")
    print(f"endpoint {endpoint}")
    print(f"ready {instance.ready if is_resolved(instance.ready) else 'unknown'}")
    return 0


def infer_named_instance(arguments: Sequence[str]) -> int:
    from kultrun.inference.contracts import InstanceId
    from kultrun.inference.service import parse_inference_request
    from kultrun.kernel.errors import KultrunError
    from kultrun.kernel.unresolved import is_resolved as resolved

    instance_id, query, err = _parse_infer_args(arguments)
    if err is not None:
        print(err, file=sys.stderr)
        return 2
    platform = build()
    _warn_if_state_root_defaulted(platform)
    try:
        response = platform.deployment_instance.infer(
            InstanceId.parse(instance_id),
            platform.hosts.current,
            parse_inference_request(query),
        )
    except KultrunError as error:
        print(f"kultrun: {error.message}", file=sys.stderr)
        return 1
    print(f"instance {response.instance_id.value}")
    print(f"request {response.request_id.value}")
    print(f"model {response.served_model}")
    print(f"runtime {response.runtime.value}")
    print(
        "runtime-version "
        f"{response.runtime_version if resolved(response.runtime_version) else '-'}"
    )
    print(f"latency-ms {response.latency_ms}")
    print(
        "input-tokens "
        f"{response.input_tokens if resolved(response.input_tokens) else '-'}"
    )
    print(
        "output-tokens "
        f"{response.output_tokens if resolved(response.output_tokens) else '-'}"
    )
    print(
        f"finish {response.finish_reason if resolved(response.finish_reason) else '-'}"
    )
    print("generated")
    print(response.generated_text)
    return 0


def _parse_infer_args(
    arguments: Sequence[str],
) -> tuple[str, dict[str, str], str | None]:
    if not arguments:
        return (
            "",
            {},
            'usage: kultrun instances infer <instance-id> --prompt "..."',
        )
    instance_id = ""
    query: dict[str, str] = {}
    pending = list(arguments)
    while pending:
        token = pending.pop(0)
        if token == "--prompt":
            if not pending:
                return "", {}, "usage: kultrun instances infer <id> --prompt TEXT"
            query["prompt"] = pending.pop(0)
            continue
        if token == "--max-tokens":
            if not pending:
                return "", {}, "usage: kultrun instances infer <id> --max-tokens N"
            query["max_output_tokens"] = pending.pop(0)
            continue
        if token == "--temperature":
            if not pending:
                return "", {}, "usage: kultrun instances infer <id> --temperature N"
            query["temperature"] = pending.pop(0)
            continue
        if token == "--timeout":
            if not pending:
                return "", {}, "usage: kultrun instances infer <id> --timeout N"
            query["timeout_seconds"] = pending.pop(0)
            continue
        if token.startswith("-"):
            return "", {}, f"kultrun: unknown infer option {token}"
        if instance_id:
            return "", {}, "usage: kultrun instances infer <instance-id> --prompt TEXT"
        instance_id = token
    if not instance_id or "prompt" not in query:
        return (
            "",
            {},
            'usage: kultrun instances infer <instance-id> --prompt "..."',
        )
    query["instance_id"] = instance_id
    return instance_id, query, None


def _token_or_dash(value: object) -> str:
    if not is_resolved(value) or value is None:
        return "-"
    text = value.value if hasattr(value, "value") else value
    return str(text) if text else "-"


def _id_or_dash(value: object) -> str:
    if value is None:
        return "-"
    ident = getattr(value, "value", value)
    return str(ident)


COMMANDS: dict[str, Callable[[Sequence[str]], int]] = {
    "version": lambda _: show_version(),
    "host": lambda _: show_host(),
    "models": _models,
    "deployments": _deployments,
    "resources": _resources,
    "instances": _instances,
    "storage": _storage,
    "runtime": _runtime,
    "runtimes": _runtimes,
    "serve": lambda _: serve(),
}


def main(argv: Sequence[str] | None = None) -> int:
    """The `kultrun` command.

    Deliberately a small command set and no framework. Each exists because
    the workflow needs it: `version` identifies a deployed build, `host`
    lets a real-host run be observed without shipping a script beside the
    product,     `models` lists the catalog and inventory and can acquire or
    delete stored artifacts, `deployments plan` shows the current
    deployment decision, `deployments acquire|admit|prepare` consume
    that plan, `resources` admits capacity, `instances`
    binds a CURRENT plan to a matching reservation and starts native
    vLLM when that path is selected, `storage` and `runtime`
    are explicit mutations, and `serve` is what the platform does.
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

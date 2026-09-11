"""Runtime-breadth exoskeleton: families, preference, one active foundation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kultrun.adapters.execution.recording import RecordingExecutor
from kultrun.adapters.host import fixtures
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.runtime.llama_cpp import LlamaCppRuntimeSupport
from kultrun.adapters.runtime.mlx import MlxRuntimeSupport
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import (
    Accelerator,
    AcceleratorVendor,
    Architecture,
    HostCapabilities,
)
from kultrun.inference.contracts import (
    HealthState,
    InferenceInstance,
    InstanceId,
    LifecycleState,
    ObservedState,
)
from kultrun.inference.service import InstanceService
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.errors import ConflictError, NotFoundError, PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.main import build, config_schema
from kultrun.model.inventory import ModelInventory
from kultrun.model.store import ModelArtifactStore
from kultrun.platform.foundation_transition import (
    FoundationTransitionService,
    production_executable_for,
)
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.catalogue import RuntimeCatalogue
from kultrun.runtime.contracts import (
    FoundationPreferenceOutcome,
    FoundationSelectionMode,
    FoundationTransitionKind,
    HostStorageClass,
    RuntimePolicy,
    RuntimePreferencePolicy,
    RuntimeReadiness,
    RuntimeResolverMode,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
)
from kultrun.runtime.families import is_apple_silicon
from kultrun.runtime.plan import is_provisionable
from kultrun.runtime.preference import (
    REASON_APPLE_MLX,
    REASON_APPLE_MLX_UNAVAILABLE,
    REASON_COMFORTABLE,
    REASON_CONSTRAINED,
    REASON_NEITHER,
    REASON_ONLY_ONE,
    recommend_foundation,
)
from kultrun.runtime.resolve import resolve
from kultrun.runtime.selection import STALE_DOMAINS
from kultrun.runtime.transition import classify_transition
from kultrun.storage.contracts import StorageCapacityEvidence, StorageEvidenceStatus
from kultrun.storage.feasibility import reservable_bytes
from tests.architecture import _imports_named
from tests.test_contracts import host_capabilities
from tests.test_inference_instance import _request, _Stack
from tests.test_runtime_foundation_selection import _services
from tests.test_runtime_resolution import _native
from tests.test_storage_manual import INSTANT

GIB = 1024**3
SOURCE = Path(__file__).resolve().parent.parent / "src"
NATIVE = Name("native-process")


def _product_llama() -> RuntimeSupportDescriptor:
    return RuntimeSupportDescriptor(
        runtime=Name("llama.cpp"),
        display_name="llama.cpp (policy fixture)",
        support_tier=RuntimeSupportTier.PRODUCT,
        production_candidate=True,
        compatible_executor_types=(NATIVE,),
        supported_os_families=("linux", "darwin"),
        supported_architectures=("x86_64", "arm64"),
        required_features=(
            "process_execution",
            "structured_argv",
            "environment_variables",
        ),
    )


def _product_mlx() -> RuntimeSupportDescriptor:
    return RuntimeSupportDescriptor(
        runtime=Name("mlx"),
        display_name="MLX (policy fixture)",
        support_tier=RuntimeSupportTier.PRODUCT,
        production_candidate=True,
        compatible_executor_types=(NATIVE,),
        supported_os_families=("darwin",),
        supported_architectures=("arm64",),
        supported_accelerator_families=("apple",),
        required_features=(
            "process_execution",
            "structured_argv",
            "environment_variables",
        ),
    )


def _apple_host() -> HostCapabilities:
    host = host_capabilities()
    return replace(
        host,
        operating_environment=replace(
            host.operating_environment,
            os_name="darwin",
            architecture=Architecture.ARM64,
        ),
        accelerators=(
            Accelerator(
                index=0,
                vendor=AcceleratorVendor.APPLE,
                model_name="Apple M-series",
                memory_total_bytes=host.memory.total_bytes,
                driver_version=NOT_PROVIDED,
                unified_memory=True,
            ),
        ),
    )


def _storage(
    host: HostCapabilities, authorizing: int
) -> dict[str, StorageCapacityEvidence]:
    return {
        "/data": StorageCapacityEvidence(
            host_id=host.host_id,
            mount_point="/data",
            quota_identity=NOT_PROVIDED,
            pool_fingerprint="fp",
            observed_at=INSTANT,
            status=StorageEvidenceStatus.AUTHORITATIVE,
            confidence=Confidence.HIGH,
            provenance=Provenance(
                producer=Name("test"),
                producer_version=NOT_PROVIDED,
                observed_at=INSTANT,
                policy_version="test",
            ),
            operational_available_bytes=authorizing,
            authorizing_available_bytes=authorizing,
            native_source="test",
            selected_reason="test",
        )
    }


def _feasible(host: HostCapabilities, *descriptors: RuntimeSupportDescriptor):
    return resolve(
        host,
        (_native(host),),
        descriptors,
        RuntimePolicy(),
        components={"vllm": "missing"},
    )


class TestFamilyDeclarations:
    def test_future_families_are_declared_not_product(self) -> None:
        llama = LlamaCppRuntimeSupport().support()
        mlx = MlxRuntimeSupport().support()
        assert llama.support_tier is RuntimeSupportTier.FUTURE
        assert mlx.support_tier is RuntimeSupportTier.FUTURE
        assert llama.production_candidate is False
        assert mlx.production_candidate is False
        catalogue = RuntimeCatalogue(
            (VllmRuntimeSupport(), LlamaCppRuntimeSupport(), MlxRuntimeSupport())
        )
        assert catalogue.product_identities() == ("vllm",)
        assert catalogue.declared_family_identities() == ("llama.cpp", "mlx", "vllm")

    def test_auto_excludes_future_and_does_not_block_vllm(self) -> None:
        host = host_capabilities()
        result = resolve(
            host,
            (_native(host),),
            (
                VllmRuntimeSupport().support(),
                LlamaCppRuntimeSupport().support(),
                MlxRuntimeSupport().support(),
            ),
            RuntimePolicy(),
            components={"vllm": "missing"},
        )
        assert "llama.cpp" in result.excluded_runtimes
        assert "mlx" in result.excluded_runtimes
        assert [item.runtime.value for item in result.candidates] == ["vllm"]
        assert is_provisionable(result.candidates[0])

    def test_explicit_future_llama_is_not_provisionable(self) -> None:
        host = host_capabilities()
        result = resolve(
            host,
            (_native(host),),
            (LlamaCppRuntimeSupport().support(),),
            RuntimePolicy(
                mode=RuntimeResolverMode.EXPLICIT, requested_runtime="llama.cpp"
            ),
        )
        evaluated = (
            *result.candidates,
            *result.unsupported,
            *result.unresolved,
        )
        assert evaluated
        assert all(not is_provisionable(item) for item in evaluated)

    def test_launch_refuses_unimplemented_families(self) -> None:
        with pytest.raises(PreconditionFailedError, match="not an executable"):
            LlamaCppRuntimeSupport().launch_spec()
        with pytest.raises(PreconditionFailedError, match="not an executable"):
            MlxRuntimeSupport().launch_spec()


class TestDecisionPolicy:
    def test_apple_with_mlx_fixture_recommends_mlx(self) -> None:
        host = _apple_host()
        assert is_apple_silicon(host)
        resolution = _feasible(host, _product_mlx(), _product_llama())
        decision = recommend_foundation(host, resolution.candidates)
        assert decision.outcome is FoundationPreferenceOutcome.RECOMMENDED
        assert decision.recommended_family == "mlx"
        assert REASON_APPLE_MLX in decision.reasons

    def test_apple_without_mlx_does_not_fabricate_or_fall_back(self) -> None:
        host = _apple_host()
        resolution = _feasible(host, _product_llama(), VllmRuntimeSupport().support())
        decision = recommend_foundation(host, resolution.candidates)
        assert decision.outcome is FoundationPreferenceOutcome.BLOCKED
        assert not is_resolved(decision.recommended_candidate_id)
        assert REASON_APPLE_MLX_UNAVAILABLE in decision.reasons

    def test_non_apple_only_vllm(self) -> None:
        host = host_capabilities()
        resolution = _feasible(
            host, VllmRuntimeSupport().support(), LlamaCppRuntimeSupport().support()
        )
        decision = recommend_foundation(host, resolution.candidates)
        assert decision.recommended_family == "vllm"
        assert REASON_ONLY_ONE in decision.reasons

    def test_only_llama_fixture(self) -> None:
        host = host_capabilities()
        resolution = _feasible(host, _product_llama())
        decision = recommend_foundation(host, resolution.candidates)
        assert decision.recommended_family == "llama.cpp"
        assert REASON_ONLY_ONE in decision.reasons

    def test_both_constrained_prefers_llama(self) -> None:
        host = host_capabilities()
        resolution = _feasible(host, VllmRuntimeSupport().support(), _product_llama())
        evidence = _storage(host, 50 * GIB)
        safe = reservable_bytes(evidence["/data"])
        assert safe is not None
        assert safe < 64 * GIB
        decision = recommend_foundation(
            host, resolution.candidates, storage_evidence=evidence
        )
        assert decision.storage_class is HostStorageClass.CONSTRAINED
        assert decision.recommended_family == "llama.cpp"
        assert REASON_CONSTRAINED in decision.reasons
        assert RuntimePreferencePolicy().comfortable_storage_bytes != 32 * GIB

    def test_both_comfortable_prefers_vllm(self) -> None:
        host = host_capabilities()
        resolution = _feasible(host, VllmRuntimeSupport().support(), _product_llama())
        evidence = _storage(host, 80 * GIB)
        safe = reservable_bytes(evidence["/data"])
        assert safe is not None
        assert safe >= 64 * GIB
        decision = recommend_foundation(
            host, resolution.candidates, storage_evidence=evidence
        )
        assert decision.storage_class is HostStorageClass.COMFORTABLE
        assert decision.recommended_family == "vllm"
        assert REASON_COMFORTABLE in decision.reasons

    def test_preference_band_is_configurable(self) -> None:
        host = host_capabilities()
        resolution = _feasible(host, VllmRuntimeSupport().support(), _product_llama())
        evidence = _storage(host, 50 * GIB)
        decision = recommend_foundation(
            host,
            resolution.candidates,
            storage_evidence=evidence,
            policy=RuntimePreferencePolicy(comfortable_storage_bytes=10 * GIB),
        )
        assert decision.recommended_family == "vllm"
        assert decision.comfortable_storage_bytes == 10 * GIB

    def test_neither_is_blocked(self) -> None:
        host = host_capabilities()
        decision = recommend_foundation(host, ())
        assert decision.outcome is FoundationPreferenceOutcome.BLOCKED
        assert REASON_NEITHER in decision.reasons


class TestFoundationSelectionIntegration:
    def test_auto_still_selects_vllm_when_future_families_are_registered(
        self, tmp_path: Path
    ) -> None:
        host = host_capabilities()
        foundation, _ = _services(tmp_path)
        overview = foundation.select_auto(
            host,
            (_native(host),),
            (
                VllmRuntimeSupport().support(),
                LlamaCppRuntimeSupport().support(),
                MlxRuntimeSupport().support(),
            ),
            components={"vllm": "missing"},
        )
        assert overview.selection.selection_mode is FoundationSelectionMode.AUTO
        chosen = next(item for item in overview.candidates if item.selected)
        row = next(
            item
            for item in overview.resolution.candidates
            if item.candidate_id.value == chosen.candidate_id
        )
        assert row.runtime.value == "vllm"
        assert overview.preference is not None
        assert overview.preference.recommended_family == "vllm"

    def test_manual_may_select_fixture_llama_but_not_future(
        self, tmp_path: Path
    ) -> None:
        host = host_capabilities()
        foundation, _ = _services(tmp_path)
        descriptors = (VllmRuntimeSupport().support(), _product_llama())
        viewed = foundation.view(
            host,
            (_native(host),),
            descriptors,
            components={"vllm": "missing"},
            storage_evidence=_storage(host, 80 * GIB),
        )
        llama = next(
            item
            for item in viewed.resolution.candidates
            if item.runtime.value == "llama.cpp"
        )
        assert is_provisionable(llama)
        selected = foundation.select_manual(
            llama.candidate_id.value,
            host,
            (_native(host),),
            descriptors,
            components={"vllm": "missing"},
            storage_evidence=_storage(host, 80 * GIB),
        )
        assert selected.selection.selection_mode is FoundationSelectionMode.MANUAL
        assert selected.selection.selected_candidate_id == llama.candidate_id.value
        assert selected.selection.recommended_candidate_id != llama.candidate_id.value
        with pytest.raises((PreconditionFailedError, NotFoundError)):
            foundation.select_manual(
                "rcand_not_a_candidate",
                host,
                (_native(host),),
                (LlamaCppRuntimeSupport().support(),),
                policy=RuntimePolicy(
                    mode=RuntimeResolverMode.EXPLICIT, requested_runtime="llama.cpp"
                ),
            )

    def test_production_build_does_not_auto_select_unimplemented(
        self, tmp_path: Path
    ) -> None:
        platform = build(
            config_schema().load({"platform": {"state_root": str(tmp_path / "state")}}),
            fixture=fixtures.DEFAULT_SHAPE,
            acquisition_adapter="fixture",
            runtime_provisioner="fixture",
            runtime_verifier="fixture",
        )
        assert platform.runtimes.product_identities() == ("vllm",)
        assert "llama.cpp" in platform.runtimes.declared_family_identities()
        assert "mlx" in platform.runtimes.declared_family_identities()
        host = platform.hosts.current
        overview = platform.foundation.view(
            host,
            (
                platform.executions.capabilities(host),
                platform.plane.container_capability(host),
            ),
            platform.runtimes.descriptors(),
            components={"vllm": "missing"},
        )
        selected = overview.selection.recommended_candidate_id
        if isinstance(selected, str):
            candidate = next(
                item
                for item in overview.resolution.candidates
                if item.candidate_id.value == selected
            )
            assert candidate.runtime.value == "vllm"


class _LlamaStub:
    @property
    def identity(self) -> Name:
        return Name("llama.cpp")

    def support(self) -> RuntimeSupportDescriptor:
        return _product_llama()

    def profile(self):
        return VllmRuntimeSupport().profile()

    def launch_spec(self, request=None):
        del request
        raise PreconditionFailedError("stub")

    def inspect_readiness(self, **kwargs):
        del kwargs
        return RuntimeReadiness(ready=False, reason="stub")


class TestOneActiveFoundation:
    def test_cannot_activate_two_product_families(self, tmp_path: Path) -> None:
        stack = _Stack(tmp_path)
        stack.runtimes = RuntimeCatalogue((VllmRuntimeSupport(), _LlamaStub()))
        stack.instances = InstanceService(
            stack.store,
            stack.clock,
            stack.inventory,
            stack.resources,
            stack.executions,
            stack.runtimes,
        )
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=4 * GIB)
        live = InferenceInstance(
            instance_id=InstanceId.generate(),
            host_id=reservation.host_id,
            model_id=artifact.model_id,
            runtime=Name("vllm"),
            executor=NATIVE,
            lifecycle_state=LifecycleState.RUNNING,
            health=HealthState.HEALTHY,
            configuration_version=1,
            observed_state=ObservedState.RUNNING,
            created_at=now_utc(),
            last_observed_at=now_utc(),
        )
        stack.store.put(live.instance_id.value, live)
        assert stack.instances.live_product_families(reservation.host_id) == {"vllm"}
        other = stack.stored(name="other-model")
        second = stack.resources.admit(
            _request(other, stack.envelope, vram=4 * GIB),
            stack.envelope,
            other,
        )
        assert second.reservation is not None
        with pytest.raises(ConflictError, match="already active"):
            stack.instances.create(other, second.reservation, runtime=Name("llama.cpp"))

    def test_same_family_second_instance_is_not_a_foreign_foundation(
        self, tmp_path: Path
    ) -> None:
        stack = _Stack(tmp_path)
        stack.runtimes = RuntimeCatalogue((VllmRuntimeSupport(),))
        stack.instances = InstanceService(
            stack.store,
            stack.clock,
            stack.inventory,
            stack.resources,
            stack.executions,
            stack.runtimes,
        )
        artifact = stack.stored()
        reservation = stack.reserve(artifact, vram=4 * GIB)
        live = InferenceInstance(
            instance_id=InstanceId.generate(),
            host_id=reservation.host_id,
            model_id=artifact.model_id,
            runtime=Name("vllm"),
            executor=NATIVE,
            lifecycle_state=LifecycleState.RUNNING,
            health=HealthState.HEALTHY,
            configuration_version=1,
            observed_state=ObservedState.RUNNING,
            created_at=now_utc(),
            last_observed_at=now_utc(),
        )
        stack.store.put(live.instance_id.value, live)
        other = stack.stored(name="same-family")
        second = stack.resources.admit(
            _request(other, stack.envelope, vram=4 * GIB),
            stack.envelope,
            other,
        )
        assert second.reservation is not None
        created = stack.instances.create(
            other, second.reservation, runtime=Name("vllm")
        )
        assert created.runtime.value == "vllm"


class TestFoundationTransition:
    def test_same_family_is_model_switch_not_rebootstrap(self) -> None:
        host = host_capabilities()
        transition = classify_transition(
            host.host_id,
            from_family="vllm",
            to_family="vllm",
            from_candidate_id="rcand_aaaaaaaaaaaaaaaa",
            to_candidate_id="rcand_bbbbbbbbbbbbbbbb",
            production_executable=True,
        )
        assert transition.transition_kind is FoundationTransitionKind.MODEL_SWITCH
        assert "stop_live_inference" in transition.required_actions
        assert "runtime_capability_profile" in transition.reusable
        assert "deployment_plan" in transition.must_recompute
        assert "host_capabilities" in transition.reusable
        assert "storage_evidence" in transition.reusable

    def test_family_change_is_rebootstrap(self) -> None:
        host = host_capabilities()
        transition = classify_transition(
            host.host_id,
            from_family="vllm",
            to_family="llama.cpp",
            from_candidate_id="rcand_aaaaaaaaaaaaaaaa",
            to_candidate_id="rcand_bbbbbbbbbbbbbbbb",
            production_executable=False,
        )
        assert transition.transition_kind is (
            FoundationTransitionKind.FOUNDATION_REBOOTSTRAP
        )
        assert transition.production_executable is False
        assert "verify_runtime" in transition.required_actions
        assert "fresh_deployment_plan" in transition.required_actions
        assert "resource_manager_admission" in transition.required_actions
        assert "inference_instance" in transition.must_recompute
        assert "host_capabilities" in transition.reusable
        assert "storage_evidence" in transition.reusable

    def test_unimplemented_target_cannot_proceed_as_verified(
        self, tmp_path: Path
    ) -> None:
        host = host_capabilities()
        foundation, _ = _services(tmp_path)
        instances = InstanceService(
            FileStore(tmp_path / "i"),
            FixedClock(now_utc()),
            ModelInventory(
                FileStore(tmp_path / "inv"), ModelArtifactStore(tmp_path / "m")
            ),
            ResourceManager(
                FileStore(tmp_path / "r"),
                FixedClock(now_utc()),
                AdmissionLock(tmp_path / "l"),
            ),
            ExecutionService(RecordingExecutor(), FileStore(tmp_path / "e")),
            RuntimeCatalogue((VllmRuntimeSupport(), LlamaCppRuntimeSupport())),
        )
        service = FoundationTransitionService(foundation, instances)
        service.inspect(host, to_family="llama.cpp", production_executable=False)
        with pytest.raises(PreconditionFailedError, match="not a verified"):
            service.require_production_executable(
                classify_transition(
                    host.host_id,
                    from_family="vllm",
                    to_family="llama.cpp",
                    production_executable=False,
                )
            )
        assert production_executable_for(None, None) is False


class TestBoundaries:
    def test_preference_does_not_import_resource_or_inference(self) -> None:
        leaks = _imports_named(
            SOURCE / "kultrun" / "runtime" / "preference.py",
            "kultrun.resource",
            "kultrun.inference",
            "kultrun.planning",
            "kultrun.execution",
            "kultrun.model",
            "kultrun.capacity",
        )
        assert leaks == []
        manager = (SOURCE / "kultrun" / "resource" / "manager.py").read_text(
            encoding="utf-8"
        )
        assert "llama.cpp" not in manager
        assert "mlx" not in manager
        assert "vllm" not in manager.lower()
        replan = (SOURCE / "kultrun" / "platform" / "storage_replan.py").read_text(
            encoding="utf-8"
        )
        assert "RuntimePreferencePolicy" not in replan
        assert "comfortable_storage" not in replan

    def test_selection_invalidates_downstream_on_family_change(
        self, tmp_path: Path
    ) -> None:
        host = host_capabilities()
        foundation, _ = _services(tmp_path)
        descriptors = (VllmRuntimeSupport().support(), _product_llama())
        first = foundation.select_auto(
            host,
            (_native(host),),
            descriptors,
            components={"vllm": "missing"},
            storage_evidence=_storage(host, 80 * GIB),
        )
        llama = next(
            item
            for item in first.resolution.candidates
            if item.runtime.value == "llama.cpp"
        )
        second = foundation.select_manual(
            llama.candidate_id.value,
            host,
            (_native(host),),
            descriptors,
            components={"vllm": "missing"},
            storage_evidence=_storage(host, 80 * GIB),
        )
        assert second.selection.generation == first.selection.generation + 1
        assert second.selection.downstream_stale is True
        assert second.selection.stale_domains == STALE_DOMAINS
        assert "eligible_model_view" in second.selection.stale_domains
        assert "deployment_plan" in second.selection.stale_domains
        assert "resource_request" in second.selection.stale_domains

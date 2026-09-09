"""Bounded highest-pressure vLLM runtime-memory calibration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.runtime.vllm_memory import (
    VllmMemoryInterpreter,
    format_fixture_logs,
)
from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import MemoryPlacement, ModelId, ModelRequirement
from kultrun.planning.contracts import SelectionPolicy
from kultrun.platform.available_models import (
    AvailableModelsLock,
    AvailableModelsService,
)
from kultrun.platform.runtime_memory import (
    CALIBRATED_INSUFFICIENT_VRAM,
    VALIDATION_UNRESOLVED,
    RuntimeMemoryCalibrationService,
    apply_runtime_profile,
    profile_store_key,
)
from kultrun.resource.contracts import (
    RequestId,
    ReservationState,
    ResourceRequest,
    WorkloadType,
)
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.contracts import (
    RuntimeMemoryProfile,
    RuntimeMemoryProfileId,
    RuntimeMemoryProfileStatus,
    RuntimeValidationStatus,
)
from kultrun.runtime.memory import (
    PressureMember,
    base_model_memory,
    calibrated_runtime_extra,
    compose_serving_vram,
    measured_non_kv_bytes,
    probe_order,
    raise_only,
    runtime_extra_bytes,
    runtime_memory_class,
    select_sentinel,
    vram_pressure,
)
from kultrun.runtime.ports import InterpretedRuntimeMemory
from tests.test_capacity import host as host_facts
from tests.test_model_funnel import (
    _envelope,
    _MapEstimator,
    _ScriptedSource,
    _service,
    _view_for,
)
from tests.test_planning_selection import _capacity
from tests.test_resource_admission import _artifact
from tests.test_resource_admission import _envelope as _resource_envelope

GIB = 1024**3


def _class(**overrides: object):
    keys = {
        "runtime": "vllm",
        "runtime_version": "0.28.0",
        "executor": "native-process",
        "capability_basis": "rcap_test",
        "accelerator_architecture": "nvidia:blackwell",
        "model_architecture": "qwen2",
        "quantization": "awq",
        "context_tokens": 8192,
        "concurrency": 1,
        "kv_dtype": "fp16",
        "model_id": "qwen-14b",
    }
    keys.update(overrides)
    return runtime_memory_class(**keys)


class TestValidationClass:
    def test_same_material_fields_share_a_class(self) -> None:
        first = _class(model_id="qwen-0.5b")
        second = _class(model_id="qwen-7b")
        assert first.token == second.token
        assert not first.singleton

    def test_quantization_splits_class(self) -> None:
        assert _class(quantization="awq").token != _class(quantization="fp16").token

    def test_architecture_splits_class(self) -> None:
        assert _class(model_architecture="qwen2").token != _class(
            model_architecture="llama"
        ).token

    def test_context_splits_class(self) -> None:
        assert _class(context_tokens=8192).token != _class(context_tokens=4096).token

    def test_runtime_version_splits_class(self) -> None:
        assert _class(runtime_version="0.28.0").token != _class(
            runtime_version="0.27.0"
        ).token

    def test_unresolved_material_is_singleton(self) -> None:
        unknown = _class(model_architecture=NOT_PROVIDED, model_id="lone")
        other = _class(model_architecture=NOT_PROVIDED, model_id="other")
        assert unknown.singleton
        assert unknown.token != other.token

    def test_class_key_is_deterministic(self) -> None:
        assert _class().token == _class().token


class TestPressureAndSentinel:
    def test_highest_pressure_is_sentinel_not_parameter_count(self) -> None:
        available = 24 * GIB
        members = (
            PressureMember("a", 5 * GIB, vram_pressure(5 * GIB, available)),
            PressureMember("b", 11 * GIB, vram_pressure(11 * GIB, available)),
            PressureMember("c", 19 * GIB, vram_pressure(19 * GIB, available)),
        )
        assert (
            members[2].vram_pressure
            > members[1].vram_pressure
            > members[0].vram_pressure
        )
        assert select_sentinel(members).model_id == "c"

    def test_class_sentinels_and_global_probe_order(self) -> None:
        available = 24 * GIB
        qwen = (
            PressureMember("qwen-0.5b", 2 * GIB, vram_pressure(2 * GIB, available)),
            PressureMember("qwen-7b", 6 * GIB, vram_pressure(6 * GIB, available)),
            PressureMember("qwen-14b", 11 * GIB, vram_pressure(11 * GIB, available)),
        )
        llama = (
            PressureMember("llama-8b", 20 * GIB, vram_pressure(20 * GIB, available)),
        )
        assert select_sentinel(qwen).model_id == "qwen-14b"
        assert select_sentinel(llama).model_id == "llama-8b"
        order = probe_order((select_sentinel(qwen), select_sentinel(llama)))
        assert [item.model_id for item in order] == ["llama-8b", "qwen-14b"]


class TestProbeDerivation:
    def test_non_kv_is_budget_minus_available_kv(self) -> None:
        assert measured_non_kv_bytes(20 * GIB, 6 * GIB) == 14 * GIB

    def test_negative_kv_still_yields_usable_non_kv(self) -> None:
        assert measured_non_kv_bytes(10 * GIB, -2 * GIB) == 12 * GIB

    def test_runtime_extra_is_non_kv_minus_load(self) -> None:
        result = runtime_extra_bytes(14 * GIB, 10 * GIB)
        assert result.valid
        assert result.extra_bytes == 4 * GIB

    def test_negative_runtime_extra_is_invalid(self) -> None:
        result = runtime_extra_bytes(10 * GIB, 12 * GIB)
        assert not result.valid
        assert result.extra_bytes is None

    def test_non_finite_runtime_extra_is_invalid(self) -> None:
        result = runtime_extra_bytes(14 * GIB, float("nan"))  # type: ignore[arg-type]
        assert not result.valid

    def test_interpreter_parses_vllm_lines(self) -> None:
        logs = format_fixture_logs(
            model_load_bytes=round(9.38 * GIB),
            available_kv_bytes=round(-2.38 * GIB),
        )
        parsed = VllmMemoryInterpreter().interpret(
            stdout=logs, stderr="", probe_budget_bytes=round(10.37 * GIB)
        )
        assert parsed.usable
        assert parsed.available_kv_bytes == round(-2.38 * GIB)
        assert parsed.model_load_bytes == round(9.38 * GIB)

    def test_base_model_floor_uses_safetensors(self) -> None:
        assert base_model_memory(round(7.8 * GIB), round(9.3 * GIB)) == round(9.3 * GIB)


class TestCalibrationTransfer:
    def test_same_class_extra_and_total_only_rise(self) -> None:
        extra = calibrated_runtime_extra(
            static_runtime_extra=GIB,
            sentinel_floor=3 * GIB,
            sentinel_ratio=0.4,
            candidate_base_bytes=8 * GIB,
        )
        assert extra >= GIB
        static_total = 10 * GIB
        calibrated = compose_serving_vram(
            base_model_bytes=8 * GIB,
            runtime_extra_bytes=extra,
            kv_bytes=GIB,
            safety_bytes=GIB,
        )
        total, lowered = raise_only(static_total, calibrated)
        assert total >= static_total
        assert not lowered

    def test_different_class_does_not_share_a_key(self) -> None:
        qwen = _class(model_architecture="qwen2", quantization="awq")
        llama = _class(model_architecture="llama", quantization="fp16")
        assert qwen.token != llama.token

    def test_member_does_not_inherit_sentinel_measured_load(self) -> None:
        load = 11 * GIB
        extra = 3 * GIB
        member_weights = 8 * GIB
        requirement = _requirement(
            weights=member_weights, kv=0, extra=0, safety=0
        )
        profile = RuntimeMemoryProfile(
            profile_id=RuntimeMemoryProfileId.parse("rmp_" + "c" * 16),
            status=RuntimeMemoryProfileStatus.MEASURED,
            basis_fingerprint="qwen-awq",
            class_key="qwen-awq",
            source_model_id="qwen-14b",
            runtime="vllm",
            host_id=HostId.generate(),
            host_fingerprint="host",
            measured_at=now_utc(),
            confidence=Confidence.HIGH,
            vllm_model_load_bytes=load,
            derived_runtime_extra_bytes=extra,
            runtime_extra_floor_bytes=extra,
            runtime_extra_ratio=extra / load,
        )
        applied = apply_runtime_profile(
            requirement,
            profile=profile,
            role="member",
            safetensors_bytes=None,
            class_key="qwen-awq",
            sentinel_model_id="qwen-14b",
            cached=True,
        )
        assert applied.base_model_bytes == member_weights
        assert applied.base_model_bytes != load
        assert applied.runtime_extra_bytes >= extra
        assert applied.status is RuntimeValidationStatus.CACHED_RUNTIME_CALIBRATION


def _requirement(
    *,
    weights: int,
    kv: int,
    extra: int = 0,
    safety: int = 768 * 1024 * 1024,
    ram: int = 8 * GIB,
) -> ModelRequirement:
    total = weights + extra + kv + safety
    return ModelRequirement(
        model_id=ModelId.generate(),
        confidence=Confidence.MEDIUM,
        storage_bytes=weights,
        peak_additional_bytes=weights,
        vram_weights_bytes=weights,
        vram_kv_bytes_per_token=kv // 8192 if kv else NOT_PROVIDED,
        vram_overhead_bytes=extra,
        ram_bytes=ram,
        estimated_vram_bytes=total,
        assumed_context_tokens=8192,
        assumed_batch_size=1,
        vram_kv_cache_bytes=kv,
        safety_allowance_bytes=safety,
        estimator_provider="llmfit",
        estimation_method="llmfit-plan",
        assumed_runtime="vllm",
        assumed_runtime_version="0.28.0",
    )


class TestFourteenBFailureReplay:
    def test_calibrated_total_exceeds_disproven_static(self) -> None:
        static = round(10.37 * GIB)
        budget = static
        load = round(9.38 * GIB)
        kv_available = round(-2.38 * GIB)
        kv_required = round(1.5 * GIB)
        non_kv = measured_non_kv_bytes(budget, kv_available)
        extra = runtime_extra_bytes(non_kv, load)
        assert extra.valid
        assert extra.extra_bytes is not None
        assert non_kv > budget
        requirement = _requirement(
            weights=round(7.885 * GIB),
            kv=kv_required,
            extra=0,
            safety=static - round(7.885 * GIB) - kv_required,
        )
        profile = RuntimeMemoryProfile(
            profile_id=RuntimeMemoryProfileId.parse("rmp_" + "b" * 16),
            status=RuntimeMemoryProfileStatus.MEASURED,
            basis_fingerprint="qwen-awq",
            class_key="qwen-awq",
            source_model_id="qwen2.5-14b-instruct-awq",
            runtime="vllm",
            executor="native-process",
            host_id=HostId.generate(),
            host_fingerprint="host",
            quantization="awq",
            context_tokens=8192,
            concurrency=1,
            probe_budget_bytes=budget,
            vllm_model_load_bytes=load,
            vllm_available_kv_bytes=kv_available,
            derived_non_kv_bytes=non_kv,
            derived_runtime_extra_bytes=extra.extra_bytes,
            runtime_extra_floor_bytes=extra.extra_bytes,
            measured_at=now_utc(),
            confidence=Confidence.HIGH,
        )
        applied = apply_runtime_profile(
            requirement,
            profile=profile,
            role="sentinel",
            safetensors_bytes=round(9.3 * GIB),
            class_key="qwen-awq",
            sentinel_model_id="qwen2.5-14b-instruct-awq",
            cached=False,
        )
        assert applied.requirement.estimated_vram_bytes != static
        assert applied.requirement.estimated_vram_bytes > static
        assert applied.status is RuntimeValidationStatus.MEASURED_RUNTIME


class TestBoundedOrchestration:
    def test_four_candidates_two_classes_two_probes(self, tmp_path: Path) -> None:
        names = {
            "qwen2.5-0.5b-instruct-awq",
            "qwen2.5-7b-instruct-awq",
            "qwen2.5-14b-instruct-awq",
            "llama-3.1-8b-instruct-fp16",
        }
        catalog = tuple(
            item
            for item in __import__(
                "kultrun.adapters.model_source.candidates",
                fromlist=["packaged_candidates"],
            ).packaged_candidates()
            if item.metadata.logical_name.value in names
        )
        assert len(catalog) == 4
        ids = [item.metadata.model_id.value for item in catalog]
        demands = {
            next(
                item.metadata.model_id.value
                for item in catalog
                if item.metadata.logical_name.value == "qwen2.5-0.5b-instruct-awq"
            ): 2 * GIB,
            next(
                item.metadata.model_id.value
                for item in catalog
                if item.metadata.logical_name.value == "qwen2.5-7b-instruct-awq"
            ): 6 * GIB,
            next(
                item.metadata.model_id.value
                for item in catalog
                if item.metadata.logical_name.value == "qwen2.5-14b-instruct-awq"
            ): 11 * GIB,
            next(
                item.metadata.model_id.value
                for item in catalog
                if item.metadata.logical_name.value == "llama-3.1-8b-instruct-fp16"
            ): 20 * GIB,
        }
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=4))
        host = host_facts()
        envelope, gpu_host = _envelope(host, vram=24 * GIB)
        capacity = replace(
            _capacity(vram=24 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="multi",
            available_vram_bytes=24 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = _service(tmp_path, models, _MapEstimator(demands)).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible=set(ids)),
            envelope,
            capacity,
            persist=True,
        )
        assert result.available.estimated_feasible_count == 4
        assert result.available.validation_class_count == 2
        assert result.available.probe_invocations == 2
        assert result.validation is not None
        assert result.validation.probe_order[0] == next(
            item.metadata.model_id.value
            for item in catalog
            if item.metadata.logical_name.value == "llama-3.1-8b-instruct-fp16"
        )

    def test_unresolved_validation_is_not_available(self, tmp_path: Path) -> None:
        catalog = __import__(
            "kultrun.adapters.model_source.candidates",
            fromlist=["packaged_candidates"],
        ).packaged_candidates()[:1]
        ident = catalog[0].metadata.model_id.value
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=1))
        host = host_facts()
        envelope, gpu_host = _envelope(host)
        capacity = replace(
            _capacity(vram=30 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="unresolved",
            available_vram_bytes=30 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        store = FileStore(tmp_path / "records")
        clock = FixedClock(now_utc())
        failed = InterpretedRuntimeMemory(
            model_load_bytes=None,
            available_kv_bytes=None,
            usable=False,
            reason="no_profile",
        )
        result = AvailableModelsService(
            store,
            clock,
            models,
            _MapEstimator({ident: 8 * GIB}),
            SelectionPolicy(),
            AvailableModelsLock(tmp_path / "locks"),
            calibrator=RuntimeMemoryCalibrationService(
                store,
                clock,
                VllmMemoryInterpreter(),
                scripted={ident: failed},
            ),
        ).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible={ident}),
            envelope,
            capacity,
            persist=True,
        )
        assert result.available.available_count == 0
        assert result.available.probe_invocations == 1
        assert any(
            item.reason == VALIDATION_UNRESOLVED for item in result.available.exclusions
        )

    def test_usable_negative_kv_profile_calibrates_class(self, tmp_path: Path) -> None:
        names = {
            "qwen2.5-0.5b-instruct-awq",
            "qwen2.5-7b-instruct-awq",
            "qwen2.5-14b-instruct-awq",
        }
        catalog = tuple(
            item
            for item in __import__(
                "kultrun.adapters.model_source.candidates",
                fromlist=["packaged_candidates"],
            ).packaged_candidates()
            if item.metadata.logical_name.value in names
        )
        ids = [item.metadata.model_id.value for item in catalog]
        demands = {
            next(
                item.metadata.model_id.value
                for item in catalog
                if "0.5b" in item.metadata.logical_name.value
            ): 2 * GIB,
            next(
                item.metadata.model_id.value
                for item in catalog
                if "7b" in item.metadata.logical_name.value
                and "14b" not in item.metadata.logical_name.value
            ): 6 * GIB,
            next(
                item.metadata.model_id.value
                for item in catalog
                if "14b" in item.metadata.logical_name.value
            ): 11 * GIB,
        }
        sentinel = next(
            item.metadata.model_id.value
            for item in catalog
            if "14b" in item.metadata.logical_name.value
        )
        small = next(
            item.metadata.model_id.value
            for item in catalog
            if "0.5b" in item.metadata.logical_name.value
        )
        budget = round(10.37 * GIB)
        load = round(9.38 * GIB)
        kv = round(-2.38 * GIB)
        non_kv = measured_non_kv_bytes(budget, kv)
        extra = runtime_extra_bytes(non_kv, load)
        assert extra.valid
        store = FileStore(tmp_path / "records")
        clock = FixedClock(now_utc())
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=3))
        host = host_facts()
        envelope, gpu_host = _envelope(host, vram=24 * GIB)
        capacity = replace(
            _capacity(vram=24 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="negkv",
            available_vram_bytes=budget,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = AvailableModelsService(
            store,
            clock,
            models,
            _MapEstimator(demands),
            SelectionPolicy(),
            AvailableModelsLock(tmp_path / "locks"),
            calibrator=RuntimeMemoryCalibrationService(
                store,
                clock,
                VllmMemoryInterpreter(),
                scripted={
                    sentinel: InterpretedRuntimeMemory(
                        model_load_bytes=load,
                        available_kv_bytes=kv,
                        usable=True,
                        extra=extra,
                    )
                },
            ),
        ).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible=set(ids)),
            envelope,
            capacity,
            persist=True,
        )
        assert result.available.probe_invocations == 1
        available_ids = {item.model_id for item in result.available.members}
        assert small in available_ids
        assert sentinel not in available_ids or any(
            item.reason == CALIBRATED_INSUFFICIENT_VRAM
            for item in result.available.exclusions
            if item.model_id == sentinel
        )

    def test_cached_profile_recomputes_without_new_probe(self, tmp_path: Path) -> None:
        names = {
            "qwen2.5-0.5b-instruct-awq",
            "qwen2.5-7b-instruct-awq",
            "qwen2.5-14b-instruct-awq",
        }
        catalog = tuple(
            item
            for item in __import__(
                "kultrun.adapters.model_source.candidates",
                fromlist=["packaged_candidates"],
            ).packaged_candidates()
            if item.metadata.logical_name.value in names
        )
        ids = [item.metadata.model_id.value for item in catalog]
        demands = {
            next(
                item.metadata.model_id.value
                for item in catalog
                if "0.5b" in item.metadata.logical_name.value
            ): 5 * GIB,
            next(
                item.metadata.model_id.value
                for item in catalog
                if "7b" in item.metadata.logical_name.value
                and "14b" not in item.metadata.logical_name.value
            ): 8 * GIB,
            next(
                item.metadata.model_id.value
                for item in catalog
                if "14b" in item.metadata.logical_name.value
            ): 11 * GIB,
        }
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=3))
        host = host_facts()
        envelope, gpu_host = _envelope(host, vram=24 * GIB)
        service = _service(tmp_path, models, _MapEstimator(demands))
        view = _view_for(gpu_host, catalog, eligible=set(ids))
        first = service.evaluate(
            gpu_host,
            view,
            envelope,
            replace(
                _capacity(vram=24 * GIB),
                host_id=gpu_host.host_id,
                snapshot_basis="wide",
                available_vram_bytes=24 * GIB,
                available_ram_bytes=64 * GIB,
                available_storage_bytes=500 * GIB,
            ),
            persist=True,
        )
        assert first.available.available_count == 3
        assert first.available.probe_invocations == 1
        squeezed = service.evaluate(
            gpu_host,
            view,
            envelope,
            replace(
                _capacity(vram=24 * GIB),
                host_id=gpu_host.host_id,
                snapshot_basis="narrow",
                available_vram_bytes=9 * GIB,
                available_ram_bytes=64 * GIB,
                available_storage_bytes=500 * GIB,
            ),
            persist=True,
        )
        assert squeezed.available.probe_invocations == 0
        assert squeezed.available.available_count == 2
        seven = next(
            item.metadata.model_id.value
            for item in catalog
            if "7b" in item.metadata.logical_name.value
            and "14b" not in item.metadata.logical_name.value
        )
        squeezed_seven = next(
            item for item in squeezed.available.members if item.model_id == seven
        )
        assert isinstance(squeezed_seven.required_vram_bytes, int)
        assert squeezed_seven.required_vram_bytes <= 9 * GIB
        restored = service.evaluate(
            gpu_host,
            view,
            envelope,
            replace(
                _capacity(vram=24 * GIB),
                host_id=gpu_host.host_id,
                snapshot_basis="wide-again",
                available_vram_bytes=24 * GIB,
                available_ram_bytes=64 * GIB,
                available_storage_bytes=500 * GIB,
            ),
            persist=True,
        )
        assert restored.available.probe_invocations == 0
        assert restored.available.available_count == 3

    def test_temporary_probe_reservation_is_released(self, tmp_path: Path) -> None:
        clock = FixedClock(now_utc())
        store = FileStore(tmp_path / "records")
        resources = ResourceManager(store, clock, AdmissionLock(tmp_path / "locks"))
        envelope = _resource_envelope()
        artifact = _artifact()
        before = resources.snapshot(envelope)
        available_before = before.accelerators[0].available_bytes
        request = ResourceRequest(
            request_id=RequestId.generate(),
            host_id=envelope.host_id,
            artifact_id=artifact.artifact_id,
            model_id=artifact.model_id,
            plan_fingerprint="runtime-memory-probe|sentinel",
            placement=MemoryPlacement.DISCRETE_GPU,
            ram_bytes=8 * GIB,
            accelerator_bytes=available_before
            if isinstance(available_before, int)
            else 10 * GIB,
            unified_bytes=NOT_PROVIDED,
            accelerator_index=0,
            workload_type=WorkloadType.EVALUATION,
        )
        admitted = resources.admit(request, envelope, artifact)
        assert admitted.reservation is not None
        held = resources.snapshot(envelope)
        assert held.accelerators[0].available_bytes != available_before
        store.put(
            profile_store_key(envelope.host_id.value, "class-a"),
            RuntimeMemoryProfile(
                profile_id=RuntimeMemoryProfileId.parse(
                    profile_store_key(envelope.host_id.value, "class-a")
                ),
                status=RuntimeMemoryProfileStatus.MEASURED,
                basis_fingerprint="class-a",
                class_key="class-a",
                source_model_id="sentinel",
                runtime="vllm",
                executor="native-process",
                host_id=envelope.host_id,
                host_fingerprint=envelope.host_fingerprint,
                quantization="awq",
                context_tokens=8192,
                concurrency=1,
                probe_budget_bytes=10 * GIB,
                derived_non_kv_bytes=12 * GIB,
                derived_runtime_extra_bytes=3 * GIB,
                runtime_extra_floor_bytes=3 * GIB,
                measured_at=clock.now(),
                confidence=Confidence.HIGH,
            ),
        )
        released = resources.release(admitted.reservation.reservation_id)
        assert released.state is ReservationState.RELEASED
        restored = resources.snapshot(envelope)
        assert restored.accelerators[0].available_bytes == available_before
        assert not any(
            item.state is ReservationState.ACTIVE for item in resources.reservations()
        )

"""Staged model funnel: discovery → compatibility → cheap bound → Available Models."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kultrun.adapters.estimators.llmfit import (
    LlmfitRequirementEstimator,
    fixture_plan,
)
from kultrun.adapters.host import fixtures
from kultrun.adapters.model_source.accelerate_fit import AccelerateStructuralProvider
from kultrun.adapters.model_source.candidates import (
    acceptance_candidate,
    packaged_candidates,
)
from kultrun.adapters.model_source.huggingface import HuggingFaceSource
from kultrun.adapters.model_source.safetensors import (
    SafetensorsWeightEvidenceProvider,
    serialized_tensor_bytes,
)
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.runtime.vllm_memory import VllmMemoryInterpreter
from kultrun.api.contracts import Method
from kultrun.capacity.envelope import CapacityService
from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.main import main
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import (
    CheapSizeClass,
    MemoryPlacement,
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelId,
    ModelRequirement,
    WeightEvidenceSource,
)
from kultrun.model.discovery import (
    DiscoveryQuery,
    DiscoveryResult,
    FunnelQuery,
    RemoteDiscoveryHit,
)
from kultrun.model.ports import WeightEvidenceProvider
from kultrun.planning.contracts import (
    AvailableViewStatus,
    DeploymentPlan,
    ModelSelection,
    ModelSelectionId,
    ModelSelectionMode,
    SelectionPolicy,
)
from kultrun.planning.evaluate import cheap_weight_fit
from kultrun.planning.service import SelectionService
from kultrun.platform.available_models import (
    AvailableModelsLock,
    AvailableModelsService,
    format_available_models,
    format_funnel,
)
from kultrun.platform.capacity_snapshot import revalidation_plan_basis
from kultrun.platform.model_selection import (
    ModelSelectionLock,
    ModelSelectionService,
)
from kultrun.platform.runtime_memory import RuntimeMemoryCalibrationService
from kultrun.runtime.contracts import (
    EligibilityReasonCode,
    EligibleModelView,
    EligibleViewStatus,
    RuntimeEligibilityStatus,
    RuntimeEligibleModelCandidate,
)
from kultrun.runtime.eligibility import fingerprint_view_id
from tests.test_capacity import accelerator, mount
from tests.test_capacity import host as host_facts
from tests.test_planning_selection import _capacity
from tests.test_runtime_model_selection import _call, _product, _realize

GIB = 1024**3
SOURCE = Path(__file__).resolve().parent.parent / "src"


class _ScriptedSource:
    identity = Name("huggingface")

    def __init__(
        self,
        entries: tuple[ModelCatalogEntry, ...],
        discovered: tuple[ModelCatalogEntry, ...],
        *,
        universe: int,
        hits: tuple[RemoteDiscoveryHit, ...] = (),
        fail: bool = False,
    ) -> None:
        self._entries = entries
        self._discovered = discovered
        self._universe = universe
        self._hits = hits
        self._fail = fail
        self.seen: DiscoveryQuery | None = None

    def candidates(self) -> tuple[ModelCatalogEntry, ...]:
        return self._entries

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        self.seen = query
        if self._fail:
            raise RuntimeError("hub down")
        return DiscoveryResult(
            universe_count=self._universe,
            discovered_count=len(self._discovered),
            criteria=query,
            catalog_entries=self._discovered,
            remote_hits=self._hits,
            live=True,
        )


class _MapEstimator:
    identity = Name("kultrun")
    version = "funnel-test"

    def __init__(self, vram: dict[str, int | object]) -> None:
        self.vram = vram
        self.calls: list[str] = []

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        self.calls.append(request.model_id.value)
        value = self.vram[request.model_id.value]
        return ModelRequirement(
            model_id=request.model_id,
            confidence=Confidence.MEDIUM,
            storage_bytes=0,
            peak_additional_bytes=0,
            vram_weights_bytes=value if isinstance(value, int) else NOT_PROVIDED,
            vram_kv_bytes_per_token=NOT_PROVIDED,
            vram_overhead_bytes=0,
            ram_bytes=GIB,
            unified_memory_bytes=NOT_PROVIDED,
            estimated_vram_bytes=value if isinstance(value, int) else NOT_PROVIDED,
            assumed_context_tokens=8192,
            supported_runtimes=(str(request.runtime),),
            estimation_method="funnel-test",
            estimator_provider="kultrun",
            estimator_version=self.version,
            assumed_runtime=str(request.runtime),
            assumed_batch_size=1,
        )


def _meta_offsets(total: int) -> dict[str, object]:
    return {"tensors": {"w": {"data_offsets": [0, total], "dtype": "F16"}}}


def _fetch_map(mapping: dict[str, dict[str, object] | None]):
    def fetch(entry: ModelCatalogEntry) -> dict[str, object] | None:
        return mapping.get(entry.metadata.source_ref)

    return fetch


class _CountingProvider:
    def __init__(self, inner: WeightEvidenceProvider) -> None:
        self.inner = inner
        self.calls: list[str] = []

    @property
    def identity(self) -> Name:
        return self.inner.identity

    def footprint(self, entry: ModelCatalogEntry):
        self.calls.append(entry.metadata.source_ref)
        return self.inner.footprint(entry)


def _view_for(
    host,
    entries: tuple[ModelCatalogEntry, ...],
    *,
    eligible: set[str],
    blocked: set[str] | None = None,
    blocked_code: EligibilityReasonCode = (
        EligibilityReasonCode.UNSUPPORTED_ARCHITECTURE
    ),
) -> EligibleModelView:
    blocked = blocked or set()
    rows = []
    for entry in entries:
        ident = entry.metadata.model_id.value
        if ident in eligible:
            status = RuntimeEligibilityStatus.ELIGIBLE
            codes: tuple[EligibilityReasonCode, ...] = ()
            reasons: tuple[str, ...] = ()
        elif ident in blocked:
            status = RuntimeEligibilityStatus.BLOCKED
            codes = (blocked_code,)
            reasons = ("blocked by eligibility",)
        else:
            status = RuntimeEligibilityStatus.UNRESOLVED
            codes = (EligibilityReasonCode.REQUIRED_MODEL_METADATA_MISSING,)
            reasons = ("metadata missing",)
        rows.append(
            RuntimeEligibleModelCandidate(
                model_id=ident,
                logical_name=entry.metadata.logical_name.value,
                status=status,
                reason_codes=codes,
                reasons=reasons,
                architecture=entry.metadata.architecture,
                quantization=entry.metadata.quantization,
                family=entry.metadata.family,
            )
        )
    return EligibleModelView(
        view_id=fingerprint_view_id(host.host_id.value, "cand", "prof", 1),
        host_id=host.host_id,
        status=EligibleViewStatus.CURRENT,
        evaluated_at=now_utc(),
        selection_mode="auto",
        selected_candidate_id="cand",
        runtime="vllm",
        runtime_version="0.28.0",
        executor="native-process",
        profile_id="prof",
        eligible_count=len(eligible),
        blocked_count=len(blocked),
        unresolved_count=len(entries) - len(eligible) - len(blocked),
        candidates=tuple(rows),
    )


def _envelope(host, vram: int = 30 * GIB):
    gpu_host = replace(
        host_facts(
            memory_total=64 * GIB,
            accelerators=(accelerator(memory=vram),),
            mounts=(mount(),),
        ),
        host_id=host.host_id,
        fingerprint=host.fingerprint,
    )
    return CapacityService(clock=FixedClock(now_utc())).compute(gpu_host, {}), gpu_host


def _service(
    tmp_path: Path,
    models: ModelCatalogue,
    estimator,
    *,
    weights=None,
    structural=None,
    policy: SelectionPolicy | None = None,
) -> AvailableModelsService:
    store = FileStore(tmp_path / "records")
    clock = FixedClock(now_utc())
    return AvailableModelsService(
        store,
        clock,
        models,
        estimator,
        policy or SelectionPolicy(),
        AvailableModelsLock(tmp_path / "locks"),
        weights=weights,
        structural=structural,
        calibrator=RuntimeMemoryCalibrationService(
            store, clock, VllmMemoryInterpreter()
        ),
    )


class TestDiscovery:
    def test_filters_are_passed_to_the_lister(self) -> None:
        seen: list[DiscoveryQuery] = []

        def list_models(query: DiscoveryQuery) -> tuple[RemoteDiscoveryHit, ...]:
            seen.append(query)
            return (RemoteDiscoveryHit("org/demo", pipeline_tag="text-generation"),)

        list_models.universe_count = 250  # type: ignore[attr-defined]
        source = HuggingFaceSource(list_models=list_models)
        query = DiscoveryQuery(
            pipeline_tag="text-generation",
            gated=False,
            apps=("vllm",),
            tags=("conversational",),
            search="qwen",
            parameter_max=8_000_000_000,
            limit=40,
        )
        result = source.discover(query)
        assert seen == [query]
        assert result.universe_count == 250
        assert result.payload()["compatibility"] is False
        names = {entry.metadata.logical_name.value for entry in result.catalog_entries}
        assert "qwen2.5-7b-instruct-awq" in names
        assert result.live is True

    def test_curated_survives_empty_remote_and_missing_vllm_tag(self) -> None:
        def list_models(_query: DiscoveryQuery) -> tuple[RemoteDiscoveryHit, ...]:
            return ()

        result = HuggingFaceSource(list_models=list_models).discover(DiscoveryQuery())
        assert result.catalog_entries == packaged_candidates()
        assert "vllm app tag" in " ".join(result.notes)

    def test_gated_filter_is_source_native(self) -> None:
        def list_models(query: DiscoveryQuery) -> tuple[RemoteDiscoveryHit, ...]:
            assert query.gated is False
            return ()

        HuggingFaceSource(list_models=list_models).discover(DiscoveryQuery(gated=False))

    def test_listing_failure_keeps_catalog(self) -> None:
        def list_models(_query: DiscoveryQuery) -> tuple[RemoteDiscoveryHit, ...]:
            raise ConnectionError("hub")

        result = HuggingFaceSource(list_models=list_models).discover(DiscoveryQuery())
        assert result.live is False
        assert result.source_failure == "ConnectionError"
        assert len(result.catalog_entries) == len(packaged_candidates())

    def test_offline_default_does_not_search(self) -> None:
        result = HuggingFaceSource().discover(DiscoveryQuery())
        assert result.live is False
        assert result.universe_count == result.discovered_count


class TestSafetensors:
    def test_single_file_bytes(self) -> None:
        total, shards = serialized_tensor_bytes(
            {
                "tensors": {
                    "a": {"data_offsets": [0, 100]},
                    "b": {"data_offsets": [100, 250]},
                }
            }
        )
        assert total == 250
        assert shards == 1

    def test_sharded_sum(self) -> None:
        total, shards = serialized_tensor_bytes(
            {
                "files": {
                    "a.safetensors": {"tensors": {"w": {"data_offsets": [0, 40]}}},
                    "b.safetensors": {"tensors": {"w": {"data_offsets": [0, 60]}}},
                }
            }
        )
        assert total == 100
        assert shards == 2

    def test_mixed_dtypes_use_offsets(self) -> None:
        total, _shards = serialized_tensor_bytes(
            {
                "tensors": {
                    "a": {"dtype": "F16", "data_offsets": [0, 16]},
                    "b": {"dtype": "U8", "data_offsets": [16, 20]},
                }
            }
        )
        assert total == 20

    def test_missing_is_unknown_not_rejection(self) -> None:
        first = packaged_candidates()[0]
        evidence = SafetensorsWeightEvidenceProvider().footprint(first)
        assert evidence.evidence_source is WeightEvidenceSource.UNAVAILABLE
        assert not is_resolved(evidence.serialized_weight_tensor_bytes)

    def test_malformed_is_typed_failure(self) -> None:
        def fetch(_entry: ModelCatalogEntry) -> dict[str, object]:
            return {"files": {"x": {"tensors": {"w": {"shape": [1]}}}}}

        evidence = SafetensorsWeightEvidenceProvider(fetch=fetch).footprint(
            packaged_candidates()[0]
        )
        assert not is_resolved(evidence.serialized_weight_tensor_bytes)
        assert evidence.provider_failure == "malformed_safetensors_metadata"

    def test_provenance_retained(self) -> None:
        entry = packaged_candidates()[0]

        def fetch(_entry: ModelCatalogEntry) -> dict[str, object]:
            return _meta_offsets(1024)

        evidence = SafetensorsWeightEvidenceProvider(fetch=fetch).footprint(entry)
        assert evidence.serialized_weight_tensor_bytes == 1024
        assert "full_weights_not_downloaded" in evidence.provenance
        assert evidence.evidence_source is WeightEvidenceSource.HUGGINGFACE_SAFETENSORS


class TestCheapRejection:
    def test_lower_bound_above_placement_is_impossible(self) -> None:
        entry = packaged_candidates()[0]
        evidence = SafetensorsWeightEvidenceProvider(
            fetch=lambda _entry: _meta_offsets(41 * GIB)
        ).footprint(entry)
        decision = cheap_weight_fit(
            evidence, _capacity(vram=24 * GIB), gpu_resident=True
        )
        assert decision.classification is CheapSizeClass.PROVEN_IMPOSSIBLE
        assert decision.reason == "weights_exceed_available_placement"

    def test_lower_bound_below_passes_to_deep(self) -> None:
        entry = packaged_candidates()[0]
        evidence = SafetensorsWeightEvidenceProvider(
            fetch=lambda _entry: _meta_offsets(15 * GIB)
        ).footprint(entry)
        decision = cheap_weight_fit(
            evidence, _capacity(vram=24 * GIB), gpu_resident=True
        )
        assert decision.classification is CheapSizeClass.PASS

    def test_equality_is_conservative_impossible(self) -> None:
        evidence = SafetensorsWeightEvidenceProvider(
            fetch=lambda _entry: _meta_offsets(24 * GIB)
        ).footprint(packaged_candidates()[0])
        decision = cheap_weight_fit(
            evidence, _capacity(vram=24 * GIB), gpu_resident=True
        )
        assert decision.classification is CheapSizeClass.PROVEN_IMPOSSIBLE

    def test_unknown_passes(self) -> None:
        first = packaged_candidates()[0]
        evidence = SafetensorsWeightEvidenceProvider().footprint(first)
        decision = cheap_weight_fit(evidence, _capacity(), gpu_resident=True)
        assert decision.classification is CheapSizeClass.UNKNOWN

    def test_offload_enabled_does_not_gpu_reject(self) -> None:
        evidence = SafetensorsWeightEvidenceProvider(
            fetch=lambda _entry: _meta_offsets(41 * GIB)
        ).footprint(packaged_candidates()[0])
        decision = cheap_weight_fit(
            evidence, _capacity(vram=24 * GIB), gpu_resident=False
        )
        assert decision.classification is not CheapSizeClass.PROVEN_IMPOSSIBLE


class TestAccelerateOptional:
    def test_absent_provider_continues(self) -> None:
        provider = AccelerateStructuralProvider()
        evidence = provider.footprint(packaged_candidates()[0])
        assert not is_resolved(evidence.serialized_weight_tensor_bytes)

    def test_does_not_enable_trust_remote_code(self) -> None:
        def analyze(_entry: ModelCatalogEntry) -> dict[str, object]:
            return {"trust_remote_code": True, "weight_bytes": 99}

        evidence = AccelerateStructuralProvider(analyze=analyze).footprint(
            packaged_candidates()[0]
        )
        assert evidence.provider_failure == "trust_remote_code_not_applicable"

    def test_result_is_not_availability(self) -> None:
        def analyze(_entry: ModelCatalogEntry) -> dict[str, object]:
            return {"weight_bytes": 1024, "trust_remote_code": False}

        evidence = AccelerateStructuralProvider(analyze=analyze).footprint(
            packaged_candidates()[0]
        )
        assert evidence.serialized_weight_tensor_bytes == 1024
        assert "not_vllm_serving_authority" in evidence.provenance


class TestFunnelCompatibilityAndSkip:
    def test_blocked_models_skip_estimator(self, tmp_path: Path) -> None:
        catalog = packaged_candidates()[:4]
        blocked = {catalog[0].metadata.model_id.value}
        eligible = {item.metadata.model_id.value for item in catalog[1:]}
        host = host_facts()
        estimator = _MapEstimator(
            {item.metadata.model_id.value: 8 * GIB for item in catalog}
        )
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=4))
        envelope, gpu_host = _envelope(host)
        capacity = replace(
            _capacity(vram=30 * GIB),
            host_id=gpu_host.host_id,
            host_fingerprint=envelope.host_fingerprint,
            snapshot_basis="snap-a",
            available_vram_bytes=30 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = _service(tmp_path, models, estimator).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible=eligible, blocked=blocked),
            envelope,
            capacity,
        )
        assert catalog[0].metadata.model_id.value not in estimator.calls
        assert result.available.estimator_invocations == len(eligible)
        assert result.available.compatibility_count == len(eligible)
        reasons = {
            item.logical_name: item.reason for item in result.available.exclusions
        }
        assert reasons[catalog[0].metadata.logical_name.value] == (
            EligibilityReasonCode.UNSUPPORTED_ARCHITECTURE.value
        )

    def test_quantization_blocked_skips_estimator(self, tmp_path: Path) -> None:
        catalog = packaged_candidates()[:3]
        blocked = {catalog[0].metadata.model_id.value}
        eligible = {item.metadata.model_id.value for item in catalog[1:]}
        host = host_facts()
        estimator = _MapEstimator(
            {item.metadata.model_id.value: 8 * GIB for item in catalog}
        )
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=3))
        envelope, gpu_host = _envelope(host)
        capacity = replace(
            _capacity(vram=30 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="snap-q",
            available_vram_bytes=30 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = _service(tmp_path, models, estimator).evaluate(
            gpu_host,
            _view_for(
                gpu_host,
                catalog,
                eligible=eligible,
                blocked=blocked,
                blocked_code=EligibilityReasonCode.UNSUPPORTED_QUANTIZATION,
            ),
            envelope,
            capacity,
        )
        assert catalog[0].metadata.model_id.value not in estimator.calls
        reasons = {
            item.logical_name: item.reason for item in result.available.exclusions
        }
        assert reasons[catalog[0].metadata.logical_name.value] == (
            EligibilityReasonCode.UNSUPPORTED_QUANTIZATION.value
        )

    def test_context_policy_and_metadata(self, tmp_path: Path) -> None:
        tiny = packaged_candidates()[0]
        seven = next(
            item
            for item in packaged_candidates()
            if item.metadata.logical_name.value == "qwen2.5-7b-instruct-awq"
        )
        catalog = (tiny, seven)
        host = host_facts()
        envelope, gpu_host = _envelope(host)
        estimator = _MapEstimator(
            {item.metadata.model_id.value: 8 * GIB for item in catalog}
        )
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=2))
        capacity = replace(
            _capacity(vram=30 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="snap-b",
            available_vram_bytes=30 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = _service(tmp_path, models, estimator).evaluate(
            gpu_host,
            _view_for(
                gpu_host,
                catalog,
                eligible={item.metadata.model_id.value for item in catalog},
            ),
            envelope,
            capacity,
            query=FunnelQuery(requested_context_tokens=8192),
        )
        assert tiny.metadata.model_id.value not in estimator.calls
        excluded = {
            item.logical_name: item.reason for item in result.available.exclusions
        }
        assert excluded[tiny.metadata.logical_name.value] == "context_unsupported"

    def test_commercial_policy_blocks_without_estimator(self, tmp_path: Path) -> None:
        tiny = packaged_candidates()[0]
        restricted = replace(
            tiny,
            metadata=replace(tiny.metadata, commercial_use_restricted=True),
        )
        catalog = (restricted,)
        host = host_facts()
        envelope, gpu_host = _envelope(host)
        estimator = _MapEstimator({restricted.metadata.model_id.value: 8 * GIB})
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=1))
        result = _service(tmp_path, models, estimator).evaluate(
            gpu_host,
            _view_for(
                gpu_host,
                catalog,
                eligible={restricted.metadata.model_id.value},
            ),
            envelope,
            replace(
                _capacity(vram=30 * GIB),
                host_id=gpu_host.host_id,
                snapshot_basis="policy",
                available_vram_bytes=30 * GIB,
                available_ram_bytes=64 * GIB,
                available_storage_bytes=500 * GIB,
            ),
            query=FunnelQuery(allow_commercially_restricted=False),
        )
        assert restricted.metadata.model_id.value not in estimator.calls
        assert result.available.exclusions[0].reason == "policy_blocked"


class TestAvailableModels:
    def test_t1_full_funnel_fixture(self, tmp_path: Path) -> None:
        all_entries = (*packaged_candidates(), acceptance_candidate())
        assert len(all_entries) == 20
        discovered = all_entries[:12]
        eligible_ids = {item.metadata.model_id.value for item in discovered[:7]}
        blocked_ids = {item.metadata.model_id.value for item in discovered[7:12]}
        cheap_ids = {
            discovered[0].metadata.source_ref,
            discovered[1].metadata.source_ref,
        }
        deep = discovered[2:7]
        available_ids = {item.metadata.model_id.value for item in deep[:3]}
        unresolved_ids = {item.metadata.model_id.value for item in deep[3:]}
        vram = {
            **dict.fromkeys(available_ids, 8 * GIB),
            **dict.fromkeys(unresolved_ids, 40 * GIB),
        }
        estimator = _MapEstimator(vram)
        mapping = {
            ref: _meta_offsets(40 * GIB) if ref in cheap_ids else _meta_offsets(GIB)
            for ref in cheap_ids
        }
        for item in deep:
            mapping[item.metadata.source_ref] = _meta_offsets(GIB)
        weights = _CountingProvider(
            SafetensorsWeightEvidenceProvider(fetch=_fetch_map(mapping))
        )
        structural = _CountingProvider(AccelerateStructuralProvider())
        models = ModelCatalogue(
            _ScriptedSource(all_entries, discovered, universe=20),
        )
        host = host_facts()
        envelope, gpu_host = _envelope(host, vram=30 * GIB)
        capacity = replace(
            _capacity(vram=30 * GIB),
            host_id=gpu_host.host_id,
            host_fingerprint=envelope.host_fingerprint,
            snapshot_basis="snap-t1",
            available_vram_bytes=30 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = _service(
            tmp_path,
            models,
            estimator,
            weights=weights,
            structural=structural,
        ).evaluate(
            gpu_host,
            _view_for(
                gpu_host,
                all_entries,
                eligible=eligible_ids,
                blocked=blocked_ids,
            ),
            envelope,
            capacity,
            persist=True,
        )
        view = result.available
        print(format_funnel(view))
        print(format_available_models(view))
        assert view.universe_count == 20
        assert view.discovered_count == 12
        assert view.compatibility_count == 7
        assert view.cheap_reject_count == 2
        assert view.deep_analyzed_count == 5
        assert view.available_count == 3
        assert view.estimator_invocations == 5
        assert len(weights.calls) == 7
        assert structural.calls == []
        names = {item.logical_name for item in view.members}
        assert names == {item.metadata.logical_name.value for item in deep[:3]}
        skipped = {
            item.metadata.model_id.value for item in all_entries[12:]
        } | blocked_ids
        skipped |= {
            discovered[0].metadata.model_id.value,
            discovered[1].metadata.model_id.value,
        }
        assert not skipped.intersection(estimator.calls)
        stored = _service(
            tmp_path,
            models,
            estimator,
            weights=SafetensorsWeightEvidenceProvider(fetch=_fetch_map(mapping)),
        ).stored(gpu_host)
        assert stored is not None
        assert stored.view_basis == view.view_basis
        assert stored.status is AvailableViewStatus.CURRENT
        assert not hasattr(stored, "recommended_model_id")
        assert not hasattr(stored, "selected_model_id")

    def test_t1_llmfit_provider_after_cheap_bound(self, tmp_path: Path) -> None:
        qwen = next(
            item
            for item in packaged_candidates()
            if item.metadata.logical_name.value == "qwen2.5-7b-instruct-awq"
        )
        catalog = (qwen,)
        ident = qwen.metadata.model_id.value
        estimator = LlmfitRequirementEstimator(
            plan=fixture_plan(
                Path(__file__).resolve().parent / "fixtures" / "estimators" / "llmfit"
            )
        )
        weights = _CountingProvider(
            SafetensorsWeightEvidenceProvider(
                fetch=_fetch_map({qwen.metadata.source_ref: _meta_offsets(GIB)})
            )
        )
        structural = _CountingProvider(AccelerateStructuralProvider(enabled=True))
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=1))
        host = host_facts()
        envelope, gpu_host = _envelope(host, vram=30 * GIB)
        capacity = replace(
            _capacity(vram=30 * GIB),
            host_id=gpu_host.host_id,
            host_fingerprint=envelope.host_fingerprint,
            snapshot_basis="snap-llmfit",
            available_vram_bytes=30 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = _service(
            tmp_path,
            models,
            estimator,
            weights=weights,
            structural=structural,
        ).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible={ident}),
            envelope,
            capacity,
        )
        assert weights.calls == [qwen.metadata.source_ref]
        assert structural.calls == []
        assert result.available.estimator_invocations == 1
        assert result.available.available_count == 1
        member = result.available.members[0]
        assert member.requirement_provider == "llmfit"
        assert member.result == "available"
        serving = estimator.estimate(
            ModelEstimationRequest(
                model_id=qwen.metadata.model_id,
                source_ref=qwen.metadata.source_ref,
                source_revision=qwen.metadata.source_revision,
                artifact_format=NOT_PROVIDED,
                quantization=qwen.metadata.quantization,
                context_tokens=8192,
                runtime="vllm",
                placement=MemoryPlacement.DISCRETE_GPU,
            )
        )
        assert (
            "vLLM serving refinement after llmfit plan components"
            in serving.assumptions
        )

    def test_same_snapshot_for_every_member(self, tmp_path: Path) -> None:
        catalog = packaged_candidates()[:3]
        ids = {item.metadata.model_id.value for item in catalog}
        estimator = _MapEstimator(dict.fromkeys(ids, 8 * GIB))
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=3))
        host = host_facts()
        envelope, gpu_host = _envelope(host)
        capacity = replace(
            _capacity(vram=30 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="same-snap",
            available_vram_bytes=30 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = _service(tmp_path, models, estimator).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible=ids),
            envelope,
            capacity,
        )
        snapshots = {
            item.snapshot_basis for item in result.assessments if item.snapshot_basis
        }
        assert snapshots == {"same-snap"}
        assert result.available.snapshot_basis == "same-snap"
        later = replace(
            capacity,
            snapshot_basis="other-snap",
            available_vram_bytes=8 * GIB,
        )
        changed = _service(tmp_path, models, estimator).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible=ids),
            envelope,
            later,
        )
        assert changed.available.view_basis != result.available.view_basis

    def test_hypothetical_candidates_do_not_consume(self, tmp_path: Path) -> None:
        catalog = packaged_candidates()[:2]
        ids = [item.metadata.model_id.value for item in catalog]
        estimator = _MapEstimator({ids[0]: 12 * GIB, ids[1]: 15 * GIB})
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=2))
        host = host_facts()
        envelope, gpu_host = _envelope(host)
        capacity = replace(
            _capacity(vram=20 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="indep",
            available_vram_bytes=20 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = _service(tmp_path, models, estimator).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible=set(ids)),
            envelope,
            capacity,
        )
        assert result.available.available_count == 2

    def test_empty_available_is_valid(self, tmp_path: Path) -> None:
        catalog = packaged_candidates()[:1]
        ident = catalog[0].metadata.model_id.value
        estimator = _MapEstimator({ident: 80 * GIB})
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=1))
        host = host_facts()
        envelope, gpu_host = _envelope(host)
        capacity = replace(
            _capacity(vram=10 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="empty",
            available_vram_bytes=10 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        result = _service(tmp_path, models, estimator).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible={ident}),
            envelope,
            capacity,
        )
        assert result.available.available_count == 0
        assert result.available.status is AvailableViewStatus.CURRENT

    def test_selector_cannot_add_members(self, tmp_path: Path) -> None:
        catalog = packaged_candidates()[:2]
        ids = [item.metadata.model_id.value for item in catalog]
        estimator = _MapEstimator({ids[0]: 8 * GIB, ids[1]: 80 * GIB})
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=2))
        host = host_facts()
        envelope, gpu_host = _envelope(host)
        capacity = replace(
            _capacity(vram=20 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="sel",
            available_vram_bytes=20 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        funnel = _service(tmp_path, models, estimator).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible=set(ids)),
            envelope,
            capacity,
        )

        selector = ModelSelectionService(
            FileStore(tmp_path / "sel"),
            FixedClock(now_utc()),
            SelectionService(estimator, FixedClock(now_utc())),
            models,
            ModelSelectionLock(tmp_path / "sellock"),
        )
        overview = selector.view(
            gpu_host,
            funnel.eligible,
            envelope,
            funnel.assessments,
            funnel.available,
        )
        assert {item.model_id for item in overview.feasible} == {
            item.model_id for item in funnel.available.members
        }
        assert catalog[1].metadata.model_id.value not in {
            item.model_id for item in overview.feasible
        }

    def test_vllm_static_feasible_is_not_available_without_calibration(
        self, tmp_path: Path
    ) -> None:
        catalog = packaged_candidates()[:1]
        ident = catalog[0].metadata.model_id.value
        estimator = _MapEstimator({ident: 8 * GIB})
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=1))
        host = host_facts()
        envelope, gpu_host = _envelope(host)
        capacity = replace(
            _capacity(vram=30 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="bypass",
            available_vram_bytes=30 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        )
        funnel = AvailableModelsService(
            FileStore(tmp_path / "records"),
            FixedClock(now_utc()),
            models,
            estimator,
            SelectionPolicy(),
            AvailableModelsLock(tmp_path / "locks"),
        ).evaluate(
            gpu_host,
            _view_for(gpu_host, catalog, eligible={ident}),
            envelope,
            capacity,
        )
        assert funnel.estimated_feasible
        assert funnel.available.available_count == 0
        assert all(
            item.stage.value == "runtime_calibration"
            for item in funnel.available.exclusions
            if item.model_id == ident
        )
        selector = ModelSelectionService(
            FileStore(tmp_path / "sel"),
            FixedClock(now_utc()),
            SelectionService(estimator, FixedClock(now_utc())),
            models,
            ModelSelectionLock(tmp_path / "sellock"),
        )
        overview = selector.view(
            gpu_host,
            funnel.eligible,
            envelope,
            funnel.assessments,
            funnel.available,
        )
        assert overview.feasible == ()


class TestProductSurfaces:
    def test_api_get_does_not_persist(self, tmp_path: Path) -> None:
        platform = _product(tmp_path)
        _realize(platform)
        listed = _call(platform, "/models/available")
        assert listed.status == 200
        payload = listed.body["payload"]
        assert payload["mutations"] is False
        assert payload["recommendation"] is False
        assert payload["selection"] is False
        assert "counts" in payload
        assert platform.available_models.stored(platform.hosts.current) is None
        refreshed = _call(platform, "/models/available/refresh", Method.POST)
        assert refreshed.status == 200
        assert refreshed.body["payload"]["mutations"] is True
        assert platform.available_models.stored(platform.hosts.current) is not None

    def test_cli_prints_available_before_recommendation(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        platform = _product(tmp_path)
        _realize(platform)
        monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
        monkeypatch.setenv("KULTRUN_FIXTURE", fixtures.DEFAULT_SHAPE)
        monkeypatch.setenv("KULTRUN_RUNTIME_PROVISIONER", "fixture")
        monkeypatch.setenv("KULTRUN_RUNTIME_VERIFIER", "fixture")
        monkeypatch.setenv("KULTRUN_MODEL_ACQUISITION_PROVIDER", "fixture")
        monkeypatch.setenv("KULTRUN_MODEL_REQUIREMENT_ESTIMATOR", "kultrun")
        assert main(["models", "available"]) == 0
        available = capsys.readouterr().out
        assert "MODEL FEASIBILITY FUNNEL" in available
        assert "AVAILABLE MODELS" in available
        assert "RECOMMENDED MODEL" not in available
        assert main(["models", "recommend"]) == 0
        printed = capsys.readouterr().out
        assert printed.index("AVAILABLE MODELS") < printed.index("RECOMMENDED MODEL")
        assert "SELECTED MODEL" in printed
        assert "MODE:" in printed

    def test_console_orders_available_before_selection(self) -> None:
        html = (
            SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
        ).read_text(encoding="utf-8")
        script = (
            SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
        ).read_text(encoding="utf-8")
        assert html.index("Available Models") < html.index("Model selection")
        assert script.index("renderAvailableModels") < script.index("renderSelection")
        assert "/models/available" in script

    def test_dynamic_shrink_and_expand(self, tmp_path: Path) -> None:
        catalog = packaged_candidates()[:3]
        ids = [item.metadata.model_id.value for item in catalog]
        estimator = _MapEstimator({ids[0]: 8 * GIB, ids[1]: 16 * GIB, ids[2]: 24 * GIB})
        models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=3))
        host = host_facts()
        envelope, gpu_host = _envelope(host)
        service = _service(tmp_path, models, estimator)

        def run(available: int) -> set[str]:
            capacity = replace(
                _capacity(vram=30 * GIB),
                host_id=gpu_host.host_id,
                snapshot_basis=f"vram-{available}",
                available_vram_bytes=available,
                available_ram_bytes=64 * GIB,
                available_storage_bytes=500 * GIB,
            )
            result = service.evaluate(
                gpu_host,
                _view_for(gpu_host, catalog, eligible=set(ids)),
                envelope,
                capacity,
            )
            return {item.logical_name for item in result.available.members}

        names = [item.metadata.logical_name.value for item in catalog]
        assert run(30 * GIB) == set(names)
        shrunk = run(18 * GIB)
        assert names[0] in shrunk
        assert names[1] in shrunk
        assert names[2] not in shrunk
        assert run(30 * GIB) == set(names)

    def test_zero_available_blocks_manual(self, tmp_path: Path) -> None:
        platform = _product(tmp_path)
        _realize(platform)
        # Force an empty available set by selecting a blocked model.
        refused = _call(
            platform,
            "/models/selection",
            Method.POST,
            mode="manual",
            model="tinyllama-1.1b-chat-q4",
        )
        assert refused.status == 412


def test_cheap_pass_is_not_available(tmp_path: Path) -> None:
    catalog = packaged_candidates()[:1]
    ident = catalog[0].metadata.model_id.value
    estimator = _MapEstimator({ident: 80 * GIB})
    models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=1))
    host = host_facts()
    envelope, gpu_host = _envelope(host)
    mapping = {catalog[0].metadata.source_ref: _meta_offsets(GIB)}
    result = _service(
        tmp_path,
        models,
        estimator,
        weights=SafetensorsWeightEvidenceProvider(fetch=_fetch_map(mapping)),
    ).evaluate(
        gpu_host,
        _view_for(gpu_host, catalog, eligible={ident}),
        envelope,
        replace(
            _capacity(vram=10 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="pass",
            available_vram_bytes=10 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        ),
    )
    assert result.available.cheap_reject_count == 0
    assert result.available.deep_analyzed_count == 1
    assert result.available.available_count == 0


def test_accelerate_structural_can_prove_impossible_but_not_available(
    tmp_path: Path,
) -> None:
    catalog = packaged_candidates()[:1]
    ident = catalog[0].metadata.model_id.value
    estimator = _MapEstimator({ident: 8 * GIB})
    models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=1))
    host = host_facts()
    envelope, gpu_host = _envelope(host)

    def analyze(_entry: ModelCatalogEntry) -> dict[str, object]:
        return {"weight_bytes": 41 * GIB, "trust_remote_code": False}

    result = _service(
        tmp_path,
        models,
        estimator,
        weights=SafetensorsWeightEvidenceProvider(),
        structural=AccelerateStructuralProvider(analyze=analyze),
    ).evaluate(
        gpu_host,
        _view_for(gpu_host, catalog, eligible={ident}),
        envelope,
        replace(
            _capacity(vram=24 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="accel",
            available_vram_bytes=24 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        ),
    )
    assert ident not in estimator.calls
    assert result.available.cheap_reject_count == 1
    assert result.available.available_count == 0
    assert result.available.exclusions[0].reason == "weights_exceed_available_placement"


def test_stale_available_view_blocks_manual(tmp_path: Path) -> None:
    catalog = packaged_candidates()[:1]
    ident = catalog[0].metadata.model_id.value
    estimator = _MapEstimator({ident: 8 * GIB})
    models = ModelCatalogue(_ScriptedSource(catalog, catalog, universe=1))
    host = host_facts()
    envelope, gpu_host = _envelope(host)
    funnel = _service(tmp_path, models, estimator).evaluate(
        gpu_host,
        _view_for(gpu_host, catalog, eligible={ident}),
        envelope,
        replace(
            _capacity(vram=30 * GIB),
            host_id=gpu_host.host_id,
            snapshot_basis="stale",
            available_vram_bytes=30 * GIB,
            available_ram_bytes=64 * GIB,
            available_storage_bytes=500 * GIB,
        ),
    )
    stale = replace(funnel.available, status=AvailableViewStatus.STALE)

    selector = ModelSelectionService(
        FileStore(tmp_path / "sel"),
        FixedClock(now_utc()),
        SelectionService(estimator, FixedClock(now_utc())),
        models,
        ModelSelectionLock(tmp_path / "sellock"),
    )
    with pytest.raises(PreconditionFailedError):
        selector.select_manual(
            catalog[0].metadata.logical_name.value,
            gpu_host,
            funnel.eligible,
            envelope,
            funnel.assessments,
            stale,
        )


def test_model_switch_drops_self_reservation_exclusion() -> None:
    plan = DeploymentPlan(
        model_id=ModelId("model_aaaaaaaaaaaaaaaa"),
        logical_name=Name("model-a"),
        source_ref="org/a",
        quantization="awq",
        runtime="vllm",
        executor_kind="native-process",
        placement=MemoryPlacement.DISCRETE_GPU,
        expected_ram_bytes=GIB,
        expected_vram_bytes=8 * GIB,
        expected_unified_bytes=NOT_PROVIDED,
        expected_storage_bytes=GIB,
        expected_utilization=0.4,
        estimator_provider="kultrun",
        policy_version="test",
        rationale=("fixture",),
        plan_basis="plan-a",
    )
    selection = ModelSelection(
        selection_id=ModelSelectionId.generate(),
        host_id=HostId.generate(),
        selection_mode=ModelSelectionMode.AUTO,
        created_at=now_utc(),
        selected_at=now_utc(),
        selection_basis="sel",
        selected_model_id=plan.model_id.value,
        selected_logical_name=plan.logical_name.value,
    )
    assert revalidation_plan_basis(plan, selection) == "plan-a"
    assert revalidation_plan_basis(plan, selection, pending_model="model-b") is None
    switched = replace(
        selection,
        selected_model_id="model_bbbbbbbbbbbbbbbb",
        selected_logical_name="model-b",
    )
    assert revalidation_plan_basis(plan, switched) is None

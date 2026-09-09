"""Stage 1.6L — feasible set vs current available capacity."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kultrun.adapters.model_source.candidates import packaged_candidates
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.unresolved import is_resolved
from kultrun.model.acquisition import request_from_entry
from kultrun.model.contracts import (
    ArtifactId,
    ArtifactState,
    ModelArtifact,
    VerificationState,
)
from kultrun.planning.contracts import CompatibilityVerdict, SelectionPolicy
from kultrun.planning.evaluate import evaluate
from kultrun.platform.capacity_snapshot import bind_current_capacity
from kultrun.platform.eligibility import catalog_facts
from kultrun.platform.requirement import (
    assess_catalog,
    feasible_candidates,
    incremental_storage_demand,
)
from kultrun.runtime.contracts import RuntimePolicy
from tests.test_planning_selection import _capacity, _metadata, _requirement
from tests.test_resource_admission import GIB, _request
from tests.test_runtime_requirement_capacity import LARGE, SMALL, _product, _realize

SEVEN = "qwen2.5-7b-instruct-awq"
FOURTEEN = "qwen2.5-14b-instruct-awq"


def _rows(platform, host, view, envelope):
    snapshot = platform.resources.snapshot(envelope, host=host)
    return assess_catalog(
        view,
        platform.models,
        envelope,
        platform.selection.estimator,
        platform.selection.policy,
        capacity=bind_current_capacity(envelope, snapshot),
        inventory=platform.inventory,
    )


def _view_envelope(platform):
    host = platform.hosts.current
    view = platform.eligibility.evaluate(
        host,
        (
            platform.executions.capabilities(host),
            platform.plane.container_capability(host),
        ),
        platform.runtimes.descriptors(),
        catalog_facts(platform.models),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    envelope = platform.capacity.compute(host, {})
    return host, view, envelope


class TestAnalyticalFeasibleSet:
    def test_catalog_rows_expose_required_vs_available(self, tmp_path: Path) -> None:
        platform = _product(tmp_path)
        _realize(platform)
        host, view, envelope = _view_envelope(platform)
        rows = _rows(platform, host, view, envelope)
        by_name = {item.logical_name: item for item in rows}
        small = by_name[SMALL]
        large = by_name[LARGE]
        blocked = by_name["tinyllama-1.1b-chat-q4"]
        assert small.eligibility_status == "eligible"
        assert small.capacity_verdict == "feasible"
        assert is_resolved(small.required_vram_bytes)
        assert is_resolved(small.available_vram_bytes)
        assert small.required_vram_bytes <= small.available_vram_bytes
        assert large.eligibility_status == "eligible"
        assert large.capacity_verdict == "infeasible_vram"
        assert blocked.capacity_verdict == "not_assessed"
        feasible = {item.logical_name for item in feasible_candidates(rows)}
        assert SMALL in feasible
        assert LARGE not in feasible
        assert "tinyllama-1.1b-chat-q4" not in feasible

    def test_infeasible_vram_ram_and_storage_reason_codes(self) -> None:
        meta = _metadata()
        req = _requirement(
            meta.model_id,
            estimated_vram_bytes=20 * GIB,
            ram_bytes=30 * GIB,
            peak_additional_bytes=40 * GIB,
        )
        capacity = replace(
            _capacity(vram=30 * GIB, ram=48 * GIB, storage=100 * GIB),
            available_vram_bytes=18 * GIB,
            available_ram_bytes=16 * GIB,
            available_storage_bytes=8 * GIB,
        )
        result = evaluate(
            meta,
            req,
            capacity,
            SelectionPolicy(),
            runtime_compatibility=CompatibilityVerdict.COMPATIBLE,
            incremental_storage_bytes=40 * GIB,
        )
        assert "infeasible_vram" in result.reasons
        assert "infeasible_ram" in result.reasons
        assert "infeasible_storage" in result.reasons

    def test_blocked_runtime_skips_capacity(self, tmp_path: Path) -> None:
        platform = _product(tmp_path)
        _realize(platform)
        host, view, envelope = _view_envelope(platform)
        rows = _rows(platform, host, view, envelope)
        blocked = next(
            item for item in rows if item.logical_name == "tinyllama-1.1b-chat-q4"
        )
        assert blocked.requirement_status.value == "refused"
        assert blocked.capacity_assessed is False
        assert blocked.capacity_verdict == "not_assessed"


class TestDynamicShrinkExpand:
    def test_unrelated_reservation_shrinks_and_release_restores(
        self, tmp_path: Path
    ) -> None:
        platform = _product(tmp_path)
        _realize(platform)
        host, view, envelope = _view_envelope(platform)
        before = _rows(platform, host, view, envelope)
        feasible_before = {item.logical_name for item in feasible_candidates(before)}
        assert SEVEN in feasible_before
        assert FOURTEEN in feasible_before
        entry = platform.models.acquirable(SMALL)
        assert entry is not None
        receipt = platform.acquisition.acquire(
            request_from_entry(entry), envelope, host.host_id
        )
        artifact = platform.inventory.get(receipt.artifact_id)
        assert artifact is not None
        admitted = platform.resources.admit(
            _request(artifact, envelope, ram=GIB, vram=12 * GIB),
            envelope,
            artifact,
        )
        assert admitted.reservation is not None
        mid = _rows(platform, host, view, envelope)
        snapshot = platform.resources.snapshot(envelope, host=host)
        assert (
            snapshot.accelerators[0].available_bytes
            < snapshot.accelerators[0].safe_bytes
        )
        feasible_mid = {item.logical_name for item in feasible_candidates(mid)}
        assert SEVEN in feasible_mid
        assert FOURTEEN not in feasible_mid
        fourteen = next(item for item in mid if item.logical_name == FOURTEEN)
        assert fourteen.capacity_verdict == "infeasible_vram"
        platform.resources.release(admitted.reservation.reservation_id)
        after = _rows(platform, host, view, envelope)
        feasible_after = {item.logical_name for item in feasible_candidates(after)}
        assert FOURTEEN in feasible_after
        assert feasible_after == feasible_before


class TestIncrementalStorage:
    def test_stored_artifact_does_not_repeat_acquisition_footprint(self) -> None:
        entry = next(
            item
            for item in packaged_candidates()
            if item.metadata.logical_name.value == SMALL
        )
        requirement = entry.requirement
        assert is_resolved(requirement.peak_additional_bytes)
        absent = incremental_storage_demand(entry, requirement, None)
        assert absent == requirement.peak_additional_bytes
        pinned = replace(
            entry,
            metadata=replace(entry.metadata, source_revision="rev-a"),
        )
        artifact = ModelArtifact(
            artifact_id=ArtifactId.generate(),
            model_id=entry.metadata.model_id,
            revision="rev-a",
            state=ArtifactState.STORED,
            quantization=entry.metadata.quantization,
            verification_state=VerificationState.PASSED,
        )

        class _Inventory:
            def find_stored(self, **kwargs: object) -> ModelArtifact:
                return artifact

        present = incremental_storage_demand(pinned, requirement, _Inventory())
        assert present == 0

    def test_stored_artifact_does_not_consume_vram(self, tmp_path: Path) -> None:
        platform = _product(tmp_path)
        _realize(platform)
        host, _view, envelope = _view_envelope(platform)
        empty = platform.resources.snapshot(envelope, host=host)
        entry = platform.models.acquirable(SMALL)
        assert entry is not None
        receipt = platform.acquisition.acquire(
            request_from_entry(entry), envelope, host.host_id
        )
        artifact = platform.inventory.get(receipt.artifact_id)
        assert artifact is not None
        assert artifact.state is ArtifactState.STORED
        stored = platform.resources.snapshot(envelope, host=host)
        assert stored.accelerators[0].reserved_bytes == 0
        assert (
            stored.accelerators[0].available_bytes
            == empty.accelerators[0].available_bytes
        )
        admitted = platform.resources.admit(
            _request(artifact, envelope, ram=2 * GIB, vram=4 * GIB),
            envelope,
            artifact,
        )
        assert admitted.reservation is not None
        running = platform.resources.snapshot(envelope, host=host)
        assert running.accelerators[0].reserved_bytes == 4 * GIB
        assert running.reserved_ram_bytes == 2 * GIB


class TestAutoManualFeasibleSet:
    def test_manual_cannot_select_infeasible(self, tmp_path: Path) -> None:
        platform = _product(tmp_path)
        _realize(platform)
        host, view, envelope = _view_envelope(platform)
        rows = _rows(platform, host, view, envelope)
        feasible = feasible_candidates(rows)
        assert len(feasible) >= 2
        auto = platform.model_selection.select_auto(host, view, envelope, rows)
        assert auto.selection.selected_logical_name in {
            item.logical_name for item in feasible
        }
        other = next(
            item.logical_name
            for item in auto.feasible
            if item.logical_name != auto.selection.recommended_logical_name
        )
        manual = platform.model_selection.select_manual(
            other, host, view, envelope, rows
        )
        assert manual.selection.selected_logical_name == other
        with pytest.raises(PreconditionFailedError) as raised:
            platform.model_selection.select_manual(LARGE, host, view, envelope, rows)
        assert raised.value.context["reason"] == "model_infeasible"


def test_no_second_feasibility_architecture() -> None:
    source = Path(__file__).resolve().parent.parent / "src" / "kultrun"
    text = "\n".join(path.read_text(encoding="utf-8") for path in source.rglob("*.py"))
    assert "GenericConstraintEngine" not in text
    assert "GenericCapabilityDSL" not in text
    assert "ModelFeasibilityV2" not in text
    assert "CapacityV2" not in text
    assert "class CurrentCapacitySnapshot" not in text

"""Model identity, compatibility, and warehouse behavior. No weight load."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from machi.adapters.model.acquire import (
    store_local,
    store_view,
    view_local,
    with_stored,
)
from machi.adapters.model.local import list_local_files
from machi.adapters.model.warehouse import list_stored, load_artifact, warehouse_root
from machi.capacity.contracts import (
    CapacityEnvelope,
    EvidenceStrength,
    MemoryCapacity,
    StorageDomainCapacity,
)
from machi.capacity.policy import default_capacity_settings
from machi.capacity.sonar import not_attempted
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import NOT_PROVIDED, is_resolved
from machi.model.compat import RuntimeView
from machi.model.contracts import (
    ArtifactLifecycle,
    AvailableModelEntry,
    CommercialUse,
    CompatibilityState,
    ModelFailure,
    ModelSourceKind,
    ProviderQualification,
    QuantizationKind,
)
from machi.model.evaluate import evaluate_source, select_entry, snapshot_for
from machi.model.events import model_events
from machi.model.files import plan_acquisition
from machi.model.identity import artifact_id, model_id
from machi.model.metadata import normalize_config
from machi.model.policy import default_model_settings
from machi.model.source import SourceFileInfo, SourceView

FIXED = dt.datetime(2026, 9, 22, 12, 0, tzinfo=dt.UTC)
ARCH = "LlamaForCausalLM"


def _runtime(
    architectures: frozenset[str] = frozenset({ARCH}),
    quantizations: frozenset[str] = frozenset({"awq", "gptq", "fp8"}),
    qualification: ProviderQualification = ProviderQualification.QUALIFIED,
    *,
    known: bool = True,
    foundation_id: str = "fgen_test",
) -> RuntimeView:
    return RuntimeView(
        architectures=architectures,
        quantizations=quantizations,
        foundation_id=foundation_id,
        provider_qualification=qualification,
        capability_known=known,
    )


def _envelope(safe_bytes: int, evidence_id: str = "cev_test") -> CapacityEnvelope:
    return CapacityEnvelope(
        evidence_id=evidence_id,
        input_token="capacity-input-token",
        memory=MemoryCapacity(
            physical_bytes=NOT_PROVIDED,
            execution_limit_bytes=NOT_PROVIDED,
            hard_ceiling_bytes=NOT_PROVIDED,
            reserve_bytes=0,
            safe_bytes=NOT_PROVIDED,
            strength=EvidenceStrength.UNRESOLVED,
            reason="memory is not the storage gate",
        ),
        accelerators=(),
        storage_domains=(
            StorageDomainCapacity(
                domain_id="dom_test",
                backing_resolved=True,
                reported_available_bytes=safe_bytes,
                specialist_remaining_bytes=NOT_PROVIDED,
                hard_bound_bytes=safe_bytes,
                reserve_bytes=0,
                safe_bytes=safe_bytes,
                protected_occupancy_bytes=NOT_PROVIDED,
                reclaimable_bytes=NOT_PROVIDED,
                potential_after_reclaim_bytes=NOT_PROVIDED,
                usable=True,
                strength=EvidenceStrength.REPORTED,
                sonar=not_attempted(),
                reason="test domain",
            ),
        ),
        settings=default_capacity_settings(),
        observed_at=FIXED,
        provider="native",
    )


def _config(
    *,
    architecture: str | None = ARCH,
    dtype: str = "bfloat16",
    context: int | None = 2048,
    parameters: int | None = None,
    remote: bool = False,
    quant: str | None = None,
    base: str | None = None,
) -> str:
    body: dict[str, object] = {"model_type": "llama"}
    if architecture is not None:
        body["architectures"] = [architecture]
    if dtype:
        body["torch_dtype"] = dtype
    if context is not None:
        body["max_position_embeddings"] = context
    if parameters is not None:
        body["num_parameters"] = parameters
    if remote:
        body["auto_map"] = {"AutoModel": "modeling.Custom"}
    if quant is not None:
        body["quantization_config"] = {"quant_method": quant}
    if base is not None:
        body["_name_or_path"] = base
    return json.dumps(body)


def _view(
    repository: str = "org/tiny-7B",
    revision: str = "abc123commit",
    requested: str = "main",
    *,
    config: str | None = None,
    files: tuple[tuple[str, int], ...] | None = None,
    license_id: str | None = "apache-2.0",
    gated: bool = False,
) -> SourceView:
    payload = config if config is not None else _config()
    listed = files if files is not None else (
        ("config.json", len(payload.encode())),
        ("model.safetensors", 32),
    )
    return SourceView(
        repository=repository,
        requested_revision=requested,
        immutable_revision=revision,
        files=tuple(SourceFileInfo(path, size) for path, size in listed),
        config_text=payload,
        index_text=None,
        license_id=license_id,
        gated=gated,
        private=False,
    )


def _entry(view: SourceView | None = None, **kwargs: object) -> AvailableModelEntry:
    source = view or _view()
    runtime = kwargs.pop("runtime", _runtime())
    capacity = kwargs.pop("capacity", _envelope(10_000_000))
    accel = kwargs.pop("accelerator_safe_bytes", 10_000_000)
    license_blocks = kwargs.pop("license_blocks", False)
    return evaluate_source(
        source,
        source_kind=ModelSourceKind.HUB,
        runtime=runtime,  # type: ignore[arg-type]
        capacity=capacity,  # type: ignore[arg-type]
        accelerator_safe_bytes=accel,  # type: ignore[arg-type]
        observed_at=FIXED,
        license_blocks=bool(license_blocks),
    )


def test_logical_model_and_exact_revision_are_distinct() -> None:
    logical = model_id(ModelSourceKind.HUB, "org/tiny-7B")
    entry = _entry()
    assert entry.definition.model_id == logical
    assert entry.definition.requested_revision == "main"
    assert entry.definition.immutable_revision == "abc123commit"
    assert "main" not in artifact_id(logical, entry.definition.immutable_revision, "v")


def test_branch_name_is_not_the_stored_revision() -> None:
    entry = _entry(_view(requested="main", revision="commitsha1"))
    assert entry.definition.requested_revision == "main"
    assert entry.definition.immutable_revision == "commitsha1"


def test_same_repo_different_revision_differs() -> None:
    left = artifact_id("mdl_aaaaaaaaaaaaaaaa", "rev-one", "bf16-none-safetensors")
    right = artifact_id("mdl_aaaaaaaaaaaaaaaa", "rev-two", "bf16-none-safetensors")
    assert left != right


def test_supported_architecture_dtype_quant_and_context() -> None:
    entry = _entry(_view(config=_config(quant="awq", parameters=123)))
    assert entry.definition.architecture == ARCH
    assert entry.definition.dtype == "bfloat16"
    assert entry.definition.quantization is QuantizationKind.AWQ
    assert entry.definition.context_length == 2048
    assert entry.definition.parameter_count == 123


def test_missing_architecture_is_unsupported() -> None:
    text = '{"torch_dtype": "float16"}'
    entry = _entry(_view(config=text))
    assert entry.compatibility.state is CompatibilityState.UNSUPPORTED
    assert entry.compatibility.failure is ModelFailure.UNSUPPORTED_ARCHITECTURE


def test_name_does_not_invent_a_parameter_count() -> None:
    entry = _entry(_view(repository="org/tiny-7B"))
    assert not is_resolved(entry.definition.parameter_count)
    meta = normalize_config(_config())
    assert not is_resolved(meta.parameter_count)


def test_remote_code_is_refused_without_executing_python(tmp_path: Path) -> None:
    settings = default_model_settings()
    assert settings.remote_code_policy == "refuse"
    bomb = tmp_path / "modeling.py"
    bomb.write_text("raise SystemExit('executed')\n", encoding="utf-8")
    config = _config(remote=True)
    (tmp_path / "config.json").write_text(config, encoding="utf-8")
    (tmp_path / "model.safetensors").write_bytes(b"weights")
    view = view_local(tmp_path, "local-remote")
    entry = evaluate_source(
        view,
        source_kind=ModelSourceKind.LOCAL,
        runtime=_runtime(),
        capacity=_envelope(10_000_000),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    assert entry.compatibility.state is CompatibilityState.BLOCKED_BY_POLICY
    assert entry.compatibility.failure is ModelFailure.REMOTE_CODE_REQUIRED
    assert entry.compatibility.technical_state is CompatibilityState.UNRESOLVED
    assert "executed" not in view.config_text if view.config_text else True


def test_declared_and_missing_license_stay_distinct_from_technical_fit() -> None:
    declared = _entry(_view(license_id="apache-2.0"))
    assert declared.definition.commercial_use is CommercialUse.DECLARED_ALLOWED
    assert declared.compatibility.technical_state is CompatibilityState.COMPATIBLE
    missing = _entry(_view(license_id=None))
    assert missing.definition.commercial_use is CommercialUse.UNKNOWN
    assert missing.compatibility.technical_state is CompatibilityState.COMPATIBLE
    blocked = _entry(_view(license_id="custom-research"), license_blocks=True)
    assert blocked.definition.commercial_use is CommercialUse.REQUIRES_REVIEW
    assert blocked.compatibility.state is CompatibilityState.BLOCKED_BY_POLICY
    assert blocked.compatibility.technical_state is CompatibilityState.COMPATIBLE
    assert blocked.compatibility.failure is ModelFailure.LICENSE_POLICY_BLOCKED


def test_runtime_recognition_quantization_and_capacity() -> None:
    recognized = _entry()
    assert recognized.compatibility.state is CompatibilityState.COMPATIBLE
    unknown = _entry(runtime=_runtime(architectures=frozenset({"OtherForCausalLM"})))
    assert unknown.compatibility.failure is ModelFailure.UNSUPPORTED_ARCHITECTURE
    awq = _entry(_view(config=_config(quant="awq")))
    assert awq.compatibility.state is CompatibilityState.COMPATIBLE
    denied = _entry(
        _view(config=_config(quant="awq")),
        runtime=_runtime(quantizations=frozenset({"gptq"})),
    )
    assert denied.compatibility.failure is ModelFailure.UNSUPPORTED_QUANTIZATION
    small = _entry(capacity=_envelope(1))
    assert small.compatibility.failure is ModelFailure.INSUFFICIENT_STORAGE
    heavy = _entry(accelerator_safe_bytes=1)
    assert heavy.compatibility.failure is ModelFailure.INSUFFICIENT_BASELINE_CAPACITY
    later = _entry(accelerator_safe_bytes=None)
    assert later.compatibility.state is CompatibilityState.CONDITIONALLY_COMPATIBLE
    deferred = _entry(runtime=_runtime(qualification=ProviderQualification.DEFERRED))
    assert deferred.compatibility.state is CompatibilityState.CONDITIONALLY_COMPATIBLE
    assert deferred.compatibility.failure is ModelFailure.NONE
    assert "deferred" in deferred.compatibility.reason
    assert deferred.compatibility.technical_state is not CompatibilityState.UNSUPPORTED


def test_snapshot_changes_when_foundation_or_capacity_changes() -> None:
    entry = _entry()
    first = snapshot_for(
        (entry,),
        foundation_id="fgen_one",
        capacity_evidence_id="cev_one",
        policy_token="immutable_commit",
        observed_at=FIXED,
    )
    second = snapshot_for(
        (entry,),
        foundation_id="fgen_two",
        capacity_evidence_id="cev_one",
        policy_token="immutable_commit",
        observed_at=FIXED,
    )
    third = snapshot_for(
        (entry,),
        foundation_id="fgen_one",
        capacity_evidence_id="cev_two",
        policy_token="immutable_commit",
        observed_at=FIXED,
    )
    assert first.input_token != second.input_token
    assert first.input_token != third.input_token
    assert first.snapshot_id != second.snapshot_id
    assert len(first.entries) == 1


def test_selection_records_the_assessment_and_does_not_start_a_runtime() -> None:
    entry = _entry()
    chosen = select_entry(
        entry,
        foundation_id="fgen_test",
        capacity_evidence_id="cev_test",
    )
    assert chosen.model_id == entry.definition.model_id
    assert chosen.compatibility_state is entry.compatibility.state
    assert chosen.immutable_revision == "abc123commit"
    events = model_events(snapshot_for(
        (entry,),
        foundation_id="fgen_test",
        capacity_evidence_id="cev_test",
        policy_token="immutable_commit",
        observed_at=FIXED,
    ), chosen, clock=FixedClock(FIXED))
    rendered = " ".join(event.event_type.value for event in events)
    assert "model.inspected" in rendered
    assert "model.selected" in rendered
    assert "api_server" not in rendered
    names = {item.value for item in ArtifactLifecycle}
    assert "loaded" not in names
    assert "running" not in names


def test_plan_skips_unrelated_weight_formats() -> None:
    plan = plan_acquisition(
        (
            ("config.json", 10),
            ("model.safetensors", 20),
            ("model.gguf", 30),
            ("demo.py", 4),
        )
    )
    names = [item.relative_path for item in plan.files]
    assert "model.safetensors" in names
    assert "config.json" in names
    assert "model.gguf" not in names
    assert "demo.py" not in names


def test_hub_revision_is_acquired_once_and_reused(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def fetch(destination: Path, relative_paths: tuple[str, ...]) -> None:
        calls.append(relative_paths)
        for relative in relative_paths:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            body = b"weights" if relative.endswith(".safetensors") else b"{}"
            target.write_bytes(body)

    view = _view(revision="commit-aaa")
    first = store_view(
        tmp_path,
        view,
        source_kind=ModelSourceKind.HUB,
        fetch=fetch,
        runtime=_runtime(),
        capacity=_envelope(10_000_000),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    second = store_view(
        tmp_path,
        view,
        source_kind=ModelSourceKind.HUB,
        fetch=fetch,
        runtime=_runtime(),
        capacity=_envelope(10_000_000),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    assert first.failure is ModelFailure.NONE
    assert first.artifact is not None
    assert first.artifact.immutable_revision == "commit-aaa"
    assert first.artifact.lifecycle is ArtifactLifecycle.STORED
    cited = with_stored(tmp_path, _entry(_view(revision="commit-aaa")))
    assert cited.artifact_id == first.artifact.artifact_id
    assert cited.lifecycle == ArtifactLifecycle.STORED.value
    assert second.artifact is not None
    assert second.artifact.artifact_id == first.artifact.artifact_id
    assert len(calls) == 1
    other = store_view(
        tmp_path,
        _view(revision="commit-bbb"),
        source_kind=ModelSourceKind.HUB,
        fetch=fetch,
        runtime=_runtime(),
        capacity=_envelope(10_000_000),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    assert other.artifact is not None
    assert other.artifact.artifact_id != first.artifact.artifact_id
    assert len(calls) == 2


def test_local_import_copies_and_leaves_the_source_unowned(tmp_path: Path) -> None:
    source = tmp_path / "external"
    source.mkdir()
    (source / "config.json").write_text(_config(), encoding="utf-8")
    (source / "model.safetensors").write_bytes(b"local-weights")
    state = tmp_path / "state"
    stored = store_local(
        state,
        source,
        "fixture-local",
        runtime=_runtime(),
        capacity=_envelope(10_000_000),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    assert stored.artifact is not None
    assert stored.artifact.lifecycle is ArtifactLifecycle.STORED
    assert (source / "model.safetensors").read_bytes() == b"local-weights"
    owned = warehouse_root(state) / stored.artifact.artifact_id / "model.safetensors"
    assert owned.read_bytes() == b"local-weights"
    assert ".machi-model.json" not in {
        path.name for path in source.iterdir()
    }


def test_partial_staging_is_not_a_stored_artifact(tmp_path: Path) -> None:
    def fetch(destination: Path, relative_paths: tuple[str, ...]) -> None:
        (destination / "config.json").write_text("partial", encoding="utf-8")
        raise OSError("interrupted")

    result = store_view(
        tmp_path,
        _view(),
        source_kind=ModelSourceKind.HUB,
        fetch=fetch,
        runtime=_runtime(),
        capacity=_envelope(10_000_000),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    assert result.failure is ModelFailure.INTERRUPTED
    assert result.artifact is None
    assert list_stored(tmp_path) == ()


def test_hashes_and_corruption(tmp_path: Path) -> None:
    payload = b"exact-bytes"

    def fetch(destination: Path, relative_paths: tuple[str, ...]) -> None:
        for relative in relative_paths:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload if relative.endswith(".safetensors") else b"{}")

    result = store_view(
        tmp_path,
        _view(),
        source_kind=ModelSourceKind.HUB,
        fetch=fetch,
        runtime=_runtime(),
        capacity=_envelope(10_000_000),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    assert result.artifact is not None
    weight = next(
        item
        for item in result.artifact.files
        if item.relative_path.endswith(".safetensors")
    )
    assert weight.sha256 == hashlib.sha256(payload).hexdigest()
    stored_path = (
        warehouse_root(tmp_path) / result.artifact.artifact_id / weight.relative_path
    )
    stored_path.write_bytes(b"tampered")
    again = store_view(
        tmp_path,
        _view(),
        source_kind=ModelSourceKind.HUB,
        fetch=fetch,
        runtime=_runtime(),
        capacity=_envelope(10_000_000),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    assert again.failure is ModelFailure.INTEGRITY_FAILED
    assert load_artifact(tmp_path, result.artifact.artifact_id) is not None
    assert stored_path.read_bytes() == b"tampered"


def test_unsafe_local_files_fail_closed(tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "config.json").write_text(_config(), encoding="utf-8")
    (linked / "model.safetensors").symlink_to(linked / "config.json")
    with pytest.raises(ValidationError, match="symlink"):
        list_local_files(linked)
    refused = store_local(
        tmp_path / "state-link",
        linked,
        "linked",
        runtime=_runtime(),
        capacity=_envelope(10_000_000),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    assert refused.failure is ModelFailure.LOCAL_IMPORT_INVALID
    fifo = tmp_path / "fifo"
    fifo.mkdir()
    (fifo / "config.json").write_text(_config(), encoding="utf-8")
    os.mkfifo(fifo / "model.safetensors")
    with pytest.raises(ValidationError, match="special"):
        list_local_files(fifo)


def test_capacity_is_checked_before_fetch(tmp_path: Path) -> None:
    called = False

    def fetch(destination: Path, relative_paths: tuple[str, ...]) -> None:
        nonlocal called
        called = True

    result = store_view(
        tmp_path,
        _view(),
        source_kind=ModelSourceKind.HUB,
        fetch=fetch,
        runtime=_runtime(),
        capacity=_envelope(1),
        accelerator_safe_bytes=10_000_000,
        observed_at=FIXED,
    )
    assert called is False
    assert result.failure is ModelFailure.INSUFFICIENT_STORAGE


def test_events_do_not_carry_a_token_or_card_body() -> None:
    entry = _entry()
    snapshot = snapshot_for(
        (entry,),
        foundation_id="fgen_test",
        capacity_evidence_id="cev_test",
        policy_token="immutable_commit",
        observed_at=FIXED,
    )
    payload = model_events(snapshot, clock=FixedClock(FIXED))[0].payload
    rendered = str(payload)
    assert "hf_" not in rendered
    assert "README" not in rendered
    assert entry.definition.repository not in rendered


def test_hard_link_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "hard"
    root.mkdir()
    original = root / "config.json"
    original.write_text(_config(), encoding="utf-8")
    os.link(original, root / "model.safetensors")
    with pytest.raises(ValidationError, match="hard link"):
        list_local_files(root)
    assert stat.S_ISREG(original.stat().st_mode)

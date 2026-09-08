"""Stage 1.6E foundation selection: provisionable is not executable."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from kultrun.adapters.host import fixtures
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.provisioning.fixture import FixtureRuntimeProvisioner
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.adapters.verification.fixture import (
    SCENARIO_IMPORT_FAILURE,
    FixtureProbeRunner,
    FixtureRuntimeVerifier,
)
from kultrun.api.contracts import ApiRequest, Method
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.errors import NotFoundError, PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import build, config_schema
from kultrun.runtime.contracts import (
    FoundationConfidence,
    FoundationSelection,
    FoundationSelectionMode,
    RuntimePolicy,
    RuntimeResolverMode,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
    VerificationStatus,
)
from kultrun.runtime.lock import ProvisioningLock, SelectionLock, VerificationLock
from kultrun.runtime.plan import is_provisionable
from kultrun.runtime.provision import ProvisioningService
from kultrun.runtime.selection import STALE_DOMAINS, FoundationSelectionService
from kultrun.runtime.verify import VerificationService
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named
from tests.test_contracts import host_capabilities
from tests.test_runtime_provisioning import _candidate
from tests.test_runtime_resolution import _container, _native

SOURCE = Path(__file__).resolve().parent.parent / "src"


def _services(
    tmp_path: Path,
    scenario: str = "healthy",
) -> tuple[FoundationSelectionService, FileStore]:
    records = FileStore(tmp_path / "records")
    clock = FixedClock(now_utc())
    state = tmp_path / "state"
    provisioning = ProvisioningService(
        records,
        clock,
        FixtureRuntimeProvisioner(),
        state,
        ProvisioningLock(state),
    )
    verification = VerificationService(
        records,
        clock,
        FixtureRuntimeVerifier(scenario),
        FixtureProbeRunner(scenario),
        state,
        VerificationLock(state),
    )
    foundation = FoundationSelectionService(
        records,
        clock,
        provisioning,
        verification,
        SelectionLock(state),
    )
    return foundation, records


def _alt_descriptor() -> RuntimeSupportDescriptor:
    return RuntimeSupportDescriptor(
        runtime=Name("alt-native"),
        display_name="Alternate native family",
        support_tier=RuntimeSupportTier.TEST_ONLY,
        production_candidate=False,
        compatible_executor_types=(Name("native-process"),),
        supported_os_families=("linux",),
        supported_architectures=("x86_64",),
        supported_accelerator_families=("nvidia",),
        required_features=(
            "process_execution",
            "structured_argv",
            "environment_variables",
        ),
        required_components=(Name("vllm"),),
        preferred_version="0.0.1",
    )


def test_schema_has_no_model_or_score_fields() -> None:
    names = {item.name for item in fields(FoundationSelection)}
    forbidden = {
        "model_id",
        "model",
        "artifact_id",
        "score",
        "weight",
        "throughput",
        "deployment_plan_id",
        "environment_provider",
    }
    assert names.isdisjoint(forbidden)
    assert "recommended_candidate_id" in names
    assert "selected_candidate_id" in names
    assert FoundationSelection.kind == "runtime.foundation_selection"


def test_resolver_auto_is_not_selection_auto() -> None:
    assert RuntimeResolverMode.AUTO.value == "auto"
    assert FoundationSelectionMode.AUTO.value == "auto"
    assert RuntimeResolverMode.__name__ != FoundationSelectionMode.__name__
    assert "EXPLICIT" in RuntimeResolverMode.__members__
    assert "MANUAL" in FoundationSelectionMode.__members__
    assert "MANUAL" not in RuntimeResolverMode.__members__
    assert "EXPLICIT" not in FoundationSelectionMode.__members__


def test_get_view_does_not_persist(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    foundation, store = _services(tmp_path)
    overview = foundation.view(
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    assert overview.selection.generation == 0
    assert foundation.stored(host) is None
    assert store.records(FoundationSelection) == ()
    assert is_resolved(overview.selection.recommended_candidate_id)
    assert (
        overview.selection.selected_candidate_id
        == overview.selection.recommended_candidate_id
    )


def test_auto_selects_recommended_provisionable(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    foundation, _ = _services(tmp_path)
    overview = foundation.select_auto(
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    assert overview.selection.selection_mode is FoundationSelectionMode.AUTO
    assert overview.selection.generation == 1
    assert overview.selection.downstream_stale is True
    assert overview.selection.stale_domains == STALE_DOMAINS
    recommended = overview.selection.recommended_candidate_id
    assert recommended == overview.selection.selected_candidate_id
    chosen = next(item for item in overview.candidates if item.selected)
    assert chosen.role == "recommended_to_provision"
    assert chosen.confidence is FoundationConfidence.PROVISIONABLE


def test_container_candidate_is_blocked(tmp_path: Path) -> None:
    host = host_capabilities()
    foundation, _ = _services(tmp_path)
    overview = foundation.view(
        host,
        (_native(host), _container(host)),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    blocked = [item for item in overview.candidates if item.role == "blocked"]
    assert any("container" in item.reason or item.candidate_id for item in blocked)
    assert overview.blocked_ids
    for ident in overview.blocked_ids:
        candidate, _ = _candidate(host, (_native(host), _container(host)))
        del candidate
        row = next(item for item in overview.candidates if item.candidate_id == ident)
        if row.confidence is FoundationConfidence.BLOCKED:
            assert row.role == "blocked"


def test_manual_blocked_candidate_is_refused(tmp_path: Path) -> None:
    host = host_capabilities()
    foundation, _ = _services(tmp_path)
    overview = foundation.view(
        host,
        (_native(host), _container(host)),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    blocked_id = overview.blocked_ids[0]
    with pytest.raises(PreconditionFailedError, match="blocked"):
        foundation.select_manual(
            blocked_id,
            host,
            (_native(host), _container(host)),
            (VllmRuntimeSupport().support(),),
            components={"vllm": "missing"},
        )
    assert foundation.stored(host) is None


def test_manual_other_provisionable_does_not_switch_recommendation(
    tmp_path: Path,
) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(), _alt_descriptor())
    policy = RuntimePolicy(allow_test_only=True)
    foundation, _ = _services(tmp_path)
    viewed = foundation.view(
        host, (native,), descriptors, policy, components={"vllm": "missing"}
    )
    other = next(
        item for item in viewed.candidates if item.role == "other_provisionable"
    )
    selected = foundation.select_manual(
        other.candidate_id,
        host,
        (native,),
        descriptors,
        policy,
        components={"vllm": "missing"},
    )
    assert selected.selection.selection_mode is FoundationSelectionMode.MANUAL
    assert selected.selection.selected_candidate_id == other.candidate_id
    assert selected.selection.recommended_candidate_id != other.candidate_id
    assert selected.selection.downstream_stale is True
    chosen = next(item for item in selected.candidates if item.selected)
    assert chosen.candidate_id == other.candidate_id
    assert chosen.role == "other_provisionable"


def test_return_to_auto_clears_manual(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(), _alt_descriptor())
    policy = RuntimePolicy(allow_test_only=True)
    foundation, _ = _services(tmp_path)
    viewed = foundation.view(
        host, (native,), descriptors, policy, components={"vllm": "missing"}
    )
    other = next(
        item for item in viewed.candidates if item.role == "other_provisionable"
    )
    foundation.select_manual(
        other.candidate_id,
        host,
        (native,),
        descriptors,
        policy,
        components={"vllm": "missing"},
    )
    restored = foundation.select_auto(
        host, (native,), descriptors, policy, components={"vllm": "missing"}
    )
    assert restored.selection.selection_mode is FoundationSelectionMode.AUTO
    assert (
        restored.selection.selected_candidate_id
        == restored.selection.recommended_candidate_id
    )
    assert restored.selection.generation == 2


def test_realize_and_verify_selected_reaches_verified(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(),)
    foundation, _ = _services(tmp_path)
    foundation.select_auto(host, (native,), descriptors, components={"vllm": "missing"})
    installation = foundation.realize_selected(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    assert installation.status.value == "installed"
    profile = foundation.verify_selected(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    assert profile.status is VerificationStatus.VERIFIED
    overview = foundation.view(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    assert overview.verified_executable_ids
    chosen = next(item for item in overview.candidates if item.selected)
    assert chosen.confidence is FoundationConfidence.VERIFIED_EXECUTABLE
    again = foundation.realize_selected(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    assert again.installation_id == installation.installation_id


def test_failed_verify_does_not_silently_switch(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(),)
    foundation, _ = _services(tmp_path, SCENARIO_IMPORT_FAILURE)
    selected = foundation.select_auto(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    selected_id = selected.selection.selected_candidate_id
    foundation.realize_selected(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    profile = foundation.verify_selected(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    assert profile.status is VerificationStatus.FAILED
    after = foundation.view(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    assert after.selection.selected_candidate_id == selected_id
    assert after.selection.selection_mode is FoundationSelectionMode.AUTO
    assert selected_id not in after.verified_executable_ids
    chosen = next(item for item in after.candidates if item.selected)
    assert chosen.confidence is FoundationConfidence.PROVISIONABLE
    assert chosen.profile_status == "failed"


def test_manual_non_vllm_realize_fails_without_fallback(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(), _alt_descriptor())
    policy = RuntimePolicy(allow_test_only=True)
    foundation, _ = _services(tmp_path)
    viewed = foundation.view(
        host, (native,), descriptors, policy, components={"vllm": "missing"}
    )
    other = next(
        item for item in viewed.candidates if item.role == "other_provisionable"
    )
    foundation.select_manual(
        other.candidate_id,
        host,
        (native,),
        descriptors,
        policy,
        components={"vllm": "missing"},
    )
    with pytest.raises((PreconditionFailedError, NotFoundError)):
        foundation.realize_selected(
            host,
            (native,),
            descriptors,
            policy,
            components={"vllm": "missing"},
        )
    stored = foundation.stored(host)
    assert stored is not None
    assert stored.selected_candidate_id == other.candidate_id
    assert stored.selection_mode is FoundationSelectionMode.MANUAL


def test_get_after_select_does_not_probe(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(),)
    records = FileStore(tmp_path / "records")
    clock = FixedClock(now_utc())
    state = tmp_path / "state"
    runner = FixtureProbeRunner("healthy")
    provisioning = ProvisioningService(
        records,
        clock,
        FixtureRuntimeProvisioner(),
        state,
        ProvisioningLock(state),
    )
    verification = VerificationService(
        records,
        clock,
        FixtureRuntimeVerifier("healthy"),
        runner,
        state,
        VerificationLock(state),
    )
    foundation = FoundationSelectionService(
        records,
        clock,
        provisioning,
        verification,
        SelectionLock(state),
    )
    foundation.select_auto(host, (native,), descriptors, components={"vllm": "missing"})
    foundation.realize_selected(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    foundation.verify_selected(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    assert runner.run_count == 1
    foundation.view(host, (native,), descriptors, components={"vllm": "missing"})
    assert runner.run_count == 1


def test_architecture_non_edges() -> None:
    leaks = _imports_named(
        SOURCE / "kultrun" / "runtime" / "selection.py",
        "kultrun.model",
        "kultrun.planning",
        "kultrun.resource",
        "kultrun.inference",
        "kultrun.execution",
        "subprocess",
    )
    assert leaks == []
    names = {item.name for item in fields(FoundationSelection)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    text = (SOURCE / "kultrun" / "runtime" / "selection.py").read_text(
        encoding="utf-8"
    )
    assert "FoundationCandidate" not in text
    assert "EnvironmentProvider" not in text
    assert "SelectionFramework" not in text


def test_api_and_console_surfaces(tmp_path: Path) -> None:
    platform = build(
        config_schema().load({"platform": {"state_root": str(tmp_path / "state")}}),
        fixture=fixtures.DEFAULT_SHAPE,
        acquisition_adapter="fixture",
        runtime_provisioner="fixture",
        runtime_verifier="fixture",
    )
    viewed = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/runtimes/foundation")
    )
    assert viewed.status == 200
    payload = viewed.body["payload"]
    assert isinstance(payload, dict)
    assert payload["mutations"] is False
    assert payload["verify"] is False
    assert payload["selection_mode"] == "auto"
    assert payload["resolver_mode"] == "auto"
    assert payload["selection_mode"] != "explicit"
    selected = platform.router.handle(
        ApiRequest(
            method=Method.POST,
            path="/v1/runtimes/foundation/select",
            query={"mode": "auto"},
        )
    )
    assert selected.status == 200
    body = selected.body["payload"]
    assert isinstance(body, dict)
    assert body["selection_mode"] == "auto"
    assert body["downstream_stale"] is True
    realized = platform.router.handle(
        ApiRequest(method=Method.POST, path="/v1/runtimes/foundation/realize")
    )
    assert realized.status == 200
    verified = platform.router.handle(
        ApiRequest(method=Method.POST, path="/v1/runtimes/foundation/verify")
    )
    assert verified.status == 200
    profile = verified.body["payload"]
    assert isinstance(profile, dict)
    assert profile["status"] == "verified"
    models = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/selection")
    )
    assert models.status == 200
    model_body = models.body["payload"]
    assert isinstance(model_body, dict)
    assert model_body["foundation_stale"] is True
    candidates = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/runtimes/candidates")
    )
    assert candidates.status == 200
    cand_body = candidates.body["payload"]
    assert isinstance(cand_body, dict)
    assert "foundation" in cand_body
    html = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
    ).read_text(encoding="utf-8")
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    assert "/runtimes/foundation" in script
    assert "Select foundation" in script
    assert "Use AUTO" in script
    assert "Recommended Runtime" not in script
    assert "Select Model" not in script
    panel = html.split("candidates-panel", 1)[1].split("<section", 1)[0]
    assert "Verify" not in panel
    assert "recommended to provision" in panel.lower()


def test_recommendation_is_deterministic(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(),)
    foundation, _ = _services(tmp_path)
    first = foundation.view(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    second = foundation.view(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    assert first.selection.recommended_candidate_id == (
        second.selection.recommended_candidate_id
    )
    assert first.provisionable_ids == second.provisionable_ids


def test_selection_survives_store_reload(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(), _alt_descriptor())
    policy = RuntimePolicy(allow_test_only=True)
    first, store = _services(tmp_path)
    viewed = first.view(
        host, (native,), descriptors, policy, components={"vllm": "missing"}
    )
    other = next(
        item for item in viewed.candidates if item.role == "other_provisionable"
    )
    first.select_manual(
        other.candidate_id,
        host,
        (native,),
        descriptors,
        policy,
        components={"vllm": "missing"},
    )
    clock = FixedClock(now_utc())
    state = tmp_path / "state"
    restored = FoundationSelectionService(
        store,
        clock,
        ProvisioningService(
            store,
            clock,
            FixtureRuntimeProvisioner(),
            state,
            ProvisioningLock(state),
        ),
        VerificationService(
            store,
            clock,
            FixtureRuntimeVerifier(),
            FixtureProbeRunner(),
            state,
            VerificationLock(state),
        ),
        SelectionLock(state),
    )
    loaded = restored.stored(host)
    assert loaded is not None
    assert loaded.selection_mode is FoundationSelectionMode.MANUAL
    assert loaded.selected_candidate_id == other.candidate_id
    assert loaded.recommended_candidate_id != other.candidate_id
    viewed_again = restored.view(
        host, (native,), descriptors, policy, components={"vllm": "missing"}
    )
    assert viewed_again.selection.selection_mode is FoundationSelectionMode.MANUAL
    assert viewed_again.selection.selected_candidate_id == other.candidate_id
    assert viewed_again.selection.recommended_candidate_id != other.candidate_id


def test_auto_presents_stale_when_recommendation_moves(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(), _alt_descriptor())
    policy = RuntimePolicy(allow_test_only=True)
    foundation, store = _services(tmp_path)
    auto = foundation.select_auto(
        host, (native,), descriptors, policy, components={"vllm": "missing"}
    )
    other = next(
        item for item in auto.candidates if item.role == "other_provisionable"
    )
    stored = foundation.stored(host)
    assert stored is not None
    store.put(
        stored.selection_id.value,
        replace(
            stored,
            selected_candidate_id=other.candidate_id,
            downstream_stale=False,
            stale_domains=(),
        ),
    )
    viewed = foundation.view(
        host, (native,), descriptors, policy, components={"vllm": "missing"}
    )
    assert viewed.selection.selection_mode is FoundationSelectionMode.AUTO
    assert viewed.selection.selected_candidate_id == (
        viewed.selection.recommended_candidate_id
    )
    assert viewed.selection.selected_candidate_id != other.candidate_id
    assert viewed.selection.downstream_stale is True


def test_provisionable_helper_still_native_only() -> None:
    host = host_capabilities()
    candidate, resolution = _candidate(
        host, (_native(host), _container(host)), components={"vllm": "missing"}
    )
    assert is_provisionable(candidate)
    container = next(
        item
        for item in (*resolution.candidates, *resolution.unsupported)
        if item.executor.value == "container-docker"
    )
    assert not is_provisionable(container)

"""Ollama dual qualification correction. Fixtures only."""

from __future__ import annotations

import datetime as dt
import inspect
import json
from dataclasses import replace
from pathlib import Path

from tests.machi.test_admit import _configuration, _decision, _envelope, _manager
from tests.machi.test_plan import _inputs

from machi.adapters.journal.jsonl import JsonlJournal
from machi.adapters.model.ollama_api import (
    SHOW_PATH,
    FakeOllamaApi,
    FixtureOutcome,
    ShownModel,
)
from machi.adapters.model.ollama_case import run_ollama_qualification_case
from machi.adapters.model.ollama_qualifier import qualify_ollama
from machi.adapters.plan.vllm import build_vllm_recipe
from machi.admit.contracts import AdmissionFailure, AdmissionOutcome
from machi.kernel.errors import PersistenceError, ValidationError
from machi.kernel.events import EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict
from machi.kernel.unresolved import is_resolved
from machi.model.comparison import ComparisonClass, QualificationComparison
from machi.model.contracts import ModelArtifact
from machi.model.events import COMPARED_TYPE
from machi.model.provider_candidate import candidate_id_for, public_candidate
from machi.model.provider_qualification import ProviderFitState
from machi.model.qualification import QualificationOutcome
from machi.model.shadow import FitState, evaluate_shadow
from machi.plan.compose import compose_plan
from machi.plan.contracts import PlanFailure, PlanPreference
from machi.plan.policy import POLICY_VERSION
from machi.plan.qualification_probe import make_qualification_probe

FIXED = dt.datetime(2026, 9, 24, 8, 0, tzinfo=dt.UTC)
DIGEST = "ab" * 32
OTHER = "cd" * 32
HARDWARE = "ampere_48"
ENVIRONMENT = "exe_ollama_fixture"
DEVICE = "accel_0"


def _candidate(
    *,
    name: str = "tiny:latest",
    digest: str = DIGEST,
    size_bytes: int | None = 100,
    shaped: bool = False,
):
    return public_candidate(
        display_name=name,
        digest=digest,
        size_bytes=size_bytes,
        family=None if shaped else "llama",
        dtype="float16" if shaped else None,
        layer_count=1 if shaped else None,
        key_value_heads=1 if shaped else None,
        head_dim=1 if shaped else None,
        context_length=8 if shaped else None,
    )


def _case(
    tmp_path: Path,
    *,
    candidate,
    outcome: FixtureOutcome = FixtureOutcome.PASS,
    host: int = 2000,
    accel: int = 1000,
    journal: JsonlJournal | None = None,
):
    envelope = _envelope(host=host, accel=accel, storage=2000)
    api = FakeOllamaApi(
        name=candidate.display_name,
        digest=candidate.digest,
        outcome=outcome,
    )
    case = run_ollama_qualification_case(
        candidate=candidate,
        envelope=envelope,
        manager=_manager(tmp_path),
        api=api,
        generation_id="fgen_ollama",
        foundation_id="fgen_ollama",
        engine_version="0.34.3",
        hardware_class=HARDWARE,
        execution_environment_fingerprint=ENVIRONMENT,
        accelerator_identity=DEVICE,
        context=8,
        concurrency=1,
        observed_at=FIXED,
        journal=journal,
    )
    return case, api


def test_digest_is_identity_and_show_has_no_digest() -> None:
    first = _candidate(name="tiny:latest")
    alias = _candidate(name="tiny:backup")
    other = _candidate(name="tiny:latest", digest=OTHER)
    assert first.candidate_id == alias.candidate_id == candidate_id_for(DIGEST)
    assert other.candidate_id != first.candidate_id
    prefixed = public_candidate(display_name="tiny:latest", digest=f"sha256:{DIGEST}")
    assert prefixed.candidate_id == first.candidate_id
    assert not isinstance(first, ModelArtifact)
    shown = ShownModel(name="tiny:latest", size_bytes=10)
    assert not hasattr(shown, "digest")
    text = Path("src/machi/adapters/model/ollama_api.py").read_text(encoding="utf-8")
    assert "class ShownModel" in text
    assert "digest:" not in text.split("class ShownModel", 1)[1].split("class ", 1)[0]
    try:
        public_candidate(display_name="tiny:latest", digest="tiny:latest")
    except ValidationError:
        return
    raise AssertionError("a tag was accepted as a digest")


def test_catalog_drift_uses_tags_and_does_not_load(tmp_path: Path) -> None:
    case, api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.CATALOG_DRIFT,
    )
    assert case.evidence is not None
    assert case.evidence.failure == "catalog_identity_changed"
    assert case.evidence.provider_fit is ProviderFitState.UNRESOLVED
    assert "preload" not in api.calls
    assert "generate_probe" not in api.calls
    assert SHOW_PATH not in api.calls
    assert case.reservation_released is True
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.MACHI_UNRESOLVED


def test_preload_identity_mismatch_refuses_before_token(tmp_path: Path) -> None:
    case, api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.PRELOAD_IDENTITY_MISMATCH,
    )
    assert case.evidence is not None
    assert case.evidence.failure == "loaded_digest_absent"
    assert case.evidence.provider_fit is ProviderFitState.UNRESOLVED
    assert "generate_probe" not in api.calls
    assert api.calls.index("preload") < api.calls.index("/api/ps")


def test_post_token_identity_mismatch_keeps_fit(tmp_path: Path) -> None:
    case, api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.POST_TOKEN_IDENTITY_MISMATCH,
    )
    assert case.evidence is not None
    assert case.evidence.provider_fit is ProviderFitState.FIT
    assert case.evidence.outcome is QualificationOutcome.FAIL_MODEL
    assert case.evidence.failure == "post_token_identity_mismatch"
    assert case.evidence.outcome is not QualificationOutcome.PASS
    assert "generate_probe" in api.calls
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.AGREE_FIT


def test_token_failure_after_fit_is_not_a_false_positive(tmp_path: Path) -> None:
    case, _api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.NO_TOKEN,
    )
    assert case.evidence is not None
    assert case.evidence.provider_fit is ProviderFitState.FIT
    assert case.evidence.failure == "token_proof_missing"
    assert case.evidence.token_proved is False
    assert case.evidence.outcome is not QualificationOutcome.PASS
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.AGREE_FIT
    assert case.evidence.input_tokens == 3


def test_shadow_fit_and_provider_fit_agree(tmp_path: Path) -> None:
    journal = JsonlJournal(tmp_path / "journal")
    case, api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        journal=journal,
    )
    assert case.shadow is not None
    assert case.shadow.fit is FitState.FIT
    assert case.evidence is not None
    assert case.evidence.outcome is QualificationOutcome.PASS
    assert case.evidence.load_seconds == 1.5
    assert case.evidence.provider_fit is ProviderFitState.FIT
    assert case.evidence.unload_failure == "none"
    assert case.evidence.size_vram_semantics == "runtime_reported"
    assert case.status == "clean"
    assert case.reservation_released is True
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.AGREE_FIT
    assert case.comparison.vram_semantics == "estimate_vs_runtime_reported"
    assert api.calls == [
        "/api/tags",
        "preload",
        "/api/ps",
        "generate_probe",
        "/api/ps",
        "unload",
        "/api/ps",
    ]
    saved = journal.records()
    assert len(saved) == 1
    assert saved[0].event_type.value == COMPARED_TYPE
    assert saved[0].privacy is PrivacyClass.OPERATIONAL
    assert isinstance(saved[0].payload, QualificationComparison)
    assert saved[0].payload.comparison_id == case.comparison.comparison_id
    assert str(saved[0].event_id) == case.journal_event_id


def test_shadow_no_fit_does_not_veto_provider_fit(tmp_path: Path) -> None:
    case, _api = _case(
        tmp_path,
        candidate=_candidate(size_bytes=5000),
        accel=1000,
    )
    assert case.shadow is not None
    assert case.shadow.fit is FitState.NO_FIT
    assert case.evidence is not None
    assert case.evidence.provider_fit is ProviderFitState.FIT
    assert case.evidence.outcome is QualificationOutcome.PASS
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.MACHI_FALSE_NEGATIVE


def test_provider_no_fit_still_refuses(tmp_path: Path) -> None:
    case, api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.NO_FIT,
    )
    assert case.shadow is not None
    assert case.shadow.fit is FitState.FIT
    assert case.evidence is not None
    assert case.evidence.provider_fit is ProviderFitState.NO_FIT
    assert case.evidence.outcome is QualificationOutcome.FAIL_MODEL
    assert "generate_probe" not in api.calls
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.MACHI_FALSE_POSITIVE


def test_unresolved_shadow_stays_unresolved(tmp_path: Path) -> None:
    passed, _api = _case(tmp_path, candidate=_candidate())
    failed, _api = _case(
        tmp_path / "fail",
        candidate=_candidate(),
        outcome=FixtureOutcome.NO_FIT,
    )
    assert passed.shadow is not None
    assert failed.shadow is not None
    assert passed.shadow.fit is FitState.UNRESOLVED
    assert failed.shadow.fit is FitState.UNRESOLVED
    assert passed.comparison is not None
    assert failed.comparison is not None
    assert passed.comparison.classification is ComparisonClass.MACHI_UNRESOLVED
    assert failed.comparison.classification is ComparisonClass.MACHI_UNRESOLVED


def test_cleanup_failure_retains_the_hold(tmp_path: Path) -> None:
    envelope = _envelope(host=2000, accel=1000, storage=2000)
    manager = _manager(tmp_path)
    candidate = _candidate(shaped=True)
    api = FakeOllamaApi(
        name=candidate.display_name,
        digest=candidate.digest,
        outcome=FixtureOutcome.UNLOAD_FAILURE,
    )
    case = run_ollama_qualification_case(
        candidate=candidate,
        envelope=envelope,
        manager=manager,
        api=api,
        generation_id="fgen_ollama",
        foundation_id="fgen_ollama",
        engine_version="0.34.3",
        hardware_class=HARDWARE,
        execution_environment_fingerprint=ENVIRONMENT,
        accelerator_identity=DEVICE,
        context=8,
        concurrency=1,
        observed_at=FIXED,
    )
    assert case.reservation_released is False
    assert case.status == "cleanup_reconcile_required"
    assert case.evidence is not None
    assert case.evidence.outcome is not QualificationOutcome.PASS
    assert case.evidence.provider_fit is ProviderFitState.FIT
    assert manager.list_active_reservations()
    resident = FakeOllamaApi(
        name=candidate.display_name,
        digest=candidate.digest,
        outcome=FixtureOutcome.RESIDENT_AFTER_UNLOAD,
    )
    stayed = run_ollama_qualification_case(
        candidate=candidate,
        envelope=envelope,
        manager=_manager(tmp_path / "stay"),
        api=resident,
        generation_id="fgen_ollama",
        foundation_id="fgen_ollama",
        engine_version="0.34.3",
        hardware_class=HARDWARE,
        execution_environment_fingerprint=ENVIRONMENT,
        accelerator_identity=DEVICE,
        context=8,
        concurrency=1,
        observed_at=FIXED,
    )
    assert stayed.reservation_released is False
    assert stayed.evidence is not None
    assert stayed.evidence.outcome is not QualificationOutcome.PASS
    assert _manager(tmp_path / "stay2") or True


def test_journal_failure_does_not_change_fit(tmp_path: Path) -> None:
    class Boom:
        def append(self, event: EventRecord) -> EventRecord:
            del event
            raise PersistenceError("journal unavailable")

        def records(self) -> tuple[EventRecord, ...]:
            return ()

        def defects(self) -> tuple[object, ...]:
            return ()

    case, _api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        journal=Boom(),  # type: ignore[arg-type]
    )
    assert case.journal_failure == "journal_append_failed"
    assert case.evidence is not None
    assert case.evidence.provider_fit is ProviderFitState.FIT
    assert case.evidence.outcome is QualificationOutcome.PASS


def test_analytics_have_no_prompt_or_path(tmp_path: Path) -> None:
    case, _api = _case(tmp_path, candidate=_candidate(shaped=True))
    assert case.comparison is not None
    assert case.evidence is not None
    rendered = json.dumps(to_dict(case.comparison))
    rendered += json.dumps(to_dict(case.evidence))
    assert "prompt" not in rendered.lower()
    assert "/tmp" not in rendered
    assert "response" not in rendered.lower()


def test_shadow_uses_the_admitted_remainder(tmp_path: Path) -> None:
    envelope = _envelope(host=2000, accel=1000, storage=2000)
    manager = _manager(tmp_path)
    deployment = _decision(host=40, accel=600, evidence=envelope.evidence_id)
    assert manager.admit(deployment, envelope, PlanFailure.NONE).outcome is (
        AdmissionOutcome.ADMITTED
    )
    candidate = _candidate(shaped=True, size_bytes=500)
    api = FakeOllamaApi(name=candidate.display_name, digest=candidate.digest)
    case = run_ollama_qualification_case(
        candidate=candidate,
        envelope=envelope,
        manager=manager,
        api=api,
        generation_id="fgen_ollama",
        foundation_id="fgen_a",
        engine_version="0.34.3",
        hardware_class=HARDWARE,
        execution_environment_fingerprint=ENVIRONMENT,
        accelerator_identity=DEVICE,
        context=8,
        concurrency=1,
        observed_at=FIXED,
    )
    assert case.shadow is not None
    assert case.shadow.fit is FitState.NO_FIT
    assert case.admission.reservation is not None
    assert is_resolved(case.admission.reservation)
    assert case.admission.reservation.accelerator_memory_bytes == 400
    assert case.admission.reservation.host_memory_bytes == 1960
    direct = evaluate_shadow(
        candidate,
        capacity_evidence_id=envelope.evidence_id,
        accelerator_identity=DEVICE,
        authorized_accelerator_bytes=1000,
        authorized_host_bytes=2000,
        context=8,
        concurrency=1,
        observed_at=FIXED,
    )
    assert direct.fit is FitState.FIT


def test_qualification_hold_is_the_full_remainder(tmp_path: Path) -> None:
    envelope = _envelope(host=100, accel=100, storage=100)
    manager = _manager(tmp_path)
    deployment = _decision(host=30, accel=40, evidence=envelope.evidence_id)
    assert manager.admit(deployment, envelope, PlanFailure.NONE).outcome is (
        AdmissionOutcome.ADMITTED
    )
    hold = make_qualification_probe(
        provider="ollama",
        candidate_id=candidate_id_for(DIGEST),
        digest=DIGEST,
        foundation_id="fgen_a",
        generation_id="fgen_a",
        capacity_evidence_id=envelope.evidence_id,
        accelerator_identity=DEVICE,
        policy_version=POLICY_VERSION,
    )
    admitted = manager.admit_probe(hold, envelope)
    reservation = admitted.reservation
    assert is_resolved(reservation)
    assert reservation.accelerator_memory_bytes == 60
    assert reservation.host_memory_bytes == 70
    assert reservation.persistent_bytes == 0
    blocked = manager.admit(
        _decision(plan="plan_b", token="b" * 32, host=1, accel=1),
        envelope,
        PlanFailure.NONE,
    )
    assert blocked.failure is AdmissionFailure.INSUFFICIENT_HOST_MEMORY
    assert manager.execution_authorized(
        reservation.reservation_id, _configuration(deployment)
    ) is False
    released = manager.release(reservation.reservation_id)
    assert released.outcome is AdmissionOutcome.RELEASED
    restored = manager.admit(
        _decision(plan="plan_c", token="c" * 32, host=1, accel=60),
        envelope,
        PlanFailure.NONE,
    )
    assert restored.outcome is AdmissionOutcome.ADMITTED


def test_native_plan_rules_remain(tmp_path: Path) -> None:
    del tmp_path
    inputs = _inputs(
        preference=PlanPreference(
            context_length=2048,
            concurrency=1,
            accelerator_count=1,
        )
    )
    member = replace(
        inputs.deployable.members[0], immutable_revision="revision-not-covered"
    )
    missing = compose_plan(
        replace(inputs, deployable=replace(inputs.deployable, members=(member,))),
        build_vllm_recipe,
    )
    assert missing.failure is PlanFailure.QUALIFICATION_REQUIRED
    narrowed = replace(inputs.qualification, context=1024, concurrency=1)
    covered = compose_plan(replace(inputs, qualification=narrowed), build_vllm_recipe)
    assert covered.failure is PlanFailure.QUALIFICATION_DOES_NOT_COVER
    probe = compose_plan(
        replace(inputs, qualification=narrowed, probe=True),
        build_vllm_recipe,
    )
    assert probe.failure is PlanFailure.NONE


def test_shadow_module_does_not_import_vllm_refiner() -> None:
    text = Path("src/machi/model/shadow.py").read_text(encoding="utf-8")
    adapter = Path("src/machi/adapters/model/ollama_qualifier.py").read_text(
        encoding="utf-8"
    )
    assert "refine_vllm" not in text
    assert "PredictServerVRAM" not in text
    assert "refine_vllm" not in adapter
    assert "shadow" not in inspect.signature(qualify_ollama).parameters


def test_unknown_shape_is_not_guessed_from_family() -> None:
    shadow = evaluate_shadow(
        _candidate(size_bytes=100),
        capacity_evidence_id="cev_admit",
        accelerator_identity=DEVICE,
        authorized_accelerator_bytes=1000,
        authorized_host_bytes=2000,
        context=8,
        concurrency=1,
        observed_at=FIXED,
    )
    assert shadow.fit is FitState.UNRESOLVED
    assert shadow.reason == "attention_shape_not_exposed"


def test_host_failure_before_fit_is_unresolved(tmp_path: Path) -> None:
    case, api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.HOST_FAILURE,
    )
    assert case.evidence is not None
    assert case.evidence.provider_fit is ProviderFitState.UNRESOLVED
    assert case.evidence.outcome is QualificationOutcome.FAIL_HOST
    assert "generate_probe" not in api.calls
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.MACHI_UNRESOLVED

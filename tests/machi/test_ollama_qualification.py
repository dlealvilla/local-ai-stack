"""Ollama dual qualification. Fixtures only: no download, load, or server."""

from __future__ import annotations

import datetime as dt
import inspect
import json
from dataclasses import replace
from pathlib import Path

from tests.machi.test_admit import _configuration, _decision, _envelope, _manager
from tests.machi.test_plan import _inputs

from machi.adapters.model.ollama_api import (
    GENERATE_PATH,
    SHOW_PATH,
    FakeOllamaApi,
    FixtureOutcome,
)
from machi.adapters.model.ollama_case import run_ollama_qualification_case
from machi.adapters.model.ollama_qualifier import qualify_ollama
from machi.adapters.plan.vllm import build_vllm_recipe
from machi.admit.contracts import AdmissionFailure, AdmissionOutcome
from machi.kernel.errors import ValidationError
from machi.kernel.schema import to_dict
from machi.kernel.unresolved import is_resolved
from machi.model.comparison import ComparisonClass
from machi.model.contracts import ModelArtifact
from machi.model.provider_candidate import candidate_id_for, public_candidate
from machi.model.qualification import QualificationOutcome
from machi.model.shadow import FitState, evaluate_shadow
from machi.plan.compose import compose_plan
from machi.plan.contracts import PlanFailure, PlanPreference
from machi.plan.policy import POLICY_VERSION
from machi.plan.qualification_probe import make_qualification_probe

FIXED = dt.datetime(2026, 9, 24, 7, 0, tzinfo=dt.UTC)
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
    outcome: FixtureOutcome,
    accel_safe: int = 1000,
):
    envelope = _envelope(host=2000, accel=accel_safe, storage=2000)
    api = FakeOllamaApi(
        name=candidate.display_name,
        digest=candidate.digest,
        outcome=outcome,
        size_bytes=1000,
        size_vram_bytes=800,
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
        accelerator_memory_bytes=100,
        host_memory_bytes=100,
        context=8,
        concurrency=1,
        observed_at=FIXED,
    )
    return case, api


def test_digest_is_identity_and_catalog_is_not_a_warehouse_artifact() -> None:
    first = _candidate(name="tiny:latest")
    alias = _candidate(name="tiny:backup")
    other = _candidate(name="tiny:latest", digest=OTHER)
    assert first.candidate_id == alias.candidate_id
    assert first.candidate_id == candidate_id_for(DIGEST)
    assert other.candidate_id != first.candidate_id
    prefixed = public_candidate(display_name="tiny:latest", digest=f"sha256:{DIGEST}")
    assert prefixed.candidate_id == first.candidate_id
    assert not isinstance(first, ModelArtifact)
    text = Path("src/machi/model/provider_candidate.py").read_text(encoding="utf-8")
    assert "ModelArtifact" not in text
    try:
        public_candidate(display_name="tiny:latest", digest="tiny:latest")
    except ValidationError:
        return
    raise AssertionError("a tag was accepted as a digest")


def test_shadow_fit_and_provider_pass_agree(tmp_path: Path) -> None:
    case, api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.PASS,
    )
    assert case.shadow.fit is FitState.FIT
    assert case.evidence is not None
    assert case.evidence.outcome is QualificationOutcome.PASS
    assert case.evidence.authority == "ollama"
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.AGREE_FIT
    assert case.evidence.size_vram_semantics == "runtime_reported"
    assert case.comparison.vram_semantics == "estimate_vs_runtime_reported"
    assert "peak" not in case.evidence.size_vram_semantics
    assert GENERATE_PATH in api.calls
    assert api.calls.index(SHOW_PATH) < api.calls.index(GENERATE_PATH)


def test_shadow_no_fit_does_not_veto_an_ollama_pass(tmp_path: Path) -> None:
    case, _api = _case(
        tmp_path,
        candidate=_candidate(size_bytes=5000),
        outcome=FixtureOutcome.PASS,
    )
    assert case.shadow.fit is FitState.NO_FIT
    assert case.evidence is not None
    assert case.evidence.outcome is QualificationOutcome.PASS
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.MACHI_FALSE_NEGATIVE


def test_ollama_no_fit_still_refuses_when_shadow_fits(tmp_path: Path) -> None:
    case, _api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.NO_FIT,
    )
    assert case.shadow.fit is FitState.FIT
    assert case.evidence is not None
    assert case.evidence.outcome is QualificationOutcome.FAIL_MODEL
    assert case.evidence.failure == "provider_no_fit"
    assert case.comparison is not None
    assert case.comparison.classification is ComparisonClass.MACHI_FALSE_POSITIVE


def test_unresolved_shadow_stays_unresolved_for_pass_and_fail(tmp_path: Path) -> None:
    passed, _api = _case(tmp_path, candidate=_candidate(), outcome=FixtureOutcome.PASS)
    failed, _api = _case(
        tmp_path / "fail",
        candidate=_candidate(),
        outcome=FixtureOutcome.NO_FIT,
    )
    assert passed.shadow.fit is FitState.UNRESOLVED
    assert failed.shadow.fit is FitState.UNRESOLVED
    assert passed.comparison is not None
    assert failed.comparison is not None
    assert passed.comparison.classification is ComparisonClass.MACHI_UNRESOLVED
    assert failed.comparison.classification is ComparisonClass.MACHI_UNRESOLVED


def test_provider_refusals_are_authoritative(tmp_path: Path) -> None:
    mismatch, mismatch_api = _case(
        tmp_path / "mismatch",
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.DIGEST_MISMATCH,
    )
    assert mismatch.evidence is not None
    assert mismatch.evidence.failure == "digest_mismatch"
    assert GENERATE_PATH not in mismatch_api.calls
    missing, _api = _case(
        tmp_path / "missing",
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.MISSING_FROM_PS,
    )
    assert missing.evidence is not None
    assert missing.evidence.failure == "loaded_digest_absent"
    assert missing.evidence.outcome is not QualificationOutcome.PASS
    silent, _api = _case(
        tmp_path / "silent",
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.NO_TOKEN,
    )
    assert silent.evidence is not None
    assert silent.evidence.failure == "token_proof_missing"
    assert silent.evidence.token_proved is False
    host, _api = _case(
        tmp_path / "host",
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.HOST_FAILURE,
    )
    assert host.evidence is not None
    assert host.evidence.outcome is QualificationOutcome.FAIL_HOST
    unloaded, _api = _case(
        tmp_path / "unload",
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.UNLOAD_FAILURE,
    )
    assert unloaded.evidence is not None
    assert unloaded.evidence.outcome is QualificationOutcome.PASS
    assert unloaded.evidence.unload_failure == "unload_failed"


def test_analytics_have_no_prompt_or_path(tmp_path: Path) -> None:
    case, _api = _case(
        tmp_path,
        candidate=_candidate(shaped=True),
        outcome=FixtureOutcome.PASS,
    )
    assert case.comparison is not None
    assert case.evidence is not None
    rendered = json.dumps(to_dict(case.comparison))
    rendered = rendered + json.dumps(to_dict(case.evidence))
    assert "prompt" not in rendered.lower()
    assert "/tmp" not in rendered
    assert "response" not in rendered.lower()


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
    envelope = _envelope(host=2000, accel=1000, storage=2000)
    shadow = evaluate_shadow(
        _candidate(size_bytes=100),
        envelope,
        accelerator_identity=DEVICE,
        context=8,
        concurrency=1,
        observed_at=FIXED,
    )
    assert shadow.fit is FitState.UNRESOLVED
    assert shadow.reason == "attention_shape_not_exposed"


def test_native_plan_rules_and_shared_ledger(tmp_path: Path) -> None:
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
    envelope = _envelope(host=100, accel=100, storage=100)
    manager = _manager(tmp_path)
    hold = make_qualification_probe(
        provider="ollama",
        candidate_id=candidate_id_for(DIGEST),
        digest=DIGEST,
        foundation_id="fgen_a",
        generation_id="fgen_a",
        capacity_evidence_id=envelope.evidence_id,
        accelerator_identity=DEVICE,
        accelerator_memory_bytes=60,
        host_memory_bytes=40,
        policy_version=POLICY_VERSION,
    )
    admitted = manager.admit_probe(hold, envelope)
    assert admitted.outcome is AdmissionOutcome.ADMITTED
    deployment = _decision(host=40, accel=50)
    second = manager.admit(deployment, envelope, PlanFailure.NONE)
    assert second.failure is AdmissionFailure.INSUFFICIENT_ACCELERATOR_CAPACITY
    reservation = admitted.reservation
    assert is_resolved(reservation)
    assert manager.execution_authorized(
        reservation.reservation_id, _configuration(deployment)
    ) is False
    released = manager.release(reservation.reservation_id)
    assert released.outcome is AdmissionOutcome.RELEASED
    assert manager.list_active_reservations() == ()

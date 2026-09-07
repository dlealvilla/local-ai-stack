"""Stage 1.6 — runtime-first ordering, eligibility, and acquisition modes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kultrun.adapters.host import fixtures
from kultrun.api.contracts import ApiRequest, Method
from kultrun.kernel.errors import NotFoundError, PreconditionFailedError
from kultrun.main import build, config_schema
from kultrun.planning.contracts import EligibilityVerdict, SelectionOutcome
from kultrun.planning.eligibility import RuntimeEligibilityEvaluator
from kultrun.runtime.contracts import (
    CompatibilityClass,
    RuntimePolicy,
    SupportTier,
    VerificationStatus,
)
from kultrun.runtime.fingerprint import verification_fingerprint

SOURCE = Path(__file__).resolve().parent.parent / "src"


def _fixture_policy() -> RuntimePolicy:
    return RuntimePolicy(
        allow_fixture_runtime=True, requested_runtime="fixture-vllm"
    )


def _platform(tmp_path: Path):
    configuration = config_schema().load(
        {
            "platform": {
                "state_root": str(tmp_path / "state"),
                "model_acquisition_provider": "fixture",
            }
        }
    )
    return build(configuration, fixture=fixtures.DEFAULT_SHAPE)


def _call(platform, path: str, *, method: Method = Method.GET, query=None, body=None):
    return platform.router.handle(
        ApiRequest(method=method, path=f"/v1{path}", query=query or {}, body=body)
    )


def _verify(platform):
    host = platform.hosts.current
    profile = platform.runtime_setup.provision_and_verify(host, _fixture_policy())
    assert profile.status is VerificationStatus.VERIFIED
    return profile


class TestResolver:
    def test_candidates_do_not_need_a_model(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        items = platform.runtime_setup.candidates(platform.hosts.current)
        families = {item.runtime_family.value for item in items}
        assert "vllm" in families
        assert "mlx" in families
        mlx = next(item for item in items if item.runtime_family.value == "mlx")
        assert mlx.compatibility is CompatibilityClass.UNSUPPORTED
        assert mlx.support_tier is SupportTier.FUTURE

    def test_explicit_incompatible_runtime_fails(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        with pytest.raises(PreconditionFailedError, match="compatible"):
            platform.runtime_setup.select(
                platform.hosts.current,
                RuntimePolicy(requested_runtime="mlx"),
            )

    def test_auto_selects_fixture_when_allowed(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        chosen = platform.runtime_setup.select(
            platform.hosts.current,
            RuntimePolicy(allow_fixture_runtime=True),
        )
        assert chosen.runtime_provider.value == "fixture-vllm"


class TestVerification:
    def test_installed_is_not_verified(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        host = platform.hosts.current
        candidate = platform.runtime_setup.select(
            host, _fixture_policy()
        )
        installation = platform.runtime_setup.provision(
            platform.runtime_setup.plan_for(candidate)
        )
        assert installation.status.value == "installed"
        assert platform.runtime_setup.verified(host) == ()
        selection = _call(platform, "/models/selection")
        assert _obj(selection.body["payload"])["outcome"] == "runtime_not_verified"

    def test_broken_runtime_blocks_normal_acquire(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        host = platform.hosts.current
        from kultrun.adapters.runtime.fixture_vllm import FixtureVllmVerifier

        platform.runtime_setup._verifiers[
            __import__("kultrun.kernel.ids", fromlist=["Name"]).Name("fixture-vllm")
        ] = FixtureVllmVerifier(succeed=False)
        candidate = platform.runtime_setup.select(
            host, _fixture_policy()
        )
        installation = platform.runtime_setup.provision(
            platform.runtime_setup.plan_for(candidate)
        )
        profile = platform.runtime_setup.verify(
            installation.installation_id.value, host
        )
        assert profile.status is VerificationStatus.FAILED
        result = platform.deployment.recommend(host, {})
        assert result["state"] == SelectionOutcome.RUNTIME_NOT_VERIFIED.value
        assert result["plan"] is None
        missing_mode = _call(
            platform,
            "/models/acquire",
            method=Method.POST,
            query={"candidate": "qwen2.5-7b-instruct-awq"},
        )
        assert missing_mode.status == 400
        normal = _call(
            platform,
            "/models/acquire",
            method=Method.POST,
            query={"mode": "normal_execution", "candidate": "qwen2.5-7b-instruct-awq"},
        )
        assert normal.status == 400
        stored = _call(
            platform,
            "/models/acquire",
            method=Method.POST,
            query={"mode": "store_only", "candidate": "qwen2.5-7b-instruct-awq"},
        )
        assert stored.status == 200


class TestEligibility:
    def test_unsupported_format_is_ineligible(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        profile = _verify(platform)
        snapshot = platform.deployment.snapshot(profile)
        tiny = platform.models.acquirable("tinyllama-1.1b-chat-q4")
        assert tiny is not None
        verdict = RuntimeEligibilityEvaluator().evaluate(tiny.metadata, snapshot)
        assert verdict.verdict is EligibilityVerdict.INELIGIBLE
        assert any(
            "format" in reason for reason in verdict.reasons
        ), verdict.reasons

    def test_awq_is_eligible(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        profile = _verify(platform)
        snapshot = platform.deployment.snapshot(profile)
        model = platform.models.acquirable("qwen2.5-7b-instruct-awq")
        assert model is not None
        verdict = RuntimeEligibilityEvaluator().evaluate(model.metadata, snapshot)
        assert verdict.verdict is EligibilityVerdict.ELIGIBLE


class TestFunnel:
    def test_full_eligible_order(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        profile = _verify(platform)
        result = platform.deployment.recommend(platform.hosts.current, {})
        assert result["plan"] is not None
        plan = result["plan"]
        assert plan.runtime_profile_id == profile.profile_id.value
        assert plan.runtime_provider == "fixture-vllm"
        receipt = platform.deployment.acquire_normal(
            str(plan.plan_id), platform.hosts.current, {}
        )
        assert receipt.state.value == "stored"
        decision = platform.admission.reserve(
            str(plan.plan_id), platform.hosts.current, {}
        )
        assert decision.verdict.value == "admitted"
        assert decision.reservation is not None
        instance = platform.instances.create(
            platform.inventory.artifacts()[0], decision.reservation
        )
        assert instance.runtime.value == "fixture-vllm"
        started = platform.instances.start(
            instance.instance_id,
            ledger_health=platform.resources.summary(
                platform.capacity.compute(platform.hosts.current, {})
            ).health,
        )
        try:
            assert started.observed_state.value == "running"
        finally:
            platform.instances.stop(instance.instance_id)

    def test_store_only_without_runtime(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        receipt = platform.deployment.acquire_store_only(
            "tinyllama-1.1b-chat-q4", platform.hosts.current, {}
        )
        artifact = platform.inventory.get(receipt.artifact_id)
        assert artifact is not None
        view = platform.deployment.currently_runnable(artifact, platform.hosts.current)
        assert view["stored"] is True
        assert view["currently_runnable"] is False
        assert view["reason"] == "no_verified_compatible_runtime"
        with pytest.raises(NotFoundError, match="deployment plan"):
            platform.admission.reserve("missing", platform.hosts.current, {})

    def test_stale_plan_rejects_normal_acquire(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        profile = _verify(platform)
        result = platform.deployment.recommend(platform.hosts.current, {})
        plan = result["plan"]
        stale = replace(profile, status=VerificationStatus.STALE)
        platform.runtime_setup.evidence.put_profile(stale)
        with pytest.raises(PreconditionFailedError, match="verified"):
            platform.deployment.acquire_normal(
                str(plan.plan_id), platform.hosts.current, {}
            )

    def test_upgrade_invalidates_fingerprint(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        profile = _verify(platform)
        installation = platform.runtime_setup.evidence.get_installation(
            profile.installation_id.value
        )
        assert installation is not None
        upgraded = replace(installation, runtime_version="fixture-9.9.9")
        platform.runtime_setup.evidence.put_installation(upgraded)
        later = platform.runtime_setup.profiles(platform.hosts.current)
        found = next(item for item in later if item.profile_id == profile.profile_id)
        assert found.status is VerificationStatus.STALE
        current = verification_fingerprint(upgraded, platform.hosts.current)
        assert current != profile.verification_fingerprint


class TestApiModes:
    def test_acquire_requires_explicit_mode(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        missing = _call(
            platform,
            "/models/acquire",
            method=Method.POST,
            query={"candidate": "tinyllama-1.1b-chat-q4"},
        )
        assert missing.status == 400

    def test_store_only_api(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        acquired = _call(
            platform,
            "/models/acquire",
            method=Method.POST,
            query={"candidate": "tinyllama-1.1b-chat-q4", "mode": "store_only"},
        )
        assert acquired.status == 200


class TestCapacityStaleAndFallback:
    def test_eligible_but_insufficient_current_capacity(self, tmp_path: Path) -> None:
        from kultrun.planning.contracts import CapacityCommitments, CapacityFitClass

        platform = _platform(tmp_path)
        profile = _verify(platform)
        snapshot = platform.deployment.snapshot(profile)
        model = platform.models.acquirable("qwen2.5-7b-instruct-awq")
        assert model is not None
        verdict = RuntimeEligibilityEvaluator().evaluate(model.metadata, snapshot)
        assert verdict.verdict is EligibilityVerdict.ELIGIBLE
        envelope = platform.capacity.compute(platform.hosts.current, {})
        recommendation = platform.selection.recommend(
            envelope=envelope,
            candidates=(model,),
            available_runtimes=(profile.runtime_family.value,),
            commitments=CapacityCommitments(reserved_vram_bytes=10**18),
            runtime=profile.runtime_family.value,
        )
        assert recommendation.primary is None
        assert recommendation.evaluations
        assert (
            recommendation.evaluations[0].capacity_fit
            is CapacityFitClass.EXCEEDS_SAFE
        )

    def test_stale_profile_blocks_start(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        profile = _verify(platform)
        result = platform.deployment.recommend(platform.hosts.current, {})
        plan = result["plan"]
        assert plan is not None
        platform.deployment.acquire_normal(
            str(plan.plan_id), platform.hosts.current, {}
        )
        decision = platform.admission.reserve(
            str(plan.plan_id), platform.hosts.current, {}
        )
        assert decision.reservation is not None
        artifact = platform.inventory.artifacts()[0]
        instance = platform.instances.create(artifact, decision.reservation)
        stale = replace(profile, status=VerificationStatus.STALE)
        platform.runtime_setup.evidence.put_profile(stale)
        started = _call(
            platform,
            "/inference/instances/start",
            method=Method.POST,
            query={"instance_id": instance.instance_id.value},
        )
        assert started.status == 412
        seen = platform.instances.get(instance.instance_id)
        assert seen is not None
        assert seen.observed_state.value == "created"

    def test_launch_failure_does_not_select_another_runtime(
        self, tmp_path: Path
    ) -> None:
        from kultrun.inference.contracts import ObservedState
        from kultrun.kernel.ids import Name
        from kultrun.resource.contracts import ReservationState

        platform = _platform(tmp_path)
        profile = _verify(platform)
        result = platform.deployment.recommend(platform.hosts.current, {})
        plan = result["plan"]
        assert plan is not None
        platform.deployment.acquire_normal(
            str(plan.plan_id), platform.hosts.current, {}
        )
        decision = platform.admission.reserve(
            str(plan.plan_id), platform.hosts.current, {}
        )
        assert decision.reservation is not None
        artifact = platform.inventory.artifacts()[0]
        instance = platform.instances.create(
            artifact, decision.reservation, runtime=Name("vllm")
        )
        started = platform.instances.start(
            instance.instance_id,
            ledger_health=platform.resources.summary(
                platform.capacity.compute(platform.hosts.current, {})
            ).health,
        )
        assert started.observed_state is ObservedState.FAILED
        assert started.runtime.value == "vllm"
        held = platform.resources.get(decision.reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE
        del profile


def _obj(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value

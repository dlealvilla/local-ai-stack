"""Tell whether a stored plan still matches its inputs. Do not edit it."""

from __future__ import annotations

from collections.abc import Callable

from machi.kernel.unresolved import is_resolved
from machi.plan.compose import PlanInputs, ServingDraft, compose_plan
from machi.plan.contracts import DeploymentConfiguration, PlanFailure, RuntimeRecipe
from machi.plan.policy import POLICY_VERSION


def assess_plan(
    configuration: DeploymentConfiguration,
    inputs: PlanInputs,
    build_recipe: Callable[[ServingDraft], RuntimeRecipe],
) -> PlanFailure:
    """Return none when the plan is still the one these inputs would produce."""
    if configuration.policy_version != POLICY_VERSION:
        return PlanFailure.STALE_POLICY_INPUT
    decision = compose_plan(inputs, build_recipe)
    if decision.failure is not PlanFailure.NONE:
        return _refusal_as_stale(configuration, inputs, decision.failure)
    current = decision.configuration
    if not is_resolved(current):
        return decision.failure
    if current.fingerprint == configuration.fingerprint:
        return PlanFailure.NONE
    if (
        current.artifact_id != configuration.artifact_id
        or current.immutable_revision != configuration.immutable_revision
        or current.model_id != configuration.model_id
    ):
        return PlanFailure.STALE_MODEL_INPUT
    if (
        current.generation_id != configuration.generation_id
        or current.foundation_id != configuration.foundation_id
    ):
        return PlanFailure.STALE_FOUNDATION_INPUT
    if current.capacity_evidence_id != configuration.capacity_evidence_id:
        return PlanFailure.STALE_CAPACITY_INPUT
    return PlanFailure.STALE_PREFERENCE_INPUT


def _refusal_as_stale(
    configuration: DeploymentConfiguration,
    inputs: PlanInputs,
    failure: PlanFailure,
) -> PlanFailure:
    artifact = inputs.artifact
    if artifact is None or artifact.artifact_id != configuration.artifact_id:
        return PlanFailure.STALE_MODEL_INPUT
    if artifact.immutable_revision != configuration.immutable_revision:
        return PlanFailure.STALE_MODEL_INPUT
    generation = inputs.foundation.generation_id
    if not isinstance(generation, str) or generation != configuration.generation_id:
        return PlanFailure.STALE_FOUNDATION_INPUT
    if inputs.envelope.evidence_id != configuration.capacity_evidence_id:
        return PlanFailure.STALE_CAPACITY_INPUT
    if failure is PlanFailure.MODEL_ARTIFACT_INTEGRITY_FAILED:
        return failure
    return failure

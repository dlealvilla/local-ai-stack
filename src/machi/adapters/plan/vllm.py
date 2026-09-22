"""Map a serving draft onto bounded vLLM settings. Does not import vLLM."""

from __future__ import annotations

from machi.plan.compose import ServingDraft
from machi.plan.contracts import PlanProvenance, PlanSetting, RuntimeRecipe
from machi.plan.policy import MEMORY_UTILIZATION, RECIPE_SCHEMA


def build_vllm_recipe(draft: ServingDraft) -> RuntimeRecipe:
    """Build the recipe from numbers Plan already chose."""
    return vllm_recipe(
        context=draft.context,
        concurrency=draft.concurrency,
        dtype=draft.definition.dtype
        if isinstance(draft.definition.dtype, str)
        else "undetermined",
        quantization=draft.definition.quantization.value,
        artifact_id=draft.artifact.artifact_id,
        context_provenance=draft.context_provenance,
        concurrency_provenance=draft.concurrency_provenance,
    )


def vllm_recipe(
    *,
    context: int,
    concurrency: int,
    dtype: str,
    quantization: str,
    artifact_id: str,
    context_provenance: PlanProvenance,
    concurrency_provenance: PlanProvenance,
) -> RuntimeRecipe:
    """One accelerator, remote code refused, artifact cited by id."""
    settings = (
        _setting("parallelism", "1", PlanProvenance.PRODUCT_DEFAULT, "one accelerator"),
        _setting(
            "tensor_parallel_size",
            "1",
            PlanProvenance.PRODUCT_DEFAULT,
            "vLLM name for parallelism",
        ),
        _setting("context_length", str(context), context_provenance, "serving context"),
        _setting(
            "max_model_len",
            str(context),
            context_provenance,
            "vLLM name for serving context",
        ),
        _setting(
            "concurrency",
            str(concurrency),
            concurrency_provenance,
            "in-flight sequences",
        ),
        _setting(
            "max_num_seqs",
            str(concurrency),
            concurrency_provenance,
            "vLLM name for concurrency",
        ),
        _setting(
            "memory_utilization",
            MEMORY_UTILIZATION,
            PlanProvenance.PRODUCT_DEFAULT,
            "fraction of the admitted safe budget",
        ),
        _setting(
            "gpu_memory_utilization",
            MEMORY_UTILIZATION,
            PlanProvenance.PRODUCT_DEFAULT,
            "vLLM name for that fraction",
        ),
        _setting("dtype", dtype, PlanProvenance.MODEL_METADATA, "artifact dtype"),
        _setting(
            "quantization",
            quantization,
            PlanProvenance.MODEL_METADATA,
            "published quantization",
        ),
        _setting(
            "remote_code",
            "refuse",
            PlanProvenance.PRODUCT_DEFAULT,
            "repository code stays refused",
        ),
        _setting(
            "trust_remote_code",
            "false",
            PlanProvenance.PRODUCT_DEFAULT,
            "vLLM name for the refusal",
        ),
        _setting(
            "artifact_reference",
            artifact_id,
            PlanProvenance.DERIVED,
            "warehouse artifact id, not a cache path",
        ),
    )
    return RuntimeRecipe(
        provider="vllm",
        schema_version=RECIPE_SCHEMA,
        settings=settings,
    )


def _setting(
    name: str,
    value: str,
    provenance: PlanProvenance,
    reason: str,
) -> PlanSetting:
    return PlanSetting(name=name, value=value, provenance=provenance, reason=reason)

"""llmfit plan adapter. Requirement only — never capacity authority.

Invokes `llmfit plan --json`. Host fit flags, recommend, and hardware
detection are ignored. `*_gb` fields are treated as GiB (2**30); see
captured fixtures. MIT-licensed optional extra, pinned at 1.1.14.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from kultrun.adapters.estimators.common import unavailable_requirement
from kultrun.adapters.estimators.vllm_serving import (
    compose_vllm_vram,
    is_vllm_runtime,
)
from kultrun.evidence.contracts import Confidence
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.contracts import (
    EstimatorFailureReason,
    MemoryPlacement,
    ModelEstimationRequest,
    ModelRequirement,
)

IDENTITY = Name("llmfit")
TESTED_VERSION = "1.1.14"
GiB = 1024**3
PLAN_TIMEOUT_SECONDS = 60
MAX_PLAN_OUTPUT_BYTES = 1_048_576


def _installed_version() -> str:
    try:
        return importlib_metadata.version("llmfit")
    except importlib_metadata.PackageNotFoundError:
        return TESTED_VERSION


#: Kultrun quantization → llmfit --quant. Unmapped → unsupported.
_QUANT = {
    "q4_k": "Q4_K_M",
    "q4_k_m": "Q4_K_M",
    "q5_k": "Q5_K_M",
    "q5_k_m": "Q5_K_M",
    "q8": "Q8_0",
    "q8_0": "Q8_0",
    "awq": "AWQ-4bit",
    "awq_4bit": "AWQ-4bit",
    "fp16": "F16",
    "f16": "F16",
    "bf16": "BF16",
    "gptq-int4": "GPTQ-Int4",
}

PlanFn = Callable[[str, int, str], dict[str, Any]]


class LlmfitRequirementEstimator:
    """Normalize llmfit plan JSON into ModelRequirement."""

    def __init__(
        self,
        *,
        plan: PlanFn | None = None,
        version: str | None = None,
    ) -> None:
        self._plan = plan if plan is not None else _subprocess_plan
        self._version = version if version is not None else _installed_version()

    @property
    def identity(self) -> Name:
        return IDENTITY

    @property
    def version(self) -> str:
        return self._version

    def invoke_plan(self, source_ref: str, context: int, quant: str) -> dict[str, Any]:
        """Return the provider JSON. Not a ModelRequirement and not capacity."""
        return self._plan(source_ref, context, quant)

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        if request.tensor_parallel != 1 or request.batch_size != 1:
            return self._fail(
                request,
                "unsupported",
                "v0 is single-device batch-1",
                EstimatorFailureReason.UNSUPPORTED_CONFIGURATION,
            )
        if request.offload_allowed:
            return self._fail(
                request,
                "unsupported",
                "cpu offload is not assumed",
                EstimatorFailureReason.UNSUPPORTED_CONFIGURATION,
            )
        if not is_resolved(request.quantization):
            return self._fail(
                request,
                "unsupported",
                "quantization is required",
                EstimatorFailureReason.UNSUPPORTED_CONFIGURATION,
            )
        if not is_resolved(request.context_tokens):
            return self._fail(
                request,
                "unsupported",
                "context is required",
                EstimatorFailureReason.UNSUPPORTED_CONFIGURATION,
            )
        quant = request.quantization
        context = request.context_tokens
        mapped = _QUANT.get(_norm(quant))
        if mapped is None:
            return self._fail(
                request,
                "unsupported",
                f"quantization {quant!r} has no llmfit mapping",
                EstimatorFailureReason.UNSUPPORTED_CONFIGURATION,
            )
        try:
            payload = self._plan(request.source_ref, context, mapped)
        except FileNotFoundError:
            return self._fail(
                request,
                "provider-unavailable",
                "llmfit executable not found",
                EstimatorFailureReason.PROVIDER_UNAVAILABLE,
            )
        except subprocess.TimeoutExpired:
            return self._fail(
                request,
                "provider-unavailable",
                "llmfit plan timed out",
                EstimatorFailureReason.PROVIDER_TIMEOUT,
            )
        except json.JSONDecodeError:
            return self._fail(
                request,
                "provider-unavailable",
                "llmfit plan was not valid JSON",
                EstimatorFailureReason.INVALID_PROVIDER_OUTPUT,
            )
        except _LlmfitPlanError as error:
            return self._fail(
                request,
                "provider-unavailable",
                error.detail,
                error.reason,
            )
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            return self._fail(
                request,
                "provider-unavailable",
                "llmfit plan failed",
                EstimatorFailureReason.PROVIDER_EXECUTION_ERROR,
            )
        returned_quant = str(payload.get("quantization") or "")
        if returned_quant != mapped:
            return self._fail(
                request,
                "unsupported",
                f"llmfit substituted quantization {returned_quant!r}",
                EstimatorFailureReason.ASSUMPTION_MISMATCH,
            )
        returned_context = payload.get("context")
        if returned_context != context:
            return self._fail(
                request,
                "unsupported",
                "llmfit substituted context",
                EstimatorFailureReason.ASSUMPTION_MISMATCH,
            )
        returned_name = str(payload.get("model_name") or "")
        if returned_name and returned_name != request.source_ref:
            return self._fail(
                request,
                "unsupported",
                f"llmfit resolved a different model {returned_name!r}",
                EstimatorFailureReason.ASSUMPTION_MISMATCH,
            )
        minimum = payload.get("minimum") or {}
        if request.placement is MemoryPlacement.CPU_ONLY:
            path = _run_path(payload, "cpu_only") or {}
            ram_gb = (path.get("minimum") or {}).get("ram_gb")
            vram_gb = None
        else:
            ram_gb = minimum.get("ram_gb")
            vram_gb = minimum.get("vram_gb")
        kv_gb = _kv_gb(payload)
        vram_bytes = _bytes(vram_gb)
        kv_bytes = _bytes(kv_gb)
        per_token: Maybe[int] = NOT_PROVIDED
        if isinstance(kv_bytes, int) and context:
            per_token = kv_bytes // context
        weights: Maybe[int] = NOT_PROVIDED
        if isinstance(vram_bytes, int):
            weights = vram_bytes
        assumptions: tuple[str, ...] = (
            "llmfit plan minimum; host fit flags ignored",
            "gb fields treated as GiB",
            "no cpu offload",
            "llmfit minimum.vram is base-model evidence, not a serving total",
        )
        estimated = vram_bytes
        kv_total: Maybe[int] = kv_bytes
        safety: Maybe[int] = NOT_PROVIDED
        if (
            is_vllm_runtime(request.runtime)
            and request.placement is MemoryPlacement.DISCRETE_GPU
        ):
            composed = compose_vllm_vram(
                weights_bytes=weights,
                kv_per_token=per_token,
                context_tokens=context,
                batch_size=request.batch_size,
                overhead_bytes=0,
                activation_bytes=NOT_PROVIDED,
            )
            estimated = composed.total_bytes
            kv_total = composed.kv_cache_bytes
            safety = composed.safety_allowance_bytes
            assumptions = (
                *assumptions,
                *composed.assumptions,
                "vLLM serving refinement after llmfit plan components",
                "engine workspace is Kultrun-owned normalization, "
                "not a second estimator",
            )
        return ModelRequirement(
            model_id=request.model_id,
            confidence=Confidence.MEDIUM,
            storage_bytes=NOT_PROVIDED,
            peak_additional_bytes=NOT_PROVIDED,
            vram_weights_bytes=weights,
            vram_kv_bytes_per_token=per_token,
            vram_overhead_bytes=0,
            ram_bytes=_bytes(ram_gb),
            unified_memory_bytes=NOT_PROVIDED,
            activation_bytes=NOT_PROVIDED,
            estimated_vram_bytes=estimated,
            assumed_context_tokens=context,
            supported_runtimes=(),
            estimation_method="llmfit-plan",
            estimator_provider=IDENTITY.value,
            estimator_version=self.version,
            assumptions=assumptions,
            measured=False,
            assumed_runtime=request.runtime,
            assumed_runtime_version=request.runtime_version,
            assumed_batch_size=request.batch_size,
            vram_kv_cache_bytes=kv_total,
            safety_allowance_bytes=safety,
        )

    def _fail(
        self,
        request: ModelEstimationRequest,
        method: str,
        reason: str,
        failure: EstimatorFailureReason,
    ) -> ModelRequirement:
        return unavailable_requirement(
            request,
            provider=IDENTITY.value,
            version=self.version,
            method=method,
            reason=reason,
            failure=failure,
        )


def build(
    *,
    plan: PlanFn | None = None,
    version: str | None = None,
) -> LlmfitRequirementEstimator:
    return LlmfitRequirementEstimator(plan=plan, version=version)


def fixture_plan(root: Path) -> PlanFn:
    """CI invoker: replay captured llmfit plan JSON. Not a product fallback."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    index: dict[tuple[str, int, str], Path] = {}
    for entry in manifest["entries"]:
        key = (entry["source_ref"], int(entry["context"]), entry["quantization"])
        index[key] = root / entry["file"]

    def plan(model: str, context: int, quant: str) -> dict[str, Any]:
        path = index.get((model, context, quant))
        if path is None or not path.is_file():
            raise FileNotFoundError(f"no captured llmfit plan for {model}")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("captured llmfit plan is not an object")
        return loaded

    return plan


class _LlmfitPlanError(Exception):
    """Typed subprocess failure. Detail is a short product reason, not stderr."""

    def __init__(self, reason: EstimatorFailureReason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def _subprocess_plan(model: str, context: int, quant: str) -> dict[str, Any]:
    binary = shutil.which("llmfit")
    if binary is None:
        raise FileNotFoundError("llmfit executable not found")
    try:
        completed = subprocess.run(
            [
                binary,
                "--no-dashboard",
                "plan",
                model,
                "--context",
                str(context),
                "--quant",
                quant,
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=PLAN_TIMEOUT_SECONDS,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        raise
    if completed.returncode != 0:
        raise _LlmfitPlanError(
            EstimatorFailureReason.PROVIDER_EXECUTION_ERROR,
            "llmfit plan failed",
        )
    stdout = completed.stdout or ""
    if len(stdout.encode("utf-8")) > MAX_PLAN_OUTPUT_BYTES:
        raise _LlmfitPlanError(
            EstimatorFailureReason.INVALID_PROVIDER_OUTPUT,
            "llmfit plan output exceeded bound",
        )
    loaded = json.loads(stdout)
    if not isinstance(loaded, dict):
        raise _LlmfitPlanError(
            EstimatorFailureReason.INVALID_PROVIDER_OUTPUT,
            "llmfit plan JSON is not an object",
        )
    return loaded


def detect_version() -> str | None:
    """Installed llmfit version, or None if the executable is absent."""
    binary = shutil.which("llmfit")
    if binary is None:
        return None
    completed = subprocess.run(
        [binary, "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        return None
    parts = completed.stdout.strip().split()
    return parts[-1] if parts else None


def _run_path(payload: dict[str, Any], name: str) -> dict[str, Any] | None:
    for item in payload.get("run_paths") or []:
        if isinstance(item, dict) and item.get("path") == name:
            return item
    return None


def _kv_gb(payload: dict[str, Any]) -> object:
    for item in payload.get("kv_alternatives") or []:
        if isinstance(item, dict) and item.get("kv_quant") == "fp16":
            return item.get("kv_cache_gb")
    return None


def _bytes(gb: object) -> Maybe[int]:
    if not isinstance(gb, (int, float)) or isinstance(gb, bool):
        return NOT_PROVIDED
    return round(float(gb) * GiB)


def _norm(value: str) -> str:
    return value.lower().replace("-", "_")

"""vLLM product runtime. Translates plan facts into a native launch recipe.

Does not import vLLM. Does not download models. Does not exec the process.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.errors import PreconditionFailedError, ValidationError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.runtime.contracts import (
    EligibilityReasonCode,
    RuntimeCapabilityProfile,
    RuntimeEligibilityStatus,
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeReadiness,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
)
from kultrun.runtime.eligibility import (
    CompatibilityDecision,
    ModelEligibilityFacts,
    declared_compatibility,
)
from kultrun.runtime.pins import VLLM_VERSION

IDENTITY = Name("vllm")
NATIVE = Name("native-process")
CONTAINER = Name("container-docker")
ENTRYPOINT = "vllm.entrypoints.openai.api_server"
LOOPBACK = "127.0.0.1"
_QUANTIZATION_FLAGS = frozenset({"awq", "gptq", "gptq-int4", "fp8"})
_OUTPUT_LIMIT_BYTES = 64 * 1024
_GRACE_PERIOD_SECONDS = 20.0
_HEALTH_TIMEOUT_SECONDS = 0.4
_READINESS_MISMATCH = "runtime_model_mismatch"


@dataclass(frozen=True, slots=True)
class VllmCompletion:
    """Adapter-owned translation of a vLLM completion. Not a domain contract."""

    text: str
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    runtime_id: str | None = None


class VllmRuntimeSupport:
    """Product vLLM adapter. Launch consumes an exact installation and artifact."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            runtime=self.identity,
            display_name="vLLM",
            executor_kind=NATIVE,
            capabilities=("declared-support", "native-openai-server"),
        )

    def support(self) -> RuntimeSupportDescriptor:
        return RuntimeSupportDescriptor(
            runtime=self.identity,
            display_name="vLLM",
            support_tier=RuntimeSupportTier.PRODUCT,
            production_candidate=True,
            compatible_executor_types=(NATIVE, CONTAINER),
            supported_os_families=("linux",),
            supported_architectures=("x86_64",),
            supported_accelerator_families=("nvidia",),
            required_features=(
                "process_execution",
                "structured_argv",
                "environment_variables",
            ),
            required_components=(Name("vllm"),),
            preferred_version=VLLM_VERSION,
            known_model_architectures=(
                "llama",
                "qwen2",
                "gpt2",
                "mistral",
                "mixtral",
                "gemma2",
                "phi3",
            ),
            known_formats=("safetensors",),
            known_quantizations=(
                "awq",
                "gptq",
                "gptq-int4",
                "fp16",
                "bf16",
                "fp32",
                "fp8",
            ),
            limitations=(
                "native-process single-GPU OpenAI server is the first serving path",
                "NVIDIA/CUDA-oriented product path",
                "container GPU exposure is unknown (K-33)",
                "streaming, cancellation, and crash recovery are not implemented",
                f"provisioning pin vllm=={VLLM_VERSION} is not engine proof",
            ),
            evidence=("stage-1.6L-native-vllm-inference",),
            confidence=Confidence.MEDIUM,
        )

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        if request is None or not _complete(request):
            raise ValidationError(
                "vLLM launch requires an exact interpreter, local model path, "
                "served-model identity, and loopback port",
                runtime=IDENTITY.value,
            )
        interpreter = _absolute_path(str(request.interpreter), "interpreter")
        model_path = _absolute_path(str(request.model_path), "model_path")
        served = str(request.served_model).strip()
        if not served or "\0" in served or served.startswith("-"):
            raise ValidationError(
                "served-model identity is not usable", served_model=served
            )
        if any(token in served for token in ("/", "\\", " ")):
            raise ValidationError(
                "served-model identity must not contain a path or flag",
                served_model=served,
            )
        bind = request.bind_address.strip() or LOOPBACK
        if bind not in {LOOPBACK, "localhost", "::1"} or bind == "0.0.0.0":
            raise ValidationError("vLLM may bind only to loopback", bind_address=bind)
        bind = LOOPBACK
        if not is_resolved(request.bind_port):
            raise ValidationError("vLLM launch requires an allocated loopback port")
        port = int(request.bind_port)
        if port < 1 or port > 65535:
            raise ValidationError("bind port is out of range", bind_port=port)
        arguments = [
            "-m",
            ENTRYPOINT,
            "--host",
            bind,
            "--port",
            str(port),
            "--model",
            str(model_path),
            "--served-model-name",
            served,
            "--no-enable-log-requests",
        ]
        if is_resolved(request.context_tokens):
            arguments.extend(["--max-model-len", str(int(request.context_tokens))])
        if is_resolved(request.concurrency):
            arguments.extend(["--max-num-seqs", str(int(request.concurrency))])
        quantization = _quantization_flag(request.quantization)
        if quantization is not None:
            arguments.extend(["--quantization", quantization])
        environment = [
            "PYTHONPATH=",
            "PYTHONUNBUFFERED=1",
            "HF_HUB_OFFLINE=1",
            "TRANSFORMERS_OFFLINE=1",
            "HF_HUB_DISABLE_TELEMETRY=1",
            "HF_HUB_DISABLE_IMPLICIT_TOKEN=1",
            "HF_TOKEN=",
            "HUGGING_FACE_HUB_TOKEN=",
            "DO_NOT_TRACK=1",
            "VLLM_NO_USAGE_STATS=1",
            "VLLM_USE_FLASHINFER_SAMPLER=0",
            "KULTRUN_GPU_MEMORY_SOURCE=runtime_default",
            (
                "KULTRUN_CONTEXT_SOURCE=plan"
                if is_resolved(request.context_tokens)
                else "KULTRUN_CONTEXT_SOURCE=runtime_default"
            ),
            (
                "KULTRUN_CONCURRENCY_SOURCE=plan"
                if is_resolved(request.concurrency)
                else "KULTRUN_CONCURRENCY_SOURCE=runtime_default"
            ),
        ]
        devices: tuple[int, ...] = ()
        if request.accelerator_index is not None:
            if request.accelerator_index < 0:
                raise ValidationError(
                    "accelerator index must be non-negative",
                    accelerator_index=request.accelerator_index,
                )
            environment.append(f"CUDA_VISIBLE_DEVICES={request.accelerator_index}")
            devices = (request.accelerator_index,)
        if is_resolved(request.installation_id):
            environment.append(
                f"KULTRUN_RUNTIME_INSTALLATION={request.installation_id}"
            )
        if is_resolved(request.runtime_version):
            environment.append(f"KULTRUN_RUNTIME_VERSION={request.runtime_version}")
        return RuntimeLaunchSpec(
            runtime=self.identity,
            profile=self.identity,
            executable=str(interpreter),
            arguments=tuple(arguments),
            environment=tuple(environment),
            output_limit_bytes=_OUTPUT_LIMIT_BYTES,
            grace_period_seconds=_GRACE_PERIOD_SECONDS,
            device_indexes=devices,
            network_bindings=(f"tcp:{bind}:{port}",),
        )

    def inspect_readiness(
        self,
        *,
        stdout: str,
        stderr: str,
        execution_alive: bool,
        bound_address: str | None = None,
        bound_port: int | None = None,
        expected_served_model: str | None = None,
    ) -> RuntimeReadiness:
        del stdout, stderr
        if not execution_alive:
            return RuntimeReadiness(ready=False, reason="execution is not alive")
        host = bound_address or LOOPBACK
        if bound_port is None:
            return RuntimeReadiness(
                ready=False,
                address=host,
                reason="bind port not allocated",
            )
        if not _health_ok(host, bound_port):
            return RuntimeReadiness(
                ready=False,
                address=host,
                port=bound_port,
                reason="health probe failed",
            )
        reported = _listed_models(host, bound_port)
        if reported is None:
            return RuntimeReadiness(
                ready=False,
                address=host,
                port=bound_port,
                reason="model list probe failed",
            )
        if expected_served_model and expected_served_model not in reported:
            return RuntimeReadiness(
                ready=False,
                address=host,
                port=bound_port,
                reason=_READINESS_MISMATCH,
                served_models=tuple(reported),
            )
        return RuntimeReadiness(
            ready=True,
            address=host,
            port=bound_port,
            reason="health and served-model identity verified",
            served_models=tuple(reported),
        )

    def complete(
        self,
        *,
        address: str,
        port: int,
        served_model: str,
        prompt: str,
        max_output_tokens: int,
        temperature: float,
        timeout_seconds: float,
    ) -> VllmCompletion:
        """Translate a generic generation into vLLM /v1/completions."""
        url = f"http://{address}:{port}/v1/completions"
        payload = {
            "model": served_model,
            "prompt": prompt,
            "max_tokens": max_output_tokens,
            "temperature": temperature,
            "stream": False,
        }
        try:
            status, body = _http_json(url, timeout_seconds, payload=payload)
        except TimeoutError as error:
            raise PreconditionFailedError(
                "inference timed out",
                reason="inference_timeout",
            ) from error
        except urllib.error.HTTPError as error:
            raise PreconditionFailedError(
                "runtime rejected the inference request",
                reason="inference_runtime_error",
                status=error.code,
            ) from error
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise PreconditionFailedError(
                    "inference timed out",
                    reason="inference_timeout",
                ) from error
            raise PreconditionFailedError(
                "runtime inference request failed",
                reason="inference_runtime_error",
            ) from error
        except OSError as error:
            if "timed out" in str(error).lower():
                raise PreconditionFailedError(
                    "inference timed out",
                    reason="inference_timeout",
                ) from error
            raise PreconditionFailedError(
                "runtime inference request failed",
                reason="inference_runtime_error",
            ) from error
        if status >= 400:
            raise PreconditionFailedError(
                "runtime rejected the inference request",
                reason="inference_runtime_error",
                status=status,
            )
        return _parse_completion(body, served_model)


def _complete(request: RuntimeLaunchRequest) -> bool:
    return (
        is_resolved(request.interpreter)
        and is_resolved(request.model_path)
        and is_resolved(request.served_model)
        and is_resolved(request.bind_port)
        and bool(str(request.interpreter).strip())
        and bool(str(request.model_path).strip())
        and bool(str(request.served_model).strip())
    )


def _absolute_path(raw: str, what: str) -> Path:
    if not raw.strip() or "\0" in raw:
        raise ValidationError(f"{what} is not a usable path")
    path = Path(raw)
    if not path.is_absolute():
        raise ValidationError(f"{what} must be an absolute path", path=raw)
    if any(part == ".." for part in path.parts):
        raise ValidationError(f"{what} must not contain '..'", path=raw)
    return path


def _quantization_flag(value: object) -> str | None:
    if not is_resolved(value) or value is None:
        return None
    token = str(value).strip().lower()
    if token in {"", "fp16", "bf16", "fp32"}:
        return None
    if token not in _QUANTIZATION_FLAGS:
        return None
    return "gptq" if token == "gptq-int4" else token


def _health_ok(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/health"
    try:
        status, _body = _http_json(url, _HEALTH_TIMEOUT_SECONDS)
    except (TimeoutError, urllib.error.URLError, OSError, ValueError):
        return False
    return status < 400


def _listed_models(host: str, port: int) -> list[str] | None:
    url = f"http://{host}:{port}/v1/models"
    try:
        status, body = _http_json(url, _HEALTH_TIMEOUT_SECONDS)
    except (TimeoutError, urllib.error.URLError, OSError, ValueError):
        return None
    if status >= 400 or not isinstance(body, dict):
        return None
    rows = body.get("data")
    if not isinstance(rows, list):
        return None
    names: list[str] = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            names.append(row["id"])
    return names


def _http_json(
    url: str, timeout: float, *, payload: dict[str, Any] | None = None
) -> tuple[int, object]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    method = "POST" if data else "GET"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = int(getattr(response, "status", 200))
    except TimeoutError:
        raise
    except urllib.error.HTTPError as error:
        if error.code >= 400:
            raise
        raw = error.read()
        status = int(error.code)
    text = raw.decode("utf-8") if raw else ""
    if not text.strip():
        return status, {}
    try:
        parsed: object = json.loads(text)
    except ValueError:
        return status, text
    return status, parsed


def _parse_completion(body: object, served_model: str) -> VllmCompletion:
    if not isinstance(body, dict):
        raise PreconditionFailedError(
            "runtime returned a malformed inference response",
            reason="inference_invalid_response",
        )
    reported = body.get("model")
    if isinstance(reported, str) and reported and reported != served_model:
        raise PreconditionFailedError(
            "runtime served a different model than planned",
            reason="runtime_model_mismatch",
            served=reported,
            expected=served_model,
        )
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise PreconditionFailedError(
            "runtime returned no completion choices",
            reason="inference_invalid_response",
        )
    first = choices[0]
    if not isinstance(first, dict):
        raise PreconditionFailedError(
            "runtime returned a malformed completion choice",
            reason="inference_invalid_response",
        )
    text = first.get("text")
    if not isinstance(text, str):
        raise PreconditionFailedError(
            "runtime returned no generated text",
            reason="inference_invalid_response",
        )
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    request_id = body.get("id")
    finish = first.get("finish_reason")
    return VllmCompletion(
        text=text,
        finish_reason=finish if isinstance(finish, str) else None,
        input_tokens=_optional_int(usage.get("prompt_tokens") if usage else None),
        output_tokens=_optional_int(usage.get("completion_tokens") if usage else None),
        runtime_id=request_id if isinstance(request_id, str) else None,
    )


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


_GGUF_QUANTIZATIONS = frozenset(
    {
        "q4_k",
        "q4_k_m",
        "q4_k_s",
        "q5_k",
        "q5_k_m",
        "q5_k_s",
        "q8_0",
        "q4_0",
        "q5_0",
        "q6_k",
        "q3_k",
        "q2_k",
        "gguf",
    }
)


class VllmModelCompatibility:
    """vLLM 0.28.0 compatibility. Capability metadata, not a model-name list."""

    @property
    def runtime(self) -> Name:
        return IDENTITY

    def evaluate(
        self,
        model: ModelEligibilityFacts,
        descriptor: RuntimeSupportDescriptor,
        profile: RuntimeCapabilityProfile,
    ) -> CompatibilityDecision:
        decision = declared_compatibility(model, descriptor, profile)
        quantization = model.quantization
        token = quantization.strip().lower() if isinstance(quantization, str) else ""
        if token not in _GGUF_QUANTIZATIONS:
            return decision
        codes = tuple(
            dict.fromkeys(
                (*decision.reason_codes, EligibilityReasonCode.UNSUPPORTED_QUANTIZATION)
            )
        )
        notes = tuple(
            dict.fromkeys((*decision.reasons, f"quantization {token} is GGUF-style"))
        )
        return CompatibilityDecision(RuntimeEligibilityStatus.BLOCKED, codes, notes)

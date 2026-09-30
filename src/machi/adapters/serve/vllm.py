"""vLLM serving commands and checks. The generic service does not see argv."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from machi.adapters.foundation.process import NativeProcessRunner, SpawnedProcess
from machi.kernel.clock import Clock
from machi.serve.native import NativeProcessEvidence
from machi.serve.policy import BIND_SCOPE
from machi.serve.ports import InferResult, LaunchRequest

_LOOPBACK = "127.0.0.1"
_PROMPT = "machi-serve-proof"
_MODULE = "vllm.entrypoints.openai.api_server"
# vLLM 0.18 documents the hermes parser for these families.
_HERMES_PREFIXES = ("Qwen/Qwen2.5-", "Qwen/QwQ-")


def documented_tool_parser(repository: str) -> str:
    """Return a verified vLLM 0.18 parser, or empty when unsupported."""
    if repository.startswith(_HERMES_PREFIXES):
        return "hermes"
    return ""


class VllmServeProvider:
    """One native vLLM process. Remote code is never enabled."""

    provider_name = "vllm"
    executor_kind = "native_process"

    def __init__(self, runner: NativeProcessRunner, clock: Clock) -> None:
        self._runner = runner
        self._clock = clock
        self._spawned: dict[str, SpawnedProcess] = {}

    def launch(self, request: LaunchRequest) -> NativeProcessEvidence:
        argv = vllm_argv(
            python_path=request.python_path,
            model_path=request.model_path,
            artifact_id=request.artifact_id,
            port=request.port,
            settings=dict(request.settings),
        )
        spawned = self._runner.spawn(
            argv,
            cwd=request.cwd,
            env=None,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
        )
        self._spawned[request.evidence_id] = spawned
        return _evidence(request, spawned, self._clock.now())

    def ready(self, evidence: NativeProcessEvidence) -> bool:
        return _status(_url(evidence.port, "/health"), timeout=2) == 200

    def infer(self, evidence: NativeProcessEvidence, artifact_id: str) -> InferResult:
        body = json.dumps(
            {"model": artifact_id, "prompt": _PROMPT, "max_tokens": 8}
        ).encode()
        request = urllib.request.Request(
            _url(evidence.port, "/v1/completions"),
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                payload = response.read()
        except urllib.error.HTTPError as exc:
            return InferResult(exc.code, False, None)
        except (urllib.error.URLError, TimeoutError, OSError):
            return InferResult(0, False, None)
        return _parsed(status, payload)

    def identity_ok(self, evidence: NativeProcessEvidence) -> bool:
        return self._runner.view(_spawned(evidence, self._spawned)).identity_ok

    def alive(self, evidence: NativeProcessEvidence) -> bool:
        return self._runner.view(_spawned(evidence, self._spawned)).alive

    def stop(self, evidence: NativeProcessEvidence, *, grace_seconds: float) -> bool:
        view = self._runner.terminate(
            _spawned(evidence, self._spawned), grace_seconds=grace_seconds
        )
        return not view.alive and view.identity_ok

    def returncode(self, evidence: NativeProcessEvidence) -> int | None:
        return self._runner.view(_spawned(evidence, self._spawned)).returncode


def vllm_argv(
    *,
    python_path: str,
    model_path: str,
    artifact_id: str,
    port: int,
    settings: dict[str, str],
) -> list[str]:
    """Map planned settings onto the pinned vLLM module. Omit empty flags.

    The OpenAI model field is the artifact id. The warehouse path stays
    on ``--model`` and is not the name the inference request sends.
    """
    if settings.get("trust_remote_code") not in (None, "false"):
        raise ValueError("remote code is refused")
    argv = [
        python_path,
        "-m",
        _MODULE,
        "--model",
        model_path,
        "--served-model-name",
        artifact_id,
        "--host",
        _LOOPBACK,
        "--port",
        str(port),
        "--tensor-parallel-size",
        settings.get("tensor_parallel_size", "1"),
    ]
    context = settings.get("max_model_len")
    if context:
        argv.extend(["--max-model-len", context])
    sequences = settings.get("max_num_seqs")
    if sequences:
        argv.extend(["--max-num-seqs", sequences])
    utilization = settings.get("gpu_memory_utilization")
    if utilization:
        argv.extend(["--gpu-memory-utilization", utilization])
    dtype = settings.get("dtype", "")
    if dtype and dtype != "undetermined":
        argv.extend(["--dtype", dtype])
    quantization = settings.get("quantization", "none")
    if quantization and quantization != "none":
        argv.extend(["--quantization", quantization])
    parser = documented_tool_parser(settings.get("source_repository", ""))
    if parser == "hermes":
        argv.extend(["--enable-auto-tool-choice", "--tool-call-parser", "hermes"])
    elif parser:
        raise ValueError("tool parser is not verified for this runtime")
    return argv


def _evidence(
    request: LaunchRequest, spawned: SpawnedProcess, started_at: datetime
) -> NativeProcessEvidence:
    return NativeProcessEvidence(
        evidence_id=request.evidence_id,
        instance_id=request.instance_id,
        pid=spawned.pid,
        process_stamp=spawned.process_stamp,
        identity_token=spawned.identity_token,
        argv_fingerprint=spawned.argv_fingerprint,
        python_basename=Path(request.python_path).name,
        bind_scope=BIND_SCOPE,
        port=request.port,
        started_at=started_at,
    )


def _spawned(
    evidence: NativeProcessEvidence, remembered: dict[str, SpawnedProcess]
) -> SpawnedProcess:
    found = remembered.get(evidence.evidence_id)
    if found is not None:
        return found
    return SpawnedProcess(
        pid=evidence.pid,
        process_stamp=evidence.process_stamp,
        identity_token=evidence.identity_token,
        argv_fingerprint=evidence.argv_fingerprint,
    )


def _url(port: int, path: str) -> str:
    return f"http://{_LOOPBACK}:{port}{path}"


def _status(url: str, *, timeout: float) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def _parsed(status: int, payload: bytes) -> InferResult:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return InferResult(status, False, None)
    if not isinstance(document, dict):
        return InferResult(status, False, None)
    choices = document.get("choices")
    valid = isinstance(choices, list) and len(choices) > 0
    usage = document.get("usage")
    tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
    if not isinstance(tokens, int):
        tokens = None
    return InferResult(status, valid and status == 200, tokens)

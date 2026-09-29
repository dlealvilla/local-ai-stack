"""Send one operator prompt to an already authorised runtime.

The prompt and response stay in the return value. This module does not
journal them and does not choose which runtime is current.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from machi.adapters.rukan.read import load_records
from machi.adapters.rukan.tokens import ollama_usage, openai_usage
from machi.serve.native import NativeProcessEvidence
from machi.serve.provider import ProviderServingInstance

_LOOPBACK = "127.0.0.1"


@dataclass(frozen=True, slots=True)
class Completion:
    """Operator-visible result. Not an InferenceProof and not a journal event."""

    outcome: str
    reason: str
    text: str
    completion_tokens: int | None
    provider: str
    instance_id: str
    model_identity: str
    input_tokens: int | None = None
    status_code: int = 0
    runtime_duration_ms: int | None = None


Completer = Callable[..., Completion]


def complete_openai(
    *,
    port: int,
    model: str,
    prompt: str,
    max_tokens: int,
    provider: str,
    instance_id: str,
) -> Completion:
    """One loopback completions call. The runtime was already authorised."""
    if port < 1 or port > 65535:
        return _failed(provider, instance_id, model, "runtime port is not local")
    body = json.dumps(
        {"model": model, "prompt": prompt, "max_tokens": max_tokens}
    ).encode()
    request = urllib.request.Request(
        f"http://{_LOOPBACK}:{port}/v1/completions",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _failed(
            provider, instance_id, model, "runtime refused the request", status_code=exc.code  # noqa: E501
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return _failed(provider, instance_id, model, "runtime did not answer")
    text, _ignored = _openai_text(payload)
    prompt_tokens, completion_tokens = openai_usage(payload)
    if text is None:
        return _failed(provider, instance_id, model, "runtime response was not text", status_code=status)  # noqa: E501
    return Completion(
        outcome="completed",
        reason="runtime returned text",
        text=text,
        completion_tokens=completion_tokens,
        provider=provider,
        instance_id=instance_id,
        model_identity=model,
        input_tokens=prompt_tokens,
        status_code=status,
    )


def complete_provider(
    *,
    base_url: str,
    name: str,
    prompt: str,
    max_tokens: int,
    context: int,
    provider: str,
    instance_id: str,
    model_identity: str,
) -> Completion:
    """One loopback provider generation. The catalog name is not chosen here."""
    if not base_url.startswith("http://127.0.0.1:"):
        return _failed(
            provider, instance_id, model_identity, "provider url is not loopback"
        )
    body = json.dumps(
        {
            "model": name,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "num_ctx": context},
        }
    ).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/generate",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _failed(
            provider,
            instance_id,
            model_identity,
            "provider refused the request",
            status_code=exc.code,
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return _failed(
            provider, instance_id, model_identity, "provider did not answer"
        )
    text = payload.get("response") if isinstance(payload, dict) else None
    prompt_tokens, completion_tokens, duration_ms = ollama_usage(payload)
    if not isinstance(text, str):
        return _failed(
            provider,
            instance_id,
            model_identity,
            "provider response was not text",
            status_code=status,
        )
    return Completion(
        outcome="completed",
        reason="provider returned text",
        text=text,
        completion_tokens=completion_tokens,
        provider=provider,
        instance_id=instance_id,
        model_identity=model_identity,
        input_tokens=prompt_tokens,
        status_code=status,
        runtime_duration_ms=duration_ms,
    )


def _openai_text(payload: object) -> tuple[str | None, int | None]:
    if not isinstance(payload, dict):
        return None, None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, None
    first = choices[0]
    if not isinstance(first, dict) or not isinstance(first.get("text"), str):
        return None, None
    usage = payload.get("usage")
    tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
    count = tokens if isinstance(tokens, int) and tokens >= 0 else None
    return first["text"], count


def store_completer(store_root: Path, provider_base: str) -> Completer:
    """Complete against the stored READY instance. The caller does not pick it."""

    def complete(
        *,
        provider: str,
        model_identity: str,
        instance_id: str,
        prompt: str,
        max_tokens: int,
    ) -> Completion:
        evidence = next(
            (
                item
                for item in load_records(store_root, NativeProcessEvidence)
                if isinstance(item, NativeProcessEvidence)
                and item.instance_id == instance_id
            ),
            None,
        )
        if isinstance(evidence, NativeProcessEvidence):
            return complete_openai(
                port=evidence.port,
                model=model_identity,
                prompt=prompt,
                max_tokens=max_tokens,
                provider=provider,
                instance_id=instance_id,
            )
        provider_instance = next(
            (
                item
                for item in load_records(store_root, ProviderServingInstance)
                if isinstance(item, ProviderServingInstance)
                and item.instance_id == instance_id
            ),
            None,
        )
        if not isinstance(provider_instance, ProviderServingInstance):
            return _failed(
                provider,
                instance_id,
                model_identity,
                "runtime endpoint is not recorded",
            )
        return complete_provider(
            base_url=provider_base,
            name=provider_instance.display_name,
            prompt=prompt,
            max_tokens=max_tokens,
            context=provider_instance.context_length,
            provider=provider,
            instance_id=instance_id,
            model_identity=model_identity,
        )

    return complete


def _failed(
    provider: str,
    instance_id: str,
    model_identity: str,
    reason: str,
    status_code: int = 0,
) -> Completion:
    return Completion(
        outcome="failed",
        reason=reason,
        text="",
        completion_tokens=None,
        provider=provider,
        instance_id=instance_id,
        model_identity=model_identity,
        status_code=status_code,
    )

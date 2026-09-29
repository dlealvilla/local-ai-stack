"""Read token counts a runtime already reported. Do not estimate."""

from __future__ import annotations


def openai_usage(payload: object) -> tuple[int | None, int | None]:
    """Input and output tokens from an OpenAI-compatible usage object."""
    if not isinstance(payload, dict):
        return None, None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None, None
    return _count(usage.get("prompt_tokens")), _count(usage.get("completion_tokens"))


def ollama_usage(payload: object) -> tuple[int | None, int | None, int | None]:
    """Input, output, and runtime duration from an Ollama generate payload."""
    if not isinstance(payload, dict):
        return None, None, None
    duration = _count(payload.get("total_duration"))
    millis = None if duration is None else duration // 1_000_000
    return (
        _count(payload.get("prompt_eval_count")),
        _count(payload.get("eval_count")),
        millis,
    )


def _count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value

"""Guardrails against accidental credential persistence.

This is not a complete DLP system. It rejects obvious secret field
names and redacts obvious secret-shaped assignments in text.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SECRET_FIELD_TOKENS = (
    "API_KEY",
    "TOKEN",
    "PASSWORD",
    "AUTHORIZATION",
    "COOKIE",
    "PRIVATE_KEY",
    "SECRET",
    "BEARER",
)

_ASSIGNMENT_RE = re.compile(
    r"(?i)(api[_-]?key|token|password|authorization|cookie|private[_-]?key|"
    r"secret|bearer|runpod_api_key)\s*[:=]\s*([^\s,;]+)"
)


class SecretRejectedError(ValueError):
    """Raised when a mapping would persist a secret-looking field."""


def _normalize(name: str) -> str:
    return name.upper().replace("-", "_")


def field_looks_secret(name: str) -> bool:
    token = _normalize(name)
    if token in {"OWNERSHIP_TOKEN", "HOST_ID_STATE"}:
        return False
    return any(part in token for part in SECRET_FIELD_TOKENS)


def assert_mapping_safe(payload: Mapping[str, Any], *, path: str = "") -> None:
    for key, value in payload.items():
        here = f"{path}.{key}" if path else key
        if field_looks_secret(str(key)):
            raise SecretRejectedError(
                f"refusing to persist secret-looking field {here}"
            )
        if isinstance(value, Mapping):
            assert_mapping_safe(value, path=here)


def redact_text(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}=REDACTED"

    return _ASSIGNMENT_RE.sub(_replace, text)


def text_contains_secret_assignment(text: str) -> bool:
    return _ASSIGNMENT_RE.search(text) is not None


def assert_text_safe(text: str, *, what: str = "text") -> None:
    if text_contains_secret_assignment(text):
        raise SecretRejectedError(f"refusing to persist secret assignment in {what}")

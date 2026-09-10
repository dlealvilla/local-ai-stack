"""Hard content boundary for Domain A operational telemetry.

Prompts, responses, documents, RAG content, secrets, and raw HTTP bodies
must never become columns or values on these records.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, cast

from kultrun.kernel.schema import Contract

FORBIDDEN_FIELD_TOKENS: frozenset[str] = frozenset(
    {
        "prompt",
        "response",
        "conversation",
        "document",
        "documents",
        "rag",
        "rag_chunk",
        "rag_chunks",
        "chunk",
        "chunks",
        "retrieved_passage",
        "retrieved_passages",
        "source_payload",
        "source_code",
        "uploaded_file",
        "file_contents",
        "secret",
        "secrets",
        "api_key",
        "apikey",
        "password",
        "token_value",
        "request_body",
        "response_body",
        "raw_body",
        "http_body",
        "payload_text",
    }
)


def forbidden_field_names(contract_type: type[Contract]) -> tuple[str, ...]:
    """Field names that would store customer content or secrets."""
    found: list[str] = []
    for item in fields(cast("Any", contract_type)):
        name = item.name.lower()
        if name in FORBIDDEN_FIELD_TOKENS:
            found.append(item.name)
            continue
        for token in FORBIDDEN_FIELD_TOKENS:
            if token in name.split("_"):
                found.append(item.name)
                break
    return tuple(found)

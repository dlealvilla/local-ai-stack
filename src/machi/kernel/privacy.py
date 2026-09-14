"""Event privacy classification (MACHI 0.5.1).

Every EventRecord carries an explicit privacy posture. Classification is
not inferred from payload contents after the fact.

Customer content is local-only. Kernel M0 never emits it. Optional
vendor export (later) is disabled by default and must never become
required for local inference.
"""

from __future__ import annotations

from enum import StrEnum


class PrivacyClass(StrEnum):
    """How an event may be stored and, later, exported."""

    #: Build id, OS family, event type, outcome, byte bands.
    PUBLIC_OPS = "public_ops"
    #: Local analytics; vendor only if settings allow and an allow-list passes.
    OPERATIONAL = "operational"
    #: Local Admin, not vendor.
    RESTRICTED = "restricted"
    #: Local only, never export, never an EventRecord payload for inference text.
    CUSTOMER_CONTENT = "customer_content"


#: Keys that must not appear in a public_ops payload document.
FORBIDDEN_PUBLIC_OPS_KEYS = frozenset(
    {
        "prompt",
        "response",
        "completion",
        "messages",
        "file_bytes",
        "secret",
        "password",
        "token",
        "credential",
        "api_key",
        "authorization",
        "env",
        "environ",
    }
)

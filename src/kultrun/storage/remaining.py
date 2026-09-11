"""Current remaining vs durable characterization.

A storage mutation changes how much is left. It does not, by itself, make
an identity-matched empirical or specialist bound false.
"""

from __future__ import annotations

from dataclasses import replace

from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import StorageCapacityEvidence


def remaining_after_usage(
    evidence: StorageCapacityEvidence,
    managed_now: Maybe[int],
) -> StorageCapacityEvidence:
    """Subtract managed growth from the last characterized remaining.

    ``authorizing_available_bytes`` on the stored record is remaining at
    characterization time. ``accounted_managed_bytes`` is how many
    platform-managed bytes were already on the pool then. When the
    accounted snapshot is missing, all currently known managed bytes are
    subtracted so a recovered ``sce_`` cannot overstate headroom.
    """
    authorizing = evidence.authorizing_available_bytes
    if not is_resolved(authorizing):
        return evidence
    if not is_resolved(managed_now):
        return evidence
    accounted = evidence.accounted_managed_bytes
    if is_resolved(accounted):
        consumed = max(0, managed_now - accounted)
    else:
        consumed = max(0, managed_now)
    remaining = max(0, authorizing - consumed)
    if remaining == authorizing:
        return evidence
    reason = evidence.selected_reason
    note = "remaining after managed usage on the same storage identity"
    if note not in reason:
        reason = f"{reason}; {note}" if reason else note
    return replace(
        evidence,
        operational_available_bytes=remaining,
        authorizing_available_bytes=remaining,
        selected_reason=reason,
    )


def usage_or_unresolved(values: dict[str, Maybe[int]], mount: str) -> Maybe[int]:
    """Missing mounts are unknown, not zero."""
    if mount not in values:
        return NOT_PROVIDED
    return values[mount]

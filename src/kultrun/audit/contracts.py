"""What changed, who changed it, whether it was permitted, and how it ended.

`docs/PRODUCT_VISION.md` §105 requires that a deployment can eventually
answer who changed a setting, installed a model, modified a permission,
connected a knowledge source, started a service, what the Admin Agent
changed and what approval was given. No stage created this concept until
the module map found it missing; retrofitting it would mean revisiting
every mutating workflow already written.

**An audit event is not a usage event.** Usage describes AI consumption;
audit describes administrative change. They answer different questions for
different audiences and collapsing them loses both.

Two fields that look redundant are not. `decision` records whether the
action was permitted; `outcome` records whether it worked. A permitted
action can still fail, and — per `docs/ROADMAP.md` Part II §6 — an
interrupted operation is never a success.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.identity.contracts import SubjectId
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning


class AuditId(EntityId):
    """Identifies one audit entry."""

    prefix = "aud"


class AuditDecision(StrEnum):
    """Whether the action was permitted."""

    ALLOWED = "allowed"
    DENIED = "denied"


class AuditOutcome(StrEnum):
    """How the action ended, once permitted.

    ``CANCELLED`` is distinct from ``FAILED`` because a cancelled operation
    that cleaned up after itself is a different fact from one that broke.
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NOT_ATTEMPTED = "not_attempted"


@contract(kind="audit.event", version=1)
@dataclass(frozen=True, slots=True)
class AuditEvent(Contract):
    """One administrative change, recorded whether or not it was allowed."""

    audit_id: AuditId = meaning("platform-minted identity of this entry")
    occurred_at: dt.datetime = meaning("when the action was attempted, UTC")
    actor_id: SubjectId = meaning("who attempted it")
    action: Name = meaning(
        "what was attempted, as a stable dotted name such as 'model.install'"
    )
    target_kind: Name = meaning("what sort of thing was acted on")
    target_id: str = meaning("which one, by identifier")
    decision: AuditDecision = meaning("whether the action was permitted")
    outcome: AuditOutcome = meaning(
        "how it ended; a permitted action can still fail or be cancelled"
    )
    reason: str | None = meaning(
        "why it was denied, or why it failed; the explanation an "
        "administrator needs and cannot reconstruct later",
        default=None,
    )
    approval_id: str | None = meaning(
        "the administrator approval that authorized it, for actions that "
        "require one",
        default=None,
    )
    correlation_id: str | None = meaning(
        "ties this entry to the request or operation that caused it", default=None
    )

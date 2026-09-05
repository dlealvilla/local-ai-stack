"""Who is acting, and on whose behalf.

`Subject` and `AccessContext` exist at Stage 0.2 rather than Stage 5.1
because they are threaded through the gateway, analytics, knowledge, agents
and audit. Retrofitting identity into a finished serving path is the
expensive case the roadmap names; the directory behind a subject is not.

`AccessContext` carries delegation from the start. An application acting
for a user is a different fact from either of them acting alone, and an
audit trail or a permission check that cannot tell them apart is unable to
answer the questions it exists to answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kultrun.kernel.ids import EntityId
from kultrun.kernel.schema import Contract, contract, meaning


class SubjectId(EntityId):
    """Identifies one acting principal."""

    prefix = "sub"


class TeamId(EntityId):
    """Identifies one team. The team itself arrives at Stage 5.1."""

    prefix = "team"


class PrincipalKind(StrEnum):
    """What sort of principal a subject is.

    Applications and services are principals too. Treating them as such
    from the beginning is what allows an audit entry or a usage event to
    attribute an action to software rather than to whichever human
    happened to be nearby.
    """

    USER = "user"
    GROUP = "group"
    TEAM = "team"
    APPLICATION = "application"
    SERVICE = "service"
    ADMINISTRATOR = "administrator"


@contract(kind="identity.subject", version=1)
@dataclass(frozen=True, slots=True)
class Subject(Contract):
    """One principal the platform can attribute an action to."""

    subject_id: SubjectId = meaning("platform-minted identity of this principal")
    principal_kind: PrincipalKind = meaning("what sort of principal this is")
    display_name: str | None = meaning(
        "name shown to an administrator; never used for authorization", default=None
    )
    external_ref: str | None = meaning(
        "identity in the upstream provider, kept verbatim for reconciliation",
        default=None,
    )


@contract(kind="identity.access_context", version=1)
@dataclass(frozen=True, slots=True)
class AccessContext(Contract):
    """The authorization context a request is evaluated in.

    Every permission decision in the platform takes one of these. Retrieval,
    routing, model access and administrative action all read the same shape,
    which is what makes one identity model serve all of them.
    """

    subject: Subject = meaning("the principal whose permissions apply")
    on_behalf_of: Subject | None = meaning(
        "the principal an application is acting for, when it is acting for one",
        default=None,
    )
    team_ids: tuple[TeamId, ...] = meaning(
        "teams whose scope this request may draw on", default=()
    )
    correlation_id: str | None = meaning(
        "ties this authorization to the request that prompted it", default=None
    )

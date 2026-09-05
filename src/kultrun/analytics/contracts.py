"""The record of what was used.

The previous attempt left an explicit instruction about this contract:
`logical_name`, `model_id`, `provider`, `service_id` and `role` are
different identities and must not be collapsed into one field, and future
usage events should further distinguish `requested_model` from
`actual_model` and record a `route_reason`. That instruction is honoured
literally here, because re-separating conflated identities after analytics
has been written is the expensive case.

The distinction earns its keep the first time a request is answered by
something other than what was asked for. A fallback, an administrator
override, a Team Brain substitution and an external provider all produce a
usage event where requested and actual differ, and a single `model` field
makes every one of those invisible.

Every measurement is `Maybe[...]`. A provider that does not report
time-to-first-token has not reported a time-to-first-token of zero.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from kultrun.identity.contracts import SubjectId, TeamId
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


class UsageId(EntityId):
    """Identifies one recorded use."""

    prefix = "use"


@contract(kind="analytics.usage_event", version=1)
@dataclass(frozen=True, slots=True)
class UsageEvent(Contract):
    """One AI request, as the platform records it.

    Recording one of these must never block the response it describes, and
    the gateway must never wait on an exporter to write one.
    """

    usage_id: UsageId = meaning("platform-minted identity of this record")
    occurred_at: dt.datetime = meaning("when the request was served, UTC")
    logical_name: Name = meaning(
        "the name the client asked for, as exposed to applications"
    )
    provider: Name = meaning(
        "what served it, such as a local runtime or an external API"
    )
    service_id: Name = meaning("the platform service that handled it")
    route_reason: Name = meaning(
        "why this route was chosen, which is what makes routing auditable"
    )
    requested_model: Name | None = meaning(
        "the model the client asked for, when it named one", default=None
    )
    actual_model: Name | None = meaning(
        "the model that answered, which is not always the one requested",
        default=None,
    )
    instance_id: str | None = meaning(
        "the serving instance, by identifier", default=None
    )
    subject_id: SubjectId | None = meaning(
        "who made the request", default=None
    )
    team_id: TeamId | None = meaning(
        "the team scope it was made under", default=None
    )
    application: Name | None = meaning(
        "the application that made it, distinct from the person", default=None
    )
    correlation_id: str | None = meaning(
        "ties this record to the request that produced it", default=None
    )
    input_tokens: Maybe[int] = meaning("tokens consumed", default=NOT_PROVIDED)
    output_tokens: Maybe[int] = meaning("tokens produced", default=NOT_PROVIDED)
    latency_seconds: Maybe[float] = meaning(
        "wall time to complete the request", default=NOT_PROVIDED
    )
    ttft_seconds: Maybe[float] = meaning(
        "time to first token, where the runtime reports it", default=NOT_PROVIDED
    )
    queue_seconds: Maybe[float] = meaning(
        "time spent waiting before work began", default=NOT_PROVIDED
    )
    error_class: Name | None = meaning(
        "how it failed, if it failed; a failed request is still a use",
        default=None,
    )
    cost_micros: Maybe[int] = meaning(
        "cost in millionths of a currency unit, for external providers",
        default=NOT_PROVIDED,
    )

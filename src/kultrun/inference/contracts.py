"""One deployed model-serving workload.

`docs/PRODUCT_VISION.md` §12 makes this a primary platform concept, and it
is deliberately distinct from the stored artifact: the same artifact can be
served by two instances with different context lengths, different
concurrency and different access policies.

**Status and health are different questions**, and Stage 1.6 requires them
kept apart. ``reachable`` asks whether the port answers; ``health`` asks
whether the API works. A process that has bound its port but cannot load
the model is reachable and unhealthy, and a platform that cannot express
that will report it as running.

**Two concurrency dimensions, never merged.** `docs/PRODUCT_VISION.md` §13:
``runtime_concurrency`` is how many requests one loaded instance handles;
``platform_max_concurrent_requests`` is the gateway's limit. The previous
attempt held a platform-level number that was never mapped to the runtime's
own control, which is why Stage 4.3 exists.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.host.contracts import HostId
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_MEASURED, Maybe
from kultrun.model.contracts import ModelId
from kultrun.resource.contracts import ReservationId


class InstanceId(EntityId):
    """Identifies one serving instance."""

    prefix = "inst"


class LifecycleState(StrEnum):
    """What the platform intends and observes about an instance."""

    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class HealthState(StrEnum):
    """Whether the instance actually works.

    ``UNKNOWN`` is a real answer, not a placeholder: an instance that has
    not been probed since restart is not healthy and is not unhealthy, and
    reconciliation must be able to say so.
    """

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@contract(kind="inference.endpoint", version=1)
@dataclass(frozen=True, slots=True)
class InferenceEndpoint(Contract):
    """Where an instance can be reached."""

    scheme: str = meaning("transport scheme")
    address: str = meaning("host or address the instance is bound to")
    port: int = meaning("port the instance is bound to")
    base_path: str = meaning("path prefix the runtime serves under", default="/")


@contract(kind="inference.instance", version=1)
@dataclass(frozen=True, slots=True)
class InferenceInstance(Contract):
    """One model being served, on one host, under one configuration."""

    instance_id: InstanceId = meaning("platform-minted identity of this instance")
    host_id: HostId = meaning("the host it runs on")
    model_id: ModelId = meaning("the model it serves")
    runtime: Name = meaning("the inference runtime adapter serving it")
    executor: Name = meaning("the executor running the process")
    lifecycle_state: LifecycleState = meaning("what the platform intends and observes")
    health: HealthState = meaning("whether the API functions, as distinct from status")
    configuration_version: int = meaning(
        "advances when the serving configuration changes, so a restart can "
        "tell a stale instance from a current one"
    )
    model_revision: Maybe[str] = meaning(
        "the model revision being served", default=NOT_MEASURED
    )
    reachable: Maybe[bool] = meaning(
        "whether the port answers; a reachable port is not a working API",
        default=NOT_MEASURED,
    )
    endpoint: InferenceEndpoint | None = meaning(
        "where it is reachable, once it is", default=None
    )
    reservation_id: ReservationId | None = meaning(
        "the resources held for it; absent means nothing is held", default=None
    )
    context_length_tokens: Maybe[int] = meaning(
        "configured context length, which is a capacity decision not a setting",
        default=NOT_MEASURED,
    )
    runtime_concurrency: Maybe[int] = meaning(
        "simultaneous requests this instance is configured to handle",
        default=NOT_MEASURED,
    )
    platform_max_concurrent_requests: Maybe[int] = meaning(
        "the gateway's limit for this instance, a different dimension from "
        "runtime concurrency",
        default=NOT_MEASURED,
    )
    access_policy_ref: str | None = meaning(
        "the policy governing who may use it, by identifier", default=None
    )
    started_at: dt.datetime | None = meaning(
        "when it began serving; absent until it does", default=None
    )

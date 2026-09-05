"""Recording administrator decisions.

Only the record. The request-approve cycle and the risk classification that
decides which actions need one are Stage 6.2.

What has to exist now is the writing-down, because Stage 1.5 is the first
mutating workflow and the constitution requires a deployment to be able to
answer what approval was given. An approval reconstructed after the fact is
not an approval.

Approvals are never rewritten. A decision that turned out to be wrong is
superseded by a later decision, not edited, because the record of what was
decided at the time is the whole value of having one.
"""

from __future__ import annotations

from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import ConflictError
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.platform.contracts import Approval, ComponentHealth, HealthStatus


class ApprovalLog:
    """The append-only record of administrator decisions."""

    component = Name("approvals")

    def __init__(self, store: Store, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def record(self, approval: Approval) -> Approval:
        """Write a decision. Refuses to overwrite an existing one."""
        key = approval.approval_id.value
        if self._store.get(Approval, key) is not None:
            raise ConflictError(
                "an approval with this identity is already recorded; "
                "supersede it with a new decision rather than editing it",
                approval_id=key,
            )
        self._store.put(key, approval)
        return approval

    def get(self, approval_id: str) -> Approval | None:
        """One decision, or None."""
        return self._store.get(Approval, approval_id)

    def all(self) -> tuple[Approval, ...]:
        """Every recorded decision, most recent first."""
        return tuple(
            sorted(
                self._store.records(Approval),
                key=lambda approval: approval.decided_at,
                reverse=True,
            )
        )

    def check_health(self) -> ComponentHealth:
        """Healthy when the log is readable."""
        try:
            self._store.keys(Approval)
        except Exception as error:
            return ComponentHealth(
                component=self.component,
                status=HealthStatus.FAILING,
                detail=f"approval log unreadable: {error}",
            )
        return ComponentHealth(component=self.component, status=HealthStatus.HEALTHY)

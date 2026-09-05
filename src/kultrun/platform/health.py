"""Aggregating health across whatever has registered itself.

The aggregate is the **worst** component status, not an average. A platform
with one failing subsystem is not three-quarters healthy, and an endpoint
that says so is worse than no endpoint.

Unknown outranks healthy for the same reason. If a component has not been
asked since startup, the platform does not know it is well, and Part II §6
requires unknown to stay unknown rather than resolve to a pass. It does not
outrank failing, because a known failure is more actionable than an
unknown.
"""

from __future__ import annotations

from kultrun.kernel.clock import Clock
from kultrun.platform.contracts import ComponentHealth, HealthReport, HealthStatus
from kultrun.platform.ports import HealthSource

#: Worst first. Aggregation takes the earliest status present.
_SEVERITY: tuple[HealthStatus, ...] = (
    HealthStatus.FAILING,
    HealthStatus.DEGRADED,
    HealthStatus.UNKNOWN,
    HealthStatus.HEALTHY,
)


class HealthAggregator:
    """Collects each registered source's own answer."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._sources: list[HealthSource] = []

    def register(self, source: HealthSource) -> None:
        """Add a source. Every domain that can be unwell registers one."""
        self._sources.append(source)

    def report(self) -> HealthReport:
        """Ask every source, and take the worst answer as the platform's."""
        components = tuple(self._check(source) for source in self._sources)
        return HealthReport(
            status=aggregate_status(components),
            observed_at=self._clock.now(),
            components=components,
        )

    def _check(self, source: HealthSource) -> ComponentHealth:
        try:
            return source.check_health()
        except Exception as error:  # a source that cannot answer is failing
            return ComponentHealth(
                component=source.component,
                status=HealthStatus.FAILING,
                detail=f"health check raised: {error}",
            )


def aggregate_status(components: tuple[ComponentHealth, ...]) -> HealthStatus:
    """The worst status present, or unknown when nothing has reported."""
    if not components:
        return HealthStatus.UNKNOWN
    present = {component.status for component in components}
    for status in _SEVERITY:
        if status in present:
            return status
    return HealthStatus.UNKNOWN

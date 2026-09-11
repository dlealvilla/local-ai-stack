"""Replaceable technology-specific storage probes.

The registry never contains vendor logic. Adapters declare `supports` and
Kultrun **always runs** every compatible probe.
"""

from __future__ import annotations

from collections.abc import Sequence

from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import ProbeReport
from kultrun.storage.limits import NATIVE_CLASS_PROBE_NAMES
from kultrun.storage.ports import StorageCapacityProbe, StorageEnvironment


class ProbeRegistry:
    """Ordered replaceable probes. Unknown technology is explicit, not verified."""

    def __init__(self, probes: Sequence[StorageCapacityProbe] = ()) -> None:
        self._probes = tuple(probes)

    @property
    def probes(self) -> tuple[StorageCapacityProbe, ...]:
        return self._probes

    def compatible(
        self, environment: StorageEnvironment
    ) -> tuple[StorageCapacityProbe, ...]:
        return tuple(item for item in self._probes if item.supports(environment))

    def run(self, environment: StorageEnvironment) -> tuple[ProbeReport, ...]:
        """Run every compatible probe. Incompatible probes are omitted.

        If none match, a single explicit 'none' report is returned so the
        caller cannot treat silence as verification.
        """
        matched = self.compatible(environment)
        if not matched:
            return (
                ProbeReport(
                    probe_name="none",
                    technology=str(
                        environment.filesystem_type
                        if is_resolved(environment.filesystem_type)
                        else "unknown"
                    ),
                    compatible=False,
                    available=False,
                    executed=False,
                    detail="no compatible technology-specific probe",
                ),
            )
        reports: list[ProbeReport] = []
        for probe in matched:
            result = probe.probe(environment)
            reports.append(
                ProbeReport(
                    probe_name=probe.name,
                    technology=probe.technology,
                    compatible=True,
                    available=result.available,
                    executed=result.executed,
                    available_bytes=result.available_bytes,
                    hard_maximum_bytes=result.hard_maximum_bytes,
                    detail=result.detail,
                )
            )
        return tuple(reports)

    def strongest_available(
        self, reports: Sequence[ProbeReport]
    ) -> tuple[Maybe[int], Maybe[int]]:
        """Last entitlement-probe available, and the smallest hard maximum.

        OS-native echoes (statvfs, GetDiskFreeSpaceEx, FUSE identify) are
        not specialist domain bytes and must not settle a pool.
        """
        hard: Maybe[int] = NOT_PROVIDED
        available: Maybe[int] = NOT_PROVIDED
        for report in reports:
            if report.probe_name in NATIVE_CLASS_PROBE_NAMES:
                continue
            if (
                report.executed
                and is_resolved(report.hard_maximum_bytes)
                and (not is_resolved(hard) or report.hard_maximum_bytes < hard)
            ):
                hard = report.hard_maximum_bytes
            if report.executed and is_resolved(report.available_bytes):
                available = report.available_bytes
        return available, hard

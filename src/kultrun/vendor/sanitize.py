"""Map local operational facts onto the vendor telemetry record.

The allow-list is the privacy boundary. Attributes not named here never
leave the host, even when export is enabled.
"""

from __future__ import annotations

from kultrun.kernel.build import identity as build_identity
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.platform.contracts import OperationalFact
from kultrun.vendor.contracts import TelemetryRecord
from kultrun.vendor.ports import ProductTelemetryExporter

_ALLOWED_ATTRS = frozenset(
    {
        "mount",
        "tier_units",
        "runtime",
        "version",
        "model",
        "latency_ms",
        "verdict",
        "candidate",
        "bytes",
        "os",
        "arch",
        "filesystem",
    }
)


def sanitize_fact(fact: OperationalFact) -> TelemetryRecord:
    """Operational metadata only. Prompt/response/document never appear."""
    parsed = _attributes(fact.attributes)
    build = build_identity()
    return TelemetryRecord(
        occurred_at=fact.occurred_at,
        event_type=fact.event_type.value,
        outcome=fact.outcome.value,
        stage=fact.stage.value,
        kultrun_build=build.build_id or build.version,
        os_name=parsed.get("os", NOT_PROVIDED),
        architecture=parsed.get("arch", NOT_PROVIDED),
        storage_technology=parsed.get("filesystem", NOT_PROVIDED),
        runtime=parsed.get("runtime", NOT_PROVIDED),
        model=parsed.get("model", NOT_PROVIDED),
        reason_code=fact.reason_code if is_resolved(fact.reason_code) else NOT_PROVIDED,
        latency_ms=_int(parsed.get("latency_ms")),
        error_class=fact.reason_code if fact.outcome.value == "fail" else NOT_PROVIDED,
    )


def _attributes(items: tuple[str, ...]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key in _ALLOWED_ATTRS:
            parsed[key] = value
    return parsed


def _int(value: str | None) -> Maybe[int]:
    if value is None or not value.isdigit():
        return NOT_PROVIDED
    return int(value)


class ExportingObserver:
    """Optional outbound hop. Never required for the platform to function."""

    def __init__(
        self,
        exporter: ProductTelemetryExporter,
        *,
        enabled: bool,
    ) -> None:
        self._exporter = exporter
        self._enabled = enabled

    def observe(self, fact: OperationalFact) -> None:
        if not self._enabled:
            return
        try:
            self._exporter.export((sanitize_fact(fact),))
        except Exception:
            return

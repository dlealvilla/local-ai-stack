"""Map local operational facts onto the vendor telemetry record.

The allow-list is the privacy boundary. Attributes not named here never
leave the host, even when export is enabled.

Three levels stay separate:

* Local operational truth (OperationalFact + domain state) always exists.
* Development/acceptance evidence stays on the host.
* Vendor product-improvement telemetry is this sanitized record, and only
  when TelemetrySettings permits. Token counts, prompts, paths, hostnames,
  usernames, and PIDs are not exported.
"""

from __future__ import annotations

from kultrun.kernel.build import identity as build_identity
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.platform.contracts import OperationalFact
from kultrun.vendor.contracts import TelemetryRecord
from kultrun.vendor.ports import ProductTelemetryExporter

#: Exact local paths, hostnames, PIDs, token counts, and content stay out.
_ALLOWED_ATTRS = frozenset(
    {
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
        "executor",
        "quantization",
        "finish_reason",
        "discovered",
        "compatible",
        "available_count",
        "support_tier",
        "profile",
        "possibility",
        "requires_reclamation",
        "byte_band",
        "product_selectable",
        "host_compatible",
        "executor_compatible",
        "capacity_feasible",
        "cleanup_lifecycle",
        "cleanup_capacity",
    }
)


def sanitize_fact(fact: OperationalFact) -> TelemetryRecord:
    """Operational metadata only. Prompt/response/document never appear."""
    parsed = _attributes(fact.attributes)
    build = build_identity()
    run_id: Maybe[str] = NOT_PROVIDED
    if is_resolved(fact.correlation_id) and fact.correlation_id.startswith("drun_"):
        run_id = fact.correlation_id
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
        run_id=run_id,
        executor=parsed.get("executor", NOT_PROVIDED),
        support_tier=parsed.get("support_tier", NOT_PROVIDED),
        profile=parsed.get("profile", NOT_PROVIDED),
        possibility=parsed.get("possibility", NOT_PROVIDED),
        requires_reclamation=parsed.get("requires_reclamation", NOT_PROVIDED),
        byte_band=parsed.get("byte_band", NOT_PROVIDED),
        discovered=parsed.get("discovered", NOT_PROVIDED),
        product_selectable=parsed.get("product_selectable", NOT_PROVIDED),
        host_compatible=parsed.get("host_compatible", NOT_PROVIDED),
        executor_compatible=parsed.get("executor_compatible", NOT_PROVIDED),
        capacity_feasible=parsed.get("capacity_feasible", NOT_PROVIDED),
        cleanup_lifecycle=parsed.get("cleanup_lifecycle", NOT_PROVIDED),
        cleanup_capacity=parsed.get("cleanup_capacity", NOT_PROVIDED),
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

"""The durable host record, its restart reconciliation, and its health.

This is the module that answers "is this the same machine as last time",
which is a different question from "do the providers agree with each other".
The second is `host/discovery.py`. Keeping them apart matters: both are
called reconciliation in ordinary speech, and one word for two operations is
how a concept begins to fragment.

Four restart outcomes, each recorded as a fact rather than acted on. A host
that cannot currently be inspected is not a host that has ceased to exist,
and a provider that stopped loading has not removed a GPU.

**This module reports facts and does not grade itself.** It says which
providers answered and what changed; whether that amounts to "degraded" is a
control-plane judgement, made where the whole platform's condition is known.
That is the same division the record store already uses — the store returns
facts, policy decides — and it is also what keeps a tier-2 domain from
importing the tier-8 contracts the health and startup ports exchange.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from kultrun.host.contracts import HostCapabilities, ProviderStatus
from kultrun.host.discovery import HostDiscoveryService
from kultrun.host.fingerprint import compute
from kultrun.kernel.errors import PersistenceError
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store

#: The singleton key for the current host's record.
CURRENT_HOST_KEY = "current"


class HostChange(StrEnum):
    """What a restart found."""

    FIRST_RUN = "first_run"
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    EVIDENCE_LOST = "evidence_lost"
    DISCOVERY_FAILED = "discovery_failed"


@dataclass(frozen=True, slots=True)
class HostLoad:
    """The outcome of establishing the current host."""

    capabilities: HostCapabilities
    change: HostChange
    detail: str


class HostInventory:
    """Holds the current host's description across restarts."""

    phase = Name("host-discovery")
    component = Name("host-discovery")

    def __init__(self, service: HostDiscoveryService, store: Store) -> None:
        self._service = service
        self._store = store
        self._loaded: HostCapabilities | None = None

    @property
    def current(self) -> HostCapabilities:
        """The established description, or a refusal before startup."""
        if self._loaded is None:
            raise PersistenceError(
                "host discovery has not run; run startup first"
            )
        return self._loaded

    @property
    def is_loaded(self) -> bool:
        return self._loaded is not None

    def establish(self) -> HostLoad:
        """Discover the host now and compare it against what was stored."""
        stored = self._store.get(HostCapabilities, CURRENT_HOST_KEY)
        observed = self._service.discover(
            host_id=stored.host_id if stored is not None else None
        )
        observed = replace(observed, fingerprint=compute(observed))

        if _all_providers_failed(observed):
            if stored is not None:
                # A host we cannot inspect has not ceased to exist. Keep the
                # record, mark the situation, and let policy decide.
                self._loaded = stored
                return HostLoad(
                    capabilities=stored,
                    change=HostChange.DISCOVERY_FAILED,
                    detail=(
                        "every provider failed; retaining the stored "
                        "record as stale"
                    ),
                )
            self._loaded = observed
            return HostLoad(
                capabilities=observed,
                change=HostChange.DISCOVERY_FAILED,
                detail="every provider failed and no record exists",
            )

        self._store.put(CURRENT_HOST_KEY, observed)
        self._loaded = observed

        if stored is None:
            return HostLoad(observed, HostChange.FIRST_RUN, "first discovery")
        if stored.fingerprint == observed.fingerprint:
            return HostLoad(
                observed, HostChange.UNCHANGED, f"fingerprint {observed.fingerprint}"
            )
        if _lost_evidence(stored, observed):
            return HostLoad(
                observed,
                HostChange.EVIDENCE_LOST,
                "fewer providers answered than last time; affected values are "
                "unresolved rather than absent",
            )
        return HostLoad(
            observed,
            HostChange.CHANGED,
            f"fingerprint {stored.fingerprint} -> {observed.fingerprint}; "
            f"cached evidence keyed on the old fingerprint is invalid",
        )

    def unavailable_providers(self) -> tuple[str, ...]:
        """Providers that did not answer this run, by name.

        A fact, not a verdict. Whether a missing provider makes the platform
        degraded depends on which one and on what else is wrong, and that is
        not knowable from inside this module.
        """
        if self._loaded is None:
            return ()
        return tuple(
            sorted(
                report.provider.value
                for report in self._loaded.provider_reports
                if report.status
                in (
                    ProviderStatus.FAILED,
                    ProviderStatus.UNAVAILABLE,
                    ProviderStatus.MISSING_PREREQUISITE,
                )
            )
        )

    def defects(self) -> tuple[str, ...]:
        """Everything this run surfaced but did not resolve."""
        if self._loaded is None:
            return ()
        found = [
            f"{report.provider}: {report.detail or report.status.value}"
            for report in self._loaded.provider_reports
            if report.status
            in (
                ProviderStatus.FAILED,
                ProviderStatus.UNAVAILABLE,
                ProviderStatus.MISSING_PREREQUISITE,
            )
        ]
        found.extend(
            f"providers disagree at {conflict.path}"
            for conflict in self._loaded.conflicts
            if conflict.resolution is None
        )
        return tuple(found)


def _all_providers_failed(capabilities: HostCapabilities) -> bool:
    reports = capabilities.provider_reports
    if not reports:
        return True
    return all(
        report.status
        in (
            ProviderStatus.FAILED,
            ProviderStatus.UNAVAILABLE,
            ProviderStatus.MISSING_PREREQUISITE,
        )
        for report in reports
    )


def _lost_evidence(stored: HostCapabilities, observed: HostCapabilities) -> bool:
    """Whether this run had fewer answering providers than the stored one."""
    def answering(capabilities: HostCapabilities) -> set[str]:
        return {
            report.provider.value
            for report in capabilities.provider_reports
            if report.status in (ProviderStatus.AVAILABLE, ProviderStatus.PARTIAL)
        }

    return bool(answering(stored) - answering(observed))

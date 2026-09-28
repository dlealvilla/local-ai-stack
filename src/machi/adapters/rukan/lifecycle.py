"""Attach Admin stop and release to the existing Serve and Admit services.

A new Admin process rebuilds those services from the store. Native identity
is the stored start stamp and serve token, not the pid by itself. Provider
stop unloads by catalog name and digest. Release stays on ResourceManager.
"""

from __future__ import annotations

from pathlib import Path

from machi.adapters.admit.lock import FileAdmissionLock
from machi.adapters.admit.log import StoreReservationLog
from machi.adapters.foundation.process import NativeProcessRunner
from machi.adapters.model.ollama_http import LoopbackOllamaClient
from machi.adapters.persistence.file_store import FileStore
from machi.adapters.serve.endpoint import choose_port
from machi.adapters.serve.log import StoreServeLog
from machi.adapters.serve.ollama import OllamaServeAdapter
from machi.adapters.serve.provider_log import StoreProviderServeLog
from machi.adapters.serve.vllm import VllmServeProvider
from machi.admit.contracts import AdmissionDecision, AdmissionOutcome
from machi.admit.service import ResourceManager
from machi.kernel.clock import SystemClock
from machi.serve.contracts import InstanceState, ServeDecision, ServeOutcome
from machi.serve.policy import ServePolicy
from machi.serve.provider import ProviderServeDecision, ProviderServeService
from machi.serve.service import ServeService

_PROVIDER = "provider_digest"


class LifecycleOwner:
    """One store, one ledger, both macropaths. The browser does not choose."""

    def __init__(
        self,
        store_root: Path,
        *,
        provider_base: str = "http://127.0.0.1:11434",
        state_root: Path | None = None,
        native: ServeService | None = None,
        provider: ProviderServeService | None = None,
        manager: ResourceManager | None = None,
    ) -> None:
        store = FileStore(store_root)
        root = state_root or Path(store_root)
        self._manager = manager or ResourceManager(
            StoreReservationLog(store), FileAdmissionLock(store.root)
        )
        clock = SystemClock()
        self._native = native or ServeService(
            StoreServeLog(store),
            VllmServeProvider(NativeProcessRunner(), clock),
            self._manager,
            ServePolicy(),
            clock,
            root,
            choose_port,
        )
        self._provider = provider or ProviderServeService(
            StoreProviderServeLog(store),
            OllamaServeAdapter(LoopbackOllamaClient(provider_base)),
            self._manager,
            clock,
        )

    def stop(self, instance_id: str, identity_kind: str) -> tuple[str, str]:
        """Stop the current instance. A held reservation is not released."""
        if identity_kind == _PROVIDER:
            return _decision(self._provider.stop(instance_id))
        return _decision(self._native.stop(instance_id))

    def release(self, instance_id: str, identity_kind: str) -> tuple[str, str]:
        """Release only after the owning service says the instance is stopped."""
        if identity_kind == _PROVIDER:
            instance = self._provider.get_instance(instance_id)
            if instance is None or instance.state is not InstanceState.STOPPED:
                return "refused", "stop before release"
            return _admission(self._manager.release(instance.reservation_id))
        result = self._native.release_after_stop(instance_id)
        if isinstance(result, AdmissionDecision):
            return _admission(result)
        return _decision(result)


def _decision(decision: ServeDecision | ProviderServeDecision) -> tuple[str, str]:
    if decision.outcome is ServeOutcome.STOPPED:
        return "ok", decision.reason
    if decision.outcome is ServeOutcome.REFUSED:
        return "refused", decision.reason
    return "failed", decision.reason


def _admission(decision: AdmissionDecision) -> tuple[str, str]:
    if decision.outcome is AdmissionOutcome.RELEASED:
        return "ok", decision.reason
    if decision.outcome is AdmissionOutcome.REFUSED:
        return "refused", decision.reason
    return "failed", decision.reason

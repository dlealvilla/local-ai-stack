"""Admin stop and release use Serve and ResourceManager, including reattachment."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from tests.machi.test_serve import ProbeRuntime, _world

from machi.adapters.admit.log import StoreReservationLog
from machi.adapters.foundation.process import NativeProcessRunner
from machi.adapters.persistence.file_store import FileStore
from machi.adapters.rukan.lifecycle import LifecycleOwner
from machi.adapters.rukan.server import AdminApplication
from machi.adapters.serve.log import StoreServeLog
from machi.adapters.serve.provider_log import StoreProviderServeLog
from machi.admit.contracts import ReservationState, ResourceReservation
from machi.admit.service import ResourceManager
from machi.kernel.build import BuildIdentity, BuildOrigin
from machi.kernel.clock import FixedClock, SystemClock
from machi.kernel.unresolved import is_resolved
from machi.serve.contracts import HealthState, InstanceState, ServeOutcome
from machi.serve.policy import ServePolicy
from machi.serve.ports import InferResult
from machi.serve.provider import (
    ProviderObservation,
    ProviderServeService,
    ProviderServingInstance,
)
from machi.serve.service import ServeService

BUILD = BuildIdentity(version="0.1.0", origin=BuildOrigin.SOURCE)
CLOCK = FixedClock(dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC))


class _NoKill(ProbeRuntime):
    def stop(self, evidence: object, *, grace_seconds: float) -> bool:
        del evidence, grace_seconds
        return False


class _Mismatch(ProbeRuntime):
    def identity_ok(self, evidence: object) -> bool:
        del evidence
        return False

    def stop(self, evidence: object, *, grace_seconds: float) -> bool:
        raise AssertionError("mismatched identity must not be signaled")


class _Catalog:
    def __init__(self) -> None:
        self.unloaded = False
        self.calls = 0

    def refresh(self, name: str, *, context: int) -> str:
        del name, context
        return "none"

    def observe(self, name: str, digest: str) -> ProviderObservation:
        del name
        if self.unloaded:
            return ProviderObservation("absent", digest, None, None)
        return ProviderObservation("expected_resident", digest, None, None)

    def infer(self, name: str, *, context: int) -> object:
        del name, context
        return InferResult(0, False, None)

    def unload(self, name: str) -> str:
        del name
        self.calls += 1
        self.unloaded = True
        return "none"


def _app(root: Path, owner: LifecycleOwner) -> AdminApplication:
    return AdminApplication(root, BUILD, lifecycle=owner, clock=CLOCK)


def test_admin_reattaches_and_releases_only_after_stop(tmp_path: Path) -> None:
    (
        service,
        manager,
        configuration,
        reservation,
        _runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path)
    started = service.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert started.outcome is ServeOutcome.READY
    store = tmp_path / "store"
    owner = LifecycleOwner(store)
    app = _app(store, owner)
    assert app.summary()["body"]["chain"]["instance_state"] == "ready"
    assert app.summary()["body"]["lifecycle"]["stop_attached"] is True
    held = app.release({})
    assert held["outcome"] == "refused"
    assert held["reason"] == "stop before release"
    assert len(manager.list_active_reservations()) == 1
    wrong = app.stop({"instance_id": "srv_other"})
    assert wrong["outcome"] == "refused"
    assert app.summary()["body"]["chain"]["instance_state"] == "ready"
    overridden = app.stop({"pid": 1})
    assert overridden["outcome"] == "refused"
    assert "runtime selection" in str(overridden["reason"])
    stopped = app.stop({})
    assert stopped["outcome"] == "ok"
    again = app.stop({})
    assert again["outcome"] == "ok"
    assert again["reason"] == "stop already recorded"
    assert app.summary()["body"]["chain"]["instance_state"] == "stopped"
    released = app.release({})
    assert released["outcome"] == "ok"
    second = app.release({})
    assert second["outcome"] == "ok"
    assert second["reason"] == "release already recorded"
    assert manager.list_active_reservations() == ()


def test_failed_stop_keeps_the_reservation(tmp_path: Path) -> None:
    (
        _service,
        manager,
        configuration,
        reservation,
        runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path)
    started = runtime
    service = _service
    ready = service.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert ready.outcome is ServeOutcome.READY
    sticky = _NoKill(NativeProcessRunner())
    sticky._spawned = started._spawned
    replacement = ServeService(
        StoreServeLog(FileStore(tmp_path / "store")),
        sticky,
        manager,
        ServePolicy(),
        SystemClock(),
        tmp_path,
        lambda _reservation, _policy: None,
    )
    owner = LifecycleOwner(tmp_path / "store", native=replacement)
    app = _app(tmp_path / "store", owner)
    failed = app.stop({})
    assert failed["outcome"] == "failed"
    assert app.summary()["body"]["chain"]["instance_state"] == "stopping"
    assert app.release({})["outcome"] == "refused"
    assert len(manager.list_active_reservations()) == 1
    assert is_resolved(ready.instance)
    evidence = service._evidence_for(ready.instance)
    assert evidence is not None
    assert runtime.alive(evidence) is True


def test_identity_mismatch_is_not_signaled(tmp_path: Path) -> None:
    (
        service,
        manager,
        configuration,
        reservation,
        runtime,
        artifact,
        selection,
        generation,
        model_path,
    ) = _world(tmp_path)
    ready = service.start(
        configuration,
        reservation.reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=True,
    )
    assert ready.outcome is ServeOutcome.READY
    mismatch = _Mismatch(NativeProcessRunner())
    mismatch._spawned = runtime._spawned
    replacement = ServeService(
        StoreServeLog(FileStore(tmp_path / "store")),
        mismatch,
        manager,
        ServePolicy(),
        SystemClock(),
        tmp_path,
        lambda _reservation, _policy: None,
    )
    app = _app(
        tmp_path / "store",
        LifecycleOwner(tmp_path / "store", native=replacement),
    )
    refused = app.stop({})
    assert refused["outcome"] == "failed"
    assert refused["reason"] == "process_identity_unresolved"
    assert len(manager.list_active_reservations()) == 1
    evidence = service._evidence_for(ready.instance)
    assert evidence is not None
    assert runtime.alive(evidence) is True


def test_provider_stop_then_release_uses_the_same_ledger(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    manager = ResourceManager(StoreReservationLog(store))
    reservation = ResourceReservation(
        reservation_id="rsv_provider",
        plan_id="plan_provider",
        fingerprint="finger",
        request_id="req_provider",
        capacity_evidence_id="cap_provider",
        accelerator_identity="accel_provider",
        accelerator_memory_bytes=8,
        host_memory_bytes=8,
        persistent_bytes=0,
        transient_bytes=0,
        cpu_count=1,
        policy_version="m8.admit.1",
        state=ReservationState.RESERVED,
    )
    store.create(reservation.reservation_id, reservation)
    digest = "a" * 64
    instance = ProviderServingInstance(
        instance_id="srv_provider",
        plan_id="plan_provider",
        fingerprint="finger",
        reservation_id="rsv_provider",
        generation_id="fgen_provider",
        digest=digest,
        display_name="smollm2:135m",
        serve_provider="ollama",
        context_length=2048,
        concurrency=1,
        state=InstanceState.READY,
        health=HealthState.READY,
        evidence_id="evidence_provider",
        policy_version="m9.serve.provider.1",
    )
    catalog = _Catalog()
    provider = ProviderServeService(
        StoreProviderServeLog(store),
        catalog,
        manager,
        SystemClock(),
    )
    provider._log.create_instance(instance)
    owner = LifecycleOwner(tmp_path, provider=provider, manager=manager)
    app = _app(tmp_path, owner)
    assert app.summary()["body"]["chain"]["model_identity_kind"] == "provider_digest"
    assert app.release({})["outcome"] == "refused"
    stopped = app.stop({})
    assert stopped["outcome"] == "ok"
    assert catalog.calls == 1
    assert app.summary()["body"]["chain"]["instance_state"] == "stopped"
    assert app.release({})["outcome"] == "ok"
    assert manager.list_active_reservations() == ()

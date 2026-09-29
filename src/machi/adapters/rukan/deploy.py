"""Customer-local deployment workflow. Coordinates. Does not admit or launch."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from machi.adapters.admit.lock import FileAdmissionLock
from machi.adapters.admit.log import StoreReservationLog
from machi.adapters.capacity.native import NativeCapacity
from machi.adapters.discover.native_accelerator import NativeAcceleratorObserver
from machi.adapters.discover.native_memory import NativeMemoryObserver
from machi.adapters.discover.native_mount import NativeMountObserver
from machi.adapters.discover.native_os_arch import NativeOSArchitectureObserver
from machi.adapters.foundation.host_runtime import observe_host_runtime
from machi.adapters.foundation.process import NativeProcessRunner
from machi.adapters.foundation.provision import ManagedVllmProvisioner
from machi.adapters.model.acquire import with_stored
from machi.adapters.model.runtime_query import query_runtime
from machi.adapters.model.warehouse import load_artifact, verify_stored, warehouse_root
from machi.adapters.persistence.file_store import FileStore
from machi.adapters.plan.vllm import build_vllm_recipe
from machi.adapters.rukan.read import load_records
from machi.adapters.serve.endpoint import choose_port
from machi.adapters.serve.log import StoreServeLog
from machi.adapters.serve.vllm import VllmServeProvider
from machi.adapters.steward.native import NativeSteward, RootClaim
from machi.admit.contracts import AdmissionOutcome, ResourceReservation
from machi.admit.service import ResourceManager
from machi.capacity.contracts import CapacityEnvelope
from machi.foundation.contracts import (
    FoundationSelection,
    ManagedGeneration,
    ProvisionMode,
    RuntimeCapability,
    SupportState,
)
from machi.foundation.policy import default_foundation_settings
from machi.foundation.resolve import resolve_candidate
from machi.kernel.clock import SystemClock
from machi.kernel.errors import ConflictError, NotFoundError, ValidationError
from machi.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, is_resolved
from machi.model.compat import RuntimeView
from machi.model.contracts import (
    AvailableModelEntry,
    AvailableModels,
    CompatibilityState,
    ModelArtifact,
    ModelSelection,
    ProviderQualification,
    SelectionProvenance,
)
from machi.model.environment import execution_environment_fingerprint
from machi.model.evaluate import evaluate_source, select_entry, snapshot_for
from machi.model.policy import default_model_settings
from machi.model.qualification import (
    POLICY_VERSION as QUALIFICATION_POLICY,
)
from machi.model.qualification import (
    DeployableMember,
    DeployableModels,
    QualificationEvidence,
    QualificationOutcome,
    QualificationRequest,
    qualification_identity,
)
from machi.model.qualify_map import evidence_for_probe
from machi.model.source import SourceFileInfo, SourceView
from machi.plan.compose import PlanInputs, compose_plan
from machi.plan.contracts import DeploymentConfiguration, PlanFailure, PlanPreference
from machi.plan.policy import DEFAULT_CONCURRENCY, DEFAULT_CONTEXT, MIN_CONTEXT
from machi.serve.contracts import InstanceState, ServeOutcome
from machi.serve.policy import ServePolicy
from machi.serve.service import ServeService

_FORBIDDEN = frozenset(
    {
        "plan_id",
        "fingerprint",
        "reservation_id",
        "instance_id",
        "pid",
        "port",
        "provider",
        "gpu",
        "safe_bytes",
        "capacity",
        "executable",
    }
)


@dataclass(frozen=True)
class DeploymentView:
    """Product-facing operation. Authoritative objects stay in their stores."""

    operation_id: str
    request_key: str
    artifact_id: str
    state: str
    plan_id: str
    reservation_id: str
    instance_id: str
    macropath: str
    failure: str
    reason: str
    next_actions: tuple[str, ...]
    foundation_id: str = ""
    generation_id: str = ""
    qualification_id: str = ""
    fingerprint: str = ""
    stages: tuple[tuple[str, str, bool], ...] = ()


class DeploymentCoordinator:
    """One active deployment. The browser supplies an artifact id and a key."""

    def __init__(
        self,
        store_root: Path,
        *,
        state_root: Path | None = None,
        serve: ServeService | None = None,
        manager: ResourceManager | None = None,
        note: object | None = None,
    ) -> None:
        self.store_root = Path(store_root)
        self.state_root = Path(state_root or store_root)
        self._lock = threading.RLock()
        self._note = note
        store = FileStore(self.store_root)
        self._manager = manager or ResourceManager(
            StoreReservationLog(store), FileAdmissionLock(store.root)
        )
        clock = SystemClock()
        self._serve = serve or ServeService(
            StoreServeLog(store),
            VllmServeProvider(NativeProcessRunner(), clock),
            self._manager,
            ServePolicy(),
            clock,
            self.state_root,
            choose_port,
        )
        self.store_root.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(
            self.store_root / "rukan-deploy.sqlite", check_same_thread=False
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY,
                request_key TEXT NOT NULL UNIQUE,
                intent_hash TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                state TEXT NOT NULL,
                plan_id TEXT NOT NULL DEFAULT '',
                reservation_id TEXT NOT NULL DEFAULT '',
                instance_id TEXT NOT NULL DEFAULT '',
                failure TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                foundation_id TEXT NOT NULL DEFAULT '',
                generation_id TEXT NOT NULL DEFAULT '',
                qualification_id TEXT NOT NULL DEFAULT '',
                fingerprint TEXT NOT NULL DEFAULT '',
                macropath TEXT NOT NULL DEFAULT '',
                actor_origin TEXT NOT NULL,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._migrate()
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def deploy(
        self,
        *,
        artifact_id: str,
        request_key: str,
        actor: str,
        now: datetime,
    ) -> DeploymentView:
        if not artifact_id or not request_key:
            raise ValidationError("deploy requires an artifact and a request key")
        digest = _intent(artifact_id)
        with self._lock:
            existing = self._by_key(request_key)
            if existing is not None and existing["intent_hash"] != digest:
                raise ValidationError("deployment request key was reused")
            active = self._active()
            if existing is None and active is not None:
                if str(active["artifact_id"]) == artifact_id and active["state"] == "ready":  # noqa: E501
                    return self._view(active)
                if active["state"] not in {"failed", "released"}:
                    raise ValidationError("one deployment is already in progress")
            if existing is None:
                operation_id = "dop_" + secrets.token_hex(8)
                self._db.execute(
                    """
                    INSERT INTO operations(
                        operation_id, request_key, intent_hash, artifact_id, state,
                        actor_origin, started_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'requested', ?, ?, ?)
                    """,
                    (
                        operation_id, request_key, digest, artifact_id, actor,
                        now.isoformat(), now.isoformat(),
                    ),
                )
                self._db.commit()
                existing = self._by_key(request_key)
            assert existing is not None
            if existing["state"] in {"failed", "ready", "stopped", "released", "recovery_required"}:  # noqa: E501
                return self._view(existing)
            return self._advance(existing, now)

    def current(self) -> DeploymentView | None:
        with self._lock:
            row = self._active() or self._latest()
            if row is None:
                return None
            return self._view(row)

    def mark_stopped(self, now: datetime) -> None:
        with self._lock:
            row = self._active()
            if row is None or row["state"] != "ready":
                return
            self._set(str(row["operation_id"]), state="stopped", updated_at=now.isoformat())  # noqa: E501
            self._emit(("deployment_stopped",), now)

    def mark_released(self, now: datetime) -> None:
        with self._lock:
            row = self._latest()
            if row is None or row["state"] not in {"stopped", "recovery_required"}:
                return
            self._set(str(row["operation_id"]), state="released", updated_at=now.isoformat())  # noqa: E501
            self._emit(("reservation_released",), now)

    def _advance(self, row: sqlite3.Row, now: datetime) -> DeploymentView:
        operation_id = str(row["operation_id"])
        artifact_id = str(row["artifact_id"])
        if row["state"] not in {"planned", "admitted", "starting"}:
            self._set(operation_id, state="evaluating", updated_at=now.isoformat())
        artifact = load_artifact(self.state_root, artifact_id)
        if artifact is None:
            return self._fail(
                operation_id, "artifact_missing", "stored artifact was not found", now
            )
        if not verify_stored(self.state_root, artifact):
            return self._fail(
                operation_id,
                "artifact_corrupt",
                "stored artifact hashes do not match",
                now,
            )
        foundation = self._foundation(row)
        if isinstance(foundation, str):
            return self._fail(operation_id, foundation, "foundation is not verified", now)  # noqa: E501
        if not isinstance(foundation.generation_id, str):
            return self._fail(
                operation_id,
                "foundation_not_ready",
                "foundation generation is not stored",
                now,
            )
        generation = _generation(self.store_root, foundation.generation_id)
        if generation is None:
            return self._fail(
                operation_id,
                "foundation_not_ready",
                "foundation generation is not stored",
                now,
            )
        self._set(
            operation_id,
            foundation_id=foundation.selection_id,
            generation_id=generation.generation_id,
            macropath=foundation.engine.value,
            updated_at=now.isoformat(),
        )
        envelope = self._planning_envelope(foundation)
        if isinstance(envelope, str):
            return self._fail(operation_id, envelope, "capacity was not usable", now)
        if str(row["reservation_id"]):
            return self._start_saved(
                operation_id, str(row["plan_id"]), str(row["reservation_id"]),
                artifact, foundation, generation, now,
            )
        if str(row["plan_id"]):
            saved = _load_plan(self.store_root, str(row["plan_id"]))
            held = _hold_for(self._manager, saved) if saved is not None else None
            if saved is not None and held is not None:
                return self._launch(
                    operation_id, saved, held.reservation_id, artifact,
                    foundation, generation, now,
                )
        pieces = _plan_pieces(self.store_root, artifact, foundation, envelope)
        if isinstance(pieces, str):
            rebuilt = self._rebuild(artifact, foundation, generation, envelope, now)
            if isinstance(rebuilt, str):
                return self._fail(operation_id, rebuilt, "deployment facts are incomplete", now)  # noqa: E501
            inputs = rebuilt
        else:
            inputs = _inputs_from(pieces, artifact, foundation, envelope)
        decision = compose_plan(inputs, build_vllm_recipe)
        if decision.failure in {
            PlanFailure.QUALIFICATION_REQUIRED,
            PlanFailure.QUALIFICATION_DOES_NOT_COVER,
        }:
            earned = self._earn(inputs, artifact, foundation, generation, envelope, now)
            if isinstance(earned, str):
                return self._fail(operation_id, earned, "qualification did not pass", now)  # noqa: E501
            if isinstance(earned, tuple):
                return self._recover(operation_id, earned[0], earned[1], now)
            inputs = earned
            decision = compose_plan(inputs, build_vllm_recipe)
        if decision.failure is not PlanFailure.NONE or not is_resolved(
            decision.configuration
        ):
            return self._fail(
                operation_id, decision.failure.value, decision.reason, now
            )
        configuration = decision.configuration
        _remember(FileStore(self.store_root), configuration.plan_id, configuration)
        self._set(
            operation_id,
            state="planned",
            plan_id=configuration.plan_id,
            fingerprint=configuration.fingerprint,
            qualification_id=_setting(configuration, "qualification_id"),
            updated_at=now.isoformat(),
        )
        held = _hold_for(self._manager, configuration)
        if held is None:
            admission = self._manager.admit(decision, envelope, PlanFailure.NONE)
            if admission.outcome is not AdmissionOutcome.ADMITTED or not is_resolved(
                admission.reservation
            ):
                return self._fail(
                    operation_id, "admission_rejected", admission.reason, now
                )
            held = admission.reservation
        self._set(
            operation_id,
            state="admitted",
            reservation_id=held.reservation_id,
            updated_at=now.isoformat(),
        )
        self._set(operation_id, state="starting", updated_at=now.isoformat())
        started = self._serve.start(
            configuration,
            held.reservation_id,
            foundation,
            generation,
            artifact,
            model_path=warehouse_root(self.state_root) / artifact.artifact_id,
            artifact_verified=True,
        )
        if started.outcome is not ServeOutcome.READY or not is_resolved(started.instance):  # noqa: E501
            return self._compensate(
                operation_id, held.reservation_id, started.reason, now
            )
        self._set(
            operation_id,
            state="ready",
            instance_id=started.instance.instance_id,
            failure="",
            reason=started.reason,
            updated_at=now.isoformat(),
        )
        self._emit(("deployment_ready",), now)
        finished = self._by_id(operation_id)
        assert finished is not None
        return self._view(finished)

    def _migrate(self) -> None:
        present = {
            str(item[1]) for item in self._db.execute("PRAGMA table_info(operations)")
        }
        for name in (
            "foundation_id",
            "generation_id",
            "qualification_id",
            "fingerprint",
            "macropath",
        ):
            if name not in present:
                self._db.execute(
                    f"ALTER TABLE operations ADD COLUMN {name} TEXT NOT NULL DEFAULT ''"
                )

    def _foundation(self, row: sqlite3.Row) -> FoundationSelection | str:
        cited = str(row["foundation_id"])
        if cited:
            found = _foundation_by_id(self.store_root, cited)
            if found is not None:
                return found
        stored = _ready_foundation(self.store_root)
        live = _live_envelope(self.state_root, self.store_root)
        if stored is not None and _ceiling(live) is None:
            return stored
        inspected = _inspect_ready(self.state_root, self.store_root)
        if inspected is not None:
            return inspected
        if stored is not None and _ceiling(live) is None:
            return stored
        return "foundation_not_ready"

    def _planning_envelope(
        self, foundation: FoundationSelection
    ) -> CapacityEnvelope | str:
        cited = _envelope_by_id(self.store_root, foundation.capacity_evidence_id)
        live = _live_envelope(self.state_root, self.store_root)
        live_ceiling = _ceiling(live)
        cited_ceiling = _ceiling(cited)
        if (
            live_ceiling is not None
            and cited_ceiling is not None
            and live_ceiling < cited_ceiling
        ):
            return "capacity_insufficient"
        if cited is not None:
            return cited
        if (
            live is not None
            and live_ceiling is not None
            and live.evidence_id == foundation.capacity_evidence_id
        ):
            _remember(FileStore(self.store_root), live.evidence_id, live)
            return live
        return "capacity_unresolved"

    def _start_saved(
        self,
        operation_id: str,
        plan_id: str,
        reservation_id: str,
        artifact: ModelArtifact,
        foundation: FoundationSelection,
        generation: ManagedGeneration,
        now: datetime,
    ) -> DeploymentView:
        configuration = _load_plan(self.store_root, plan_id)
        if configuration is None:
            return self._recover(
                operation_id, "plan_missing", "saved plan could not be reloaded", now
            )
        return self._launch(
            operation_id, configuration, reservation_id, artifact, foundation,
            generation, now,
        )

    def _launch(
        self,
        operation_id: str,
        configuration: DeploymentConfiguration,
        reservation_id: str,
        artifact: ModelArtifact,
        foundation: FoundationSelection,
        generation: ManagedGeneration,
        now: datetime,
    ) -> DeploymentView:
        self._set(operation_id, state="starting", updated_at=now.isoformat())
        started = self._serve.start(
            configuration,
            reservation_id,
            foundation,
            generation,
            artifact,
            model_path=warehouse_root(self.state_root) / artifact.artifact_id,
            artifact_verified=True,
        )
        if started.outcome is not ServeOutcome.READY or not is_resolved(started.instance):  # noqa: E501
            return self._compensate(operation_id, reservation_id, started.reason, now)
        self._set(
            operation_id,
            state="ready",
            instance_id=started.instance.instance_id,
            plan_id=configuration.plan_id,
            reservation_id=reservation_id,
            fingerprint=configuration.fingerprint,
            failure="",
            reason=started.reason,
            updated_at=now.isoformat(),
        )
        self._emit(("deployment_ready",), now)
        row = self._by_id(operation_id)
        assert row is not None
        return self._view(row)

    def _earn(
        self,
        inputs: PlanInputs,
        artifact: ModelArtifact,
        foundation: FoundationSelection,
        generation: ManagedGeneration,
        envelope: CapacityEnvelope,
        now: datetime,
    ) -> PlanInputs | str | tuple[str, str]:
        """Run one reserved proof. A passing id comes from qualification_identity."""
        probe = compose_plan(replace(inputs, probe=True), build_vllm_recipe)
        if probe.failure is not PlanFailure.NONE or not is_resolved(probe.configuration):  # noqa: E501
            return probe.failure.value
        configuration = probe.configuration
        _remember(FileStore(self.store_root), configuration.plan_id, configuration)
        held = _hold_for(self._manager, configuration)
        if held is None:
            admission = self._manager.admit(probe, envelope, PlanFailure.NONE)
            if admission.outcome is not AdmissionOutcome.ADMITTED or not is_resolved(
                admission.reservation
            ):
                return "admission_rejected"
            held = admission.reservation
        started_at = time.monotonic()
        started = self._serve.start(
            configuration,
            held.reservation_id,
            foundation,
            generation,
            artifact,
            model_path=warehouse_root(self.state_root) / artifact.artifact_id,
            artifact_verified=True,
        )
        load_seconds = time.monotonic() - started_at
        proved = None
        generate_seconds = None
        instance = started.instance if is_resolved(started.instance) else None
        if started.outcome is ServeOutcome.READY and instance is not None:
            prove_started = time.monotonic()
            proved = self._serve.prove(instance.instance_id)
            generate_seconds = time.monotonic() - prove_started
            if is_resolved(proved.instance):
                instance = proved.instance
        release_problem = _release_probe(self._serve, self._manager, held.reservation_id)  # noqa: E501
        if release_problem is not None:
            return ("release_unproven", release_problem)
        tokens = None
        failure = started.failure.value if hasattr(started, "failure") else started.reason  # noqa: E501
        proved_ok = proved is not None and proved.outcome is ServeOutcome.PROVEN
        if proved is not None:
            failure = proved.failure.value if hasattr(proved, "failure") else proved.reason  # noqa: E501
            proof = proved.proof
            if is_resolved(proof) and isinstance(proof.completion_tokens, int):
                tokens = proof.completion_tokens
        request = _request_for(inputs, foundation, generation, envelope)
        if isinstance(request, str):
            return request
        evidence = evidence_for_probe(
            request,
            artifact_id=artifact.artifact_id,
            ready=started.outcome is ServeOutcome.READY,
            proved=proved_ok and isinstance(tokens, int) and tokens > 0,
            failure=failure or "probe",
            completion_tokens=tokens,
            load_seconds=load_seconds,
            generate_seconds=generate_seconds,
            peak_vram_bytes=None,
            peak_ram_bytes=None,
            observed_at=now,
        )
        if evidence.outcome is not QualificationOutcome.PASS:
            return "qualification_failed"
        _remember(FileStore(self.store_root), evidence.qualification_id, evidence)
        return _with_evidence(inputs, evidence, envelope, now)

    def _rebuild(
        self,
        artifact: ModelArtifact,
        foundation: FoundationSelection,
        generation: ManagedGeneration,
        envelope: CapacityEnvelope,
        now: datetime,
    ) -> PlanInputs | str:
        if not isinstance(foundation.generation_id, str):
            return "foundation_not_ready"
        runtime = _runtime_view(generation, foundation.generation_id)
        if not runtime.capability_known:
            return "runtime_capability_unresolved"
        entry = evaluate_source(
            _source_view(self.state_root, artifact),
            source_kind=artifact.source_kind,
            runtime=runtime,
            capacity=envelope,
            accelerator_safe_bytes=_ceiling(envelope),
            observed_at=now,
        )
        entry = with_stored(self.state_root, entry)
        if entry.compatibility.state is not CompatibilityState.COMPATIBLE:
            return entry.compatibility.failure.value
        capability = _capability_for(self.store_root, foundation)
        if capability is None:
            return "foundation_not_ready"
        identity = foundation.generation_id
        available = snapshot_for(
            (entry,),
            foundation_id=identity,
            capacity_evidence_id=envelope.evidence_id,
            policy_token=default_model_settings().revision_policy,
            observed_at=now,
        )
        request = _request_from_entry(
            entry, foundation, generation, envelope, capability.version
        )
        if isinstance(request, str):
            return request
        evidence = _carrier(request, artifact.artifact_id, now)
        static = entry.requirement.static_weight_bytes
        deployable = DeployableModels(
            snapshot_id=f"dep_{evidence.qualification_id[-12:]}",
            capacity_snapshot_id=envelope.evidence_id,
            members=(
                DeployableMember(
                    model_id=entry.definition.model_id,
                    immutable_revision=entry.definition.immutable_revision,
                    qualification_id=evidence.qualification_id,
                    total_required_vram_bytes=(
                        static if isinstance(static, int) else NOT_PROVIDED
                    ),
                ),
            ),
            observed_at=now,
        )
        try:
            selection = select_entry(
                entry,
                deployable,
                foundation_id=identity,
                capacity_evidence_id=envelope.evidence_id,
                provenance=SelectionProvenance.ADMINISTRATOR_SELECTED,
            )
        except ValidationError:
            return "qualification_required"
        _remember(FileStore(self.store_root), available.snapshot_id, available)
        _remember(FileStore(self.store_root), selection.selection_id, selection)
        _remember(FileStore(self.store_root), deployable.snapshot_id, deployable)
        return PlanInputs(
            selection=selection,
            available=available,
            artifact=artifact,
            artifact_verified=True,
            foundation=foundation,
            capability=capability,
            envelope=envelope,
            preference=PlanPreference(
                context_length=NOT_PROVIDED,
                concurrency=NOT_PROVIDED,
                accelerator_count=1,
            ),
            deployable=deployable,
            qualification=evidence,
            hardware_class=evidence.hardware_class,
            execution_environment_fingerprint=(
                evidence.execution_environment_fingerprint
            ),
        )

    def _recover(
        self, operation_id: str, failure: str, reason: str, now: datetime
    ) -> DeploymentView:
        self._set(
            operation_id,
            state="recovery_required",
            failure=failure,
            reason=reason[:240],
            updated_at=now.isoformat(),
        )
        self._emit(("deployment_failed",), now)
        row = self._by_id(operation_id)
        assert row is not None
        return self._view(row)

    def _compensate(self, operation_id: str, reservation_id: str, reason: str, now: datetime) -> DeploymentView:  # noqa: E501
        instance = None
        for item in self._serve.list_instances():
            if item.reservation_id == reservation_id:
                instance = item
        if instance is not None and instance.state is not InstanceState.STOPPED:
            try:
                stopped = self._serve.stop(instance.instance_id)
            except ConflictError:
                return self._recover(
                    operation_id, "serve_failed", "stop evidence conflicted", now
                )
            if stopped.outcome is not ServeOutcome.STOPPED:
                self._set(
                    operation_id,
                    state="recovery_required",
                    failure="serve_failed",
                    reason=reason,
                    updated_at=now.isoformat(),
                )
                self._emit(("deployment_failed",), now)
                row = self._by_id(operation_id)
                assert row is not None
                return self._view(row)
        released = self._manager.release(reservation_id)
        if released.outcome is not AdmissionOutcome.RELEASED:
            self._set(
                operation_id,
                state="recovery_required",
                failure="release_unproven",
                reason=reason,
                updated_at=now.isoformat(),
            )
        else:
            self._set(
                operation_id,
                state="failed",
                failure="serve_failed",
                reason=reason,
                updated_at=now.isoformat(),
            )
        self._emit(("deployment_failed",), now)
        row = self._by_id(operation_id)
        assert row is not None
        return self._view(row)

    def _fail(self, operation_id: str, failure: str, reason: str, now: datetime) -> DeploymentView:  # noqa: E501
        self._set(
            operation_id,
            state="failed",
            failure=failure,
            reason=reason[:240],
            updated_at=now.isoformat(),
        )
        self._emit(("deployment_failed",), now)
        row = self._by_id(operation_id)
        assert row is not None
        return self._view(row)

    def _emit(self, reasons: tuple[str, ...], now: datetime) -> None:
        note = self._note
        if note is None:
            return
        method = getattr(note, "note", None)
        if method is not None:
            method(reasons, now, immediate=True)

    def _view(self, row: sqlite3.Row) -> DeploymentView:
        state = str(row["state"])
        actions: tuple[str, ...] = ()
        if state == "ready":
            actions = ("stop", "infer")
        elif state == "stopped" or state == "recovery_required":
            actions = ("release",)
        elif state == "failed":
            actions = ("retry",)
        return DeploymentView(
            operation_id=str(row["operation_id"]),
            request_key=str(row["request_key"]),
            artifact_id=str(row["artifact_id"]),
            state=state,
            plan_id=str(row["plan_id"]),
            reservation_id=str(row["reservation_id"]),
            instance_id=str(row["instance_id"]),
            macropath=str(row["macropath"]),
            failure=str(row["failure"]),
            reason=str(row["reason"]),
            next_actions=actions,
            foundation_id=str(row["foundation_id"]),
            generation_id=str(row["generation_id"]),
            qualification_id=str(row["qualification_id"]),
            fingerprint=str(row["fingerprint"]),
            stages=_stages(state),
        )

    def _set(self, operation_id: str, **fields: str) -> None:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        self._db.execute(
            f"UPDATE operations SET {assignments} WHERE operation_id = ?",
            (*fields.values(), operation_id),
        )
        self._db.commit()

    def _by_key(self, request_key: str) -> sqlite3.Row | None:
        found = self._db.execute(
            "SELECT * FROM operations WHERE request_key = ?", (request_key,)
        ).fetchone()
        return found if isinstance(found, sqlite3.Row) else None

    def _by_id(self, operation_id: str) -> sqlite3.Row | None:
        found = self._db.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        return found if isinstance(found, sqlite3.Row) else None

    def _active(self) -> sqlite3.Row | None:
        found = self._db.execute(
            """
            SELECT * FROM operations
            WHERE state NOT IN ('failed', 'released')
            ORDER BY started_at DESC LIMIT 1
            """
        ).fetchone()
        return found if isinstance(found, sqlite3.Row) else None

    def _latest(self) -> sqlite3.Row | None:
        found = self._db.execute(
            "SELECT * FROM operations ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return found if isinstance(found, sqlite3.Row) else None


def reject_deploy_body(body: dict[str, object]) -> str | None:
    """The browser may name an artifact and a request key."""
    found = _FORBIDDEN.intersection(body)
    if found:
        return "deploy intent included an authority field"
    artifact = body.get("artifact_id")
    key = body.get("request_key")
    if not isinstance(artifact, str) or not isinstance(key, str):
        return "deploy requires artifact_id and request_key"
    return None


def _intent(artifact_id: str) -> str:
    return hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()


def _ready_foundation(root: Path) -> FoundationSelection | None:
    rows = [
        item
        for item in load_records(root, FoundationSelection)
        if isinstance(item, FoundationSelection) and item.support is SupportState.READY
    ]
    return rows[-1] if rows else None


def _generation(root: Path, generation_id: str) -> ManagedGeneration | None:
    for item in load_records(root, ManagedGeneration):
        if isinstance(item, ManagedGeneration) and item.generation_id == generation_id:
            return item
    return None


def _envelope_by_id(root: Path, evidence_id: str) -> CapacityEnvelope | None:
    for item in load_records(root, CapacityEnvelope):
        if isinstance(item, CapacityEnvelope) and item.evidence_id == evidence_id:
            return item
    return None


def _foundation_by_id(root: Path, selection_id: str) -> FoundationSelection | None:
    for item in load_records(root, FoundationSelection):
        if isinstance(item, FoundationSelection) and item.selection_id == selection_id:
            return item
    return None


def _plan_pieces(
    root: Path,
    artifact: ModelArtifact,
    foundation: FoundationSelection,
    envelope: CapacityEnvelope,
) -> (
    tuple[
        ModelSelection,
        AvailableModels,
        RuntimeCapability,
        DeployableModels,
        QualificationEvidence,
    ]
    | str
):
    identity = foundation.generation_id
    if not isinstance(identity, str):
        identity = foundation.selection_id
    selections = [
        item
        for item in load_records(root, ModelSelection)
        if isinstance(item, ModelSelection) and item.artifact_id == artifact.artifact_id
    ]
    available = [
        item
        for item in load_records(root, AvailableModels)
        if isinstance(item, AvailableModels)
        and item.foundation_id == identity
        and item.capacity_evidence_id == envelope.evidence_id
    ]
    capabilities = [
        item
        for item in load_records(root, RuntimeCapability)
        if isinstance(item, RuntimeCapability) and item.engine is foundation.engine
    ]
    qualifications = [
        item
        for item in load_records(root, QualificationEvidence)
        if isinstance(item, QualificationEvidence)
        and item.artifact_id == artifact.artifact_id
    ]
    if not selections or not available or not capabilities or not qualifications:
        return "qualification_required"
    passed = [
        item for item in qualifications if item.outcome is QualificationOutcome.PASS
    ]
    qualification = passed[-1] if passed else qualifications[-1]
    deployable = [
        item
        for item in load_records(root, DeployableModels)
        if isinstance(item, DeployableModels)
        and any(
            member.qualification_id == qualification.qualification_id
            for member in item.members
        )
    ]
    if not deployable:
        return "qualification_required"
    return (
        selections[-1],
        available[-1],
        capabilities[-1],
        deployable[-1],
        qualification,
    )


def _inputs_from(
    pieces: tuple[
        ModelSelection,
        AvailableModels,
        RuntimeCapability,
        DeployableModels,
        QualificationEvidence,
    ],
    artifact: ModelArtifact,
    foundation: FoundationSelection,
    envelope: CapacityEnvelope,
) -> PlanInputs:
    return PlanInputs(
        selection=pieces[0],
        available=pieces[1],
        artifact=artifact,
        artifact_verified=True,
        foundation=foundation,
        capability=pieces[2],
        envelope=envelope,
        preference=PlanPreference(
            context_length=NOT_PROVIDED,
            concurrency=NOT_PROVIDED,
            accelerator_count=1,
        ),
        deployable=pieces[3],
        qualification=pieces[4],
        hardware_class=pieces[4].hardware_class,
        execution_environment_fingerprint=pieces[4].execution_environment_fingerprint,
    )


def _remember(store: FileStore, key: str, record: object) -> None:
    from machi.kernel.schema import Contract

    if not isinstance(record, Contract):
        return
    try:
        store.create(key, record)
    except ConflictError:
        return


def _hold_for(
    manager: ResourceManager, configuration: DeploymentConfiguration
) -> ResourceReservation | None:
    for item in manager.list_active_reservations():
        if (
            item.plan_id == configuration.plan_id
            and item.fingerprint == configuration.fingerprint
        ):
            return item
    return None


def _load_plan(root: Path, plan_id: str) -> DeploymentConfiguration | None:
    if not plan_id:
        return None
    try:
        return FileStore(root).get(DeploymentConfiguration, plan_id)
    except NotFoundError:
        return None


def _setting(configuration: DeploymentConfiguration, name: str) -> str:
    for item in configuration.settings:
        if item.name == name:
            return item.value
    return ""


def _ceiling(envelope: CapacityEnvelope | None) -> int | None:
    if envelope is None:
        return None
    known = [
        int(item.safe_bytes)
        for item in envelope.accelerators
        if isinstance(item.safe_bytes, int)
    ]
    if not known:
        return None
    return max(known)


def _live_envelope(state_root: Path, store_root: Path) -> CapacityEnvelope | None:
    try:
        root = str(state_root.expanduser().resolve())
        store = FileStore(store_root)
        occupancy = NativeSteward((RootClaim(path=root),), store=store).assess()
        memory = NativeMemoryObserver().observe()
        accelerators = NativeAcceleratorObserver().observe()
        mounts = NativeMountObserver().observe()
        parts = (
            memory.observed_at.isoformat(),
            accelerators.observed_at.isoformat(),
            mounts.observed_at.isoformat(),
            occupancy.observed_at.isoformat(),
        )
        return NativeCapacity(
            memory=memory,
            accelerators=accelerators,
            mounts=mounts,
            occupancy=occupancy,
            evidence_id="cap_cli",
            input_parts=parts,
        ).evaluate()
    except (OSError, ValidationError):
        return None


def _inspect_ready(state_root: Path, store_root: Path) -> FoundationSelection | None:
    try:
        root = state_root.expanduser().resolve()
        store = FileStore(store_root)
        occupancy = NativeSteward((RootClaim(path=str(root)),), store=store).assess()
        memory = NativeMemoryObserver().observe()
        accelerators = NativeAcceleratorObserver().observe()
        mounts = NativeMountObserver().observe()
        os_observation = NativeOSArchitectureObserver().observe()
        parts = (
            os_observation.observed_at.isoformat(),
            memory.observed_at.isoformat(),
            accelerators.observed_at.isoformat(),
            mounts.observed_at.isoformat(),
            occupancy.observed_at.isoformat(),
        )
        envelope = NativeCapacity(
            memory=memory,
            accelerators=accelerators,
            mounts=mounts,
            occupancy=occupancy,
            evidence_id="cap_foundation",
            input_parts=parts,
        ).evaluate()
        settings = default_foundation_settings(
            mode=ProvisionMode.INSPECT_ONLY, backend="cuda"
        )
        candidate = resolve_candidate(
            os_observation=os_observation,
            accelerators=accelerators,
            capacity=envelope,
            backend="cuda",
            prerequisite_ready=None,
            host_runtime=observe_host_runtime(accelerators),
            python_version=settings.python_version,
        )
        result = ManagedVllmProvisioner(uv_executable="uv").apply(
            state_root=root,
            candidate=candidate,
            settings=settings,
            capacity_evidence_id=envelope.evidence_id,
        )
    except (OSError, ValidationError):
        return None
    selection = result.selection
    if selection.support is not SupportState.READY:
        return None
    if not isinstance(selection.generation_id, str):
        return None
    store = FileStore(store_root)
    _remember(store, envelope.evidence_id, envelope)
    _remember(store, selection.selection_id, selection)
    generation = result.generation
    if isinstance(generation, ManagedGeneration):
        _remember(store, generation.generation_id, generation)
    capability = result.capability
    if isinstance(capability, RuntimeCapability):
        _remember(store, "runtime_capability", capability)
    return selection


def _runtime_view(generation: ManagedGeneration, foundation_id: str) -> RuntimeView:
    with tempfile.TemporaryDirectory() as tmp:
        architectures, quantizations, predicates = query_runtime(
            Path(generation.python_path), Path(tmp) / "runtime.json"
        )
    return RuntimeView(
        architectures=architectures,
        quantizations=quantizations,
        foundation_id=foundation_id,
        provider_qualification=ProviderQualification.QUALIFIED,
        capability_known=bool(architectures),
        predicates=predicates,
    )


def _source_view(state_root: Path, artifact: ModelArtifact) -> SourceView:
    root = warehouse_root(state_root) / artifact.artifact_id
    config_path = root / "config.json"
    config_text = (
        config_path.read_text(encoding="utf-8") if config_path.is_file() else None
    )
    index_path = root / "model.safetensors.index.json"
    index_text = (
        index_path.read_text(encoding="utf-8") if index_path.is_file() else None
    )
    return SourceView(
        repository=artifact.repository,
        requested_revision=artifact.immutable_revision,
        immutable_revision=artifact.immutable_revision,
        files=tuple(
            SourceFileInfo(item.relative_path, item.size_bytes) for item in artifact.files  # noqa: E501
        ),
        config_text=config_text,
        index_text=index_text,
        license_id=None,
        gated=False,
        private=False,
    )


def _capability_for(
    root: Path, foundation: FoundationSelection
) -> RuntimeCapability | None:
    rows = [
        item
        for item in load_records(root, RuntimeCapability)
        if isinstance(item, RuntimeCapability) and item.engine is foundation.engine
    ]
    return rows[-1] if rows else None


def _primary_device(envelope: CapacityEnvelope) -> object | None:
    ranked: list[tuple[int, int, object]] = []
    for device in envelope.accelerators:
        if isinstance(device.safe_bytes, int):
            ranked.append((-device.safe_bytes, device.ordinal, device))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked[0][2]


def _chosen_context(definition: object) -> int:
    declared = getattr(definition, "context_length", None)
    if isinstance(declared, int):
        chosen = min(declared, DEFAULT_CONTEXT)
        if chosen < MIN_CONTEXT:
            return declared
        return chosen
    return DEFAULT_CONTEXT


def _request_from_entry(
    entry: object,
    foundation: FoundationSelection,
    generation: ManagedGeneration,
    envelope: CapacityEnvelope,
    engine_version: str,
) -> QualificationRequest | str:
    definition = getattr(entry, "definition", None)
    if definition is None or not isinstance(foundation.generation_id, str):
        return "qualification_required"
    backend = foundation.backend
    backend_name = backend.value if is_resolved(backend) else ""
    if not backend_name:
        return "foundation_not_ready"
    device = _primary_device(envelope)
    identity = getattr(device, "identity", "")
    if not isinstance(identity, str) or not identity:
        return "capacity_unresolved"
    dtype = definition.dtype if isinstance(definition.dtype, str) else "undetermined"
    try:
        fingerprint = execution_environment_fingerprint(
            vendor="nvidia" if backend_name == "cuda" else "amd",
            accelerator_model=identity,
            capability="unspecified",
            runtime_capability=engine_version,
            generation_id=foundation.generation_id,
        )
    except ValueError:
        return "qualification_required"
    return QualificationRequest(
        model_id=definition.model_id,
        immutable_revision=definition.immutable_revision,
        generation_id=foundation.generation_id,
        engine=foundation.engine.value,
        engine_version=engine_version,
        backend=backend_name,
        hardware_class="unspecified",
        execution_environment_fingerprint=fingerprint,
        dtype=dtype,
        quantization=definition.quantization.value,
        context=_chosen_context(definition),
        concurrency=DEFAULT_CONCURRENCY,
        tensor_parallel=1,
        policy_version=QUALIFICATION_POLICY,
    )


def _request_for(
    inputs: PlanInputs,
    foundation: FoundationSelection,
    generation: ManagedGeneration,
    envelope: CapacityEnvelope,
) -> QualificationRequest | str:
    entry = _matching_entry(inputs)
    if entry is None:
        return "qualification_required"
    version = inputs.capability.version if inputs.capability is not None else generation.vllm_version  # noqa: E501
    return _request_from_entry(entry, foundation, generation, envelope, version)


def _carrier(
    request: QualificationRequest, artifact_id: str, now: datetime
) -> QualificationEvidence:
    """In-memory probe input. The id is qualification_identity, and it is not stored."""
    identity = qualification_identity(
        revision=request.immutable_revision,
        generation_id=request.generation_id,
        engine=request.engine,
        engine_version=request.engine_version,
        backend=request.backend,
        hardware_class=request.hardware_class,
        execution_environment_fingerprint=request.execution_environment_fingerprint,
        dtype=request.dtype,
        quantization=request.quantization,
        context=request.context,
        concurrency=request.concurrency,
        tensor_parallel=request.tensor_parallel,
        policy_version=request.policy_version,
    )
    return QualificationEvidence(
        qualification_id=identity,
        artifact_id=artifact_id,
        immutable_revision=request.immutable_revision,
        generation_id=request.generation_id,
        engine=request.engine,
        engine_version=request.engine_version,
        backend=request.backend,
        hardware_class=request.hardware_class,
        execution_environment_fingerprint=request.execution_environment_fingerprint,
        dtype=request.dtype,
        quantization=request.quantization,
        context=request.context,
        concurrency=request.concurrency,
        tensor_parallel=request.tensor_parallel,
        policy_version=request.policy_version,
        outcome=QualificationOutcome.FAIL_HOST,
        failure="probe_not_yet_run",
        load_seconds=NOT_MEASURED,
        ttft_seconds=NOT_MEASURED,
        tokens_per_second=NOT_MEASURED,
        peak_vram_bytes=NOT_MEASURED,
        peak_ram_bytes=NOT_MEASURED,
        measured=False,
        observed_at=now,
    )


def _matching_entry(inputs: PlanInputs) -> AvailableModelEntry | None:
    matches = [
        item
        for item in inputs.available.entries
        if item.definition.model_id == inputs.selection.model_id
        and item.definition.immutable_revision == inputs.selection.immutable_revision
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _with_evidence(
    inputs: PlanInputs,
    evidence: QualificationEvidence,
    envelope: CapacityEnvelope,
    now: datetime,
) -> PlanInputs:
    entry = _matching_entry(inputs)
    if entry is None:
        return inputs
    definition = entry.definition
    static = entry.requirement.static_weight_bytes
    identity = inputs.foundation.generation_id
    if not isinstance(identity, str):
        identity = inputs.foundation.selection_id
    deployable = DeployableModels(
        snapshot_id=f"dep_{evidence.qualification_id[-12:]}",
        capacity_snapshot_id=envelope.evidence_id,
        members=(
            DeployableMember(
                model_id=definition.model_id,
                immutable_revision=definition.immutable_revision,
                qualification_id=evidence.qualification_id,
                total_required_vram_bytes=static if isinstance(static, int) else NOT_PROVIDED,  # noqa: E501
            ),
        ),
        observed_at=now,
    )
    selection = select_entry(
        entry,
        deployable,
        foundation_id=identity,
        capacity_evidence_id=envelope.evidence_id,
    )
    return replace(
        inputs,
        selection=selection,
        deployable=deployable,
        qualification=evidence,
        hardware_class=evidence.hardware_class,
        execution_environment_fingerprint=evidence.execution_environment_fingerprint,
        probe=False,
    )


def _release_probe(serve: ServeService, manager: ResourceManager, reservation_id: str) -> str | None:  # noqa: E501
    instance = None
    for item in serve.list_instances():
        if item.reservation_id == reservation_id and item.state is not InstanceState.STOPPED:  # noqa: E501
            instance = item
    if instance is not None:
        stopped = serve.stop(instance.instance_id)
        if stopped.outcome is not ServeOutcome.STOPPED:
            return stopped.reason
        released = serve.release_after_stop(instance.instance_id)
    else:
        released = manager.release(reservation_id)
    if getattr(released, "outcome", None) is not AdmissionOutcome.RELEASED:
        return "reservation release was not proven"
    return None


def _stages(state: str) -> tuple[tuple[str, str, bool], ...]:
    labels = (
        ("model_verified", "Model verified"),
        ("runtime_verified", "Runtime verified"),
        ("capacity_evaluated", "Capacity evaluated"),
        ("plan_created", "Plan created"),
        ("resources_reserved", "Resources reserved"),
        ("starting", "Starting model server"),
        ("ready", "READY"),
    )
    rank = {
        "requested": 0,
        "evaluating": 1,
        "planned": 4,
        "admitted": 5,
        "starting": 6,
        "ready": 7,
        "stopped": 7,
        "released": 7,
    }.get(state, 0)
    return tuple(
        (item_id, label, index < rank) for index, (item_id, label) in enumerate(labels)
    )


def public_view(view: DeploymentView) -> dict[str, object]:
    return {
        "operation_id": view.operation_id,
        "state": view.state,
        "artifact_id": view.artifact_id,
        "macropath": view.macropath,
        "plan_id": view.plan_id,
        "reservation_id": view.reservation_id,
        "instance_id": view.instance_id,
        "foundation_id": view.foundation_id,
        "generation_id": view.generation_id,
        "qualification_id": view.qualification_id,
        "fingerprint": view.fingerprint,
        "failure": view.failure,
        "reason": view.reason,
        "next_actions": list(view.next_actions),
        "stages": [
            {"id": item[0], "label": item[1], "done": item[2]} for item in view.stages
        ],
    }


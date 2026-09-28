"""Composition root and CLI.

The only module that names a concrete adapter alongside Kernel, Install,
and Discover types. Kernel never imports adapters. Domain modules never
import adapters. Kernel never owns state-root policy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
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
from machi.adapters.foundation.uv_tool import ManagedUv
from machi.adapters.journal.jsonl import JsonlJournal
from machi.adapters.model.acquire import (
    StoreResult,
    store_local,
    store_view,
    view_local,
    with_stored,
)
from machi.adapters.model.hub import (
    credential_supplied,
    fetch_files,
    inspect_repository,
)
from machi.adapters.model.runtime_query import query_runtime
from machi.adapters.model.warehouse import cache_root
from machi.adapters.persistence.file_store import FileStore
from machi.adapters.plan.vllm import build_vllm_recipe
from machi.adapters.prerequisites.amd_smi import AmdSmiPrerequisiteAdapter
from machi.adapters.serve.endpoint import choose_port
from machi.adapters.serve.log import StoreServeLog
from machi.adapters.serve.vllm import VllmServeProvider
from machi.adapters.steward.native import NativeSteward, RootClaim
from machi.admit.contracts import AdmissionDecision
from machi.admit.policy import POLICY_VERSION as ADMIT_POLICY_VERSION
from machi.admit.service import ResourceManager
from machi.capacity.contracts import CapacityEnvelope
from machi.capacity.events import capacity_events
from machi.discover.contracts import (
    AcceleratorObservation,
    MemoryObservation,
    OSArchitectureObservation,
)
from machi.discover.events import (
    accelerator_observed,
    memory_observed,
    mounts_observed,
    os_arch_observed,
)
from machi.discover.mount_contracts import MountObservation, WriteProbePolicy
from machi.discover.ports import (
    AcceleratorObserver,
    MemoryObserver,
    MountObserver,
    OSArchitectureObserver,
)
from machi.foundation.contracts import (
    FailureCode,
    FoundationSelection,
    FoundationSet,
    ManagedGeneration,
    ProvisionMode,
)
from machi.foundation.events import foundation_events
from machi.foundation.policy import BACKEND_CHOICES, default_foundation_settings
from machi.foundation.resolve import resolve_candidate
from machi.install.binder import StateRootBinder
from machi.install.contracts import (
    InstallRecordEstablishment,
    InstallRunEstablishment,
    InstallRunRecord,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    SelectionSource,
    StateRootBinding,
)
from machi.install.defaults import (
    MACHI_OWNER_FILENAME,
    STATE_ROOT_VARIABLE,
    journal_dir,
)
from machi.install.events import (
    install_bound,
    install_record_established,
    local_ownership_marked,
    ownership_registry_seeded,
    state_root_bound,
)
from machi.install.identity import InstallIdentity
from machi.install.marker import SelfOwnershipMarker
from machi.install.registry import RegistrySeed
from machi.install.run import InstallRunStore
from machi.kernel.alive import kernel_alive
from machi.kernel.build import identity as build_identity
from machi.kernel.clock import FixedClock, SystemClock
from machi.kernel.errors import (
    MachiError,
    NotFoundError,
    PersistenceError,
    ValidationError,
)
from machi.kernel.events import EventRecord
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.journal import JournalDefect
from machi.kernel.schema import Contract, to_dict, validate_registry
from machi.kernel.store_proof import StoreProof, store_proved
from machi.kernel.unresolved import Maybe, is_resolved
from machi.model.compat import RuntimeView
from machi.model.contracts import (
    AvailableModels,
    ModelArtifact,
    ModelFailure,
    ModelSourceKind,
    ProviderQualification,
)
from machi.model.evaluate import evaluate_source, snapshot_for
from machi.model.events import acquisition_events, model_events
from machi.model.policy import DEFAULT_TIMEOUT, default_model_settings
from machi.model.qualification import QualificationEvidence, QualificationRequest
from machi.model.qualify_map import evidence_for_probe
from machi.plan.compose import PlanInputs
from machi.plan.compose import compose_plan as compose_plan_domain
from machi.plan.contracts import DeploymentConfiguration, PlanDecision, PlanFailure
from machi.plan.policy import (
    ACCELERATOR_COUNT,
    DEFAULT_CONCURRENCY,
    DEFAULT_CONTEXT,
    MEMORY_UTILIZATION,
    POLICY_VERSION,
)
from machi.prerequisites.contracts import (
    PolicyMode,
    PrerequisiteReadinessReport,
    SettingProvenance,
)
from machi.prerequisites.policy import default_prerequisite_policy, policy_with_mode
from machi.prerequisites.ports import PrerequisiteAdapter
from machi.prerequisites.service import PrerequisiteReadiness
from machi.serve.contracts import InstanceState, ServeDecision, ServeOutcome
from machi.serve.policy import BIND_SCOPE, ServePolicy
from machi.serve.policy import POLICY_VERSION as SERVE_POLICY_VERSION
from machi.serve.service import ServeService
from machi.steward.contracts import (
    GenerationHint,
    OccupancyMap,
    OwnershipStatus,
    ProtectionHint,
)
from machi.steward.events import steward_events


def prove_alive(journal_dir_path: Path) -> EventRecord:
    """Persist one kernel.alive event into the injected journal directory."""
    validate_registry(module_prefix="machi.")
    journal = JsonlJournal(journal_dir_path)
    return journal.append(kernel_alive())


def put_store_proof(
    *,
    store_dir_path: Path,
    key: str,
    token: str,
    journal_dir_path: Path | None,
) -> tuple[StoreProof, bool, bool, EventRecord | None, Path]:
    """Create or re-enter a Kernel StoreProof under an injected store root."""
    validate_registry(module_prefix="machi.")
    store = FileStore(store_dir_path)
    result = store.create(key, StoreProof(token=token))
    proof = store.get(StoreProof, key)
    event = None
    if journal_dir_path is not None:
        event = JsonlJournal(journal_dir_path).append(store_proved(result, key=key))
    return proof, result.created, result.existed, event, store.root


def get_store_proof(*, store_dir_path: Path, key: str) -> StoreProof:
    """Read a Kernel StoreProof from an injected store root."""
    validate_registry(module_prefix="machi.")
    return FileStore(store_dir_path).get(StoreProof, key)


def read_events(
    journal_dir_path: Path,
) -> tuple[tuple[EventRecord, ...], tuple[JournalDefect, ...]]:
    journal = JsonlJournal(journal_dir_path)
    return journal.records(), journal.defects()


def bind_state_root(
    *,
    explicit: str | None,
    environment: str | None,
    journal_dir_path: Path | None,
) -> tuple[StateRootBinding, EventRecord, Path]:
    """Bind a state root, then persist install.state_root.bound via Kernel."""
    validate_registry(module_prefix="machi.")
    binder = StateRootBinder()
    binding = binder.bind(explicit=explicit, environment=environment)
    target = (
        journal_dir_path
        if journal_dir_path is not None
        else journal_dir(Path(binding.root))
    )
    event = JsonlJournal(target).append(state_root_bound(binding))
    return binding, event, target


def mark_local_ownership(
    *,
    explicit: str | None,
    environment: str | None,
    journal_dir_path: Path | None,
) -> tuple[
    StateRootBinding, EventRecord, LocalOwnershipEstablishment, EventRecord, Path
]:
    """Bind via 1.2.1, mark via 1.3.1, then persist both Kernel events.

    The marker runs before the journal write so a refused claim does not
    create Install bootstrap files in an unknown tree.
    """
    validate_registry(module_prefix="machi.")
    binding = StateRootBinder().bind(explicit=explicit, environment=environment)
    establishment = SelfOwnershipMarker().establish(binding)
    target = (
        journal_dir_path
        if journal_dir_path is not None
        else journal_dir(Path(binding.root))
    )
    journal = JsonlJournal(target)
    bind_event = journal.append(state_root_bound(binding))
    mark_event = journal.append(local_ownership_marked(establishment))
    return binding, bind_event, establishment, mark_event, target


def seed_local_registry(
    *,
    explicit: str | None,
    environment: str | None,
    registry_store_dir: Path,
    journal_dir_path: Path | None,
) -> tuple[
    StateRootBinding,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    EventRecord,
    Path,
    Path,
]:
    """Bind, mark, then seed the control-plane registry via an injected Store.

    RegistrySeed does not choose the Store root. Composition supplies it.
    """
    validate_registry(module_prefix="machi.")
    binding = StateRootBinder().bind(explicit=explicit, environment=environment)
    establishment = SelfOwnershipMarker().establish(binding)
    store = FileStore(registry_store_dir)
    seeded = RegistrySeed().seed(binding, establishment, store)
    target = (
        journal_dir_path
        if journal_dir_path is not None
        else journal_dir(Path(binding.root))
    )
    journal = JsonlJournal(target)
    journal.append(state_root_bound(binding))
    journal.append(local_ownership_marked(establishment))
    seed_event = journal.append(ownership_registry_seeded(seeded))
    return binding, establishment, seeded, seed_event, target, store.root


def establish_install_record(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path,
    journal_dir_path: Path | None,
) -> tuple[
    StateRootBinding,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    InstallRecordEstablishment,
    EventRecord,
    Path,
    Path,
]:
    """Bind, mark, seed registry, then persist InstallRecord via an injected Store.

    InstallIdentity does not choose the Store root. Composition supplies it.
    Bind/mark/seed events in this invocation stay without InstallId.
    The InstallRecord event carries the newly established identity.
    """
    validate_registry(module_prefix="machi.")
    binding = StateRootBinder().bind(explicit=explicit, environment=environment)
    establishment = SelfOwnershipMarker().establish(binding)
    store = FileStore(store_dir)
    seeded = RegistrySeed().seed(binding, establishment, store)
    established = InstallIdentity().establish(
        binding, establishment, seeded, store, build_identity()
    )
    target = (
        journal_dir_path
        if journal_dir_path is not None
        else journal_dir(Path(binding.root))
    )
    journal = JsonlJournal(target)
    journal.append(state_root_bound(binding))
    journal.append(local_ownership_marked(establishment))
    journal.append(ownership_registry_seeded(seeded))
    record_event = journal.append(install_record_established(established))
    return (
        binding,
        establishment,
        seeded,
        established,
        record_event,
        target,
        store.root,
    )


def establish_install_run(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path,
    journal_dir_path: Path | None,
) -> tuple[
    StateRootBinding,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    InstallRecordEstablishment,
    InstallRunEstablishment,
    EventRecord,
    Path,
    Path,
]:
    """Reconstruct M1 through 1.1.1, then persist InstallRun via an injected Store.

    InstallRunStore does not choose the Store root. Composition supplies it.
    Predecessor events in this invocation keep historically correct
    unresolved fields. The install.bound event resolves InstallId and
    InstallRunId and leaves HostId unresolved.
    """
    validate_registry(module_prefix="machi.")
    binding = StateRootBinder().bind(explicit=explicit, environment=environment)
    establishment = SelfOwnershipMarker().establish(binding)
    store = FileStore(store_dir)
    seeded = RegistrySeed().seed(binding, establishment, store)
    established = InstallIdentity().establish(
        binding, establishment, seeded, store, build_identity()
    )
    run = InstallRunStore().establish(established.record, store, build_identity())
    target = (
        journal_dir_path
        if journal_dir_path is not None
        else journal_dir(Path(binding.root))
    )
    journal = JsonlJournal(target)
    journal.append(state_root_bound(binding))
    journal.append(local_ownership_marked(establishment))
    journal.append(ownership_registry_seeded(seeded))
    journal.append(install_record_established(established))
    bound_event = journal.append(install_bound(run, established.record))
    return (
        binding,
        establishment,
        seeded,
        established,
        run,
        bound_event,
        target,
        store.root,
    )


def observe_os_architecture(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path | None,
    journal_dir_path: Path | None,
    observer: OSArchitectureObserver | None = None,
) -> tuple[
    OSArchitectureObservation,
    EventRecord,
    Maybe[InstallId],
    Maybe[InstallRunId],
    Path | None,
]:
    """Observe OS/arch. Re-enter M1 for correlation when a Store is supplied.

    Does not mint HostId, does not persist a HostProfile, and does not
    rewrite install.bound. Install events are not journaled here.
    """
    validate_registry(module_prefix="machi.")
    if store_dir is not None and explicit is None and environment is None:
        raise ValidationError(
            "discover os-arch needs --state-root or MACHI_STATE_ROOT when "
            "a control-plane Store is supplied",
        )
    install_id: Maybe[InstallId] | None = None
    install_run_id: Maybe[InstallRunId] | None = None
    binding_root: Path | None = None
    if store_dir is not None:
        binding = StateRootBinder().bind(explicit=explicit, environment=environment)
        establishment = SelfOwnershipMarker().establish(binding)
        store = FileStore(store_dir)
        seeded = RegistrySeed().seed(binding, establishment, store)
        established = InstallIdentity().establish(
            binding, establishment, seeded, store, build_identity()
        )
        run = InstallRunStore().establish(established.record, store, build_identity())
        install_id = established.record.install_id
        install_run_id = run.record.install_run_id
        binding_root = Path(binding.root)
        _warn_if_defaulted(binding)
    observation = (observer or NativeOSArchitectureObserver()).observe()
    event = os_arch_observed(
        observation,
        install_id=install_id,
        install_run_id=install_run_id,
    )
    target: Path | None = None
    if journal_dir_path is not None:
        target = journal_dir_path
    elif binding_root is not None:
        target = journal_dir(binding_root)
    if target is not None:
        event = JsonlJournal(target).append(event)
    return observation, event, event.install_id, event.install_run_id, target


def observe_memory(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path | None,
    journal_dir_path: Path | None,
    observer: MemoryObserver | None = None,
) -> tuple[
    MemoryObservation,
    EventRecord,
    Maybe[InstallId],
    Maybe[InstallRunId],
    Path | None,
]:
    """Observe physical/system memory. Re-enter M1 when a Store is supplied.

    Does not mint HostId, does not persist a HostProfile, does not rewrite
    install.bound or discover.os_arch.observed, and does not compute capacity.
    """
    validate_registry(module_prefix="machi.")
    if store_dir is not None and explicit is None and environment is None:
        raise ValidationError(
            "discover memory needs --state-root or MACHI_STATE_ROOT when "
            "a control-plane Store is supplied",
        )
    install_id: Maybe[InstallId] | None = None
    install_run_id: Maybe[InstallRunId] | None = None
    binding_root: Path | None = None
    if store_dir is not None:
        binding = StateRootBinder().bind(explicit=explicit, environment=environment)
        establishment = SelfOwnershipMarker().establish(binding)
        store = FileStore(store_dir)
        seeded = RegistrySeed().seed(binding, establishment, store)
        established = InstallIdentity().establish(
            binding, establishment, seeded, store, build_identity()
        )
        run = InstallRunStore().establish(established.record, store, build_identity())
        install_id = established.record.install_id
        install_run_id = run.record.install_run_id
        binding_root = Path(binding.root)
        _warn_if_defaulted(binding)
    observation = (observer or NativeMemoryObserver()).observe()
    event = memory_observed(
        observation,
        install_id=install_id,
        install_run_id=install_run_id,
    )
    target: Path | None = None
    if journal_dir_path is not None:
        target = journal_dir_path
    elif binding_root is not None:
        target = journal_dir(binding_root)
    if target is not None:
        event = JsonlJournal(target).append(event)
    return observation, event, event.install_id, event.install_run_id, target


def observe_accelerator(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path | None,
    journal_dir_path: Path | None,
    observer: AcceleratorObserver | None = None,
) -> tuple[
    AcceleratorObservation,
    EventRecord,
    Maybe[InstallId],
    Maybe[InstallRunId],
    Path | None,
]:
    """Observe accelerators. Re-enter M1 when a Store is supplied.

    Does not mint HostId, does not persist a HostProfile, does not rewrite
    predecessor events, and does not compute capacity.
    """
    validate_registry(module_prefix="machi.")
    if store_dir is not None and explicit is None and environment is None:
        raise ValidationError(
            "discover accelerator needs --state-root or MACHI_STATE_ROOT when "
            "a control-plane Store is supplied",
        )
    install_id: Maybe[InstallId] | None = None
    install_run_id: Maybe[InstallRunId] | None = None
    binding_root: Path | None = None
    if store_dir is not None:
        binding = StateRootBinder().bind(explicit=explicit, environment=environment)
        establishment = SelfOwnershipMarker().establish(binding)
        store = FileStore(store_dir)
        seeded = RegistrySeed().seed(binding, establishment, store)
        established = InstallIdentity().establish(
            binding, establishment, seeded, store, build_identity()
        )
        run = InstallRunStore().establish(established.record, store, build_identity())
        install_id = established.record.install_id
        install_run_id = run.record.install_run_id
        binding_root = Path(binding.root)
        _warn_if_defaulted(binding)
    observation = (observer or NativeAcceleratorObserver()).observe()
    event = accelerator_observed(
        observation,
        install_id=install_id,
        install_run_id=install_run_id,
    )
    target: Path | None = None
    if journal_dir_path is not None:
        target = journal_dir_path
    elif binding_root is not None:
        target = journal_dir(binding_root)
    if target is not None:
        event = JsonlJournal(target).append(event)
    return observation, event, event.install_id, event.install_run_id, target


def observe_mounts(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path | None,
    journal_dir_path: Path | None,
    write_probe: bool = False,
    observer: MountObserver | None = None,
) -> tuple[
    MountObservation,
    EventRecord,
    Maybe[InstallId],
    Maybe[InstallRunId],
    Path | None,
]:
    """Observe mount topology. Re-enter M1 when a Store is supplied.

    Does not mint HostId, does not persist a HostProfile, does not rewrite
    predecessor events, and does not compute SAFE storage.
    """
    validate_registry(module_prefix="machi.")
    if store_dir is not None and explicit is None and environment is None:
        raise ValidationError(
            "discover mounts needs --state-root or MACHI_STATE_ROOT when "
            "a control-plane Store is supplied",
        )
    install_id: Maybe[InstallId] | None = None
    install_run_id: Maybe[InstallRunId] | None = None
    binding_root: Path | None = None
    if store_dir is not None:
        binding = StateRootBinder().bind(explicit=explicit, environment=environment)
        establishment = SelfOwnershipMarker().establish(binding)
        store = FileStore(store_dir)
        seeded = RegistrySeed().seed(binding, establishment, store)
        established = InstallIdentity().establish(
            binding, establishment, seeded, store, build_identity()
        )
        run = InstallRunStore().establish(established.record, store, build_identity())
        install_id = established.record.install_id
        install_run_id = run.record.install_run_id
        binding_root = Path(binding.root)
        _warn_if_defaulted(binding)
    selected = observer
    if selected is None:
        policy = WriteProbePolicy.BOUNDED if write_probe else None
        selected = NativeMountObserver(write_probe_policy=policy)
    observation = selected.observe()
    event = mounts_observed(
        observation,
        install_id=install_id,
        install_run_id=install_run_id,
    )
    target: Path | None = None
    if journal_dir_path is not None:
        target = journal_dir_path
    elif binding_root is not None:
        target = journal_dir(binding_root)
    if target is not None:
        event = JsonlJournal(target).append(event)
    return observation, event, event.install_id, event.install_run_id, target


def assess_steward(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path | None,
    journal_dir_path: Path | None,
    generation: str,
    protection: str,
) -> tuple[OccupancyMap, tuple[EventRecord, ...], Path | None]:
    """Classify one known root. Does not create markers or delete."""
    validate_registry(module_prefix="machi.")
    if explicit is None and environment is None:
        raise ValidationError(
            "steward assess needs --state-root or MACHI_STATE_ROOT",
        )
    raw = explicit if explicit is not None else environment
    assert raw is not None
    root = str(Path(raw).expanduser().resolve())
    store = FileStore(store_dir) if store_dir is not None else None
    occupancy = NativeSteward(
        (
            RootClaim(
                path=root,
                generation=GenerationHint(generation),
                protection=ProtectionHint(protection),
            ),
        ),
        store=store,
    ).assess()
    install_id: Maybe[InstallId] | None = None
    install_run_id: Maybe[InstallRunId] | None = None
    if store is not None and occupancy.resources:
        found = occupancy.resources[0].install_id
        if isinstance(found, str):
            install_id = InstallId(found)
            try:
                existing = store.get(InstallRunRecord, found)
            except NotFoundError:
                existing = None
            if existing is not None:
                install_run_id = existing.install_run_id
    events = steward_events(
        occupancy,
        install_id=install_id,
        install_run_id=install_run_id,
    )
    target: Path | None = journal_dir_path
    if target is None and (Path(root) / "journal").is_dir():
        target = journal_dir(Path(root))
    if target is not None:
        journal = JsonlJournal(target)
        events = tuple(journal.append(event) for event in events)
    return occupancy, events, target


def evaluate_capacity(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path | None,
    journal_dir_path: Path | None,
) -> tuple[CapacityEnvelope, tuple[EventRecord, ...], Path | None]:
    """Derive a planning envelope. Does not run Sonar unless a later flag asks."""
    validate_registry(module_prefix="machi.")
    memory = NativeMemoryObserver().observe()
    accelerators = NativeAcceleratorObserver().observe()
    mounts = NativeMountObserver().observe()
    occupancy = None
    root = None
    store = FileStore(store_dir) if store_dir is not None else None
    if explicit is not None or environment is not None:
        raw = explicit if explicit is not None else environment
        assert raw is not None
        root = str(Path(raw).expanduser().resolve())
        occupancy = NativeSteward((RootClaim(path=root),), store=store).assess()
    parts = (
        memory.observed_at.isoformat(),
        accelerators.observed_at.isoformat(),
        mounts.observed_at.isoformat(),
        occupancy.observed_at.isoformat() if occupancy is not None else "none",
    )
    envelope = NativeCapacity(
        memory=memory,
        accelerators=accelerators,
        mounts=mounts,
        occupancy=occupancy,
        evidence_id="cap_cli",
        input_parts=parts,
    ).evaluate()
    events = capacity_events(envelope)
    target = journal_dir_path
    if target is None and root is not None and (Path(root) / "journal").is_dir():
        target = journal_dir(Path(root))
    if target is not None:
        journal = JsonlJournal(target)
        events = tuple(journal.append(event) for event in events)
    return envelope, events, target


def inspect_foundation(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path | None,
    journal_dir_path: Path | None,
    mode: ProvisionMode,
    backend: str,
) -> tuple[FoundationSet, tuple[EventRecord, ...], Path | None]:
    """Resolve native vLLM. Inspection does not install. Provision is explicit."""
    validate_registry(module_prefix="machi.")
    if explicit is None and environment is None:
        raise ValidationError(
            "foundation needs --state-root or MACHI_STATE_ROOT",
        )
    raw = explicit if explicit is not None else environment
    assert raw is not None
    root = str(Path(raw).expanduser().resolve())
    store = FileStore(store_dir) if store_dir is not None else None
    occupancy = NativeSteward((RootClaim(path=root),), store=store).assess()
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
    settings = default_foundation_settings(mode=mode, backend=backend)
    candidate = resolve_candidate(
        os_observation=os_observation,
        accelerators=accelerators,
        capacity=envelope,
        backend=backend,
        prerequisite_ready=None,
        host_runtime=observe_host_runtime(accelerators),
        python_version=settings.python_version,
    )
    uv: str | Callable[[Path], str] = "uv"
    if mode is ProvisionMode.PROVISION and candidate.failure is FailureCode.NONE:
        owned = any(
            resource.ownership is OwnershipStatus.VERIFIED_MACHI_OWNED
            for resource in occupancy.resources
        )
        if not owned:
            raise ValidationError(
                "foundation provision requires a verified Machi-owned state root",
            )
        uv = ManagedUv().resolve
    result = ManagedVllmProvisioner(uv_executable=uv).apply(
        state_root=Path(root),
        candidate=candidate,
        settings=settings,
        capacity_evidence_id=envelope.evidence_id,
    )
    install_id: Maybe[InstallId] | None = None
    install_run_id: Maybe[InstallRunId] | None = None
    if store is not None and occupancy.resources:
        found = occupancy.resources[0].install_id
        if isinstance(found, str):
            install_id = InstallId(found)
            try:
                existing = store.get(InstallRunRecord, found)
            except NotFoundError:
                existing = None
            if existing is not None:
                install_run_id = existing.install_run_id
    events = foundation_events(
        result,
        install_id=install_id,
        install_run_id=install_run_id,
    )
    target = journal_dir_path
    if target is None and (Path(root) / "journal").is_dir():
        target = journal_dir(Path(root))
    if target is not None:
        journal = JsonlJournal(target)
        events = tuple(journal.append(event) for event in events)
    return result, events, target


def evaluate_prerequisites(
    *,
    explicit: str | None,
    environment: str | None,
    store_dir: Path | None,
    journal_dir_path: Path | None,
    mode: PolicyMode,
    adapter: PrerequisiteAdapter | None = None,
) -> tuple[
    PrerequisiteReadinessReport,
    tuple[EventRecord, ...],
    Maybe[InstallId],
    Maybe[InstallRunId],
    Path | None,
]:
    """Inspect a vendor CLI prerequisite. Discover remains read-only.

    Mutation happens only when mode is remediate and the adapter allowlists
    the action. Discover remains read-only. This is not admission.
    """
    validate_registry(module_prefix="machi.")
    if store_dir is not None and explicit is None and environment is None:
        raise ValidationError(
            "prerequisites check needs --state-root or MACHI_STATE_ROOT when "
            "a control-plane Store is supplied",
        )
    install_id: Maybe[InstallId] | None = None
    install_run_id: Maybe[InstallRunId] | None = None
    binding_root: Path | None = None
    if store_dir is not None:
        binding = StateRootBinder().bind(explicit=explicit, environment=environment)
        establishment = SelfOwnershipMarker().establish(binding)
        store = FileStore(store_dir)
        seeded = RegistrySeed().seed(binding, establishment, store)
        established = InstallIdentity().establish(
            binding, establishment, seeded, store, build_identity()
        )
        run = InstallRunStore().establish(established.record, store, build_identity())
        install_id = established.record.install_id
        install_run_id = run.record.install_run_id
        binding_root = Path(binding.root)
        _warn_if_defaulted(binding)
    selected = adapter or AmdSmiPrerequisiteAdapter()
    policy = default_prerequisite_policy()
    if mode is not policy.mode:
        policy = policy_with_mode(
            mode,
            provenance=SettingProvenance.ADMINISTRATOR,
            reason="selected on the invocation",
            source=policy,
        )
    report, events = PrerequisiteReadiness().evaluate(
        selected,
        policy,
        install_id=install_id,
        install_run_id=install_run_id,
    )
    target: Path | None = None
    if journal_dir_path is not None:
        target = journal_dir_path
    elif binding_root is not None:
        target = journal_dir(binding_root)
    if target is not None:
        journal = JsonlJournal(target)
        events = tuple(journal.append(event) for event in events)
    leading = events[0]
    return report, events, leading.install_id, leading.install_run_id, target


def show_version() -> int:
    identity = build_identity()
    print(identity.describe())
    print(f"  origin        {identity.origin.value}")
    print(f"  version       {identity.version}")
    print(f"  source commit {identity.source_commit or '-'}")
    print(f"  build id      {identity.build_id or '-'}")
    print(f"  built at      {identity.built_at or '-'}")
    standing = "acceptable" if identity.acceptable_as_evidence else "development only"
    print(f"  evidence      {standing}")
    return 0


def _print_document(record: Contract) -> None:
    print(json.dumps(to_dict(record), indent=2, sort_keys=True))


def _format_maybe(value: object) -> str:
    if is_resolved(value):
        rendered = getattr(value, "value", value)
        return str(rendered)
    reason = getattr(value, "reason", None)
    if reason is not None:
        return f"unresolved({reason.value})"
    return "unresolved"


def _format_bytes_human(value: object) -> str:
    """CLI-only display. Canonical contract values remain integer bytes."""
    if not is_resolved(value) or not isinstance(value, int):
        return "-"
    gib = 1024 * 1024 * 1024
    whole, remainder = divmod(value, gib)
    if remainder == 0:
        return f"{whole} GiB"
    mib = 1024 * 1024
    mib_whole, mib_remainder = divmod(value, mib)
    if mib_remainder == 0:
        return f"{mib_whole} MiB"
    return f"{whole} GiB + {remainder} bytes"


def _require_journal_dir(ns: argparse.Namespace) -> Path:
    if ns.journal_dir is None:
        raise ValidationError(
            "journal directory is required; Kernel does not choose an install root",
        )
    return Path(ns.journal_dir)


def _environment_override() -> str | None:
    configured = os.environ.get(STATE_ROOT_VARIABLE, "").strip()
    return configured or None


def _warn_if_defaulted(binding: StateRootBinding) -> None:
    if binding.selection_source is not SelectionSource.PLATFORM_DEFAULT:
        return
    if not build_identity().is_artifact:
        return
    print(
        f"warning: no state root configured; using {binding.root}\n"
        f"         set {STATE_ROOT_VARIABLE} or pass --state-root to keep "
        f"durable state in a chosen location",
        file=sys.stderr,
    )


def _model_runtime(
    *,
    runtime_python: Path | None,
    foundation_id: str,
    qualification: str,
) -> RuntimeView:
    """Query the managed interpreter when one is supplied. Do not guess."""
    architectures: frozenset[str] = frozenset()
    quantizations: frozenset[str] = frozenset()
    capability_known = False
    if runtime_python is not None:
        with tempfile.TemporaryDirectory() as tmp:
            architectures, quantizations, predicates = query_runtime(
                runtime_python,
                Path(tmp) / "runtime.json",
            )
        capability_known = bool(architectures)
    else:
        predicates = ()
    return RuntimeView(
        architectures=architectures,
        quantizations=quantizations,
        foundation_id=foundation_id,
        provider_qualification=ProviderQualification(qualification),
        capability_known=capability_known,
        predicates=predicates,
    )


def _device_ceiling(envelope: CapacityEnvelope) -> int | None:
    """Largest single-device SAFE baseline. Devices are not summed."""
    known = [
        int(item.safe_bytes)
        for item in envelope.accelerators
        if is_resolved(item.safe_bytes) and isinstance(item.safe_bytes, int)
    ]
    if not known:
        return None
    return max(known)


def inspect_model(
    *,
    source_path: Path,
    label: str,
    journal_dir_path: Path | None,
    state_root: Path | None = None,
    foundation_id: str = "foundation_unspecified",
    capacity_evidence_id: str = "capacity_unspecified",
    qualification: str = "unknown",
    runtime_python: Path | None = None,
) -> tuple[AvailableModels, tuple[EventRecord, ...]]:
    """Inspect one local directory. This does not download or load weights."""
    validate_registry(module_prefix="machi.")
    observed = dt.datetime.now(dt.UTC)
    runtime = _model_runtime(
        runtime_python=runtime_python,
        foundation_id=foundation_id,
        qualification=qualification,
    )
    view = view_local(source_path, label)
    entry = evaluate_source(
        view,
        source_kind=ModelSourceKind.LOCAL,
        runtime=runtime,
        capacity=None,
        accelerator_safe_bytes=None,
        observed_at=observed,
    )
    if state_root is not None:
        entry = with_stored(state_root, entry)
    settings = default_model_settings()
    snapshot = snapshot_for(
        (entry,),
        foundation_id=foundation_id,
        capacity_evidence_id=capacity_evidence_id,
        policy_token=settings.revision_policy,
        observed_at=observed,
    )
    events_out = model_events(snapshot, clock=FixedClock(observed))
    if journal_dir_path is not None:
        journal = JsonlJournal(journal_dir_path)
        for event in events_out:
            journal.append(event)
    return snapshot, events_out


def _print_model_snapshot(
    snapshot: AvailableModels,
    events_out: tuple[EventRecord, ...],
    journal_dir_path: str | None,
) -> None:
    model_entry = snapshot.entries[0]
    print(f"state    {model_entry.compatibility.state.value}")
    print(f"failure  {model_entry.compatibility.failure.value}")
    print(f"revision {model_entry.definition.immutable_revision}")
    remote = str(model_entry.definition.requires_remote_code).lower()
    print(f"remote   {remote}")
    print("mode     inspect_only")
    journal_shown = (
        str(JsonlJournal(Path(journal_dir_path)).path) if journal_dir_path else "-"
    )
    print(f"journal  {journal_shown}")
    _print_document(snapshot)
    for event in events_out:
        _print_document(event)


def _inspect_hub(
    ns: argparse.Namespace,
) -> tuple[AvailableModels, tuple[EventRecord, ...]]:
    """Resolve one repository revision. Weights stay remote."""
    validate_registry(module_prefix="machi.")
    observed = dt.datetime.now(dt.UTC)
    if ns.state_root:
        cache = cache_root(Path(ns.state_root))
        cache.mkdir(parents=True, exist_ok=True)
        view = inspect_repository(ns.repository, ns.revision, cache=cache)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            view = inspect_repository(ns.repository, ns.revision, cache=Path(tmp))
    runtime = _model_runtime(
        runtime_python=Path(ns.runtime_python) if ns.runtime_python else None,
        foundation_id=ns.foundation_id,
        qualification=ns.qualification,
    )
    capacity = None
    accelerator_safe_bytes = None
    evidence_id = "capacity_unspecified"
    if ns.state_root:
        envelope, _events, _journal = evaluate_capacity(
            explicit=ns.state_root,
            environment=_environment_override(),
            store_dir=Path(ns.store_dir) if ns.store_dir else None,
            journal_dir_path=Path(ns.journal_dir) if ns.journal_dir else None,
        )
        capacity = envelope
        accelerator_safe_bytes = _device_ceiling(envelope)
        evidence_id = envelope.evidence_id
    entry = evaluate_source(
        view,
        source_kind=ModelSourceKind.HUB,
        runtime=runtime,
        capacity=capacity,
        accelerator_safe_bytes=accelerator_safe_bytes,
        observed_at=observed,
    )
    if ns.state_root:
        entry = with_stored(Path(ns.state_root), entry)
    settings = default_model_settings()
    snapshot = snapshot_for(
        (entry,),
        foundation_id=ns.foundation_id,
        capacity_evidence_id=evidence_id,
        policy_token=settings.revision_policy,
        observed_at=observed,
    )
    events_out = model_events(snapshot, clock=FixedClock(observed))
    if ns.journal_dir:
        journal = JsonlJournal(Path(ns.journal_dir))
        for event in events_out:
            journal.append(event)
    return snapshot, events_out


def _planning_inputs(
    ns: argparse.Namespace,
) -> tuple[CapacityEnvelope, RuntimeView, dt.datetime]:
    if not ns.state_root:
        raise ValidationError("state root is required before acquisition")
    envelope, _events, _journal = evaluate_capacity(
        explicit=ns.state_root,
        environment=_environment_override(),
        store_dir=Path(ns.store_dir) if ns.store_dir else None,
        journal_dir_path=Path(ns.journal_dir) if ns.journal_dir else None,
    )
    runtime = _model_runtime(
        runtime_python=Path(ns.runtime_python) if ns.runtime_python else None,
        foundation_id=ns.foundation_id,
        qualification=ns.qualification,
    )
    return envelope, runtime, dt.datetime.now(dt.UTC)


def _finish_store(
    ns: argparse.Namespace,
    stored: StoreResult,
    observed: dt.datetime,
) -> int:
    events_out = acquisition_events(
        artifact=stored.artifact,
        failure=stored.failure,
        artifact_id=stored.artifact_id,
        clock=FixedClock(observed),
    )
    if ns.journal_dir:
        journal = JsonlJournal(Path(ns.journal_dir))
        for event in events_out:
            journal.append(event)
    print(f"failure  {stored.failure.value}")
    lifecycle = stored.artifact.lifecycle.value if stored.artifact is not None else "-"
    print(f"lifecycle {lifecycle}")
    if stored.artifact is not None:
        print(f"revision {stored.artifact.immutable_revision}")
        print(f"bytes    {stored.artifact.total_bytes}")
        print(f"files    {len(stored.artifact.files)}")
    for event in events_out:
        _print_document(event)
    if stored.failure is ModelFailure.NONE:
        return 0
    return 2


def _import_local(ns: argparse.Namespace) -> int:
    envelope, runtime, observed = _planning_inputs(ns)
    stored = store_local(
        Path(ns.state_root),
        Path(ns.path),
        ns.label,
        runtime=runtime,
        capacity=envelope,
        accelerator_safe_bytes=_device_ceiling(envelope),
        observed_at=observed,
    )
    return _finish_store(ns, stored, observed)


def _acquire_hub(ns: argparse.Namespace) -> int:
    envelope, runtime, observed = _planning_inputs(ns)
    cache = cache_root(Path(ns.state_root))
    try:
        view = inspect_repository(ns.repository, ns.revision, cache=cache)
    except ValidationError as exc:
        try:
            failure = ModelFailure(exc.message)
        except ValueError:
            failure = ModelFailure.SOURCE_UNAVAILABLE
        print(f"failure  {failure.value}")
        print("lifecycle -")
        return 2

    def _fetch(destination: Path, relative_paths: tuple[str, ...]) -> None:
        fetch_files(
            view,
            destination,
            relative_paths,
            cache=cache,
            timeout_seconds=DEFAULT_TIMEOUT,
        )

    stored = store_view(
        Path(ns.state_root),
        view,
        source_kind=ModelSourceKind.HUB,
        fetch=_fetch,
        runtime=runtime,
        capacity=envelope,
        accelerator_safe_bytes=_device_ceiling(envelope),
        observed_at=observed,
        credential_present=credential_supplied(),
    )
    return _finish_store(ns, stored, observed)


def start_serving(
    configuration: DeploymentConfiguration,
    reservation_id: str,
    selection: FoundationSelection,
    generation: ManagedGeneration,
    artifact: ModelArtifact,
    *,
    model_path: Path,
    store: FileStore,
    state_root: Path,
    artifact_verified: bool,
) -> ServeDecision:
    """Start the reserved vLLM runtime. This does not admit or provision."""
    validate_registry(module_prefix="machi.")
    service = ServeService(
        StoreServeLog(store),
        VllmServeProvider(NativeProcessRunner(), SystemClock()),
        ResourceManager(StoreReservationLog(store), FileAdmissionLock(store.root)),
        ServePolicy(),
        SystemClock(),
        state_root,
        choose_port,
    )
    return service.start(
        configuration,
        reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=artifact_verified,
    )


def qualify_reserved(
    configuration: DeploymentConfiguration,
    reservation_id: str,
    selection: FoundationSelection,
    generation: ManagedGeneration,
    artifact: ModelArtifact,
    request: QualificationRequest,
    *,
    model_path: Path,
    store: FileStore,
    state_root: Path,
    artifact_verified: bool,
    sample_peaks: Callable[[], tuple[int | None, int | None]] | None = None,
) -> QualificationEvidence:
    """Run one reserved vLLM proof and persist qualification evidence.

    This is not catalogue discovery. The caller already chose the candidate.
    """
    validate_registry(module_prefix="machi.")
    service = ServeService(
        StoreServeLog(store),
        VllmServeProvider(NativeProcessRunner(), SystemClock()),
        ResourceManager(StoreReservationLog(store), FileAdmissionLock(store.root)),
        ServePolicy(),
        SystemClock(),
        state_root,
        choose_port,
    )
    started_at = time.monotonic()
    started = service.start(
        configuration,
        reservation_id,
        selection,
        generation,
        artifact,
        model_path=model_path,
        artifact_verified=artifact_verified,
    )
    load_seconds = time.monotonic() - started_at
    ready = started.outcome is ServeOutcome.READY
    proved = None
    generate_seconds = None
    if ready and is_resolved(started.instance):
        prove_started = time.monotonic()
        proved = service.prove(started.instance.instance_id)
        generate_seconds = time.monotonic() - prove_started
    instance = started.instance if is_resolved(started.instance) else None
    if proved is not None and is_resolved(proved.instance):
        instance = proved.instance
    peak_vram_bytes = None
    peak_ram_bytes = None
    if sample_peaks is not None and ready:
        peak_vram_bytes, peak_ram_bytes = sample_peaks()
    if instance is not None and instance.state is not InstanceState.STOPPED:
        service.stop(instance.instance_id)
        service.release_after_stop(instance.instance_id)
    tokens = None
    failure = started.failure.value
    proved_ok = proved is not None and proved.outcome is ServeOutcome.PROVEN
    if proved is not None:
        failure = proved.failure.value
        proof = proved.proof
        if is_resolved(proof) and isinstance(proof.completion_tokens, int):
            tokens = proof.completion_tokens
    return evidence_for_probe(
        request,
        artifact_id=artifact.artifact_id,
        ready=ready,
        proved=proved_ok and isinstance(tokens, int) and tokens > 0,
        failure=failure,
        completion_tokens=tokens,
        load_seconds=load_seconds,
        generate_seconds=generate_seconds,
        peak_vram_bytes=peak_vram_bytes,
        peak_ram_bytes=peak_ram_bytes,
        observed_at=dt.datetime.now(dt.UTC),
    )


def admit_resources(
    decision: PlanDecision,
    capacity: CapacityEnvelope,
    plan_currency: PlanFailure,
    store: FileStore,
) -> AdmissionDecision:
    """Reserve a current plan. This does not start a runtime."""
    validate_registry(module_prefix="machi.")
    manager = ResourceManager(
        StoreReservationLog(store),
        FileAdmissionLock(store.root),
    )
    return manager.admit(decision, capacity, plan_currency)


def _inspect_reservations(store_dir: Path) -> int:
    """Print stored holds. Reconciliation still needs a live envelope."""
    store = FileStore(store_dir)
    log = StoreReservationLog(store)
    manager = ResourceManager(log, FileAdmissionLock(store.root))
    records, malformed = log.reservations()
    print(f"reservations {len(records)}")
    for item in records:
        visible = manager.get_reservation(item.reservation_id)
        state = visible.state.value if visible is not None else item.state.value
        print(f"id       {item.reservation_id}")
        print(f"state    {state}")
        print(f"plan     {item.plan_id}")
        print(f"finger   {item.fingerprint}")
        print(f"capacity {item.capacity_evidence_id}")
        print(f"device   {item.accelerator_identity}")
        print(f"accel    {item.accelerator_memory_bytes}")
        print(f"host     {item.host_memory_bytes}")
        print(f"persist  {item.persistent_bytes}")
        print(f"transient {item.transient_bytes}")
        print(f"cpu      {item.cpu_count}")
        print(f"policy   {item.policy_version}")
    print(f"malformed {malformed}")
    print("refusals none_stored")
    print("reconcile capacity_required")
    return 0


def compose_plan(inputs: PlanInputs) -> PlanDecision:
    """Compose one vLLM plan. This does not admit, load, or launch."""
    validate_registry(module_prefix="machi.")
    return compose_plan_domain(inputs, build_vllm_recipe)


def _export_rukan_analytics(ns: argparse.Namespace) -> int:
    """Write one analytics bundle. This does not change operational state."""
    from machi.adapters.rukan.analytics_export import export_analytics, write_analytics
    from machi.kernel.build import identity

    text = export_analytics(
        Path(ns.store_dir),
        Path(ns.journal_dir) if ns.journal_dir else None,
        identity(),
        exported_at=dt.datetime.now(dt.UTC).isoformat(),
    )
    write_analytics(Path(ns.output), text)
    print("product  Rukan")
    print(f"bundle   {ns.output}")
    print("network  false")
    return 0


def _serve_rukan_command_center(ns: argparse.Namespace) -> int:
    """Bind the loopback Command Center. The browser is not the store."""
    from machi.adapters.rukan.hub import CommandHub, serve_command_center

    hub = CommandHub(Path(ns.data_dir))
    print("product  Rukan Command Center")
    print(f"bind     127.0.0.1:{ns.port}")
    print("store    sqlite")
    serve_command_center(
        hub,
        port=ns.port,
        static_dir=Path(ns.static_dir) if ns.static_dir else None,
    )
    return 0


def _serve_rukan_admin(ns: argparse.Namespace) -> int:
    """Bind the loopback Rukan Admin seam. It does not choose a runtime."""
    from machi.adapters.rukan.complete import store_completer
    from machi.adapters.rukan.lifecycle import LifecycleOwner
    from machi.adapters.rukan.server import (
        AdminApplication,
        AdminHandlers,
        serve_admin,
    )
    from machi.kernel.build import identity

    if not str(ns.provider_base).startswith("http://127.0.0.1:"):
        raise ValidationError("provider base must be loopback")
    application = AdminApplication(
        Path(ns.store_dir),
        identity(),
        journal_dir=Path(ns.journal_dir) if ns.journal_dir else None,
        static_dir=Path(ns.static_dir) if ns.static_dir else None,
        handlers=AdminHandlers(
            complete=store_completer(Path(ns.store_dir), ns.provider_base),
            inspect_model=lambda body: _admin_inspect(ns, body),
            import_model=lambda body: _admin_import(ns, body),
            acquire_model=lambda body: _admin_acquire(ns, body),
        ),
        lifecycle=LifecycleOwner(
            Path(ns.store_dir),
            provider_base=ns.provider_base,
            state_root=Path(getattr(ns, "state_root", None) or ns.store_dir),
        ),
    )
    print("product  Rukan Admin")
    print(f"bind     127.0.0.1:{ns.port}")
    serve_admin(application, port=ns.port)
    return 0


def _admin_inspect(
    ns: argparse.Namespace, body: dict[str, object]
) -> tuple[str, str, dict[str, object]]:
    source = body.get("source_path")
    label = body.get("label")
    if not isinstance(source, str) or not isinstance(label, str) or not label:
        return "refused", "inspect requires source_path and label", {}
    try:
        snapshot, _events = inspect_model(
            source_path=Path(source),
            label=label,
            journal_dir_path=None,
            state_root=Path(ns.state_root) if ns.state_root else None,
        )
    except MachiError as exc:
        return "refused", exc.message, {}
    entry = snapshot.entries[0]
    return (
        "ok",
        "inspected",
        {
            "state": entry.compatibility.state.value,
            "failure": entry.compatibility.failure.value,
            "revision": entry.definition.immutable_revision,
        },
    )


def _admin_import(
    ns: argparse.Namespace, body: dict[str, object]
) -> tuple[str, str, dict[str, object]]:
    if not ns.state_root:
        return "refused", "state root is not configured", {}
    source = body.get("source_path")
    label = body.get("label")
    if not isinstance(source, str) or not isinstance(label, str) or not label:
        return "refused", "import requires source_path and label", {}
    holder = argparse.Namespace(
        state_root=ns.state_root,
        path=source,
        label=label,
        store_dir=ns.store_dir,
        journal_dir=None,
        foundation_id="foundation_unspecified",
        qualification="unknown",
        runtime_python=None,
    )
    try:
        envelope, runtime, observed = _planning_inputs(holder)
        stored = store_local(
            Path(ns.state_root),
            Path(source),
            label,
            runtime=runtime,
            capacity=envelope,
            accelerator_safe_bytes=_device_ceiling(envelope),
            observed_at=observed,
        )
    except MachiError as exc:
        return "refused", exc.message, {}
    artifact_id = stored.artifact_id or "not_recorded"
    return "ok" if stored.failure.value == "none" else "failed", stored.failure.value, {
        "artifact_id": artifact_id,
        "failure": stored.failure.value,
    }


def _admin_acquire(
    ns: argparse.Namespace, body: dict[str, object]
) -> tuple[str, str, dict[str, object]]:
    if not ns.state_root:
        return "refused", "state root is not configured", {}
    repository = body.get("repository")
    revision = body.get("revision")
    if not isinstance(repository, str) or not isinstance(revision, str):
        return "refused", "acquire requires repository and revision", {}
    holder = argparse.Namespace(
        state_root=ns.state_root,
        repository=repository,
        revision=revision,
        store_dir=ns.store_dir,
        journal_dir=None,
        foundation_id="foundation_unspecified",
        qualification="unknown",
        runtime_python=None,
    )
    try:
        code = _acquire_hub(holder)
    except MachiError as exc:
        return "refused", exc.message, {}
    if code == 0:
        return "ok", "acquired", {"repository": repository, "revision": revision}
    return "failed", "acquire did not store the revision", {
        "repository": repository,
        "revision": revision,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="machi", description="Machi")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="identify this Machi artifact or checkout")

    kernel = sub.add_parser("kernel", help="Kernel (Block 0) commands")
    kernel_sub = kernel.add_subparsers(dest="kernel_command", required=True)

    prove = kernel_sub.add_parser(
        "prove",
        help="append one kernel.alive event to an injected journal directory",
    )
    prove.add_argument(
        "--journal-dir",
        required=True,
        help="directory for events.jsonl; Kernel does not choose the Install root",
    )

    events = kernel_sub.add_parser(
        "events",
        help="read back EventRecord documents from an injected journal directory",
    )
    events.add_argument("--journal-dir", required=True)

    store_put = kernel_sub.add_parser(
        "store-put",
        help="create or re-enter a Kernel StoreProof under an injected store root",
    )
    store_put.add_argument(
        "--store-dir",
        required=True,
        help="injected Store root; Kernel does not choose the Install state root",
    )
    store_put.add_argument("--key", required=True, help="caller-owned logical identity")
    store_put.add_argument(
        "--token",
        default="prove",
        help="opaque proof token; not a domain entity",
    )
    store_put.add_argument(
        "--journal-dir",
        default=None,
        help="optional journal for kernel.store.proved; Store does not require it",
    )
    store_get = kernel_sub.add_parser(
        "store-get",
        help="read a Kernel StoreProof from an injected store root",
    )
    store_get.add_argument("--store-dir", required=True)
    store_get.add_argument("--key", required=True)

    install = sub.add_parser("install", help="Install (Block 1) commands")
    install_sub = install.add_subparsers(dest="install_command", required=True)
    bind = install_sub.add_parser(
        "bind-root",
        help="resolve and establish this installation's state root",
    )
    bind.add_argument(
        "--state-root",
        default=None,
        help="explicit state root; wins over MACHI_STATE_ROOT and the default",
    )
    bind.add_argument(
        "--journal-dir",
        default=None,
        help="Kernel journal directory; defaults to <state-root>/journal",
    )
    mark = install_sub.add_parser(
        "mark-local",
        help="bind the state root then write or validate local ownership evidence",
    )
    mark.add_argument(
        "--state-root",
        default=None,
        help="explicit state root consumed via 1.2.1; 1.3.1 does not re-resolve policy",
    )
    mark.add_argument(
        "--journal-dir",
        default=None,
        help="Kernel journal directory; defaults to <state-root>/journal",
    )
    seed = install_sub.add_parser(
        "seed-registry",
        help="bind, mark locally, then seed the control-plane ownership registry",
    )
    seed.add_argument(
        "--state-root",
        default=None,
        help="explicit state root consumed via 1.2.1 and 1.3.1",
    )
    seed.add_argument(
        "--registry-store-dir",
        required=True,
        help="injected control-plane Store root; not chosen from the state root",
    )
    seed.add_argument(
        "--journal-dir",
        default=None,
        help="Kernel journal directory; defaults to <state-root>/journal",
    )
    establish = install_sub.add_parser(
        "establish-record",
        help="bind, mark, seed registry, then persist a stable InstallRecord",
    )
    establish.add_argument(
        "--state-root",
        default=None,
        help="explicit state root consumed via 1.2.1, 1.3.1, and 1.3.2",
    )
    establish.add_argument(
        "--store-dir",
        required=True,
        help="injected control-plane Store root; same tree as seed-registry",
    )
    establish.add_argument(
        "--journal-dir",
        default=None,
        help="Kernel journal directory; defaults to <state-root>/journal",
    )
    establish_run = install_sub.add_parser(
        "establish-run",
        help="bind, mark, seed, persist InstallRecord, then persist InstallRun",
    )
    establish_run.add_argument(
        "--state-root",
        default=None,
        help="explicit state root consumed via 1.2.1 through 1.1.1",
    )
    establish_run.add_argument(
        "--store-dir",
        required=True,
        help="injected control-plane Store root; same tree as establish-record",
    )
    establish_run.add_argument(
        "--journal-dir",
        default=None,
        help="Kernel journal directory; defaults to <state-root>/journal",
    )

    discover = sub.add_parser("discover", help="Discover (Block 2) commands")
    discover_sub = discover.add_subparsers(dest="discover_command", required=True)
    os_arch = discover_sub.add_parser(
        "os-arch",
        help="observe OS family and CPU architecture; does not mint HostId",
    )
    os_arch.add_argument(
        "--state-root",
        default=None,
        help="explicit state root used only to re-enter M1 correlation",
    )
    os_arch.add_argument(
        "--store-dir",
        default=None,
        help="injected control-plane Store; required to resolve InstallId/InstallRunId",
    )
    os_arch.add_argument(
        "--journal-dir",
        default=None,
        help="journal directory; defaults to <state-root>/journal when Store is set",
    )
    memory = discover_sub.add_parser(
        "memory",
        help="observe reported physical/system memory; not safe capacity",
    )
    memory.add_argument(
        "--state-root",
        default=None,
        help="explicit state root used only to re-enter M1 correlation",
    )
    memory.add_argument(
        "--store-dir",
        default=None,
        help="injected control-plane Store; required to resolve InstallId/InstallRunId",
    )
    memory.add_argument(
        "--journal-dir",
        default=None,
        help="journal directory; defaults to <state-root>/journal when Store is set",
    )
    accelerator = discover_sub.add_parser(
        "accelerator",
        help="observe accelerator devices; not capacity or a primary-GPU view",
    )
    accelerator.add_argument(
        "--state-root",
        default=None,
        help="explicit state root used only to re-enter M1 correlation",
    )
    accelerator.add_argument(
        "--store-dir",
        default=None,
        help="injected control-plane Store; required to resolve InstallId/InstallRunId",
    )
    accelerator.add_argument(
        "--journal-dir",
        default=None,
        help="journal directory; defaults to <state-root>/journal when Store is set",
    )
    mounts = discover_sub.add_parser(
        "mounts",
        help="observe filesystem/mount topology; not SAFE storage capacity",
    )
    mounts.add_argument(
        "--state-root",
        default=None,
        help="explicit state root used only to re-enter M1 correlation",
    )
    mounts.add_argument(
        "--store-dir",
        default=None,
        help="injected control-plane Store; required to resolve InstallId/InstallRunId",
    )
    mounts.add_argument(
        "--journal-dir",
        default=None,
        help="journal directory; defaults to <state-root>/journal when Store is set",
    )
    mounts.add_argument(
        "--write-probe",
        action="store_true",
        help="enable a tiny observational write probe; never fill-until-failure",
    )

    steward = sub.add_parser(
        "steward",
        help="classify ownership and occupancy; does not delete",
    )
    steward_sub = steward.add_subparsers(dest="steward_command", required=True)
    assess = steward_sub.add_parser(
        "assess",
        help="classify caller-supplied roots; never crawl mounts or delete",
    )
    assess.add_argument("--state-root", default=None, help="known managed root")
    assess.add_argument(
        "--store-dir",
        default=None,
        help="injected control-plane Store used only to read ownership records",
    )
    assess.add_argument(
        "--journal-dir",
        default=None,
        help="journal directory; defaults to an existing <state-root>/journal",
    )
    assess.add_argument(
        "--generation",
        choices=["current", "obsolete", "abandoned", "rollback"],
        default="current",
        help="caller-supplied generation; never inferred from the path name",
    )
    assess.add_argument(
        "--protection",
        choices=["default", "rollback", "evidence", "policy", "unprotected"],
        default="default",
        help="caller-supplied protection; active resources stay protected",
    )

    capacity = sub.add_parser(
        "capacity",
        help="derive a SAFE planning envelope; does not admit or run Sonar by default",
    )
    capacity_sub = capacity.add_subparsers(dest="capacity_command", required=True)
    evaluate = capacity_sub.add_parser(
        "evaluate",
        help="compose reported, proven, and SAFE ceilings from current observations",
    )
    evaluate.add_argument("--state-root", default=None)
    evaluate.add_argument("--store-dir", default=None)
    evaluate.add_argument("--journal-dir", default=None)

    foundation = sub.add_parser(
        "foundation",
        help="resolve or provision a managed native vLLM foundation",
    )
    foundation_sub = foundation.add_subparsers(dest="foundation_command", required=True)
    foundation_inspect = foundation_sub.add_parser(
        "inspect",
        help="resolve support without installing",
    )
    foundation_provision = foundation_sub.add_parser(
        "provision",
        help="create or reuse a managed vLLM generation",
    )
    for foundation_command in (foundation_inspect, foundation_provision):
        foundation_command.add_argument("--state-root", default=None)
        foundation_command.add_argument("--store-dir", default=None)
        foundation_command.add_argument("--journal-dir", default=None)
        foundation_command.add_argument(
            "--backend",
            choices=list(BACKEND_CHOICES),
            default="auto",
        )

    model = sub.add_parser(
        "model",
        help="inspect or import a model artifact; does not load or serve it",
    )
    model_sub = model.add_subparsers(dest="model_command", required=True)
    model_inspect = model_sub.add_parser(
        "inspect",
        help="read local metadata and assess compatibility; no weight download",
    )
    model_import = model_sub.add_parser(
        "import",
        help="copy a local artifact into the owned warehouse",
    )
    model_acquire = model_sub.add_parser(
        "acquire",
        help="download one explicit hub revision into the warehouse",
    )
    for model_command in (model_inspect, model_import, model_acquire):
        model_command.add_argument("--state-root", default=None)
        model_command.add_argument("--store-dir", default=None)
        model_command.add_argument("--journal-dir", default=None)
        model_command.add_argument("--foundation-id", default="foundation_unspecified")
        model_command.add_argument(
            "--qualification",
            choices=["qualified", "deferred", "unknown"],
            default="unknown",
        )
        model_command.add_argument("--runtime-python", default=None)
    model_inspect.add_argument("--path", default=None)
    model_inspect.add_argument("--label", default=None)
    model_inspect.add_argument("--repository", default=None)
    model_inspect.add_argument("--revision", default="main")
    model_import.add_argument("--path", required=True)
    model_import.add_argument("--label", required=True)
    model_acquire.add_argument("--repository", required=True)
    model_acquire.add_argument("--revision", default="main")

    plan = sub.add_parser(
        "plan",
        help="show the planning policy; composition does not admit or launch",
    )
    plan_sub = plan.add_subparsers(dest="plan_command", required=True)
    plan_sub.add_parser(
        "policy",
        help="print the versioned single-accelerator defaults",
    )

    admit = sub.add_parser(
        "admit",
        help="inspect stored holds or print policy; this command does not serve",
    )
    admit_sub = admit.add_subparsers(dest="admit_command", required=True)
    admit_sub.add_parser("policy", help="print the admission policy version")

    serve = sub.add_parser(
        "serve",
        help="show the serving policy; this command does not start a runtime",
    )
    serve_sub = serve.add_subparsers(dest="serve_command", required=True)
    serve_sub.add_parser("policy", help="print the native vLLM serve bounds")

    admin = sub.add_parser(
        "admin",
        help="serve the loopback Rukan Admin seam; this does not admit",
    )
    admin_sub = admin.add_subparsers(dest="admin_command", required=True)
    admin_serve = admin_sub.add_parser(
        "serve",
        help="bind 127.0.0.1 and project stored deployment evidence",
    )
    admin_serve.add_argument("--store-dir", required=True)
    admin_serve.add_argument("--journal-dir", default=None)
    admin_serve.add_argument("--static-dir", default=None)
    admin_serve.add_argument("--port", type=int, default=8765)
    admin_serve.add_argument("--state-root", default=None)

    analytics = sub.add_parser(
        "analytics",
        help="read-only Rukan analytics export; this does not mutate state",
    )
    analytics_sub = analytics.add_subparsers(dest="analytics_command", required=True)
    analytics_export = analytics_sub.add_parser(
        "export",
        help="write one versioned JSONL bundle from the local store and journal",
    )
    analytics_export.add_argument("--store-dir", required=True)
    analytics_export.add_argument("--journal-dir", default=None)
    analytics_export.add_argument("--output", required=True)

    command_center = sub.add_parser(
        "command-center",
        help="serve the loopback Rukan Command Center; this does not admit",
    )
    command_sub = command_center.add_subparsers(
        dest="command_center_command", required=True
    )
    command_serve = command_sub.add_parser(
        "serve",
        help="bind 127.0.0.1, own SQLite, and scan the inbox on refresh",
    )
    command_serve.add_argument("--data-dir", required=True)
    command_serve.add_argument("--port", type=int, default=8780)
    command_serve.add_argument("--static-dir", default=None)
    admin_serve.add_argument(
        "--provider-base",
        default="http://127.0.0.1:11434",
        help="loopback provider API used only after a READY provider instance",
    )
    inspect = admit_sub.add_parser(
        "inspect",
        help="print stored holds; does not admit, release, or serve",
    )
    inspect.add_argument("--store-dir", required=True)

    readiness = sub.add_parser(
        "prerequisites",
        help="inspect and optionally remediate environment prerequisites",
    )
    readiness_sub = readiness.add_subparsers(
        dest="prerequisites_command", required=True
    )
    check = readiness_sub.add_parser(
        "check",
        help="inspect/diagnose/plan a vendor CLI; mutate only with remediate policy",
    )
    check.add_argument(
        "--policy",
        choices=["observe_only", "plan_only", "remediate"],
        default="plan_only",
        help="observe_only and plan_only never mutate; remediate is allowlisted",
    )
    check.add_argument(
        "--state-root",
        default=None,
        help="explicit state root used only to re-enter M1 correlation",
    )
    check.add_argument(
        "--store-dir",
        default=None,
        help="injected control-plane Store; required to resolve InstallId/InstallRunId",
    )
    check.add_argument(
        "--journal-dir",
        default=None,
        help="journal directory; defaults to <state-root>/journal when Store is set",
    )

    ns = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if ns.command == "version":
            return show_version()
        if ns.command == "kernel" and ns.kernel_command == "prove":
            event = prove_alive(_require_journal_dir(ns))
            print(f"journal  {JsonlJournal(_require_journal_dir(ns)).path}")
            _print_document(event)
            return 0
        if ns.command == "kernel" and ns.kernel_command == "events":
            records, defects = read_events(_require_journal_dir(ns))
            print(f"records  {len(records)}")
            print(f"defects  {len(defects)}")
            for record in records:
                _print_document(record)
            for defect in defects:
                _print_document(defect)
            return 0
        if ns.command == "kernel" and ns.kernel_command == "store-put":
            proof, created, existed, proof_event, store_root = put_store_proof(
                store_dir_path=Path(ns.store_dir),
                key=ns.key,
                token=ns.token,
                journal_dir_path=Path(ns.journal_dir) if ns.journal_dir else None,
            )
            print(f"store    {store_root}")
            print(f"created  {str(created).lower()}")
            print(f"existed  {str(existed).lower()}")
            print(f"kind     {proof.kind}")
            _print_document(proof)
            if proof_event is not None:
                _print_document(proof_event)
            return 0
        if ns.command == "kernel" and ns.kernel_command == "store-get":
            proof = get_store_proof(store_dir_path=Path(ns.store_dir), key=ns.key)
            print(f"kind     {proof.kind}")
            _print_document(proof)
            return 0
        if ns.command == "install" and ns.install_command == "bind-root":
            binding, event, target = bind_state_root(
                explicit=ns.state_root,
                environment=_environment_override(),
                journal_dir_path=Path(ns.journal_dir) if ns.journal_dir else None,
            )
            _warn_if_defaulted(binding)
            print(f"root     {binding.root}")
            print(f"source   {binding.selection_source.value}")
            print(f"existed  {str(binding.existed).lower()}")
            print(f"created  {str(binding.created).lower()}")
            print(f"journal  {JsonlJournal(target).path}")
            _print_document(binding)
            _print_document(event)
            return 0
        if ns.command == "install" and ns.install_command == "mark-local":
            binding, _bind_event, establishment, mark_event, target = (
                mark_local_ownership(
                    explicit=ns.state_root,
                    environment=_environment_override(),
                    journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
                )
            )
            _warn_if_defaulted(binding)
            print(f"root     {binding.root}")
            print(f"marker   {Path(binding.root) / MACHI_OWNER_FILENAME}")
            print(f"status   {establishment.status.value}")
            print(f"dual     {str(establishment.dual_ownership).lower()}")
            print(f"destroy  {str(establishment.destructive_authorization).lower()}")
            print(f"journal  {JsonlJournal(target).path}")
            _print_document(establishment)
            _print_document(mark_event)
            return 0
        if ns.command == "install" and ns.install_command == "seed-registry":
            binding, establishment, seeded, seed_event, target, registry_root = (
                seed_local_registry(
                    explicit=ns.state_root,
                    environment=_environment_override(),
                    registry_store_dir=Path(ns.registry_store_dir),
                    journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
                )
            )
            _warn_if_defaulted(binding)
            print(f"root     {binding.root}")
            print(f"marker   {Path(binding.root) / MACHI_OWNER_FILENAME}")
            print(f"registry {registry_root}")
            print(f"status   {seeded.status.value}")
            print(f"dual     {str(seeded.dual_ownership).lower()}")
            print(f"destroy  {str(seeded.destructive_authorization).lower()}")
            print(f"created  {str(seeded.created).lower()}")
            print(f"existed  {str(seeded.existed).lower()}")
            print(f"journal  {JsonlJournal(target).path}")
            _print_document(establishment)
            _print_document(seeded)
            _print_document(seed_event)
            return 0
        if ns.command == "install" and ns.install_command == "establish-record":
            (
                binding,
                _establishment,
                _seeded,
                established,
                record_event,
                target,
                store_root,
            ) = establish_install_record(
                explicit=ns.state_root,
                environment=_environment_override(),
                store_dir=Path(ns.store_dir),
                journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
            )
            _warn_if_defaulted(binding)
            print(f"root     {binding.root}")
            print(f"marker   {Path(binding.root) / MACHI_OWNER_FILENAME}")
            print(f"store    {store_root}")
            print(f"install  {established.record.install_id.value}")
            print(f"status   {established.status.value}")
            print(f"dual     {str(established.dual_ownership).lower()}")
            print(f"destroy  {str(established.destructive_authorization).lower()}")
            print(f"created  {str(established.created).lower()}")
            print(f"existed  {str(established.existed).lower()}")
            print(f"journal  {JsonlJournal(target).path}")
            _print_document(established)
            _print_document(record_event)
            return 0
        if ns.command == "install" and ns.install_command == "establish-run":
            (
                binding,
                _establishment,
                _seeded,
                established,
                run,
                bound_event,
                target,
                store_root,
            ) = establish_install_run(
                explicit=ns.state_root,
                environment=_environment_override(),
                store_dir=Path(ns.store_dir),
                journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
            )
            _warn_if_defaulted(binding)
            print(f"root     {binding.root}")
            print(f"marker   {Path(binding.root) / MACHI_OWNER_FILENAME}")
            print(f"store    {store_root}")
            print(f"install  {established.record.install_id.value}")
            print(f"run      {run.record.install_run_id.value}")
            print(f"status   {run.status.value}")
            print(f"dual     {str(run.dual_ownership).lower()}")
            print(f"destroy  {str(run.destructive_authorization).lower()}")
            print(f"created  {str(run.created).lower()}")
            print(f"existed  {str(run.existed).lower()}")
            print(f"journal  {JsonlJournal(target).path}")
            _print_document(run)
            _print_document(bound_event)
            return 0
        if ns.command == "discover" and ns.discover_command == "os-arch":
            observation, event, install_id, install_run_id, journal_target = (
                observe_os_architecture(
                    explicit=ns.state_root,
                    environment=_environment_override(),
                    store_dir=Path(ns.store_dir) if ns.store_dir else None,
                    journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
                )
            )
            print(f"os       {_format_maybe(observation.os_family)}")
            print(f"arch     {_format_maybe(observation.architecture)}")
            print(f"os_stat  {observation.os_status.value}")
            print(f"arch_st  {observation.architecture_status.value}")
            print(f"raw_os   {observation.raw_os or '-'}")
            print(f"raw_arch {observation.raw_architecture or '-'}")
            print(f"observer {observation.observer}")
            print(f"install  {_format_maybe(install_id)}")
            print(f"run      {_format_maybe(install_run_id)}")
            print(f"host     {_format_maybe(event.host_id)}")
            journal_shown = (
                str(JsonlJournal(journal_target).path)
                if journal_target is not None
                else "-"
            )
            print(f"journal  {journal_shown}")
            _print_document(observation)
            _print_document(event)
            return 0
        if ns.command == "discover" and ns.discover_command == "memory":
            memory_observation, event, install_id, install_run_id, journal_target = (
                observe_memory(
                    explicit=ns.state_root,
                    environment=_environment_override(),
                    store_dir=Path(ns.store_dir) if ns.store_dir else None,
                    journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
                )
            )
            print(f"total    {_format_maybe(memory_observation.physical_total_bytes)}")
            print(
                "human    "
                + _format_bytes_human(memory_observation.physical_total_bytes)
            )
            print(f"status   {memory_observation.physical_total_status.value}")
            print(f"source   {memory_observation.source.value}")
            print(f"observer {memory_observation.observer}")
            print(f"raw      {memory_observation.raw_total or '-'}")
            print(f"install  {_format_maybe(install_id)}")
            print(f"run      {_format_maybe(install_run_id)}")
            print(f"host     {_format_maybe(event.host_id)}")
            journal_shown = (
                str(JsonlJournal(journal_target).path)
                if journal_target is not None
                else "-"
            )
            print(f"journal  {journal_shown}")
            _print_document(memory_observation)
            _print_document(event)
            return 0
        if ns.command == "discover" and ns.discover_command == "accelerator":
            (
                accelerator_observation,
                event,
                install_id,
                install_run_id,
                journal_target,
            ) = observe_accelerator(
                explicit=ns.state_root,
                environment=_environment_override(),
                store_dir=Path(ns.store_dir) if ns.store_dir else None,
                journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
            )
            print(f"devices  {len(accelerator_observation.devices)}")
            print(f"status   {accelerator_observation.status.value}")
            print(f"observer {accelerator_observation.observer}")
            for provider_report in accelerator_observation.providers:
                count = (
                    f" devices={provider_report.device_count}"
                    if is_resolved(provider_report.device_count)
                    else ""
                )
                detail = f" {provider_report.detail}" if provider_report.detail else ""
                print(
                    "provider "
                    f"{provider_report.provider} "
                    f"{provider_report.status.value}{count}{detail}"
                )
            for device in accelerator_observation.devices:
                print(
                    "device   "
                    f"{device.ordinal} "
                    f"{_format_maybe(device.vendor)} "
                    f"{device.model_name or '-'} "
                    f"{_format_maybe(device.device_type)} "
                    f"{_format_maybe(device.memory_topology)} "
                    f"{_format_maybe(device.memory_total_bytes)} "
                    f"{device.identity} "
                    f"{device.source.value}"
                )
            print(f"install  {_format_maybe(install_id)}")
            print(f"run      {_format_maybe(install_run_id)}")
            print(f"host     {_format_maybe(event.host_id)}")
            journal_shown = (
                str(JsonlJournal(journal_target).path)
                if journal_target is not None
                else "-"
            )
            print(f"journal  {journal_shown}")
            _print_document(accelerator_observation)
            _print_document(event)
            return 0
        if ns.command == "discover" and ns.discover_command == "mounts":
            mount_observation, event, install_id, install_run_id, journal_target = (
                observe_mounts(
                    explicit=ns.state_root,
                    environment=_environment_override(),
                    store_dir=Path(ns.store_dir) if ns.store_dir else None,
                    journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
                    write_probe=ns.write_probe,
                )
            )
            print(f"entries  {len(mount_observation.entries)}")
            print(f"status   {mount_observation.status.value}")
            print(f"observer {mount_observation.observer}")
            print(f"provider {mount_observation.provider}")
            print(f"ns       {mount_observation.namespace_context.value}")
            print(f"invalid  {mount_observation.invalid_record_count}")
            print(f"probe    {mount_observation.settings.write_probe_policy.value}")
            for entry in mount_observation.entries:
                print(
                    "mount    "
                    f"{entry.mount_id} "
                    f"{entry.mount_point} "
                    f"{entry.filesystem_type or '-'} "
                    f"{entry.access_mode.value} "
                    f"{entry.storage_class.value} "
                    f"{_format_maybe(entry.backing_store_id)} "
                    f"total={_format_maybe(entry.reported_capacity.total_bytes)} "
                    f"free={_format_maybe(entry.reported_capacity.free_bytes)} "
                    f"avail={_format_maybe(entry.reported_capacity.available_bytes)}"
                )
            print(f"install  {_format_maybe(install_id)}")
            print(f"run      {_format_maybe(install_run_id)}")
            print(f"host     {_format_maybe(event.host_id)}")
            journal_shown = (
                str(JsonlJournal(journal_target).path)
                if journal_target is not None
                else "-"
            )
            print(f"journal  {journal_shown}")
            _print_document(mount_observation)
            _print_document(event)
            return 0
        if ns.command == "steward" and ns.steward_command == "assess":
            occupancy, steward_events_out, journal_target = assess_steward(
                explicit=ns.state_root,
                environment=_environment_override(),
                store_dir=Path(ns.store_dir) if ns.store_dir else None,
                journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
                generation=ns.generation,
                protection=ns.protection,
            )
            print(f"resources {len(occupancy.resources)}")
            print(f"provider {occupancy.provider}")
            print(f"delete   {occupancy.destructive_authorization}")
            for resource in occupancy.resources:
                print(
                    "root     "
                    f"{resource.ownership.value} "
                    f"{resource.lifecycle.value} "
                    f"{resource.protection.value} "
                    f"{resource.reclaimability.value} "
                    f"bytes={_format_maybe(resource.size_bytes)}"
                )
            print(
                "install  "
                + (
                    _format_maybe(steward_events_out[0].install_id)
                    if steward_events_out
                    else "unresolved(not_provided)"
                )
            )
            print(
                "host     "
                + (
                    _format_maybe(steward_events_out[0].host_id)
                    if steward_events_out
                    else "unresolved(not_provided)"
                )
            )
            journal_shown = (
                str(JsonlJournal(journal_target).path)
                if journal_target is not None
                else "-"
            )
            print(f"journal  {journal_shown}")
            _print_document(occupancy)
            for event in steward_events_out:
                _print_document(event)
            return 0
        if ns.command == "capacity" and ns.capacity_command == "evaluate":
            envelope, capacity_events_out, journal_target = evaluate_capacity(
                explicit=ns.state_root,
                environment=_environment_override(),
                store_dir=Path(ns.store_dir) if ns.store_dir else None,
                journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
            )
            print(f"evidence {envelope.evidence_id}")
            print(f"memory   {_format_maybe(envelope.memory.safe_bytes)}")
            print(f"accel    {len(envelope.accelerators)}")
            print(f"storage  {len(envelope.storage_domains)}")
            print(f"sonar    {envelope.settings.sonar_writes.value}")
            print(f"host     {_format_maybe(capacity_events_out[0].host_id)}")
            journal_shown = (
                str(JsonlJournal(journal_target).path)
                if journal_target is not None
                else "-"
            )
            print(f"journal  {journal_shown}")
            _print_document(envelope)
            for event in capacity_events_out:
                _print_document(event)
            return 0
        if ns.command == "foundation" and ns.foundation_command in {
            "inspect",
            "provision",
        }:
            mode = (
                ProvisionMode.INSPECT_ONLY
                if ns.foundation_command == "inspect"
                else ProvisionMode.PROVISION
            )
            foundation_set, foundation_events_out, journal_target = inspect_foundation(
                explicit=ns.state_root,
                environment=_environment_override(),
                store_dir=Path(ns.store_dir) if ns.store_dir else None,
                journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
                mode=mode,
                backend=ns.backend,
            )
            selection = foundation_set.selection
            print(f"support  {selection.support.value}")
            print(f"failure  {selection.failure.value}")
            print(f"engine   {selection.engine.value}")
            print(f"executor {selection.executor.value}")
            print(f"backend  {_format_maybe(selection.backend)}")
            print(f"mode     {foundation_set.settings.provision_mode.value}")
            print(f"python   {foundation_set.settings.python_version}")
            print(f"vllm     {foundation_set.settings.vllm_version}")
            print(
                "install  "
                + (
                    _format_maybe(foundation_events_out[0].install_id)
                    if foundation_events_out
                    else "unresolved(not_provided)"
                )
            )
            journal_shown = (
                str(JsonlJournal(journal_target).path)
                if journal_target is not None
                else "-"
            )
            print(f"journal  {journal_shown}")
            _print_document(foundation_set)
            for event in foundation_events_out:
                _print_document(event)
            return 0
        if ns.command == "model" and ns.model_command == "inspect":
            if ns.repository:
                model_snapshot, model_events_out = _inspect_hub(ns)
            else:
                if not ns.path or not ns.label:
                    raise ValidationError("local inspect requires --path and --label")
                model_snapshot, model_events_out = inspect_model(
                    source_path=Path(ns.path),
                    label=ns.label,
                    journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
                    foundation_id=ns.foundation_id,
                    qualification=ns.qualification,
                    runtime_python=(
                        Path(ns.runtime_python) if ns.runtime_python else None
                    ),
                    state_root=Path(ns.state_root) if ns.state_root else None,
                )
            _print_model_snapshot(model_snapshot, model_events_out, ns.journal_dir)
            return 0
        if ns.command == "model" and ns.model_command == "import":
            return _import_local(ns)
        if ns.command == "model" and ns.model_command == "acquire":
            return _acquire_hub(ns)
        if ns.command == "plan" and ns.plan_command == "policy":
            print(f"policy   {POLICY_VERSION}")
            print(f"accel    {ACCELERATOR_COUNT}")
            print(f"context  {DEFAULT_CONTEXT}")
            print(f"concur   {DEFAULT_CONCURRENCY}")
            print(f"util     {MEMORY_UTILIZATION}")
            print("remote   refuse")
            print("reserve  false")
            return 0
        if ns.command == "admit" and ns.admit_command == "policy":
            print(f"policy   {ADMIT_POLICY_VERSION}")
            print("accel    1")
            print("serve    false")
            return 0
        if ns.command == "admin" and ns.admin_command == "serve":
            return _serve_rukan_admin(ns)
        if ns.command == "analytics" and ns.analytics_command == "export":
            return _export_rukan_analytics(ns)
        if ns.command == "command-center" and ns.command_center_command == "serve":
            return _serve_rukan_command_center(ns)
        if ns.command == "serve" and ns.serve_command == "policy":
            print(f"policy   {SERVE_POLICY_VERSION}")
            print(f"bind     {BIND_SCOPE}")
            print("provider vllm")
            print("executor native_process")
            print("pid      false")
            print("witness  projection")
            return 0
        if ns.command == "admit" and ns.admit_command == "inspect":
            return _inspect_reservations(Path(ns.store_dir))
        if ns.command == "prerequisites" and ns.prerequisites_command == "check":
            (
                readiness_report,
                readiness_events,
                install_id,
                install_run_id,
                journal_target,
            ) = evaluate_prerequisites(
                explicit=ns.state_root,
                environment=_environment_override(),
                store_dir=Path(ns.store_dir) if ns.store_dir else None,
                journal_dir_path=(Path(ns.journal_dir) if ns.journal_dir else None),
                mode=PolicyMode(ns.policy),
            )
            print(f"target   {readiness_report.target.target_id.value}")
            print(f"adapter  {readiness_report.target.adapter_id}")
            print(f"policy   {readiness_report.policy.mode.value}")
            print(f"before   {readiness_report.readiness_before.value}")
            print(f"after    {readiness_report.readiness_after.value}")
            print(f"code     {readiness_report.diagnosis.code.value}")
            print(f"mutated  {str(readiness_report.mutated).lower()}")
            print(f"install  {_format_maybe(install_id)}")
            print(f"run      {_format_maybe(install_run_id)}")
            journal_shown = (
                str(JsonlJournal(journal_target).path)
                if journal_target is not None
                else "-"
            )
            print(f"journal  {journal_shown}")
            print(f"events   {len(readiness_events)}")
            _print_document(readiness_report)
            return 0
    except PersistenceError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    except MachiError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 2
    print("error: unhandled command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

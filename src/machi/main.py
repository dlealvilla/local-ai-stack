"""Composition root and CLI.

The only module that names a concrete adapter alongside Kernel, Install,
and Discover types. Kernel never imports adapters. Domain modules never
import adapters. Kernel never owns state-root policy.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from machi.adapters.discover.native_accelerator import NativeAcceleratorObserver
from machi.adapters.discover.native_memory import NativeMemoryObserver
from machi.adapters.discover.native_os_arch import NativeOSArchitectureObserver
from machi.adapters.journal.jsonl import JsonlJournal
from machi.adapters.persistence.file_store import FileStore
from machi.adapters.prerequisites.amd_smi import AmdSmiPrerequisiteAdapter
from machi.discover.contracts import (
    AcceleratorObservation,
    MemoryObservation,
    OSArchitectureObservation,
)
from machi.discover.events import (
    accelerator_observed,
    memory_observed,
    os_arch_observed,
)
from machi.discover.ports import (
    AcceleratorObserver,
    MemoryObserver,
    OSArchitectureObserver,
)
from machi.install.binder import StateRootBinder
from machi.install.contracts import (
    InstallRecordEstablishment,
    InstallRunEstablishment,
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
from machi.kernel.errors import MachiError, PersistenceError, ValidationError
from machi.kernel.events import EventRecord
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.journal import JournalDefect
from machi.kernel.schema import Contract, to_dict, validate_registry
from machi.kernel.store_proof import StoreProof, store_proved
from machi.kernel.unresolved import Maybe, is_resolved
from machi.prerequisites.contracts import (
    PolicyMode,
    PrerequisiteReadinessReport,
    SettingProvenance,
)
from machi.prerequisites.policy import default_prerequisite_policy, policy_with_mode
from machi.prerequisites.ports import PrerequisiteAdapter
from machi.prerequisites.service import PrerequisiteReadiness


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

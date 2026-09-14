"""Composition root and CLI.

The only module that names a concrete adapter alongside Kernel and
Install types. Kernel never imports adapters. Install never imports
adapters. Kernel never owns state-root policy.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from machi.adapters.journal.jsonl import JsonlJournal
from machi.adapters.persistence.file_store import FileStore
from machi.install.binder import StateRootBinder
from machi.install.contracts import (
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
    local_ownership_marked,
    ownership_registry_seeded,
    state_root_bound,
)
from machi.install.marker import SelfOwnershipMarker
from machi.install.registry import RegistrySeed
from machi.kernel.alive import kernel_alive
from machi.kernel.build import identity as build_identity
from machi.kernel.errors import MachiError, PersistenceError, ValidationError
from machi.kernel.events import EventRecord
from machi.kernel.journal import JournalDefect
from machi.kernel.schema import Contract, to_dict, validate_registry
from machi.kernel.store_proof import StoreProof, store_proved


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

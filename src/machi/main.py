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
from machi.install.binder import StateRootBinder
from machi.install.contracts import SelectionSource, StateRootBinding
from machi.install.defaults import STATE_ROOT_VARIABLE, journal_dir
from machi.install.events import state_root_bound
from machi.kernel.alive import kernel_alive
from machi.kernel.build import identity as build_identity
from machi.kernel.errors import MachiError, PersistenceError, ValidationError
from machi.kernel.events import EventRecord
from machi.kernel.journal import JournalDefect
from machi.kernel.schema import Contract, to_dict, validate_registry


def prove_alive(journal_dir_path: Path) -> EventRecord:
    """Persist one kernel.alive event into the injected journal directory."""
    validate_registry(module_prefix="machi.")
    journal = JsonlJournal(journal_dir_path)
    return journal.append(kernel_alive())


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

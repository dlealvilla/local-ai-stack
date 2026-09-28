"""Read persisted contracts for a Rukan projection. Does not mutate them."""

from __future__ import annotations

import json
from pathlib import Path

from machi.kernel.errors import PersistenceError, UnknownKindError, ValidationError
from machi.kernel.schema import Contract, from_dict

RecordT = type[Contract]


def load_records(root: Path, contract_type: RecordT) -> tuple[Contract, ...]:
    """Load one kind. Unreadable files are skipped by the caller via errors."""
    directory = Path(root) / contract_type.kind
    if not directory.is_dir():
        return ()
    loaded: list[Contract] = []
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("."):
            continue
        loaded.append(_load(path))
    return tuple(loaded)


def load_errors(root: Path, contract_type: RecordT) -> int:
    """Count records of this kind that could not be decoded. No paths returned."""
    directory = Path(root) / contract_type.kind
    if not directory.is_dir():
        return 0
    failed = 0
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            _load(path)
        except (
            OSError,
            PersistenceError,
            UnknownKindError,
            ValidationError,
            json.JSONDecodeError,
        ):
            failed += 1
    return failed


def _load(path: Path) -> Contract:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValidationError("stored record is not an object")
    document.pop("record_key", None)
    return from_dict(document)

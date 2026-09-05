"""A JSON-file record store: the reference implementation of ``Store``.

One record per file, laid out as ``<root>/<kind>/<key>.json``. Every record
carries its kind, version and key inside the document as well as in its
path, so a record recovered by hand is self-describing.

Writes are atomic. The record is written to a uniquely named temporary file
in its own directory, flushed to disk, and then moved onto the final path
with :func:`os.replace`, which is atomic within a filesystem. A reader
therefore never observes a partial record, and a crash mid-write leaves the
previous version intact.

This is `WORKING`, not permanent: single writer, no index, no query. See
`docs/DEBT.md`. It is replaced when a second writer process or a non-key
lookup is needed, which the roadmap expects at Milestone 2 or 4.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path

from kultrun.kernel.errors import PersistenceError
from kultrun.kernel.persistence import (
    ReconciliationReport,
    RecordT,
    StoreDefect,
    validate_record_key,
)
from kultrun.kernel.schema import Contract, from_dict, to_dict

_TEMPORARY_PREFIX = ".writing-"
_SUFFIX = ".json"


class FileStore:
    """A record store backed by one JSON file per record."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        """The directory this store owns."""
        return self._root

    # -- writing ----------------------------------------------------------

    def put(self, key: str, record: Contract) -> None:
        validate_record_key(key)
        if not record.kind:
            raise PersistenceError(
                "cannot store an abstract contract",
                contract=type(record).__qualname__,
            )
        document = to_dict(record)
        document["record_key"] = key
        directory = self._directory(record.kind)
        directory.mkdir(parents=True, exist_ok=True)
        self._write_atomically(directory / f"{key}{_SUFFIX}", document)

    def _write_atomically(self, destination: Path, document: dict[str, object]) -> None:
        payload = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
        temporary = destination.parent / (
            f"{_TEMPORARY_PREFIX}{destination.name}.{secrets.token_hex(4)}"
        )
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise PersistenceError(
                "could not write record", path=str(destination), reason=str(error)
            ) from error

    # -- reading ----------------------------------------------------------

    def get(self, contract_type: type[RecordT], key: str) -> RecordT | None:
        validate_record_key(key)
        path = self._directory(contract_type.kind) / f"{key}{_SUFFIX}"
        if not path.exists():
            return None
        return self._load(path, contract_type)

    def keys(self, contract_type: type[Contract]) -> tuple[str, ...]:
        directory = self._directory(contract_type.kind)
        if not directory.is_dir():
            return ()
        return tuple(
            sorted(
                path.name[: -len(_SUFFIX)]
                for path in directory.glob(f"*{_SUFFIX}")
                if not path.name.startswith(_TEMPORARY_PREFIX)
            )
        )

    def records(self, contract_type: type[RecordT]) -> tuple[RecordT, ...]:
        return tuple(
            record
            for key in self.keys(contract_type)
            if (record := self.get(contract_type, key)) is not None
        )

    def _load(self, path: Path, contract_type: type[RecordT]) -> RecordT:
        raw = self._read_document(path)
        raw.pop("record_key", None)
        record = from_dict(raw)
        if not isinstance(record, contract_type):
            raise PersistenceError(
                "stored record is not of the requested kind",
                path=str(path),
                expected=contract_type.kind,
                found=record.kind,
            )
        return record

    def _read_document(self, path: Path) -> dict[str, object]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            raise PersistenceError(
                "could not read record", path=str(path), reason=str(error)
            ) from error
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise PersistenceError(
                "stored record is not valid JSON", path=str(path), reason=str(error)
            ) from error
        if not isinstance(document, dict):
            raise PersistenceError(
                "stored record is not an object",
                path=str(path),
                found=type(document).__name__,
            )
        return document

    # -- removing ---------------------------------------------------------

    def delete(self, contract_type: type[Contract], key: str) -> bool:
        validate_record_key(key)
        path = self._directory(contract_type.kind) / f"{key}{_SUFFIX}"
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise PersistenceError(
                "could not delete record", path=str(path), reason=str(error)
            ) from error
        return True

    # -- reconciliation ---------------------------------------------------

    def reconcile(self) -> ReconciliationReport:
        """Sweep interrupted writes and report every record that will not load.

        A defect is reported, never skipped. The store returns facts; whether
        an unreadable record should stop startup is a policy decision that
        belongs to `platform`.
        """
        swept = self._sweep_temporaries()
        verified = 0
        defects: list[StoreDefect] = []
        for path in sorted(self._root.glob(f"*/*{_SUFFIX}")):
            if path.name.startswith(_TEMPORARY_PREFIX):
                continue
            claimed: str | None = None
            try:
                document = self._read_document(path)
                raw_kind = document.get("kind")
                claimed = raw_kind if isinstance(raw_kind, str) else None
                document.pop("record_key", None)
                from_dict(document)
            except Exception as error:  # reported as a defect, never raised
                defects.append(
                    StoreDefect(
                        location=str(path.relative_to(self._root)),
                        problem=str(error),
                        record_kind=claimed,
                    )
                )
            else:
                verified += 1
        return ReconciliationReport(
            swept_temporaries=swept,
            records_verified=verified,
            defects=tuple(defects),
        )

    def _sweep_temporaries(self) -> int:
        swept = 0
        for path in self._root.glob(f"*/{_TEMPORARY_PREFIX}*"):
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise PersistenceError(
                    "could not remove an interrupted write",
                    path=str(path),
                    reason=str(error),
                ) from error
            swept += 1
        return swept

    def _directory(self, kind: str) -> Path:
        return self._root / kind


def build(root: str | Path) -> FileStore:
    """Factory for the adapter registry."""
    return FileStore(Path(root))


def temporary_store() -> tuple[FileStore, tempfile.TemporaryDirectory[str]]:
    """A store in a throwaway directory. Returns the handle so callers can clean up."""
    handle = tempfile.TemporaryDirectory()
    return FileStore(Path(handle.name)), handle

"""JSON-file entity store: the reference implementation of ``Store``.

One record per file, laid out as ``<root>/<kind>/<key>.json``. Every
record carries its kind, version and key inside the document as well
as in its path, so a record recovered by hand is self-describing.

Creates are exclusive. The record is written to a uniquely named
temporary file in the same directory, flushed, then published with
``os.link`` so an existing entity is never replaced. That link is
this adapter's publication primitive, not a Store port requirement.
Filesystems that cannot link must fail closed here or be served by a
different Store adapter. Identical re-entry returns the stored
record. Conflicting or malformed existing records fail closed.

This adapter does not read environment variables, does not choose a
state root, does not talk to the journal, and does not implement
ownership or cleanup.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from machi.kernel.errors import (
    ConflictError,
    NotFoundError,
    PersistenceError,
    ValidationError,
)
from machi.kernel.schema import Contract, from_dict, to_dict
from machi.kernel.store import RecordT, StoreCreateResult, validate_record_key

_TEMPORARY_PREFIX = ".writing-"
_SUFFIX = ".json"


class FileStore:
    """A record store backed by one JSON file per record."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        """The injected directory this store uses. Kernel did not choose it."""
        return self._root

    def create(self, key: str, record: Contract) -> StoreCreateResult:
        validate_record_key(key)
        if not record.kind:
            raise PersistenceError(
                "cannot store an abstract contract",
                contract=type(record).__qualname__,
            )
        dest = self._path(record.kind, key)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PersistenceError(
                "failed to create the store kind directory",
                path=str(dest.parent),
            ) from exc
        if dest.exists():
            return self._existing(dest, key, record)
        try:
            self._write_exclusive(dest, key, record)
        except FileExistsError:
            return self._existing(dest, key, record)
        return StoreCreateResult(record=record, created=True, existed=False)

    def get(self, contract_type: type[RecordT], key: str) -> RecordT:
        validate_record_key(key)
        dest = self._path(contract_type.kind, key)
        if not dest.exists():
            raise NotFoundError(
                "stored record does not exist",
                kind=contract_type.kind,
                key=key,
            )
        return self._load(dest, key, contract_type)

    def _existing(self, dest: Path, key: str, record: Contract) -> StoreCreateResult:
        loaded = self._load(dest, key, type(record))
        if loaded != record:
            raise ConflictError(
                "stored record already exists and does not match; "
                "refusing to overwrite",
                key=key,
                kind=record.kind,
            )
        return StoreCreateResult(record=loaded, created=False, existed=True)

    def _write_exclusive(self, dest: Path, key: str, record: Contract) -> None:
        document = to_dict(record)
        document["record_key"] = key
        payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
        tmp = dest.with_name(f"{_TEMPORARY_PREFIX}{dest.name}.{secrets.token_hex(8)}")
        try:
            fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(tmp, dest)
            except FileExistsError:
                raise
            _fsync_directory(dest.parent)
        except FileExistsError:
            if dest.exists():
                raise
            raise PersistenceError(
                "failed to write the stored record",
                path=str(dest),
            ) from None
        except OSError as exc:
            raise PersistenceError(
                "failed to write the stored record",
                path=str(dest),
            ) from exc
        finally:
            tmp.unlink(missing_ok=True)

    def _load(self, dest: Path, key: str, contract_type: type[RecordT]) -> RecordT:
        if not dest.is_file():
            raise ConflictError(
                "stored record path exists and is not a file",
                key=key,
            )
        try:
            raw = dest.read_text(encoding="utf-8")
        except OSError as exc:
            raise PersistenceError(
                "failed to read the stored record",
                path=str(dest),
            ) from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "stored record is malformed JSON; refusing to repair",
                key=key,
            ) from exc
        if not isinstance(payload, dict):
            raise ValidationError(
                "stored record is not a JSON object; refusing to repair",
                key=key,
            )
        stored_key = payload.pop("record_key", None)
        if stored_key != key:
            raise ValidationError(
                "stored record_key does not match the requested key; "
                "refusing to repair",
                key=key,
            )
        original_version = payload.get("schema_version")
        try:
            loaded = from_dict(payload)
        except Exception as exc:
            raise ValidationError(
                "stored record is not a valid Machi contract; refusing to repair",
                key=key,
            ) from exc
        if not isinstance(loaded, contract_type):
            raise ConflictError(
                "stored record is not of the requested kind; refusing to coerce",
                expected=contract_type.kind,
                found=getattr(loaded, "kind", None),
            )
        if (
            isinstance(original_version, int)
            and not isinstance(original_version, bool)
            and original_version != loaded.schema_version
        ):
            self._rewrite_current(dest, key, loaded, original_version)
        return loaded

    def _path(self, kind: str, key: str) -> Path:
        if "/" in kind or "\\" in kind or ".." in kind or not kind:
            raise ValidationError(
                "contract kind is not a safe store directory name",
                kind=kind,
            )
        dest = (self._root / kind / f"{key}{_SUFFIX}").resolve()
        try:
            dest.relative_to(self._root.resolve())
        except ValueError as exc:
            raise ValidationError(
                "store path escaped the injected root",
                key=key,
            ) from exc
        return dest

    def _rewrite_current(
        self, dest: Path, key: str, record: Contract, from_version: int
    ) -> None:
        """Replace one migrated record, then append a migration note."""
        document = to_dict(record)
        document["record_key"] = key
        payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
        temporary = dest.with_name(
            f"{_TEMPORARY_PREFIX}{dest.name}.{secrets.token_hex(8)}"
        )
        try:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(dest)
            _fsync_directory(dest.parent)
        except OSError as exc:
            raise PersistenceError(
                "failed to rewrite the migrated record",
                path=str(dest),
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)
        self._note_migration(record.kind, key, from_version, record.schema_version)

    def _note_migration(
        self, kind: str, key: str, from_version: int, to_version: int
    ) -> None:
        path = self._root / "_schema_migrations.jsonl"
        line = json.dumps(
            {
                "kind": kind,
                "key": key,
                "from_version": from_version,
                "to_version": to_version,
            },
            sort_keys=True,
        )
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise PersistenceError(
                "failed to record the schema migration",
                path=str(path),
            ) from exc


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        return
    finally:
        os.close(fd)

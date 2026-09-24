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
from dataclasses import dataclass
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
_RECEIPT_PHASES = frozenset({"intent", "complete"})


@dataclass(frozen=True, slots=True)
class MigrationFault:
    """Stops one migration phase. Production store leaves this unset."""

    fail_intent: bool = False
    fail_record: bool = False
    fail_complete: bool = False


class FileStore:
    """A record store backed by one JSON file per record."""

    def __init__(
        self, root: Path, *, migration_fault: MigrationFault | None = None
    ) -> None:
        self._root = Path(root)
        self._migration_fault = migration_fault

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
        self._converge_migration(dest, key, loaded, original_version)
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

    def _converge_migration(
        self,
        dest: Path,
        key: str,
        loaded: Contract,
        stored_version: object,
    ) -> None:
        """Finish a migration receipt without claiming the two files are atomic."""
        kind = loaded.kind
        upgraded = _older_version(stored_version, loaded.schema_version)
        receipt = self._read_receipt(kind, key)
        if receipt is None:
            if not upgraded:
                return
            assert isinstance(stored_version, int)
            self._write_receipt(
                kind, key, stored_version, loaded.schema_version, "intent"
            )
            self._replace_record(dest, key, loaded)
            self._write_receipt(
                kind, key, stored_version, loaded.schema_version, "complete"
            )
            return
        from_version = _receipt_version(receipt, "from_version", key)
        to_version = _receipt_version(receipt, "to_version", key)
        phase = receipt.get("phase")
        if phase == "complete":
            if upgraded or stored_version != to_version:
                raise PersistenceError(
                    "migration receipt claims completion but the record "
                    "is not that version",
                    key=key,
                )
            return
        if phase != "intent":
            raise PersistenceError("migration receipt phase is unknown", key=key)
        if to_version != loaded.schema_version:
            raise PersistenceError(
                "migration intent does not match the current contract",
                key=key,
            )
        if upgraded:
            if from_version != stored_version:
                raise PersistenceError(
                    "migration intent does not match the stored version",
                    key=key,
                )
            self._replace_record(dest, key, loaded)
        elif stored_version != loaded.schema_version:
            raise PersistenceError(
                "migration intent does not match the stored record",
                key=key,
            )
        self._write_receipt(kind, key, from_version, to_version, "complete")

    def _replace_record(self, dest: Path, key: str, record: Contract) -> None:
        fault = self._migration_fault
        if fault is not None and fault.fail_record:
            raise PersistenceError(
                "migration record rewrite was interrupted",
                path=str(dest),
            )
        document = to_dict(record)
        document["record_key"] = key
        payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
        self._publish_replace(dest, payload, "failed to rewrite the migrated record")

    def _receipt_path(self, kind: str, key: str) -> Path:
        if "/" in kind or "\\" in kind or ".." in kind or not kind:
            raise ValidationError(
                "contract kind is not a safe store directory name",
                kind=kind,
            )
        dest = (self._root / "_schema_migration" / kind / f"{key}.json").resolve()
        try:
            dest.relative_to(self._root.resolve())
        except ValueError as exc:
            raise ValidationError(
                "migration receipt path escaped the injected root",
                key=key,
            ) from exc
        return dest

    def _read_receipt(self, kind: str, key: str) -> dict[str, object] | None:
        path = self._receipt_path(kind, key)
        if not path.exists():
            return None
        if not path.is_file():
            raise PersistenceError(
                "migration receipt path is not a file",
                path=str(path),
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PersistenceError(
                "migration receipt is unreadable",
                path=str(path),
            ) from exc
        if not isinstance(payload, dict):
            raise PersistenceError(
                "migration receipt is not an object",
                path=str(path),
            )
        if payload.get("kind") != kind or payload.get("key") != key:
            raise PersistenceError(
                "migration receipt does not match this record",
                key=key,
            )
        if payload.get("phase") not in _RECEIPT_PHASES:
            raise PersistenceError("migration receipt phase is unknown", key=key)
        return payload

    def _write_receipt(
        self,
        kind: str,
        key: str,
        from_version: int,
        to_version: int,
        phase: str,
    ) -> None:
        fault = self._migration_fault
        if fault is not None and phase == "intent" and fault.fail_intent:
            raise PersistenceError(
                "migration intent was not recorded",
                key=key,
            )
        if fault is not None and phase == "complete" and fault.fail_complete:
            raise PersistenceError(
                "migration completion was not recorded",
                key=key,
            )
        document = {
            "from_version": from_version,
            "key": key,
            "kind": kind,
            "phase": phase,
            "to_version": to_version,
        }
        payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
        self._publish_replace(
            self._receipt_path(kind, key),
            payload,
            "failed to record the schema migration",
        )

    def _publish_replace(self, dest: Path, payload: str, message: str) -> None:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PersistenceError(message, path=str(dest)) from exc
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
            raise PersistenceError(message, path=str(dest)) from exc
        finally:
            temporary.unlink(missing_ok=True)


def _older_version(stored: object, current: int) -> bool:
    return (
        isinstance(stored, int)
        and not isinstance(stored, bool)
        and stored != current
    )


def _receipt_version(receipt: dict[str, object], field: str, key: str) -> int:
    value = receipt.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PersistenceError("migration receipt version is not usable", key=key)
    return value


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

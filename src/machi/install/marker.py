"""SelfOwnershipMarker (MACHI 1.3.1).

Establish and validate the local Machi ownership evidence for one
bound state root. This is not dual ownership and does not authorize
destruction. Component 1.3.2 owns the registry half.

The marker contract is a local-evidence document. Exclusive publication
currently uses POSIX ``os.link`` inside this writer so a crash cannot
replace an existing marker. That primitive is this component's
filesystem mechanic, not a Kernel Store rule and not an ownership
semantic. Filesystems that cannot link fail closed. A non-link publisher
is a future provider selection, not a silent overwrite.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from machi.install.contracts import (
    LocalOwnershipEstablishment,
    LocalOwnershipMarker,
    LocalOwnershipStatus,
    StateRootBinding,
)
from machi.install.defaults import (
    JOURNAL_EVENTS_FILENAME,
    JOURNAL_LEAF,
    KULTRUN_OWNER_FILENAME,
    MACHI_OWNER_FILENAME,
    PRODUCT_NAMESPACE,
)
from machi.install.events import root_fingerprint
from machi.kernel.build import identity as build_identity
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ConflictError, PersistenceError, ValidationError
from machi.kernel.ids import LocalOwnershipId
from machi.kernel.schema import from_dict, to_dict

BOOTSTRAP_NAMES = frozenset({JOURNAL_LEAF})


class SelfOwnershipMarker:
    """Local marker only. Never scans siblings, never deletes, never registers."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def establish(self, binding: StateRootBinding) -> LocalOwnershipEstablishment:
        """Create or validate the local marker for this binding.

        Consumes ``StateRootBinding``. Does not resolve a state root of its own.
        """
        root = Path(binding.root)
        if not root.is_dir():
            raise ValidationError(
                "state root from the binding is not a directory",
                path=binding.root,
            )
        expected = root_fingerprint(binding.root)
        kultrun = root / KULTRUN_OWNER_FILENAME
        if kultrun.is_file():
            raise ConflictError(
                "refusing to claim a tree that already carries Kultrun "
                "ownership evidence; Steward may reason about it later",
            )
        dest = root / MACHI_OWNER_FILENAME
        if dest.exists():
            marker = self._load_existing(dest, expected)
            return self._result(marker, existed=True, created=False)
        self._require_claimable(binding, root)
        marker = self._new_marker(expected)
        self._write_exclusive(dest, marker)
        return self._result(marker, existed=False, created=True)

    def _new_marker(self, fingerprint: str) -> LocalOwnershipMarker:
        build = build_identity()
        return LocalOwnershipMarker(
            marker_id=LocalOwnershipId.generate(),
            product=PRODUCT_NAMESPACE,
            root_fingerprint=fingerprint,
            created_at=self._clock.now(),
            created_by_build_id=build.build_id,
            created_by_origin=build.origin.value,
        )

    def _result(
        self,
        marker: LocalOwnershipMarker,
        *,
        existed: bool,
        created: bool,
    ) -> LocalOwnershipEstablishment:
        return LocalOwnershipEstablishment(
            marker=marker,
            status=LocalOwnershipStatus.LOCAL_MARKER_PRESENT,
            dual_ownership=False,
            destructive_authorization=False,
            existed=existed,
            created=created,
        )

    def _load_existing(
        self, dest: Path, expected_fingerprint: str
    ) -> LocalOwnershipMarker:
        if not dest.is_file():
            raise ConflictError(
                "ownership marker path exists and is not a file",
            )
        try:
            raw = dest.read_text(encoding="utf-8")
        except OSError as exc:
            raise PersistenceError(
                "failed to read the local ownership marker",
            ) from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "local ownership marker is malformed JSON; refusing to repair",
            ) from exc
        if not isinstance(payload, dict):
            raise ValidationError(
                "local ownership marker is not a JSON object; refusing to repair",
            )
        try:
            loaded = from_dict(payload)
        except Exception as exc:
            raise ValidationError(
                "local ownership marker is not a valid Machi marker; "
                "refusing to repair",
            ) from exc
        if not isinstance(loaded, LocalOwnershipMarker):
            raise ValidationError(
                "local ownership marker has the wrong contract kind; "
                "refusing to repair",
                kind=getattr(loaded, "kind", None),
            )
        if loaded.product != PRODUCT_NAMESPACE:
            raise ConflictError(
                "local ownership marker belongs to a different product; "
                "refusing to repair",
                product=loaded.product,
            )
        if loaded.root_fingerprint != expected_fingerprint:
            raise ConflictError(
                "local ownership marker is bound to a different state root; "
                "refusing to treat a copied marker as valid",
            )
        return loaded

    def _require_claimable(self, binding: StateRootBinding, root: Path) -> None:
        try:
            names = {entry.name for entry in root.iterdir()}
        except OSError as exc:
            raise PersistenceError(
                "failed to inspect the state root before claiming",
            ) from exc
        names.discard(MACHI_OWNER_FILENAME)
        if binding.created and names <= BOOTSTRAP_NAMES:
            return
        if not names:
            return
        if names == BOOTSTRAP_NAMES and _looks_like_machi_journal(root / JOURNAL_LEAF):
            return
        raise ConflictError(
            "refusing to claim a tree with unknown pre-existing content; "
            "1.3.1 does not implement adoption",
        )

    def _write_exclusive(self, dest: Path, marker: LocalOwnershipMarker) -> None:
        document = json.dumps(to_dict(marker), indent=2, sort_keys=True) + "\n"
        tmp = dest.with_name(f".{dest.name}.{secrets.token_hex(8)}.tmp")
        try:
            fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(document)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                # Exclusive publish currently uses POSIX link, as FileStore
                # does. That is this marker writer, not a Store port rule.
                os.link(tmp, dest)
            except FileExistsError as exc:
                raise ConflictError(
                    "ownership marker already exists; refusing to overwrite",
                ) from exc
            _fsync_directory(dest.parent)
        except ConflictError:
            raise
        except OSError as exc:
            raise PersistenceError(
                "failed to write the local ownership marker",
            ) from exc
        finally:
            tmp.unlink(missing_ok=True)


def _looks_like_machi_journal(path: Path) -> bool:
    return path.is_dir() and (path / JOURNAL_EVENTS_FILENAME).is_file()


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

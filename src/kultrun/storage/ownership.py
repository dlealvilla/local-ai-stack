"""Dual ownership: a local marker at a managed root, and a central registry.

Automatic deletion requires positive agreement. A missing marker, a
missing registry row, a material disagreement, an active reference, or a
legacy unlabelled tree is never a reason to delete.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import replace
from pathlib import Path

from kultrun.host.contracts import HostId
from kultrun.kernel.build import identity as build_identity
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.persistence import Store
from kultrun.kernel.schema import from_dict, to_dict
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import (
    LOCAL_OWNER_FILENAME,
    CleanupPolicy,
    CleanupReport,
    InstallationGeneration,
    InstallationGenerationId,
    LifecycleState,
    ManagedResourceType,
    OwnershipConflict,
    OwnershipId,
    OwnershipRecord,
)
from kultrun.storage.limits import CREATED_BY

LEGACY_DIRECTORY_NAMES = frozenset(
    {
        "runtimes",
        "models",
        "cache",
        "staging",
        "tmp",
        "temp",
        "telemetry",
        "logs",
        ".kultrun-probe",
        ".kultrun-sonar",
    }
)


class OwnershipService:
    """Assert, reconcile, and classify managed roots. Never guesses ownership."""

    def __init__(self, store: Store, clock: Clock, state_root: Path) -> None:
        self._store = store
        self._clock = clock
        self._state_root = Path(state_root).resolve()

    @property
    def state_root(self) -> Path:
        return self._state_root

    def assert_owned(
        self,
        root: Path,
        host_id: HostId,
        resource_type: ManagedResourceType,
        *,
        lifecycle: LifecycleState = LifecycleState.PREPARING,
        cleanup_policy: CleanupPolicy = CleanupPolicy.RETAIN,
        protected: bool = False,
        rollback_protected: bool = False,
        evidence_retained: bool = False,
        storage_pool_id: object = NOT_PROVIDED,
        quota_identity: object = NOT_PROVIDED,
        installation_generation_id: object = NOT_PROVIDED,
        runtime_installation_id: object = NOT_PROVIDED,
        artifact_id: object = NOT_PROVIDED,
        deployment_id: object = NOT_PROVIDED,
        allowed_roots: Sequence[Path] | None = None,
        ownership_id: OwnershipId | None = None,
    ) -> OwnershipRecord:
        """Create a managed root, write the marker, and index it.

        The directory is created if needed. Existing unrelated files inside
        it are not deleted.
        """
        resolved = Path(root).resolve()
        self._require_within(resolved, allowed_roots)
        resolved.mkdir(parents=True, exist_ok=True)
        now = self._clock.now()
        record = OwnershipRecord(
            ownership_id=ownership_id or OwnershipId.generate(),
            host_id=host_id,
            resource_type=resource_type,
            managed_root=str(resolved),
            created_at=now,
            kultrun_version=build_identity().version,
            created_by=CREATED_BY,
            lifecycle_state=lifecycle,
            cleanup_policy=cleanup_policy,
            protected=protected,
            rollback_protected=rollback_protected,
            evidence_retained=evidence_retained,
            storage_pool_id=_maybe_str(storage_pool_id),
            quota_identity=_maybe_str(quota_identity),
            installation_generation_id=_maybe_str(installation_generation_id),
            runtime_installation_id=_maybe_str(runtime_installation_id),
            artifact_id=_maybe_str(artifact_id),
            deployment_id=_maybe_str(deployment_id),
        )
        self._write_marker(resolved, record)
        self._store.put(record.ownership_id.value, record)
        return record

    def ensure_platform_roots(self, host_id: HostId) -> None:
        """Label significant managed roots. Does not delete existing files."""
        roots = (
            (
                self._state_root,
                ManagedResourceType.STATE_ROOT,
                CleanupPolicy.RETAIN,
                True,
            ),
            (
                self._state_root / "runtimes",
                ManagedResourceType.RUNTIME_FINAL,
                CleanupPolicy.RETAIN,
                True,
            ),
            (
                self._state_root / "models",
                ManagedResourceType.MODEL_ARTIFACT,
                CleanupPolicy.RETAIN,
                True,
            ),
            (
                self._state_root / "cache",
                ManagedResourceType.INSTALL_CACHE,
                CleanupPolicy.DISPOSABLE,
                False,
            ),
            (
                self._state_root / "tmp",
                ManagedResourceType.TEMP,
                CleanupPolicy.DISPOSABLE,
                False,
            ),
            (
                self._state_root / "telemetry",
                ManagedResourceType.TELEMETRY,
                CleanupPolicy.RETAIN,
                False,
            ),
            (
                self._state_root / "logs",
                ManagedResourceType.LOGS,
                CleanupPolicy.RETAIN,
                True,
            ),
        )
        for path, resource_type, policy, protected in roots:
            if self.load_marker(path) is not None:
                continue
            self.assert_owned(
                path,
                host_id,
                resource_type,
                lifecycle=(
                    LifecycleState.ACTIVE if protected else LifecycleState.PREPARING
                ),
                cleanup_policy=policy,
                protected=protected,
            )

    def open_generation(
        self,
        host_id: HostId,
        *,
        rollback_protected: bool = False,
    ) -> InstallationGeneration:
        """Open a managed generation. Not an upgrade/rollback engine."""
        record = InstallationGeneration(
            generation_id=InstallationGenerationId.generate(),
            host_id=host_id,
            created_at=self._clock.now(),
            lifecycle_state=LifecycleState.PREPARING,
            rollback_protected=rollback_protected,
        )
        self._store.put(record.generation_id.value, record)
        return record

    def attach_to_generation(
        self,
        generation: InstallationGeneration,
        ownership_id: OwnershipId,
    ) -> InstallationGeneration:
        if ownership_id.value in generation.ownership_ids:
            return generation
        updated = replace(
            generation,
            ownership_ids=(*generation.ownership_ids, ownership_id.value),
        )
        self._store.put(updated.generation_id.value, updated)
        return updated

    def update(self, record: OwnershipRecord) -> OwnershipRecord:
        """Rewrite marker and registry together. Partial update is refused."""
        root = Path(record.managed_root)
        if not root.is_dir():
            raise ValidationError(
                "managed root is missing",
                managed_root=record.managed_root,
            )
        self._write_marker(root, record)
        self._store.put(record.ownership_id.value, record)
        return record

    def get(self, ownership_id: OwnershipId) -> OwnershipRecord | None:
        """Return the registry row, or None when it is absent."""
        return self._store.get(OwnershipRecord, ownership_id.value)

    def forget(self, ownership_id: OwnershipId) -> None:
        """Drop a registry row after the root has been confirmed gone."""
        self._store.delete(OwnershipRecord, ownership_id.value)

    def records(self) -> tuple[OwnershipRecord, ...]:
        return self._store.records(OwnershipRecord)

    def load_marker(self, root: Path) -> OwnershipRecord | None:
        """Read a local marker. Invalid JSON is absence, not a guess."""
        marker = Path(root) / LOCAL_OWNER_FILENAME
        if not marker.is_file():
            return None
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            loaded = from_dict(payload)
        except Exception:
            return None
        return loaded if isinstance(loaded, OwnershipRecord) else None

    def classify(
        self,
        root: Path,
        *,
        active_roots: Iterable[Path] = (),
        allowed_roots: Sequence[Path] | None = None,
    ) -> tuple[OwnershipConflict, OwnershipRecord | None]:
        """Decide whether this root may be deleted. Default is do-not-delete."""
        resolved = Path(root).resolve()
        if not self._is_within(resolved, allowed_roots):
            return OwnershipConflict.PATH_ESCAPE, None
        marker = self.load_marker(resolved)
        by_path = self._registry_for_path(resolved)
        by_id = self.get(marker.ownership_id) if marker is not None else None
        if marker is None and by_path is None:
            if _looks_legacy(resolved, self._state_root):
                return OwnershipConflict.LEGACY_UNLABELLED, None
            return OwnershipConflict.MANIFEST_MISSING, None
        if marker is None:
            return OwnershipConflict.MANIFEST_MISSING, by_path
        if Path(marker.managed_root).resolve() != resolved:
            return OwnershipConflict.IDENTITY_MISMATCH, marker
        if by_id is None and by_path is None:
            return OwnershipConflict.REGISTRY_MISSING, marker
        if by_id is None or (
            by_path is not None and by_path.ownership_id != marker.ownership_id
        ):
            return OwnershipConflict.IDENTITY_MISMATCH, marker
        if not _agree(marker, by_id):
            return OwnershipConflict.IDENTITY_MISMATCH, marker
        if _is_active(resolved, active_roots):
            return OwnershipConflict.ACTIVE_REFERENCE, marker
        if (
            marker.protected
            or marker.rollback_protected
            or marker.evidence_retained
            or marker.lifecycle_state
            in {LifecycleState.ACTIVE, LifecycleState.RETAINED}
        ):
            return OwnershipConflict.PROTECTED, marker
        return OwnershipConflict.NONE, marker

    def reconcile(
        self,
        *,
        scan_roots: Sequence[Path] | None = None,
        allowed_roots: Sequence[Path] | None = None,
    ) -> tuple[OwnershipRecord, ...]:
        """Rebuild missing registry rows from valid local markers.

        Never deletes. Never overwrites a conflicting registry row.
        """
        rebuilt: list[OwnershipRecord] = []
        roots = list(scan_roots) if scan_roots is not None else [self._state_root]
        seen: set[str] = set()
        for base in roots:
            if not Path(base).is_dir():
                continue
            for marker in Path(base).rglob(LOCAL_OWNER_FILENAME):
                parent = marker.parent
                loaded = self.load_marker(parent)
                if loaded is None:
                    continue
                if loaded.ownership_id.value in seen:
                    continue
                seen.add(loaded.ownership_id.value)
                existing = self.get(loaded.ownership_id)
                if existing is None:
                    if not self._is_within(Path(loaded.managed_root), allowed_roots):
                        continue
                    self._store.put(loaded.ownership_id.value, loaded)
                    rebuilt.append(loaded)
                    continue
                if not _agree(existing, loaded):
                    continue
        return tuple(rebuilt)

    def cleanup_disposable(
        self,
        host_id: HostId,
        *,
        active_roots: Iterable[Path] = (),
        allowed_roots: Sequence[Path] | None = None,
        extra_roots: Sequence[Path] = (),
    ) -> CleanupReport:
        """Delete only disposable, dual-owned, unreferenced Kultrun state."""
        allowed = (
            tuple(allowed_roots) if allowed_roots is not None else (self._state_root,)
        )
        inspected = 0
        removed = 0
        bytes_removed = 0
        unresolved: list[str] = []
        protected: list[str] = []
        legacy: list[str] = []
        candidates = self._inventory_paths(extra_roots)
        for path in candidates:
            inspected += 1
            conflict, record = self.classify(
                path, active_roots=active_roots, allowed_roots=allowed
            )
            location = str(path)
            if conflict is OwnershipConflict.LEGACY_UNLABELLED:
                legacy.append(location)
                continue
            if conflict is OwnershipConflict.PROTECTED:
                protected.append(location)
                continue
            if conflict is not OwnershipConflict.NONE or record is None:
                unresolved.append(location)
                continue
            if record.host_id != host_id:
                unresolved.append(location)
                continue
            if record.cleanup_policy is not CleanupPolicy.DISPOSABLE:
                protected.append(location)
                continue
            if record.lifecycle_state not in {
                LifecycleState.FAILED,
                LifecycleState.DISPOSABLE,
            }:
                protected.append(location)
                continue
            size = _tree_bytes(path)
            if not self._delete_owned(path, record):
                unresolved.append(location)
                continue
            self._store.delete(OwnershipRecord, record.ownership_id.value)
            removed += 1
            bytes_removed += size
        return CleanupReport(
            host_id=host_id,
            inspected=inspected,
            removed=removed,
            bytes_removed=bytes_removed,
            unresolved=tuple(unresolved),
            protected=tuple(protected),
            legacy_unlabelled=tuple(legacy),
            rediscovery_required=True,
        )

    def _inventory_paths(self, extra_roots: Sequence[Path]) -> tuple[Path, ...]:
        found: dict[str, Path] = {}
        for record in self.records():
            path = Path(record.managed_root)
            found[str(path.resolve()) if path.exists() else record.managed_root] = path
        for base in (self._state_root, *extra_roots):
            if not Path(base).is_dir():
                continue
            for marker in Path(base).rglob(LOCAL_OWNER_FILENAME):
                parent = marker.parent.resolve()
                found[str(parent)] = parent
            if Path(base).resolve() == self._state_root:
                for child in Path(base).iterdir():
                    if child.is_dir() and child.name in LEGACY_DIRECTORY_NAMES:
                        found.setdefault(str(child.resolve()), child)
        return tuple(found.values())

    def _write_marker(self, root: Path, record: OwnershipRecord) -> None:
        marker = root / LOCAL_OWNER_FILENAME
        payload = to_dict(record)
        marker.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _delete_owned(self, path: Path, record: OwnershipRecord) -> bool:
        marker = self.load_marker(path)
        if marker is None or marker.ownership_id != record.ownership_id:
            return False
        try:
            shutil.rmtree(path)
        except OSError:
            return False
        return not path.exists()

    def _require_within(self, path: Path, allowed_roots: Sequence[Path] | None) -> None:
        if not self._is_within(path, allowed_roots):
            raise ValidationError(
                "managed root is outside allowed storage roots",
                managed_root=str(path),
            )

    def _is_within(self, path: Path, allowed_roots: Sequence[Path] | None) -> bool:
        allowed = [self._state_root]
        if allowed_roots is not None:
            allowed = [Path(item).resolve() for item in allowed_roots]
        resolved = path.resolve()
        for root in allowed:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _registry_for_path(self, resolved: Path) -> OwnershipRecord | None:
        for item in self.records():
            try:
                if Path(item.managed_root).resolve() == resolved:
                    return item
            except OSError:
                continue
        return None


def _agree(left: OwnershipRecord, right: OwnershipRecord) -> bool:
    return (
        left.ownership_id == right.ownership_id
        and left.host_id == right.host_id
        and left.resource_type == right.resource_type
        and Path(left.managed_root).resolve() == Path(right.managed_root).resolve()
        and left.created_by == right.created_by == CREATED_BY
    )


def _is_active(path: Path, active_roots: Iterable[Path]) -> bool:
    resolved = path.resolve()
    for item in active_roots:
        try:
            other = Path(item).resolve()
        except OSError:
            continue
        if other == resolved:
            return True
        try:
            other.relative_to(resolved)
            return True
        except ValueError:
            continue
    return False


def _looks_legacy(path: Path, state_root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(state_root)
    except ValueError:
        return False
    return relative.parts[0] in LEGACY_DIRECTORY_NAMES if relative.parts else False


def _tree_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    for current, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(current) / name).stat().st_size
            except OSError:
                continue
    return total


def _maybe_str(value: object) -> Maybe[str]:
    if not is_resolved(value) or value is None:
        return NOT_PROVIDED
    return str(value)

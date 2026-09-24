"""Sequential per-kind schema upgrades. Unknown versions fail closed."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from machi.kernel.errors import (
    InternalError,
    UnknownKindError,
    UnknownVersionError,
    ValidationError,
)

Upgrade = Callable[[Mapping[str, Any]], dict[str, Any]]
_UPGRADES: dict[tuple[str, int], Upgrade] = {}
_CHAIN_LIMIT = 16


def register_upgrade(kind: str, from_version: int, upgrade: Upgrade) -> None:
    """Register the only step from ``from_version`` to the next version."""
    if from_version < 1:
        raise InternalError("upgrade source version must be positive", kind=kind)
    _UPGRADES[(kind, from_version)] = upgrade


def migrate_document(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return the current-version document. A current record is unchanged."""
    kind = data.get("kind")
    version = data.get("schema_version")
    if not isinstance(kind, str):
        raise ValidationError("record has no 'kind'", got=type(kind).__name__)
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValidationError(
            "record has no integer 'schema_version'",
            kind=kind,
        )
    current = _current_version(kind)
    if current is None:
        raise UnknownKindError("no contract is registered under this kind", kind=kind)
    if version > current:
        raise UnknownVersionError(
            "contract kind is known, but not at this version",
            kind=kind,
            requested_version=version,
            known_versions=_known_versions(kind),
        )
    document = dict(data)
    steps = 0
    while int(document["schema_version"]) < current:
        source = int(document["schema_version"])
        upgrade = _UPGRADES.get((kind, source))
        if upgrade is None:
            raise UnknownVersionError(
                "no registered upgrade for this contract version",
                kind=kind,
                requested_version=source,
                known_versions=_known_versions(kind),
            )
        upgraded = upgrade(document)
        if upgraded.get("schema_version") != source + 1:
            raise InternalError(
                "upgrade must advance exactly one schema version",
                kind=kind,
                from_version=source,
            )
        if upgraded.get("kind") != kind:
            raise InternalError("upgrade must not change the contract kind", kind=kind)
        document = upgraded
        steps += 1
        if steps > _CHAIN_LIMIT:
            raise InternalError("upgrade chain is too long", kind=kind)
    return document


def _current_version(kind: str) -> int | None:
    versions = _known_versions(kind)
    if not versions:
        return None
    return versions[-1]


def _known_versions(kind: str) -> list[int]:
    from machi.kernel.schema import registered_contracts

    return sorted(
        version for registered, version in registered_contracts() if registered == kind
    )

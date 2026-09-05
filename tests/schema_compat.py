"""Classify a fingerprint difference as compatible or breaking.

The previous attempt's own migration discipline was "prefer additive
introduction, a compatibility period, caller migration, then explicit
deprecation." That is a sound rule and this is the mechanical form of it:

- adding an **optional** field to a shipped contract is compatible;
- adding a **required** field, removing a field, changing a field's type,
  changing its nullability or unknown-ness, or restating its meaning is
  breaking and demands a ``schema_version`` bump;
- removing a whole shipped ``kind@version`` is breaking;
- adding a new ``kind@version`` is compatible.

A change of meaning that keeps both name and type cannot be caught here.
That is why the meaning text is part of the fingerprint: a human reads it in
the diff. The limit is recorded in `docs/DEBT.md` rather than pretended away.
"""

from __future__ import annotations

from typing import Any

_SHAPE_KEYS = ("type", "nullable", "may_be_unresolved")


def breaking_changes(
    committed: dict[str, Any], current: dict[str, Any]
) -> list[str]:
    """Every difference that requires a schema_version bump."""
    problems: list[str] = []
    for identity, old in committed.items():
        new = current.get(identity)
        if new is None:
            problems.append(f"{identity}: a shipped contract was removed")
            continue
        problems.extend(_compare_fields(identity, old["fields"], new["fields"]))
    return problems


def _compare_fields(
    identity: str, old: dict[str, Any], new: dict[str, Any]
) -> list[str]:
    problems: list[str] = []
    for name, previous in old.items():
        current = new.get(name)
        if current is None:
            problems.append(f"{identity}.{name}: field removed")
            continue
        for key in _SHAPE_KEYS:
            if previous[key] != current[key]:
                problems.append(
                    f"{identity}.{name}: {key} changed from "
                    f"{previous[key]!r} to {current[key]!r}"
                )
        if previous["meaning"] != current["meaning"]:
            problems.append(
                f"{identity}.{name}: meaning was restated; if the field now means "
                f"something different, bump schema_version"
            )
    for name, current in new.items():
        if name not in old and not current["optional"]:
            problems.append(
                f"{identity}.{name}: a required field was added to a shipped contract"
            )
    return problems


def compatible_additions(
    committed: dict[str, Any], current: dict[str, Any]
) -> list[str]:
    """Differences that are allowed without a version bump."""
    additions = [
        f"{identity}: new contract"
        for identity in current
        if identity not in committed
    ]
    for identity, new in current.items():
        old = committed.get(identity)
        if old is None:
            continue
        additions.extend(
            f"{identity}.{name}: optional field added"
            for name, field in new["fields"].items()
            if name not in old["fields"] and field["optional"]
        )
    return additions

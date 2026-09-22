"""Bounded occupancy measurement for one verified root.

Counts in-tree inode sizes once. Does not follow symlinks, does not
cross onto another device, and does not delete.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from machi.kernel.unresolved import NOT_MEASURED, Maybe, Unresolved


@dataclass(frozen=True, slots=True)
class TreeMeasurement:
    """Bytes inside one root, plus the safety stops that fired."""

    size_bytes: Maybe[int]
    symlink_escapes: int
    mount_crossings: int
    inaccessible: int


def measure_owned_tree(root: Path) -> TreeMeasurement:
    """Measure ``root`` without leaving it. A symlink root is not measured."""
    if root.is_symlink():
        return TreeMeasurement(
            size_bytes=Unresolved(
                NOT_MEASURED.reason, "refusing to measure through a symlink root"
            ),
            symlink_escapes=1,
            mount_crossings=0,
            inaccessible=0,
        )
    try:
        root_stat = os.lstat(root)
    except OSError:
        return TreeMeasurement(
            size_bytes=NOT_MEASURED,
            symlink_escapes=0,
            mount_crossings=0,
            inaccessible=1,
        )
    seen: set[tuple[int, int]] = set()
    total = 0
    escapes = 0
    crossings = 0
    inaccessible = 0

    def add(stat: os.stat_result) -> None:
        nonlocal total
        key = (stat.st_dev, stat.st_ino)
        if key in seen:
            return
        seen.add(key)
        total += stat.st_size

    def walk(directory: Path) -> None:
        nonlocal escapes, crossings, inaccessible
        try:
            children = list(directory.iterdir())
        except OSError:
            inaccessible += 1
            return
        for child in children:
            try:
                stat = os.lstat(child)
            except OSError:
                inaccessible += 1
                continue
            if child.is_symlink():
                if _escapes(child, root):
                    escapes += 1
                add(stat)
                continue
            if stat.st_dev != root_stat.st_dev:
                crossings += 1
                continue
            add(stat)
            if child.is_dir():
                walk(child)

    add(root_stat)
    if root.is_dir():
        walk(root)
    if inaccessible:
        return TreeMeasurement(
            size_bytes=Unresolved(
                NOT_MEASURED.reason, "part of the managed root could not be read"
            ),
            symlink_escapes=escapes,
            mount_crossings=crossings,
            inaccessible=inaccessible,
        )
    return TreeMeasurement(
        size_bytes=total,
        symlink_escapes=escapes,
        mount_crossings=crossings,
        inaccessible=0,
    )


def _escapes(link: Path, root: Path) -> bool:
    try:
        raw = link.readlink()
    except OSError:
        return True
    target = raw if raw.is_absolute() else link.parent / raw
    normalized = Path(os.path.normpath(target))
    try:
        normalized.relative_to(root)
    except ValueError:
        return True
    return False

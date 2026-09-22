"""Bounded observational write probe (MACHI 2.4.1).

A tiny create/write/fsync/delete against a Machi-owned temporary name.
Success means this path accepted that payload. It does not prove usable
GiB and it does not compute SAFE storage. Discover does not fill disks.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from pathlib import Path

from machi.discover.mount_contracts import WriteProbeOutcome
from machi.discover.mounts import MAX_WRITE_PROBE_BYTES
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import Maybe

PROBE_PREFIX = ".machi-mount-probe-"
_DETAIL_MAX = 160


def bounded_write_probe(
    directory: str,
    max_bytes: int,
    *,
    random_token: Callable[[int], str] | None = None,
) -> tuple[WriteProbeOutcome, Maybe[int], Maybe[bool], str]:
    """Write a tiny payload and delete it. Never fill, never walk trees."""
    if max_bytes < 1 or max_bytes > MAX_WRITE_PROBE_BYTES:
        raise ValidationError(
            "write probe payload is outside the observational bound",
            max_bytes=max_bytes,
        )
    token = (random_token or secrets.token_hex)(6)
    target = Path(directory) / f"{PROBE_PREFIX}{token}"
    payload = b"m" * max_bytes
    created = False
    try:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        created = True
        try:
            written = os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        if written != max_bytes:
            cleaned = _try_remove_probe(target)
            return (
                WriteProbeOutcome.FAILED
                if cleaned
                else WriteProbeOutcome.CLEANUP_FAILED,
                max_bytes,
                cleaned,
                _detail("short write during observational probe"),
            )
        cleaned = _try_remove_probe(target)
        if not cleaned:
            return (
                WriteProbeOutcome.CLEANUP_FAILED,
                max_bytes,
                False,
                _detail(
                    "observational probe wrote then failed to remove the temp file"
                ),
            )
        return WriteProbeOutcome.SUCCEEDED, max_bytes, True, ""
    except OSError as exc:
        cleaned = True
        if created or target.exists():
            cleaned = _try_remove_probe(target)
        outcome = (
            WriteProbeOutcome.CLEANUP_FAILED
            if created and not cleaned
            else WriteProbeOutcome.FAILED
        )
        return (
            outcome,
            max_bytes,
            cleaned,
            _detail(f"observational probe failed: {exc}"),
        )


def _try_remove_probe(target: Path) -> bool:
    try:
        target.unlink()
        return True
    except OSError:
        return False


def _detail(text: str) -> str:
    if len(text) <= _DETAIL_MAX:
        return text
    return text[: _DETAIL_MAX - 3] + "..."

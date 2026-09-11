"""Deterministic incompressible payload for empirical writes.

Not a CSPRNG. Repeatable, bounded memory, not all-zero blocks.
"""

from __future__ import annotations

import hashlib

PAYLOAD_VERSION = "shake128-v1"
_DOMAIN = b"kultrun-sonar-v2"


def fill_payload(buffer: bytearray, start_offset: int) -> None:
    """Fill ``buffer`` as bytes ``[start_offset, start_offset+len)``."""
    if not buffer:
        return
    seed = start_offset.to_bytes(16, "little") + _DOMAIN
    buffer[:] = hashlib.shake_128(seed).digest(len(buffer))

"""Bounded loopback port allocation. Not a network orchestration platform."""

from __future__ import annotations

import socket
from collections.abc import Iterable

from kultrun.kernel.errors import PreconditionFailedError

LOOPBACK = "127.0.0.1"
_ATTEMPTS = 8


def allocate_loopback_port(occupied: Iterable[int] = ()) -> int:
    """Pick a free loopback TCP port. Collision with live instances is refused."""
    taken = {int(port) for port in occupied}
    for _ in range(_ATTEMPTS):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((LOOPBACK, 0))
            port = int(sock.getsockname()[1])
        if port not in taken:
            return port
    raise PreconditionFailedError(
        "no free loopback port for this instance",
        reason="endpoint_unavailable",
    )


def is_loopback(address: str) -> bool:
    """True for IPv4/IPv6 loopback identities this vertical may bind."""
    token = address.strip().lower()
    return token in {LOOPBACK, "localhost", "::1"}

"""Loopback port selection. Occupied ports are skipped, never killed."""

from __future__ import annotations

import hashlib
import socket

from machi.serve.policy import ServePolicy

_LOOPBACK = "127.0.0.1"


def choose_port(reservation_id: str, policy: ServePolicy) -> int | None:
    """Pick one free port in the bounded window. None means the window is full."""
    if policy.port_span < 1:
        return None
    offset = int(hashlib.sha256(reservation_id.encode()).hexdigest()[:8], 16)
    offset %= policy.port_span
    for step in range(policy.port_span):
        port = policy.port_base + ((offset + step) % policy.port_span)
        if _free(port):
            return port
    return None


def _free(port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((_LOOPBACK, port))
    except OSError:
        return False
    else:
        return True
    finally:
        probe.close()

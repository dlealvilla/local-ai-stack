"""Serve policy. Native vLLM and one provider path have separate versions."""

from __future__ import annotations

from dataclasses import dataclass

POLICY_VERSION = "m9.serve.1"
PROVIDER_POLICY_VERSION = "m9.serve.provider.1"
BIND_SCOPE = "loopback"
PORT_BASE = 18080
PORT_SPAN = 32
STARTUP_TIMEOUT_SECONDS = 180.0
STOP_GRACE_SECONDS = 10.0
INFERENCE_TIMEOUT_SECONDS = 60.0
LOG_MAX_BYTES = 65536


@dataclass(frozen=True, slots=True)
class ServePolicy:
    """Inspectable bounds. Tests may use a shorter copy."""

    version: str = POLICY_VERSION
    startup_timeout_seconds: float = STARTUP_TIMEOUT_SECONDS
    stop_grace_seconds: float = STOP_GRACE_SECONDS
    inference_timeout_seconds: float = INFERENCE_TIMEOUT_SECONDS
    log_max_bytes: int = LOG_MAX_BYTES
    port_base: int = PORT_BASE
    port_span: int = PORT_SPAN

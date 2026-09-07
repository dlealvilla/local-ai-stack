"""Reference serving runtime. Translates a request into a loopback recipe."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeReadiness,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
)

IDENTITY = Name("reference-serving")
EXECUTOR_KIND = Name("native-process")
WORKLOAD_MODULE = "kultrun.adapters.runtime.serving_workload"
READY_MARKER = "kultrun-reference-serving:ready"
_IMPORT_ROOT = str(Path(__file__).resolve().parents[3])


class ReferenceServingRuntime:
    """Produces argv for the reference HTTP server. Does not exec."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            runtime=self.identity,
            display_name="Reference serving (lifecycle harness)",
            executor_kind=EXECUTOR_KIND,
            capabilities=("process-lifecycle", "loopback-health", "readiness"),
        )

    def support(self) -> RuntimeSupportDescriptor:
        return RuntimeSupportDescriptor(
            runtime=self.identity,
            display_name="Reference serving (lifecycle harness)",
            support_tier=RuntimeSupportTier.TEST_ONLY,
            production_candidate=False,
            supported_os_families=("linux", "darwin"),
            supported_architectures=("x86_64", "arm64"),
            compatible_executor_types=(EXECUTOR_KIND, Name("recording")),
            required_features=(
                "process_execution",
                "structured_argv",
                "environment_variables",
                "stdout_capture",
            ),
            known_modalities=(),
            limitations=(
                "TEST_ONLY reference harness",
                "not a production model-serving runtime",
                "loopback HTTP only",
            ),
            evidence=("stage-1.5B-reference-serving",),
            confidence=Confidence.HIGH,
        )

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        mode = request.mode if request is not None else "healthy"
        instance_id = request.instance_id if request is not None else ""
        bind = request.bind_address if request is not None else "127.0.0.1"
        return RuntimeLaunchSpec(
            runtime=self.identity,
            profile=self.identity,
            executable=sys.executable,
            arguments=("-m", WORKLOAD_MODULE),
            environment=(
                "KULTRUN_REFERENCE_SERVING=1",
                f"KULTRUN_REFERENCE_SERVING_MODE={mode}",
                f"KULTRUN_INSTANCE_ID={instance_id}",
                f"KULTRUN_REFERENCE_BIND={bind}",
                f"PYTHONPATH={_child_pythonpath()}",
            ),
            grace_period_seconds=2.0,
            network_bindings=(f"tcp:{bind}:0",),
        )

    def inspect_readiness(
        self,
        *,
        stdout: str,
        stderr: str,
        execution_alive: bool,
        bound_address: str | None = None,
        bound_port: int | None = None,
    ) -> RuntimeReadiness:
        del stderr
        if not execution_alive:
            return RuntimeReadiness(
                ready=False, reason="execution is not alive"
            )
        parsed = _ready_from_stdout(stdout)
        host = bound_address or (parsed[0] if parsed is not None else None)
        published = parsed[1] if parsed is not None else None
        port = bound_port if bound_port is not None else published
        if host is None or port is None:
            return RuntimeReadiness(
                ready=False, reason="bind address not published"
            )
        if not _health_ok(host, port):
            return RuntimeReadiness(
                ready=False,
                address=host,
                port=port,
                reason="health probe failed",
            )
        return RuntimeReadiness(
            ready=True,
            address=host,
            port=port,
            reason="loopback /health ready",
        )


def _child_pythonpath() -> str:
    current = os.environ.get("PYTHONPATH", "")
    if not current:
        return _IMPORT_ROOT
    parts = current.split(os.pathsep)
    if _IMPORT_ROOT in parts:
        return current
    return _IMPORT_ROOT + os.pathsep + current


def _ready_from_stdout(stdout: str) -> tuple[str, int] | None:
    for line in stdout.splitlines():
        if not line.startswith(READY_MARKER):
            continue
        parts = line.split()
        if len(parts) >= 3:
            try:
                return parts[1], int(parts[2])
            except ValueError:
                return None
    return None


def _health_ok(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=0.4) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False
    return bool(isinstance(body, dict) and body.get("ready") is True)


def build() -> ReferenceServingRuntime:
    return ReferenceServingRuntime()

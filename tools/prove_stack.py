"""Shared helpers for installed-wheel inference proofs. Not product code."""

from __future__ import annotations

import datetime as dt
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.capacity.contracts import (
    AcceleratorCapacity,
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import (
    Accelerator,
    AcceleratorVendor,
    Architecture,
    CpuFacts,
    ExecutionCapabilities,
    HostCapabilities,
    HostId,
    MemoryFacts,
    MountFacts,
    NetworkFacts,
    OperatingEnvironment,
)
from kultrun.inference.service import InstanceService
from kultrun.kernel.clock import FixedClock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED
from kultrun.model.contracts import (
    ArtifactId,
    ArtifactState,
    MemoryPlacement,
    ModelArtifact,
    ModelId,
)
from kultrun.model.inventory import ModelInventory
from kultrun.model.store import ModelArtifactStore
from kultrun.resource.contracts import (
    RequestId,
    ResourceRequest,
    ResourceReservation,
    WorkloadType,
)
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.catalogue import RuntimeCatalogue
from kultrun.runtime.contracts import RuntimeLaunchRequest, RuntimeLaunchSpec

INSTANT = dt.datetime(2026, 9, 7, 21, 0, tzinfo=dt.UTC)
GIB = 1024**3
SMALL = 4 * GIB

PROTOCOL = r"""
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = os.environ.get("KULTRUN_VLLM_FIXTURE_HOST", "127.0.0.1")
PORT = int(os.environ.get("KULTRUN_VLLM_FIXTURE_PORT", "0"))
MODEL = os.environ.get("KULTRUN_VLLM_FIXTURE_MODEL", "fixture")
DELAY = float(os.environ.get("KULTRUN_VLLM_FIXTURE_DELAY", "0"))
LOG_BYTES = int(os.environ.get("KULTRUN_VLLM_FIXTURE_LOG_BYTES", "0"))
STARTED = time.monotonic()

if LOG_BYTES > 0:
    import threading
    def _flood():
        sent = 0
        chunk = ("noise " * 128) + "\n"
        while sent < LOG_BYTES:
            sys.stdout.write(chunk)
            sys.stdout.flush()
            sys.stderr.write(chunk)
            sys.stderr.flush()
            sent += 2 * len(chunk)
            time.sleep(0.01)
    threading.Thread(target=_flood, daemon=True).start()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return
    def _send(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if self.path == "/health":
            if (time.monotonic() - STARTED) < DELAY:
                self._send(503, {"error": "loading"})
                return
            self._send(200, {"status": "ok"})
            return
        if self.path == "/v1/models":
            self._send(200, {"data": [{"id": MODEL, "object": "model"}]})
            return
        self._send(404, {"error": "missing"})
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8") or "{}")
        prompt = str(payload.get("prompt", ""))
        self._send(200, {
            "id": "cmpl-fixture",
            "model": MODEL,
            "choices": [{"text": "ok:" + prompt[:80], "finish_reason": "stop"}],
        })

HTTPServer((HOST, PORT), Handler).serve_forever()
"""


def _layered(safe: int) -> LayeredBytes:
    return LayeredBytes(
        reported_bytes=safe * 2,
        effective_bytes=safe,
        safe_bytes=safe,
        confidence=Confidence.HIGH,
        provenance=Provenance(
            producer=Name("test"),
            producer_version="t",
            observed_at=INSTANT,
            policy_version="t",
        ),
    )


def host_capabilities() -> HostCapabilities:
    return HostCapabilities(
        host_id=HostId.generate(),
        fingerprint="abc123",
        detected_at=INSTANT,
        operating_environment=OperatingEnvironment(
            os_name="linux",
            os_version="6.8.0",
            architecture=Architecture.X86_64,
            kernel_version=NOT_MEASURED,
            virtualized=True,
        ),
        cpu=CpuFacts(
            vendor="AuthenticAMD",
            model_name=NOT_MEASURED,
            physical_cores=32,
            logical_cores=64,
        ),
        memory=MemoryFacts(
            total_bytes=274_877_906_944,
            available_bytes=NOT_MEASURED,
            unified_with_accelerator=False,
        ),
        execution=ExecutionCapabilities(
            native_process=True, docker=True, podman=NOT_MEASURED
        ),
        network=NetworkFacts(
            hostname="reference", loopback_address="127.0.0.1", occupied_ports=(22,)
        ),
        accelerators=(
            Accelerator(
                index=0,
                vendor=AcceleratorVendor.NVIDIA,
                model_name="L40S",
                memory_total_bytes=48_305_799_168,
                driver_version="550.90.07",
                unified_memory=False,
            ),
        ),
        mounts=(
            MountFacts(
                mount_point="/",
                device=NOT_MEASURED,
                filesystem_type="ext4",
                total_bytes=1_000_000_000_000,
                free_bytes=900_000_000_000,
            ),
        ),
    )


class Stack:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.store = FileStore(tmp_path / "records")
        self.clock = FixedClock(INSTANT)
        self.artifacts = ModelArtifactStore(tmp_path / "models")
        self.inventory = ModelInventory(self.store, self.artifacts)
        self.resources = ResourceManager(
            self.store, self.clock, AdmissionLock(tmp_path / "locks")
        )
        self.executions = ExecutionService(
            NativeProcessExecutor(SystemClock()), self.store
        )
        self.runtimes = RuntimeCatalogue((ReferenceServingRuntime(),))
        self.instances = InstanceService(
            self.store,
            self.clock,
            self.inventory,
            self.resources,
            self.executions,
            self.runtimes,
            startup_timeout=1.2,
        )
        self.envelope = CapacityEnvelope(
            host_id=HostId.generate(),
            host_fingerprint="test-host",
            computed_at=INSTANT,
            policy_version="test",
            memory=_layered(48 * GIB),
            memory_requirement=EvidenceRequirement.SUFFICIENT,
            accelerators=(
                AcceleratorCapacity(
                    index=0,
                    memory=_layered(24 * GIB),
                    requirement=EvidenceRequirement.SUFFICIENT,
                ),
            ),
            pools=(
                PoolCapacity(
                    mount_point="/data",
                    space=_layered(10**11),
                    requirement=EvidenceRequirement.SUFFICIENT,
                    filesystem_type="ext4",
                ),
            ),
        )

    def stored(self) -> ModelArtifact:
        artifact = ModelArtifact(
            artifact_id=ArtifactId.generate(),
            model_id=ModelId.generate(),
            revision="rev-a",
            state=ArtifactState.STORED,
            logical_name="probe-model",
            installed_bytes=8 * GIB,
            quantization="q4",
        )
        path = self.artifacts.manifest_path(artifact.artifact_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        self.inventory.put(artifact, HostId.generate())
        found = self.inventory.get(artifact.artifact_id)
        assert found is not None
        return found

    def reserve(self, artifact: ModelArtifact) -> ResourceReservation:
        decision = self.resources.admit(
            ResourceRequest(
                request_id=RequestId.generate(),
                host_id=self.envelope.host_id,
                artifact_id=artifact.artifact_id,
                model_id=artifact.model_id,
                plan_fingerprint="test-plan",
                placement=MemoryPlacement.DISCRETE_GPU,
                ram_bytes=2 * GIB,
                accelerator_bytes=SMALL,
                unified_bytes=NOT_PROVIDED,
                logical_name=artifact.logical_name,
                accelerator_index=0,
                incremental_storage_bytes=NOT_PROVIDED,
                workload_type=WorkloadType.INFERENCE,
                model_revision=artifact.revision,
                quantization=artifact.quantization,
            ),
            self.envelope,
            artifact,
        )
        assert decision.reservation is not None
        return decision.reservation


def make_stack(tmp_path: Path) -> Stack:
    return Stack(tmp_path)


def wrap_launch(original: Any) -> Any:
    delay = float(os.environ.get("KULTRUN_DELAY", "0"))
    log_bytes = int(os.environ.get("KULTRUN_LOG_BYTES", "262144"))

    def launch_spec(
        self: VllmRuntimeSupport, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        spec = original(self, request)
        assert isinstance(spec, RuntimeLaunchSpec)
        assert request is not None
        extra = (
            f"KULTRUN_VLLM_FIXTURE_HOST={request.bind_address}",
            f"KULTRUN_VLLM_FIXTURE_PORT={request.bind_port}",
            f"KULTRUN_VLLM_FIXTURE_MODEL={request.served_model}",
            f"KULTRUN_VLLM_FIXTURE_DELAY={delay}",
            f"KULTRUN_VLLM_FIXTURE_LOG_BYTES={log_bytes}",
        )
        return replace(
            spec,
            executable=sys.executable,
            arguments=("-c", PROTOCOL),
            environment=spec.environment + extra,
            grace_period_seconds=2.0,
        )

    return launch_spec

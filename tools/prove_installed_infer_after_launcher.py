#!/usr/bin/env python3
"""Prove installed-wheel capture lifetime + infer-after-launcher + telemetry.

Development/acceptance proof, not a product command. Run with the isolated
venv python after a clean wheel install. Must not import the source checkout.

    python tools/prove_installed_infer_after_launcher.py
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

PROMPT = "UNIQUE_INSTALLED_INFER_TOKEN_16L"
LAUNCHER = r"""
from __future__ import annotations

import os
from pathlib import Path

from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.adapters.telemetry.sqlite import SQLiteTelemetryStore
from kultrun.inference.contracts import InferenceInstance, InstanceId, ObservedState
from kultrun.inference.endpoint import LOOPBACK, allocate_loopback_port
from kultrun.inference.service import InstanceService, served_model_identity
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.platform.deployment_instance import InstanceView
from kultrun.platform.telemetry_observe import bind_deployment_instance
from kultrun.resource.contracts import LedgerHealth
from kultrun.runtime.catalogue import RuntimeCatalogue
from kultrun.runtime.contracts import RuntimeLaunchRequest
from kultrun.telemetry.service import BestEffortRecorder
from prove_stack import host_capabilities, make_stack, wrap_launch

tmp = Path(os.environ["KULTRUN_TMP"])
stack = make_stack(tmp)
original = VllmRuntimeSupport.launch_spec
VllmRuntimeSupport.launch_spec = wrap_launch(original)
stack.runtimes = RuntimeCatalogue(
    (stack.runtimes.get(Name("reference-serving")), VllmRuntimeSupport())
)
stack.instances = InstanceService(
    stack.store,
    stack.clock,
    stack.inventory,
    stack.resources,
    stack.executions,
    stack.runtimes,
    startup_timeout=8.0,
    live_executor="native-process",
)
db = tmp / "telemetry" / "kultrun-telemetry.sqlite3"
recorder = BestEffortRecorder(SQLiteTelemetryStore.open(db, stack.clock))

class _Facade:
    def start(self, instance_id, host, *, ledger_health, serving_mode="healthy"):
        del host, serving_mode
        found = stack.store.get(InferenceInstance, instance_id.value)
        port = allocate_loopback_port()
        request = RuntimeLaunchRequest(
            instance_id=found.instance_id.value,
            artifact_id=(
                found.artifact_id.value if found.artifact_id is not None else ""
            ),
            interpreter=str(tmp / "venv" / "bin" / "python"),
            model_path=str(tmp / "artifact-model"),
            served_model=served_model_identity(found),
            bind_address=LOOPBACK,
            bind_port=port,
            accelerator_index=0,
            quantization=NOT_PROVIDED,
            runtime_version="0.28.0",
            reserved_accelerator_bytes=4 * 1024**3,
            accelerator_memory_total_bytes=32 * 1024**3,
        )
        started = stack.instances.start(
            instance_id, ledger_health=ledger_health, launch_request=request,
        )
        return InstanceView(started, "current")

    def stop(self, instance_id, host):
        del host
        return InstanceView(stack.instances.stop(instance_id), "current")

bound = bind_deployment_instance(_Facade(), recorder, stack.clock)
instance_id = InstanceId.parse(os.environ["KULTRUN_INSTANCE"])
view = bound.start(
    instance_id, host_capabilities(), ledger_health=LedgerHealth.WITHIN_CAPACITY,
)
assert view.instance.observed_state is ObservedState.RUNNING
assert view.instance.endpoint is not None
print(
    f"PARENT_SUCCESS pid={os.getpid()} child={view.instance.pid} "
    f"port={view.instance.endpoint.port}",
    flush=True,
)
raise SystemExit(0)
"""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def main() -> int:
    from prove_stack import make_stack  # type: ignore[import-not-found]

    import kultrun
    from kultrun.adapters.execution.native_process import NativeProcessExecutor
    from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
    from kultrun.execution.service import ExecutionService
    from kultrun.inference.contracts import (
        InferenceInstance,
        InferenceRequest,
        ObservedState,
    )
    from kultrun.inference.service import InstanceService
    from kultrun.kernel.clock import SystemClock
    from kultrun.kernel.ids import Name
    from kultrun.runtime.catalogue import RuntimeCatalogue

    origin = Path(kultrun.__file__).resolve()
    if "site-packages" not in str(origin):
        print(f"FAIL: kultrun is not an installed artifact: {origin}", file=sys.stderr)
        return 2
    tools = Path(__file__).resolve().parent
    site = origin.parent.parent
    work = Path(tempfile.mkdtemp(prefix="kultrun-installed-infer-"))
    (work / "artifact-model").mkdir()
    (work / "artifact-model" / "config.json").write_text("{}", encoding="utf-8")
    interpreter = work / "venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
    interpreter.chmod(0o755)
    stack = make_stack(work)
    artifact = stack.stored()
    reservation = stack.reserve(artifact)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(site), str(tools)))
    env["KULTRUN_TMP"] = str(work)
    env["KULTRUN_INSTANCE"] = instance.instance_id.value
    env["KULTRUN_LOG_BYTES"] = "262144"
    launcher = work / "start_cli.py"
    launcher.write_text(LAUNCHER, encoding="utf-8")
    finished = subprocess.run(
        [sys.executable, str(launcher)],
        cwd=str(work),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if finished.returncode != 0:
        print(finished.stdout)
        print(finished.stderr, file=sys.stderr)
        return finished.returncode or 3
    child = int(finished.stdout.strip().rsplit("child=", 1)[1].split()[0])
    try:
        if not _pid_alive(child):
            print("child died when parent exited", file=sys.stderr)
            return 4
        recorded = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert recorded is not None
        assert recorded.observed_state is ObservedState.RUNNING
        other = InstanceService(
            stack.store,
            SystemClock(),
            stack.inventory,
            stack.resources,
            ExecutionService(NativeProcessExecutor(SystemClock()), stack.store),
            RuntimeCatalogue(
                (stack.runtimes.get(Name("reference-serving")), VllmRuntimeSupport())
            ),
            live_executor="native-process",
        )
        generated = other.infer(instance.instance_id, InferenceRequest(prompt=PROMPT))
        if not generated.generated_text.startswith("ok:" + PROMPT[:80]):
            print(generated.generated_text, file=sys.stderr)
            return 5
        database = work / "telemetry" / "kultrun-telemetry.sqlite3"
        blob = database.read_bytes()
        if PROMPT.encode("utf-8") in blob:
            print("telemetry stored prompt payload", file=sys.stderr)
            return 6
        connection = sqlite3.connect(database)
        try:
            runs = connection.execute("SELECT COUNT(*) FROM deployment_run").fetchone()
            events = connection.execute(
                "SELECT COUNT(*) FROM deployment_event"
            ).fetchone()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            connection.close()
        if runs is None or runs[0] < 1 or events is None or events[0] < 1:
            print("telemetry missing run/event rows", file=sys.stderr)
            return 7
        if integrity != ("ok",):
            print(integrity, file=sys.stderr)
            return 8
        payload = {
            "parent_exit_code": finished.returncode,
            "child_pid": child,
            "child_alive": True,
            "generated_prefix": generated.generated_text[:40],
            "deployment_runs": runs[0],
            "deployment_events": events[0],
            "integrity": "ok",
            "kultrun_file": str(origin),
            "result": "PASS",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(child, signal.SIGKILL)


if __name__ == "__main__":
    raise SystemExit(main())

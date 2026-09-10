"""Acceptance: capture-lifetime + telemetry + infer-after-launcher.

Physical T5 must start → CLI return → infer, without inspect/list/reconcile.
"""

from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

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
from kultrun.resource.contracts import ReservationState
from kultrun.runtime.catalogue import RuntimeCatalogue
from tests.test_inference_instance import SMALL, _Stack

REPO = Path(__file__).resolve().parent.parent
PROMPT = "UNIQUE_ACCEPTANCE_INFER_TOKEN_16L"

START_CLI = r"""
from pathlib import Path
import os
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.adapters.telemetry.sqlite import SQLiteTelemetryStore
from kultrun.inference.contracts import InferenceInstance, InstanceId, ObservedState
from kultrun.inference.service import InstanceService
from kultrun.kernel.ids import Name
from kultrun.platform.deployment_instance import InstanceView
from kultrun.platform.telemetry_observe import bind_deployment_instance
from kultrun.resource.contracts import LedgerHealth
from kultrun.runtime.catalogue import RuntimeCatalogue
from kultrun.telemetry.service import BestEffortRecorder
from tests.test_contracts import host_capabilities
from tests.test_inference_instance import _Stack
from tests.test_runtime_vllm_inference import _complete_request
from tests.test_telemetry import _Boom
from tests.vllm_protocol import wrap_launch_with_protocol

tmp = Path(os.environ["KULTRUN_TMP"])
delay = float(os.environ.get("KULTRUN_DELAY", "0"))
mode = os.environ.get("KULTRUN_MODE", "healthy")
boom = os.environ.get("KULTRUN_TELEMETRY_BOOM", "") == "1"
db = tmp / "telemetry" / "kultrun-telemetry.sqlite3"
stack = _Stack(tmp)
original = VllmRuntimeSupport.launch_spec
VllmRuntimeSupport.launch_spec = wrap_launch_with_protocol(
    original, mode=mode, delay=delay, log_bytes=131072
)
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
if boom:
    recorder = BestEffortRecorder(_Boom())
else:
    sqlite = SQLiteTelemetryStore.open(db, stack.clock)
    recorder = BestEffortRecorder(sqlite)

class _Facade:
    def start(self, instance_id, host, *, ledger_health, serving_mode="healthy"):
        del host, serving_mode
        found = stack.store.get(InferenceInstance, instance_id.value)
        started = stack.instances.start(
            instance_id,
            ledger_health=ledger_health,
            launch_request=_complete_request(tmp, found),
        )
        return InstanceView(started, "current")

    def stop(self, instance_id, host):
        del host
        return InstanceView(stack.instances.stop(instance_id), "current")

bound = bind_deployment_instance(_Facade(), recorder, stack.clock)
instance_id = InstanceId.parse(os.environ["KULTRUN_INSTANCE"])
view = bound.start(
    instance_id,
    host_capabilities(),
    ledger_health=LedgerHealth.WITHIN_CAPACITY,
)
assert view.instance.observed_state is ObservedState.RUNNING
assert view.instance.endpoint is not None
error = recorder.last_error or ""
Path(os.environ["KULTRUN_ERROR_FILE"]).write_text(error, encoding="utf-8")
print(
    f"PARENT_SUCCESS pid={os.getpid()} child={view.instance.pid} "
    f"port={view.instance.endpoint.port}",
    flush=True,
)
raise SystemExit(0)
"""


def _pythonpath() -> str:
    return os.pathsep.join(
        (str(Path(kultrun.__file__).resolve().parent.parent), str(REPO))
    )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _other_instances(stack: _Stack) -> InstanceService:
    stack.runtimes = RuntimeCatalogue(
        (stack.runtimes.get(Name("reference-serving")), VllmRuntimeSupport())
    )
    return InstanceService(
        stack.store,
        SystemClock(),
        stack.inventory,
        stack.resources,
        ExecutionService(NativeProcessExecutor(SystemClock()), stack.store),
        stack.runtimes,
        live_executor="native-process",
    )


def _launch_start_cli(
    tmp_path: Path,
    instance_id: str,
    *,
    delay: float = 0.0,
    boom: bool = False,
) -> tuple[subprocess.CompletedProcess[str], int]:
    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath()
    env["KULTRUN_TMP"] = str(tmp_path)
    env["KULTRUN_INSTANCE"] = instance_id
    env["KULTRUN_DELAY"] = str(delay)
    env["KULTRUN_TELEMETRY_BOOM"] = "1" if boom else "0"
    env["KULTRUN_ERROR_FILE"] = str(tmp_path / "telemetry-error.txt")
    script = tmp_path / "start_cli.py"
    script.write_text(START_CLI, encoding="utf-8")
    finished = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr + finished.stdout
    child = int(finished.stdout.strip().rsplit("child=", 1)[1].split()[0])
    return finished, child


def test_native_process_has_no_pipe_pumps() -> None:
    source = Path(
        Path(kultrun.__file__).resolve().parent
        / "adapters"
        / "execution"
        / "native_process.py"
    ).read_text(encoding="utf-8")
    assert "kultrun-exec-capture" not in source
    assert "stdout=subprocess.PIPE" not in source
    assert "stderr=subprocess.PIPE" not in source
    assert "start_new_session=True" in source
    assert "_anonymous_file" in source
    assert "os.pread" in source
    assert "K-99" in source


def test_telemetry_start_parent_exits_and_child_stays(tmp_path: Path) -> None:
    stack = _Stack(tmp_path)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    finished, child = _launch_start_cli(tmp_path, instance.instance_id.value)
    try:
        assert "PARENT_SUCCESS" in finished.stdout
        assert _pid_alive(child)
        recorded = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert recorded is not None
        assert recorded.observed_state is ObservedState.RUNNING
        database = tmp_path / "telemetry" / "kultrun-telemetry.sqlite3"
        assert database.is_file()
        connection = sqlite3.connect(database)
        try:
            runs = connection.execute("SELECT COUNT(*) FROM deployment_run").fetchone()
            events = connection.execute(
                "SELECT COUNT(*) FROM deployment_event"
            ).fetchone()
            assert runs is not None
            assert runs[0] >= 1
            assert events is not None
            assert events[0] >= 1
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            assert integrity == ("ok",)
        finally:
            connection.close()
        names = [thread.name for thread in threading.enumerate()]
        assert not any("kultrun-exec" in name for name in names)
    finally:
        _kill_group(child)


def test_telemetry_disk_full_parent_still_exits(tmp_path: Path) -> None:
    stack = _Stack(tmp_path)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    finished, child = _launch_start_cli(
        tmp_path, instance.instance_id.value, boom=True
    )
    try:
        assert finished.returncode == 0
        assert _pid_alive(child)
        recorded = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert recorded is not None
        assert recorded.observed_state is ObservedState.RUNNING
        error = (tmp_path / "telemetry-error.txt").read_text(encoding="utf-8")
        assert "disk full" in error
        held = stack.resources.get(reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE
    finally:
        _kill_group(child)


def test_second_process_infer_after_launcher_exit(tmp_path: Path) -> None:
    stack = _Stack(tmp_path)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    finished, child = _launch_start_cli(tmp_path, instance.instance_id.value)
    try:
        assert finished.returncode == 0
        recorded = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert recorded is not None
        assert recorded.endpoint is not None
        url = f"http://{recorded.endpoint.address}:{recorded.endpoint.port}/health"
        with urllib.request.urlopen(url, timeout=2) as response:
            assert response.status == 200
        other = _other_instances(stack)
        generated = other.infer(instance.instance_id, InferenceRequest(prompt=PROMPT))
        assert generated.generated_text.startswith("ok:" + PROMPT[:80])
        still = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert still is not None
        assert still.observed_state is ObservedState.RUNNING
        database = tmp_path / "telemetry" / "kultrun-telemetry.sqlite3"
        blob = database.read_bytes()
        assert PROMPT.encode("utf-8") not in blob
    finally:
        _kill_group(child)


def test_k31_inspect_after_launcher_does_not_kill(tmp_path: Path) -> None:
    stack = _Stack(tmp_path)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    _finished, child = _launch_start_cli(tmp_path, instance.instance_id.value)
    try:
        before = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert before is not None
        assert before.observed_state is ObservedState.RUNNING
        other = _other_instances(stack)
        seen = other.observe(instance.instance_id)
        assert seen.observed_state is ObservedState.UNKNOWN
        report = other.reconcile()
        assert "UNKNOWN" in report
        refused = other.stop(instance.instance_id)
        assert "unverified" in str(refused.failure_reason)
        assert _pid_alive(child)
        held = stack.resources.get(reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE
    finally:
        _kill_group(child)


def test_long_run_delayed_ready_then_infer(tmp_path: Path) -> None:
    stack = _Stack(tmp_path)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    started = time.monotonic()
    finished, child = _launch_start_cli(
        tmp_path, instance.instance_id.value, delay=0.8
    )
    try:
        assert finished.returncode == 0
        assert time.monotonic() - started < 8.0
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            assert _pid_alive(child)
            time.sleep(1.0)
        recorded = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert recorded is not None
        assert recorded.ready is True
        other = _other_instances(stack)
        generated = other.infer(
            instance.instance_id, InferenceRequest(prompt="late-hello")
        )
        assert generated.generated_text.startswith("ok:late-hello")
        database = tmp_path / "telemetry" / "kultrun-telemetry.sqlite3"
        connection = sqlite3.connect(database)
        try:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        finally:
            connection.close()
    finally:
        _kill_group(child)


def test_physical_t5_order_is_documented() -> None:
    text = (
        Path(__file__).resolve().parent.parent
        / "docs"
        / "stages"
        / "STAGE-1.6L-real-vllm-inference.md"
    ).read_text(encoding="utf-8")
    assert "DO NOT inspect/list/reconcile" in text
    assert "instances infer" in text
    assert "K-31" in text

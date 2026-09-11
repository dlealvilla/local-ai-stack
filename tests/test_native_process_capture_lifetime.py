"""NativeProcessExecutor capture must not pin the launching CLI to the child.

A serving child stays up after the parent interpreter exits, keeps writing
stdout/stderr, and does not depend on pipe-pump threads in that parent.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import pytest

import kultrun
from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.execution.contracts import ExecutionOwnership, ExecutionState, ExecutorSpec
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import HostId
from kultrun.inference.contracts import (
    InferenceInstance,
    InferenceRequest,
    ObservedState,
)
from kultrun.inference.service import InstanceService
from kultrun.kernel.clock import SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.resource.contracts import ReservationState
from kultrun.runtime.catalogue import RuntimeCatalogue
from tests.test_inference_instance import SMALL, _Stack
from tests.test_runtime_vllm_inference import _complete_request
from tests.vllm_protocol import wrap_launch_with_protocol

HOST = HostId.generate()
PIPE_SCALE = 256 * 1024
REPO = Path(__file__).resolve().parent.parent

CHILD = r"""
import os
import signal
import sys
import time

signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
progress = os.environ["KULTRUN_PROGRESS"]
ready_file = os.environ["KULTRUN_READY_FILE"]
ready_after = int(os.environ.get("KULTRUN_READY_AFTER", "0"))
hold_seconds = float(os.environ.get("KULTRUN_HOLD_SECONDS", "0"))
chunk = b"O" * 2048
err = b"E" * 2048
written = 0
while written < ready_after:
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(err)
    sys.stderr.buffer.flush()
    written += 2048
    Path = __import__("pathlib").Path
    Path(progress).write_text(str(written), encoding="utf-8")
Path = __import__("pathlib").Path
Path(ready_file).write_text("READY", encoding="utf-8")
print("READY", flush=True)
print("READY-ERR", file=sys.stderr, flush=True)
started = time.monotonic()
while hold_seconds <= 0 or (time.monotonic() - started) < hold_seconds:
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(err)
    sys.stderr.buffer.flush()
    written += 2048
    if written % (2048 * 16) == 0:
        Path = __import__("pathlib").Path
        Path(progress).write_text(str(written), encoding="utf-8")
    time.sleep(0.01)
raise SystemExit(0)
"""

LAUNCHER = r"""
from __future__ import annotations

import os
import sys
import time

from pathlib import Path

from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.execution.contracts import ExecutorSpec
from kultrun.host.contracts import HostId

def main() -> None:
    executor = NativeProcessExecutor()
    spec = ExecutorSpec(
        executable=sys.executable,
        arguments=("-c", os.environ["KULTRUN_CHILD"]),
        environment=(
            f"KULTRUN_PROGRESS={os.environ['KULTRUN_PROGRESS']}",
            f"KULTRUN_READY_FILE={os.environ['KULTRUN_READY_FILE']}",
            f"KULTRUN_READY_AFTER={os.environ.get('KULTRUN_READY_AFTER', '0')}",
            f"KULTRUN_HOLD_SECONDS={os.environ.get('KULTRUN_HOLD_SECONDS', '0')}",
        ),
        output_limit_bytes=4096,
    )
    handle = executor.start(HostId.generate(), spec)
    ready_path = Path(os.environ["KULTRUN_READY_FILE"])
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        handle = executor.observe(handle)
        if ready_path.exists():
            print(
                f"PARENT_SUCCESS pid={os.getpid()} child={handle.pid}",
                flush=True,
            )
            raise SystemExit(0)
        if handle.observed_state.value in {"exited", "failed"}:
            print(handle.stdout, file=sys.stderr)
            print(handle.stderr, file=sys.stderr)
            raise SystemExit(2)
        time.sleep(0.05)
    raise SystemExit(3)

if __name__ == "__main__":
    main()
"""


def _pythonpath() -> str:
    return str(Path(kultrun.__file__).resolve().parent.parent)


def _env_with_kultrun() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath()
    return env


def _capture_thread_names() -> list[str]:
    return [
        thread.name for thread in threading.enumerate() if "kultrun-exec" in thread.name
    ]


def _fd_count() -> int:
    path = Path("/dev/fd")
    if not path.exists():
        return 0
    return len(list(path.iterdir()))


def _named_capture_files() -> set[str]:
    return {path.name for path in Path(tempfile.gettempdir()).glob("kultrun-exec-*")}


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


def _spec(*args: str, **overrides: object) -> ExecutorSpec:
    payload: dict[str, object] = {
        "executable": sys.executable,
        "arguments": args,
        "output_limit_bytes": 4096,
    }
    payload.update(overrides)
    return ExecutorSpec(**payload)  # type: ignore[arg-type]


def _launch_serving_parent(
    tmp_path: Path, *, ready_after: int = PIPE_SCALE
) -> tuple[subprocess.CompletedProcess[str], int, Path]:
    progress = tmp_path / "progress"
    ready_file = tmp_path / "ready"
    env = _env_with_kultrun()
    env["KULTRUN_CHILD"] = CHILD
    env["KULTRUN_PROGRESS"] = str(progress)
    env["KULTRUN_READY_FILE"] = str(ready_file)
    env["KULTRUN_READY_AFTER"] = str(ready_after)
    env["KULTRUN_HOLD_SECONDS"] = "0"
    launcher = tmp_path / "launcher.py"
    launcher.write_text(LAUNCHER, encoding="utf-8")
    started = time.monotonic()
    finished = subprocess.run(
        [sys.executable, str(launcher)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    elapsed = time.monotonic() - started
    assert finished.returncode == 0, finished.stderr
    assert "PARENT_SUCCESS" in finished.stdout
    child = int(finished.stdout.strip().rsplit("child=", 1)[1])
    assert elapsed < 20
    return finished, child, progress


def _bind_vllm_fixture(
    stack: _Stack,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str = "healthy",
    log_bytes: int = 0,
    delay: float = 0.0,
    timeout: float = 8.0,
) -> None:
    original = VllmRuntimeSupport.launch_spec
    monkeypatch.setattr(
        VllmRuntimeSupport,
        "launch_spec",
        wrap_launch_with_protocol(
            original, mode=mode, delay=delay, log_bytes=log_bytes
        ),
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
        startup_timeout=timeout,
        live_executor="native-process",
    )


def _other_instances(stack: _Stack) -> InstanceService:
    return InstanceService(
        stack.store,
        SystemClock(),
        stack.inventory,
        stack.resources,
        ExecutionService(NativeProcessExecutor(SystemClock()), stack.store),
        stack.runtimes,
        live_executor="native-process",
    )


def test_cli_parent_exits_while_child_keeps_writing(tmp_path: Path) -> None:
    named_before = _named_capture_files()
    finished, child, progress = _launch_serving_parent(tmp_path)
    try:
        assert _pid_alive(child)
        before = int(progress.read_text(encoding="utf-8"))
        time.sleep(2.0)
        assert _pid_alive(child)
        after = int(progress.read_text(encoding="utf-8"))
        assert after - before >= 64 * 1024
        assert "kultrun-exec-capture" not in finished.stderr
        assert _named_capture_files() == named_before
    finally:
        _kill_group(child)


def test_parent_exit_is_normal_python_shutdown(tmp_path: Path) -> None:
    finished, child, _progress = _launch_serving_parent(tmp_path, ready_after=2048)
    try:
        assert finished.returncode == 0
        assert "os._exit" not in Path(tmp_path / "launcher.py").read_text(
            encoding="utf-8"
        )
        assert _pid_alive(child)
    finally:
        _kill_group(child)


def test_short_lived_command_still_exits_and_captures() -> None:
    executor = NativeProcessExecutor()
    handle = executor.start(
        HOST,
        _spec("-c", "import sys; print('short-ok'); print('err', file=sys.stderr)"),
    )
    deadline = time.monotonic() + 5
    current = handle
    while time.monotonic() < deadline:
        current = executor.observe(current)
        if current.observed_state in {ExecutionState.EXITED, ExecutionState.FAILED}:
            break
        time.sleep(0.05)
    assert current.observed_state is ExecutionState.EXITED
    assert current.exit_code == 0
    assert "short-ok" in current.stdout
    assert "err" in current.stderr
    assert handle.execution_id.value not in executor._live
    assert _capture_thread_names() == []


def test_stdout_is_bounded_for_a_flood() -> None:
    executor = NativeProcessExecutor()
    handle = executor.start(
        HOST,
        _spec(
            "-c",
            "import sys; sys.stdout.write('x' * 8000); sys.stdout.flush()",
            output_limit_bytes=200,
        ),
    )
    deadline = time.monotonic() + 5
    current = handle
    while time.monotonic() < deadline:
        current = executor.observe(current)
        if current.observed_state in {ExecutionState.EXITED, ExecutionState.FAILED}:
            break
        time.sleep(0.05)
    assert current.output_truncated is True
    assert len(current.stdout.encode("utf-8")) <= 200
    assert current.observed_state is ExecutionState.EXITED


def test_natural_child_exit_releases_capture_fds() -> None:
    executor = NativeProcessExecutor()
    before_fds = _fd_count()
    handle = executor.start(
        HOST,
        _spec("-c", "print('gone')", output_limit_bytes=64),
    )
    deadline = time.monotonic() + 5
    current = handle
    while time.monotonic() < deadline:
        current = executor.observe(current)
        if current.observed_state is ExecutionState.EXITED:
            break
        time.sleep(0.05)
    assert current.observed_state is ExecutionState.EXITED
    assert executor._live == {}
    assert _capture_thread_names() == []
    assert _fd_count() <= before_fds + 2


def test_capture_read_fds_are_not_inheritable() -> None:
    executor = NativeProcessExecutor()
    handle = executor.start(HOST, _spec("-c", "import time; time.sleep(8)"))
    try:
        live = executor._live[handle.execution_id.value]
        assert os.get_inheritable(live.stdout_fd) is False
        assert os.get_inheritable(live.stderr_fd) is False
        assert live.process.stdout is None
        assert live.process.stderr is None
    finally:
        executor.stop(handle)


def test_stop_and_restart_same_executor_no_stale_capture() -> None:
    executor = NativeProcessExecutor()
    first = executor.start(HOST, _spec("-c", "import time; time.sleep(30)"))
    running = executor.observe(first)
    assert running.observed_state is ExecutionState.RUNNING
    stopped = executor.stop(running)
    assert stopped.observed_state in {ExecutionState.EXITED, ExecutionState.FAILED}
    assert first.execution_id.value not in executor._live
    second = executor.start(HOST, _spec("-c", "import time; time.sleep(30)"))
    try:
        assert second.execution_id != first.execution_id
        assert list(executor._live) == [second.execution_id.value]
        assert _capture_thread_names() == []
    finally:
        executor.stop(second)


def test_two_live_workloads_are_independent() -> None:
    executor = NativeProcessExecutor()
    first = executor.start(HOST, _spec("-c", "import time; time.sleep(30)"))
    second = executor.start(HOST, _spec("-c", "import time; time.sleep(30)"))
    try:
        assert first.pid != second.pid
        assert len(executor._live) == 2
        executor.stop(first)
        left = executor.observe(second)
        assert left.observed_state is ExecutionState.RUNNING
        assert is_resolved(second.pid)
        assert _pid_alive(int(second.pid))
        assert first.execution_id.value not in executor._live
    finally:
        executor.stop(first)
        executor.stop(second)


def test_start_stop_cycles_do_not_leak_capture_resources() -> None:
    executor = NativeProcessExecutor()
    threads_before = threading.active_count()
    fds_before = _fd_count()
    named_before = _named_capture_files()
    for _ in range(8):
        handle = executor.start(HOST, _spec("-c", "import time; time.sleep(30)"))
        observed = executor.observe(handle)
        assert observed.observed_state is ExecutionState.RUNNING
        executor.stop(observed)
    assert executor._live == {}
    assert _capture_thread_names() == []
    assert threading.active_count() <= threads_before + 2
    assert _fd_count() <= fds_before + 4
    assert _named_capture_files() == named_before


def test_child_exit_before_ready_keeps_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _Stack(tmp_path)
    _bind_vllm_fixture(stack, monkeypatch, mode="exit-immediately")
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    started_at = time.monotonic()
    failed = stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, instance),
    )
    assert time.monotonic() - started_at < 2.0
    assert failed.observed_state is ObservedState.FAILED
    assert "exited" in str(failed.failure_reason)
    held = stack.resources.get(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.ACTIVE


def test_never_ready_timeout_cleans_owned_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _Stack(tmp_path)
    _bind_vllm_fixture(stack, monkeypatch, mode="delayed", delay=30.0, timeout=0.4)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    started_at = time.monotonic()
    failed = stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, instance),
    )
    assert time.monotonic() - started_at < 2.5
    assert failed.observed_state is ObservedState.FAILED
    live = [
        item
        for item in stack.executions.list()
        if item.observed_state.value == "running"
        and item.ownership is ExecutionOwnership.OWNED
    ]
    assert live == []
    assert stack.executions._executor._live == {}  # type: ignore[attr-defined]
    held = stack.resources.get(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.ACTIVE


def test_in_process_start_stop_restart_and_two_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _Stack(tmp_path)
    _bind_vllm_fixture(stack, monkeypatch)
    first_art = stack.stored(name="one")
    second_art = stack.stored(name="two")
    first_res = stack.reserve(first_art, vram=SMALL)
    second_res = stack.reserve(second_art, vram=SMALL)
    first = stack.instances.create(first_art, first_res, runtime=Name("vllm"))
    second = stack.instances.create(second_art, second_res, runtime=Name("vllm"))
    started = stack.instances.start(
        first.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, first),
    )
    assert started.observed_state is ObservedState.RUNNING
    other = stack.instances.start(
        second.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, second),
    )
    assert other.pid != started.pid
    stopped = stack.instances.stop(first.instance_id)
    assert stopped.observed_state is ObservedState.STOPPED
    held = stack.resources.get(first_res.reservation_id)
    assert held is not None
    assert held.state is ReservationState.ACTIVE
    still = stack.instances.observe(second.instance_id)
    assert still.observed_state is ObservedState.RUNNING
    restarted = stack.instances.start(
        first.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, first),
    )
    assert restarted.observed_state is ObservedState.RUNNING
    assert restarted.execution_id != started.execution_id
    assert _capture_thread_names() == []
    stack.instances.stop(first.instance_id)
    stack.instances.stop(second.instance_id)


def test_instance_start_cli_exits_and_second_process_can_infer(
    tmp_path: Path,
) -> None:
    stack = _Stack(tmp_path)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    env = _env_with_kultrun()
    env["PYTHONPATH"] = os.pathsep.join((_pythonpath(), str(REPO)))
    env["KULTRUN_TMP"] = str(tmp_path)
    env["KULTRUN_INSTANCE"] = instance.instance_id.value
    script = tmp_path / "start_cli.py"
    script.write_text(
        """
from pathlib import Path
import os
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.inference.contracts import InferenceInstance, InstanceId, ObservedState
from kultrun.inference.service import InstanceService
from kultrun.kernel.ids import Name
from kultrun.resource.contracts import LedgerHealth
from kultrun.runtime.catalogue import RuntimeCatalogue
from tests.test_inference_instance import _Stack
from tests.test_runtime_vllm_inference import _complete_request
from tests.vllm_protocol import wrap_launch_with_protocol

tmp = Path(os.environ["KULTRUN_TMP"])
stack = _Stack(tmp)
original = VllmRuntimeSupport.launch_spec
VllmRuntimeSupport.launch_spec = wrap_launch_with_protocol(
    original, mode="healthy", delay=0.0, log_bytes=131072
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
instance_id = InstanceId.parse(os.environ["KULTRUN_INSTANCE"])
recorded = stack.store.get(InferenceInstance, instance_id.value)
assert recorded is not None
started = stack.instances.start(
    instance_id,
    ledger_health=LedgerHealth.WITHIN_CAPACITY,
    launch_request=_complete_request(tmp, recorded),
)
assert started.observed_state is ObservedState.RUNNING
assert started.endpoint is not None
print(
    f"PARENT_SUCCESS pid={os.getpid()} child={started.pid} "
    f"port={started.endpoint.port}",
    flush=True,
)
raise SystemExit(0)
""",
        encoding="utf-8",
    )
    finished = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr + finished.stdout
    child = int(finished.stdout.strip().rsplit("child=", 1)[1].split()[0])
    try:
        assert _pid_alive(child)
        recorded = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert recorded is not None
        assert recorded.observed_state is ObservedState.RUNNING
        assert recorded.ready is True
        assert recorded.endpoint is not None
        url = f"http://{recorded.endpoint.address}:{recorded.endpoint.port}/health"
        with urllib.request.urlopen(url, timeout=2) as response:
            assert response.status == 200
        stack.runtimes = RuntimeCatalogue(
            (stack.runtimes.get(Name("reference-serving")), VllmRuntimeSupport())
        )
        other = _other_instances(stack)
        generated = other.infer(
            instance.instance_id, InferenceRequest(prompt="hello world")
        )
        assert generated.generated_text.startswith("ok:hello world")
        still = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert still is not None
        assert still.observed_state is ObservedState.RUNNING
        seen = other.observe(instance.instance_id)
        assert seen.observed_state is ObservedState.RUNNING
        stopped = other.stop(instance.instance_id)
        assert stopped.observed_state is ObservedState.STOPPED
        deadline = time.monotonic() + 2.0
        while _pid_alive(child) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _pid_alive(child)
        held = stack.resources.get(reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE
    finally:
        _kill_group(child)


def test_high_log_volume_during_owned_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _Stack(tmp_path)
    _bind_vllm_fixture(stack, monkeypatch, log_bytes=2 * 1024 * 1024, timeout=5.0)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    started = stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, instance),
    )
    try:
        assert started.observed_state is ObservedState.RUNNING
        assert is_resolved(started.pid)
        os.kill(int(started.pid), 0)
    finally:
        stack.instances.stop(instance.instance_id)


def test_readiness_still_uses_persist_false() -> None:
    source = Path(
        Path(__file__).resolve().parent.parent
        / "src"
        / "kultrun"
        / "inference"
        / "service.py"
    ).read_text(encoding="utf-8")
    assert "self._executions.observe(execution_id, persist=False)" in source
    assert source.count("persist=False") >= 3

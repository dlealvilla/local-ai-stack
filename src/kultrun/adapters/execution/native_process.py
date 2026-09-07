"""Start a process with exec, not a shell.

PID reuse protection is limited to the lifetime of this adapter instance:
we hold the Popen object. After a control-plane restart the service marks
surviving PIDs UNVERIFIED rather than signalling them. See `docs/DEBT.md`
K-31.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import IO

from kultrun.evidence.contracts import Confidence
from kultrun.execution.contracts import (
    ExecutionHealth,
    ExecutionId,
    ExecutionOwnership,
    ExecutionState,
    ExecutorAvailability,
    ExecutorCapabilityProfile,
    ExecutorHandle,
    ExecutorSpec,
    FeatureSupport,
    environment_as_dict,
)
from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.errors import InternalError, ValidationError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, is_resolved

IDENTITY = Name("native-process")

#: Capture threads read this many bytes at a time.
_CHUNK = 4096


@dataclass
class _Capture:
    limit: int
    chunks: list[bytes]
    size: int = 0
    truncated: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def feed(self, data: bytes) -> None:
        with self.lock:
            if self.size >= self.limit:
                self.truncated = True
                return
            take = data[: self.limit - self.size]
            self.chunks.append(take)
            self.size += len(take)
            if len(data) > len(take):
                self.truncated = True

    def text(self) -> str:
        with self.lock:
            raw = b"".join(self.chunks)
        return raw.decode("utf-8", errors="replace")


@dataclass
class _Live:
    spec: ExecutorSpec
    process: subprocess.Popen[bytes]
    stdout: _Capture
    stderr: _Capture
    threads: tuple[threading.Thread, ...]


class NativeProcessExecutor:
    """`subprocess.Popen` with an argument vector. `shell` is never True."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._live: dict[str, _Live] = {}
        self._lock = threading.Lock()

    @property
    def identity(self) -> Name:
        return IDENTITY

    def capabilities(self, host: HostCapabilities) -> ExecutorCapabilityProfile:
        """Truthful native-process features on this host. Does not exec."""
        native = host.execution.native_process
        process = (
            FeatureSupport.SUPPORTED if native else FeatureSupport.UNSUPPORTED
        )
        vendors = tuple(
            sorted({item.vendor.value for item in host.accelerators})
        )
        return ExecutorCapabilityProfile(
            executor=self.identity,
            executor_type=Name("process"),
            host_id=host.host_id,
            host_fingerprint=host.fingerprint,
            availability=(
                ExecutorAvailability.AVAILABLE
                if native
                else ExecutorAvailability.UNAVAILABLE
            ),
            process_execution=process,
            structured_argv=process,
            environment_variables=process,
            working_directory=process,
            filesystem_access="host_native",
            networking="host_native",
            port_binding=process,
            accelerator_exposure=process,
            bounded_stdout=process,
            bounded_stderr=process,
            lifecycle_observation=process,
            graceful_termination=process,
            forced_termination=process,
            isolation=FeatureSupport.UNSUPPORTED,
            reason=(
                NOT_PROVIDED
                if native
                else "host does not advertise native process execution"
            ),
            accelerator_exposure_mode="host_process_inheritance",
            limitations=(
                "container_isolation unsupported",
                "no CDI device attachment",
                "no Docker or OCI execution",
            ),
            evidence=(
                f"os={host.operating_environment.os_name}",
                f"arch={host.operating_environment.architecture.value}",
                f"native_process={native}",
                f"accelerator_vendors={','.join(vendors) or 'none'}",
            ),
            confidence=Confidence.HIGH if native else Confidence.LOW,
        )

    def start(self, host_id: HostId, spec: ExecutorSpec) -> ExecutorHandle:
        """Exec the spec. Fails closed if the executable cannot be resolved."""
        resolved = _resolve_executable(spec.executable)
        env = os.environ.copy()
        env.update(environment_as_dict(spec.environment))
        stdout_cap = _Capture(limit=spec.output_limit_bytes, chunks=[])
        stderr_cap = _Capture(limit=spec.output_limit_bytes, chunks=[])
        argv = [resolved, *spec.arguments]
        try:
            process = subprocess.Popen(
                argv,
                cwd=spec.working_directory,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                bufsize=0,
            )
        except OSError as error:
            now = self._clock.now()
            return ExecutorHandle(
                execution_id=ExecutionId.generate(),
                host_id=host_id,
                executor=self.identity,
                desired_state=ExecutionState.RUNNING,
                observed_state=ExecutionState.FAILED,
                health=ExecutionHealth.UNKNOWN,
                ownership=ExecutionOwnership.ABSENT,
                created_at=now,
                executable=resolved,
                arguments=spec.arguments,
                exited_at=now,
                detail=str(error),
            )
        if process.stdout is None or process.stderr is None:
            process.kill()
            raise InternalError("stdout and stderr pipes were not created")
        threads = (
            _pump(process.stdout, stdout_cap),
            _pump(process.stderr, stderr_cap),
        )
        execution_id = ExecutionId.generate()
        live = _Live(
            spec=spec,
            process=process,
            stdout=stdout_cap,
            stderr=stderr_cap,
            threads=threads,
        )
        with self._lock:
            self._live[execution_id.value] = live
        now = self._clock.now()
        return ExecutorHandle(
            execution_id=execution_id,
            host_id=host_id,
            executor=self.identity,
            desired_state=ExecutionState.RUNNING,
            observed_state=ExecutionState.RUNNING,
            health=ExecutionHealth.UNKNOWN,
            ownership=ExecutionOwnership.OWNED,
            created_at=now,
            executable=resolved,
            arguments=spec.arguments,
            pid=process.pid,
            started_at=now,
        )

    def observe(self, handle: ExecutorHandle) -> ExecutorHandle:
        """Refresh from the live Popen, or refuse to claim a stranger PID."""
        with self._lock:
            live = self._live.get(handle.execution_id.value)
        if live is None:
            return _unclaimed(handle)
        code = live.process.poll()
        stdout = live.stdout.text()
        stderr = live.stderr.text()
        truncated = live.stdout.truncated or live.stderr.truncated
        if code is None:
            return replace(
                handle,
                observed_state=ExecutionState.RUNNING,
                ownership=ExecutionOwnership.OWNED,
                pid=live.process.pid,
                stdout=stdout,
                stderr=stderr,
                output_truncated=truncated,
            )
        with self._lock:
            self._live.pop(handle.execution_id.value, None)
        _join(live.threads)
        state = ExecutionState.EXITED if code == 0 else ExecutionState.FAILED
        return replace(
            handle,
            observed_state=state,
            ownership=ExecutionOwnership.ABSENT,
            pid=NOT_MEASURED,
            exit_code=code,
            exited_at=handle.exited_at or self._clock.now(),
            stdout=stdout,
            stderr=stderr,
            output_truncated=truncated,
        )

    def stop(self, handle: ExecutorHandle) -> ExecutorHandle:
        """SIGTERM the process group, then SIGKILL after the spec's grace."""
        with self._lock:
            live = self._live.get(handle.execution_id.value)
        if live is None:
            return _unclaimed(handle)
        stopping = replace(
            handle,
            desired_state=ExecutionState.STOPPING,
            observed_state=ExecutionState.STOPPING,
        )
        _signal_group(live.process, signal.SIGTERM)
        try:
            live.process.wait(timeout=live.spec.grace_period_seconds)
        except subprocess.TimeoutExpired:
            _signal_group(live.process, signal.SIGKILL)
            try:
                live.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                return replace(
                    stopping,
                    observed_state=ExecutionState.FAILED,
                    detail="process did not exit after SIGKILL",
                )
        return self.observe(stopping)


def build(clock: Clock | None = None) -> NativeProcessExecutor:
    """The composition root's constructor."""
    return NativeProcessExecutor(clock)


def _resolve_executable(executable: str) -> str:
    path = Path(executable)
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    # Relative names (including an interpreter path that is already absolute
    # but not yet checked) go through PATH only when they contain no slash.
    if os.sep not in executable and (not os.altsep or os.altsep not in executable):
        found = _which(executable)
        if found is not None:
            return found
    if path.is_file():
        return str(path.resolve())
    raise ValidationError("executable not found", executable=executable)


def _which(name: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _pump(stream: IO[bytes], capture: _Capture) -> threading.Thread:
    """Copy available pipe bytes as they arrive.

    Buffered `read(n)` waits until n bytes or EOF. A hold workload writes a
    short line and then sleeps, so the console would show empty stdout until
    the process exited. `os.read` returns as soon as any data is in the pipe.
    """

    def run() -> None:
        fd = stream.fileno()
        try:
            while True:
                try:
                    chunk = os.read(fd, _CHUNK)
                except OSError:
                    return
                if not chunk:
                    return
                capture.feed(chunk)
        finally:
            stream.close()

    thread = threading.Thread(target=run, name="kultrun-exec-capture", daemon=False)
    thread.start()
    return thread


def _join(threads: tuple[threading.Thread, ...]) -> None:
    for thread in threads:
        thread.join(timeout=1.0)


def _signal_group(process: subprocess.Popen[bytes], sig: int) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return


def _unclaimed(handle: ExecutorHandle) -> ExecutorHandle:
    """A record whose process this adapter no longer holds.

    If a PID is recorded and still exists we do not own it enough to
    signal. If it does not exist, it is absent.
    """
    if handle.observed_state in (ExecutionState.EXITED, ExecutionState.FAILED):
        return replace(handle, ownership=ExecutionOwnership.ABSENT)
    if is_resolved(handle.pid) and _pid_exists(handle.pid):
        return replace(
            handle,
            ownership=ExecutionOwnership.UNVERIFIED,
            observed_state=ExecutionState.RUNNING,
            health=ExecutionHealth.UNKNOWN,
            detail="PID exists but this control plane did not start it in this process",
        )
    return replace(
        handle,
        ownership=ExecutionOwnership.ABSENT,
        observed_state=ExecutionState.EXITED,
        pid=NOT_MEASURED,
        detail=handle.detail or "process is no longer owned by this control plane",
    )


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True

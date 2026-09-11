"""Start a process with exec, not a shell.

Ownership is a persisted process cookie, not the in-memory Popen object.
A later control-plane process may reacquire a matching PID. A PID that
exists without a matching cookie is UNVERIFIED and is never signalled.

Stdout and stderr are anonymous files, not pipes. Capture into the handle
is a bounded prefix. The launching interpreter may exit while a serving
child continues writing. Log-file growth across a long-lived child is K-99.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

from kultrun.adapters.execution.process_identity import (
    EXECUTION_ENV,
    IdentityMatch,
    capture_cookie,
    parse_cookie,
    pid_exists,
    verify_live,
)
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
from kultrun.execution.resolve import is_interpreter_component, native_interpreter
from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, is_resolved

IDENTITY = Name("native-process")


@dataclass
class _Live:
    spec: ExecutorSpec
    process: subprocess.Popen[bytes]
    stdout_fd: int
    stderr_fd: int


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
        process = FeatureSupport.SUPPORTED if native else FeatureSupport.UNSUPPORTED
        vendors = tuple(sorted({item.vendor.value for item in host.accelerators}))
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
        spec_env = environment_as_dict(spec.environment)
        env.update(spec_env)
        execution_id = ExecutionId.generate()
        env[EXECUTION_ENV] = execution_id.value
        if "PYTHONPATH" not in spec_env:
            root = _package_parent()
            current = env.get("PYTHONPATH", "")
            parts = current.split(os.pathsep) if current else []
            if root not in parts:
                env["PYTHONPATH"] = root + os.pathsep + current if current else root
        argv = [resolved, *spec.arguments]
        stdout_r = stdout_w = stderr_r = stderr_w = -1
        try:
            stdout_r, stdout_w = _anonymous_file()
            stderr_r, stderr_w = _anonymous_file()
            process = subprocess.Popen(
                argv,
                cwd=spec.working_directory,
                env=env,
                stdout=stdout_w,
                stderr=stderr_w,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as error:
            _close_fd(stdout_r)
            _close_fd(stdout_w)
            _close_fd(stderr_r)
            _close_fd(stderr_w)
            now = self._clock.now()
            return ExecutorHandle(
                execution_id=execution_id,
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
        _close_fd(stdout_w)
        _close_fd(stderr_w)
        live = _Live(
            spec=spec,
            process=process,
            stdout_fd=stdout_r,
            stderr_fd=stderr_r,
        )
        with self._lock:
            self._live[execution_id.value] = live
        cookie = capture_cookie(
            process.pid,
            execution_id.value,
            grace_seconds=spec.grace_period_seconds,
        )
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
            external_identity=(
                cookie.serialise() if cookie is not None else NOT_MEASURED
            ),
        )

    def observe(self, handle: ExecutorHandle) -> ExecutorHandle:
        """Refresh from the live Popen, or reacquire a matching cookie."""
        with self._lock:
            live = self._live.get(handle.execution_id.value)
            if live is None:
                return self._reacquire(handle)
            code = live.process.poll()
            stdout, out_truncated = _read_prefix(
                live.stdout_fd, live.spec.output_limit_bytes
            )
            stderr, err_truncated = _read_prefix(
                live.stderr_fd, live.spec.output_limit_bytes
            )
            truncated = out_truncated or err_truncated
            if code is None:
                cookie = handle.external_identity
                if not is_resolved(cookie):
                    captured = capture_cookie(
                        live.process.pid,
                        handle.execution_id.value,
                        grace_seconds=live.spec.grace_period_seconds,
                    )
                    cookie = (
                        captured.serialise() if captured is not None else cookie
                    )
                return replace(
                    handle,
                    observed_state=ExecutionState.RUNNING,
                    ownership=ExecutionOwnership.OWNED,
                    pid=live.process.pid,
                    stdout=stdout,
                    stderr=stderr,
                    output_truncated=truncated,
                    external_identity=cookie,
                )
            self._live.pop(handle.execution_id.value, None)
            stdout_fd = live.stdout_fd
            stderr_fd = live.stderr_fd
            live.stdout_fd = -1
            live.stderr_fd = -1
        _close_fd(stdout_fd)
        _close_fd(stderr_fd)
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
        if live is not None:
            return self._stop_live(handle, live)
        observed = self._reacquire(handle)
        if observed.ownership is not ExecutionOwnership.OWNED:
            return observed
        return self._stop_reattached(observed)

    def _stop_live(self, handle: ExecutorHandle, live: _Live) -> ExecutorHandle:
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

    def _stop_reattached(self, handle: ExecutorHandle) -> ExecutorHandle:
        pid = handle.pid
        if not is_resolved(pid):
            return _unclaimed(handle)
        cookie = parse_cookie(handle.external_identity)
        pgid = cookie.pgid if cookie is not None else pid
        grace = cookie.grace_seconds if cookie is not None else 2.0
        stopping = replace(
            handle,
            desired_state=ExecutionState.STOPPING,
            observed_state=ExecutionState.STOPPING,
        )
        _killpg(pgid, signal.SIGTERM)
        deadline = time.monotonic() + max(0.05, grace)
        while pid_exists(pid) and time.monotonic() < deadline:
            _reap(pid)
            time.sleep(0.05)
        if pid_exists(pid):
            _killpg(pgid, signal.SIGKILL)
            _kill_pid(pid, signal.SIGKILL)
            extra = time.monotonic() + 2
            while pid_exists(pid) and time.monotonic() < extra:
                _reap(pid)
                time.sleep(0.05)
            if pid_exists(pid):
                return replace(
                    stopping,
                    ownership=ExecutionOwnership.ABSENT,
                    observed_state=ExecutionState.FAILED,
                    detail="process did not exit after SIGKILL",
                )
        _reap(pid)
        return self.observe(stopping)

    def _reacquire(self, handle: ExecutorHandle) -> ExecutorHandle:
        if handle.observed_state in (ExecutionState.EXITED, ExecutionState.FAILED):
            return replace(handle, ownership=ExecutionOwnership.ABSENT)
        if not is_resolved(handle.pid) or not pid_exists(handle.pid):
            return replace(
                handle,
                ownership=ExecutionOwnership.ABSENT,
                observed_state=ExecutionState.EXITED,
                pid=NOT_MEASURED,
                detail=(
                    handle.detail
                    or "process is no longer owned by this control plane"
                ),
            )
        cookie = parse_cookie(handle.external_identity)
        if cookie is None:
            return replace(
                handle,
                ownership=ExecutionOwnership.UNVERIFIED,
                observed_state=ExecutionState.RUNNING,
                health=ExecutionHealth.UNKNOWN,
                detail=(
                    "PID exists but this control plane did not start it in this process"
                ),
            )
        verdict = verify_live(
            handle.pid, cookie, handle.execution_id.value
        )
        if verdict == IdentityMatch.MATCH:
            return replace(
                handle,
                ownership=ExecutionOwnership.OWNED,
                observed_state=ExecutionState.RUNNING,
                health=ExecutionHealth.UNKNOWN,
                detail=None,
            )
        if verdict == IdentityMatch.MISMATCH:
            return replace(
                handle,
                ownership=ExecutionOwnership.ABSENT,
                observed_state=ExecutionState.EXITED,
                pid=NOT_MEASURED,
                detail="process identity does not match the persisted execution",
            )
        return replace(
            handle,
            ownership=ExecutionOwnership.UNVERIFIED,
            observed_state=ExecutionState.RUNNING,
            health=ExecutionHealth.UNKNOWN,
            detail="process identity cannot be proven",
        )


def build(clock: Clock | None = None) -> NativeProcessExecutor:
    """The composition root's constructor."""
    return NativeProcessExecutor(clock)


def _resolve_executable(executable: str) -> str:
    if is_interpreter_component(executable):
        return native_interpreter()
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


def _package_parent() -> str:
    import kultrun

    return str(Path(kultrun.__file__).resolve().parent.parent)


def _which(name: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _anonymous_file() -> tuple[int, int]:
    """Read/write fds for an unlinked file the child can keep writing to."""
    fd, name = tempfile.mkstemp(prefix="kultrun-exec-", suffix=".log")
    try:
        Path(name).unlink()
    except OSError:
        _close_fd(fd)
        raise
    write_fd = os.dup(fd)
    os.set_inheritable(fd, False)
    os.set_inheritable(write_fd, True)
    return fd, write_fd


def _read_prefix(fd: int, limit: int) -> tuple[str, bool]:
    """Bounded prefix of a capture file. Does not drain or grow in memory."""
    if fd < 0 or limit < 1:
        return "", False
    try:
        data = os.pread(fd, limit + 1, 0)
    except OSError:
        return "", False
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", errors="replace"), truncated


def _close_fd(fd: int) -> None:
    if fd < 0:
        return
    try:
        os.close(fd)
    except OSError:
        return


def _signal_group(process: subprocess.Popen[bytes], sig: int) -> None:
    _killpg(process.pid, sig)


def _kill_pid(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        return


def _killpg(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        return


def _reap(pid: int) -> None:
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return
    except OSError:
        return


def _unclaimed(handle: ExecutorHandle) -> ExecutorHandle:
    """Fallback when reacquisition is impossible."""
    if handle.observed_state in (ExecutionState.EXITED, ExecutionState.FAILED):
        return replace(handle, ownership=ExecutionOwnership.ABSENT)
    if is_resolved(handle.pid) and pid_exists(handle.pid):
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

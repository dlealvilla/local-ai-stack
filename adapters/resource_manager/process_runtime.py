"""ResourceManager runtime wrapper around the existing process executor.

AI_DEPLOYMENT_PHASE9_PROCESS_RUNTIME_V1

The executor remains responsible for launching a service specification.

This adapter provides the lifecycle contract needed by ResourceManager:
- build a service specification;
- call the existing executor.start();
- capture durable process identity;
- stop only the exact process previously started.

The adapter intentionally does not know about vLLM, Docker, GPUs, or models.
Those remain behind ServiceSpecProvider / executor boundaries.
"""

from __future__ import annotations

import hashlib
import os
import signal
import time
from collections.abc import Mapping
from typing import Any, Protocol


class ProcessRuntimeError(RuntimeError):
    pass


class ProcessIdentityError(ProcessRuntimeError):
    pass


class ServiceSpecProvider(Protocol):
    def build(
        self,
        *,
        model_id: str,
        metadata: Mapping[str, Any],
    ) -> Any:
        ...


class ProcessExecutorLike(Protocol):
    def start(
        self,
        service_spec: Any,
    ) -> Any:
        ...


def _proc_start_ticks(pid: int) -> int | None:
    """Read Linux /proc process start time.

    Field 22 in /proc/<pid>/stat uniquely distinguishes a reused PID for the
    lifetime of the boot.
    """

    path = f"/proc/{pid}/stat"

    try:
        raw = open(
            path,
            "r",
            encoding="utf-8",
        ).read()
    except (FileNotFoundError, PermissionError, OSError):
        return None

    # comm is enclosed in parentheses and may contain spaces.
    end = raw.rfind(")")

    if end < 0:
        return None

    remainder = raw[end + 2:].split()

    # After removing PID + comm, starttime (field 22) becomes index 19.
    if len(remainder) <= 19:
        return None

    try:
        return int(remainder[19])
    except (TypeError, ValueError):
        return None


def _proc_command_sha256(pid: int) -> str | None:
    path = f"/proc/{pid}/cmdline"

    try:
        value = open(
            path,
            "rb",
        ).read()
    except (FileNotFoundError, PermissionError, OSError):
        return None

    if not value:
        return None

    return hashlib.sha256(value).hexdigest()


def _process_exists(pid: int) -> bool:
    if pid <= 1:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


class ProcessExecutorRuntime:
    """ResourceManager runtime backed by an existing ProcessExecutor."""

    def __init__(
        self,
        *,
        executor: ProcessExecutorLike,
        service_spec_provider: ServiceSpecProvider,
        stop_timeout_seconds: float = 15.0,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        self._executor = executor
        self._service_spec_provider = service_spec_provider

        self._stop_timeout_seconds = float(
            stop_timeout_seconds
        )

        self._poll_interval_seconds = float(
            poll_interval_seconds
        )

        if self._stop_timeout_seconds <= 0:
            raise ValueError(
                "stop_timeout_seconds must be positive"
            )

        if self._poll_interval_seconds <= 0:
            raise ValueError(
                "poll_interval_seconds must be positive"
            )

        # Optional convenience handles for processes created during the
        # current Python process lifetime. Durable stop semantics do not
        # depend on this dictionary.
        self._handles: dict[str, Any] = {}

    def start(
        self,
        *,
        workload_id: str,
        model_id: str,
        metadata: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        service_spec = self._service_spec_provider.build(
            model_id=model_id,
            metadata=metadata,
        )

        process = self._executor.start(
            service_spec
        )

        pid = getattr(
            process,
            "pid",
            None,
        )

        # Remain compatible if an executor later returns structured state.
        if pid is None and isinstance(
            process,
            Mapping,
        ):
            pid = process.get("pid")

        if isinstance(pid, bool) or not isinstance(pid, int):
            raise ProcessRuntimeError(
                "executor.start() did not return a process/PID"
            )

        if pid <= 1:
            raise ProcessRuntimeError(
                f"executor returned unsafe PID: {pid}"
            )

        if not _process_exists(pid):
            raise ProcessRuntimeError(
                "executor returned a process that is not alive: "
                f"{pid}"
            )

        start_ticks = _proc_start_ticks(pid)

        if start_ticks is None:
            raise ProcessRuntimeError(
                "could not capture Linux process identity for PID "
                f"{pid}"
            )

        command_sha256 = _proc_command_sha256(
            pid
        )

        if command_sha256 is None:
            raise ProcessRuntimeError(
                "could not capture process command identity for PID "
                f"{pid}"
            )

        if hasattr(process, "poll"):
            self._handles[
                workload_id
            ] = process

        return {
            "runtime_kind": "process_executor",
            "pid": pid,
            "proc_start_ticks": start_ticks,
            "command_sha256": command_sha256,
        }

    def _verify_identity(
        self,
        *,
        pid: int,
        expected_start_ticks: int,
        expected_command_sha256: str,
    ) -> None:
        if pid <= 1:
            raise ProcessIdentityError(
                f"refusing unsafe PID: {pid}"
            )

        if not _process_exists(pid):
            return

        actual_start_ticks = _proc_start_ticks(
            pid
        )

        if actual_start_ticks is None:
            raise ProcessIdentityError(
                "cannot verify current process start time "
                f"for PID {pid}"
            )

        if actual_start_ticks != expected_start_ticks:
            raise ProcessIdentityError(
                "PID identity mismatch; refusing to stop a reused PID "
                f"{pid}"
            )

        actual_command_sha256 = (
            _proc_command_sha256(pid)
        )

        if actual_command_sha256 is None:
            raise ProcessIdentityError(
                "cannot verify current process command "
                f"for PID {pid}"
            )

        if (
            actual_command_sha256
            != expected_command_sha256
        ):
            raise ProcessIdentityError(
                "process command identity mismatch; refusing stop "
                f"for PID {pid}"
            )

    def stop(
        self,
        *,
        workload_id: str,
        model_id: str,
        runtime_state: Mapping[str, Any],
    ) -> None:
        pid = runtime_state.get(
            "pid"
        )

        start_ticks = runtime_state.get(
            "proc_start_ticks"
        )

        command_sha256 = runtime_state.get(
            "command_sha256"
        )

        if isinstance(pid, bool) or not isinstance(pid, int):
            raise ProcessIdentityError(
                "runtime state has no valid PID"
            )

        if (
            isinstance(start_ticks, bool)
            or not isinstance(start_ticks, int)
        ):
            raise ProcessIdentityError(
                "runtime state has no process start identity"
            )

        if (
            not isinstance(command_sha256, str)
            or not command_sha256
        ):
            raise ProcessIdentityError(
                "runtime state has no command identity"
            )

        if not _process_exists(pid):
            self._handles.pop(
                workload_id,
                None,
            )
            return

        self._verify_identity(
            pid=pid,
            expected_start_ticks=start_ticks,
            expected_command_sha256=command_sha256,
        )

        handle = self._handles.get(
            workload_id
        )

        if (
            handle is not None
            and getattr(handle, "pid", None) == pid
            and hasattr(handle, "terminate")
        ):
            handle.terminate()

        else:
            os.kill(
                pid,
                signal.SIGTERM,
            )

        deadline = (
            time.monotonic()
            + self._stop_timeout_seconds
        )

        while time.monotonic() < deadline:
            if not _process_exists(pid):
                self._handles.pop(
                    workload_id,
                    None,
                )
                return

            # A Popen handle can reliably distinguish an exited child that
            # remains briefly as a zombie until wait() collects it.
            if handle is not None and hasattr(
                handle,
                "poll",
            ):
                if handle.poll() is not None:
                    if hasattr(handle, "wait"):
                        try:
                            handle.wait(
                                timeout=0
                            )
                        except Exception:
                            pass

                    self._handles.pop(
                        workload_id,
                        None,
                    )
                    return

            time.sleep(
                self._poll_interval_seconds
            )

        # Phase 9 v1 intentionally refuses automatic SIGKILL.
        raise ProcessRuntimeError(
            "process did not exit after SIGTERM within "
            f"{self._stop_timeout_seconds} seconds; "
            "manual/reconciliation handling required"
        )

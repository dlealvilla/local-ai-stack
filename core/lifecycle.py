import os
import signal
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / ".state"
LOG_DIR = PROJECT_ROOT / "logs"


def pid_file(service_id):
    return STATE_DIR / f"{service_id}.pid"


def log_file(service_id):
    return LOG_DIR / f"{service_id}.log"


def pid_is_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def read_pid(service_id):
    path = pid_file(service_id)

    if not path.is_file():
        return None

    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def port_is_open(host, port):
    try:
        with socket.create_connection(
            (host, port),
            timeout=1.0,
        ):
            return True
    except OSError:
        return False


def tail_log(service_id, lines=30):
    path = log_file(service_id)

    if not path.is_file():
        return ""

    return "\n".join(
        path.read_text(
            errors="replace"
        ).splitlines()[-lines:]
    )


def start_service(
    service_id,
    service_spec,
    executor,
    timeout=180,
):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    existing_pid = read_pid(service_id)

    if (
        existing_pid
        and pid_is_running(existing_pid)
    ):
        return {
            "status": "already_running",
            "pid": existing_pid,
            "log": str(log_file(service_id)),
        }

    pid_path = pid_file(service_id)

    if pid_path.exists():
        pid_path.unlink()

    command = executor.build_command(
        service_spec
    )

    environment = executor.build_environment(
        service_spec
    )

    log_path = log_file(service_id)

    with log_path.open("a") as log:
        log.write("\n" + "=" * 70 + "\n")
        log.write(
            f"AI Stack {service_id} start: "
            f"{datetime.now().isoformat()}\n"
        )
        log.write(
            "Command: "
            + " ".join(command)
            + "\n"
        )
        log.write("=" * 70 + "\n")
        log.flush()

        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    pid_path.write_text(str(process.pid))

    network = service_spec["network"]

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if process.poll() is not None:
            pid_path.unlink(
                missing_ok=True
            )

            return {
                "status": "failed",
                "pid": process.pid,
                "log": str(log_path),
                "log_tail": tail_log(
                    service_id
                ),
            }

        if port_is_open(
            network["host"],
            network["port"],
        ):
            return {
                "status": "ready",
                "pid": process.pid,
                "host": network["host"],
                "port": network["port"],
                "log": str(log_path),
            }

        time.sleep(2)

    return {
        "status": "starting",
        "pid": process.pid,
        "host": network["host"],
        "port": network["port"],
        "log": str(log_path),
    }



def process_group_is_running(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def stop_service(
    service_id,
    service_spec,
    timeout=20,
):
    """
    Stop a service started by start_service().

    PROVISIONAL:
    Service ownership is currently tracked with a PID file and
    an isolated process group created by start_new_session=True.

    Future versions should store richer service identity/state
    so process ownership can be validated more strongly.
    """

    pid_path = pid_file(service_id)
    pid = read_pid(service_id)

    if pid is None:
        pid_path.unlink(missing_ok=True)

        return {
            "status": "not_running",
        }

    if not pid_is_running(pid):
        pid_path.unlink(missing_ok=True)

        return {
            "status": "stale",
            "pid": pid,
        }

    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        pid_path.unlink(missing_ok=True)

        return {
            "status": "stale",
            "pid": pid,
        }

    # Safety guard: never terminate the shell / controller's
    # own process group.
    if pgid == os.getpgrp():
        return {
            "status": "failed",
            "pid": pid,
            "reason": (
                "Refusing to terminate the controller's "
                "own process group."
            ),
        }

    try:
        os.killpg(
            pgid,
            signal.SIGTERM,
        )
    except ProcessLookupError:
        pid_path.unlink(missing_ok=True)

        return {
            "status": "stopped",
            "pid": pid,
        }

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if not process_group_is_running(pgid):
            pid_path.unlink(missing_ok=True)

            return {
                "status": "stopped",
                "pid": pid,
            }

        time.sleep(0.5)

    # PROVISIONAL:
    # If graceful termination fails, force-stop the isolated
    # service process group.
    try:
        os.killpg(
            pgid,
            signal.SIGKILL,
        )
    except ProcessLookupError:
        pass

    force_deadline = time.monotonic() + 5

    while time.monotonic() < force_deadline:
        if not process_group_is_running(pgid):
            break

        time.sleep(0.25)

    pid_path.unlink(missing_ok=True)

    network = service_spec.get("network", {})

    return {
        "status": "forced",
        "pid": pid,
        "host": network.get("host"),
        "port": network.get("port"),
    }

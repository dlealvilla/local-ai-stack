import subprocess
import time

from pathlib import Path

from core.model_inventory import (
    build_platform_state,
)


PROVIDER = "current_cli"

REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


def capture_workload_state():
    """
    Capture enabled service runtime state.

    WORKING adapter:
    uses the normalized Platform State already exposed by
    the product.

    This adapter intentionally does not teach the maintenance
    subsystem about vLLM, Open WebUI, gateway implementations,
    or Platform API process details.
    """

    state = build_platform_state()

    services = []

    for service in (
        state[
            "deployment"
        ][
            "services"
        ]
    ):
        if not service.get(
            "enabled",
            False,
        ):
            continue

        observed = (
            service.get(
                "observed"
            )
            or {}
        )

        services.append({
            "id": (
                service[
                    "id"
                ]
            ),

            "role": (
                service[
                    "role"
                ]
            ),

            "provider": (
                service[
                    "provider"
                ]
            ),

            "running": bool(
                observed.get(
                    "running",
                    False,
                )
            ),
        })

    running = [
        item
        for item in services
        if item[
            "running"
        ]
    ]

    if not services:
        mode = "no_enabled_services"

    elif len(
        running
    ) == len(
        services
    ):
        mode = "all_running"

    elif not running:
        mode = "all_stopped"

    else:
        mode = "partial"

    return {
        "provider": PROVIDER,

        "mode": mode,

        "enabled_service_count": len(
            services
        ),

        "running_service_count": len(
            running
        ),

        "services": services,
    }


def _run_ai_command(
    command,
    *,
    timeout_seconds,
):
    """
    WORKING lifecycle implementation.

    The current CLI is reused because it already owns the
    dependency-aware service start/stop sequencing.

    FUTURE:
    Resource Manager will provide richer per-service restoration.
    """

    result = subprocess.run(
        [
            str(
                REPO_ROOT
                / "ai"
            ),
            command,
        ],

        cwd=REPO_ROOT,

        capture_output=True,
        text=True,

        timeout=(
            timeout_seconds
        ),

        check=False,
    )

    payload = {
        "command": command,

        "returncode": (
            result.returncode
        ),

        "stdout": (
            result.stdout
        ),

        "stderr": (
            result.stderr
        ),
    }

    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or (
                "Unknown lifecycle failure"
            )
        )

        raise RuntimeError(
            "./ai "
            + command
            + " failed: "
            + detail[-2000:]
        )

    return payload


def _wait_for_mode(
    expected_mode,
    *,
    timeout_seconds,
):
    deadline = (
        time.monotonic()
        + timeout_seconds
    )

    latest = None

    while (
        time.monotonic()
        < deadline
    ):
        latest = (
            capture_workload_state()
        )

        if (
            latest[
                "mode"
            ]
            == expected_mode
        ):
            return latest

        time.sleep(
            1.0
        )

    raise RuntimeError(
        "Timed out waiting for workload mode "
        + expected_mode
        + "; latest="
        + str(latest)
    )


def validate_restorable_state(
    state,
):
    """
    Current whole-stack CLI can exactly restore two states:

        all enabled services running
        all enabled services stopped

    A partially running deployment is refused rather than silently
    changed into a different state.

    FUTURE:
    Phase 9 Resource Manager can restore arbitrary per-service
    loaded/running state.
    """

    mode = state.get(
        "mode"
    )

    if mode not in {
        "all_running",
        "all_stopped",
        "no_enabled_services",
    }:
        raise RuntimeError(
            "Maintenance calibration currently refuses "
            "a partially running workload because exact "
            "per-service restoration is not yet available."
        )

    return True


def stop_for_maintenance(
    prior_state,
    *,
    timeout_seconds,
):
    validate_restorable_state(
        prior_state
    )

    if prior_state[
        "mode"
    ] in {
        "all_stopped",
        "no_enabled_services",
    }:
        return {
            "performed": False,

            "reason": (
                "workload_already_stopped"
            ),

            "state": (
                prior_state
            ),

            "command": None,
        }

    command_result = (
        _run_ai_command(
            "stop",

            timeout_seconds=(
                timeout_seconds
            ),
        )
    )

    stopped_state = (
        _wait_for_mode(
            "all_stopped",

            timeout_seconds=(
                timeout_seconds
            ),
        )
    )

    return {
        "performed": True,

        "reason": None,

        "state": (
            stopped_state
        ),

        "command": (
            command_result
        ),
    }


def restore_after_maintenance(
    prior_state,
    *,
    timeout_seconds,
):
    validate_restorable_state(
        prior_state
    )

    if prior_state[
        "mode"
    ] in {
        "all_stopped",
        "no_enabled_services",
    }:
        return {
            "performed": False,

            "reason": (
                "prior_workload_was_stopped"
            ),

            "state": (
                capture_workload_state()
            ),

            "command": None,
        }

    command_result = (
        _run_ai_command(
            "start",

            timeout_seconds=(
                timeout_seconds
            ),
        )
    )

    restored_state = (
        _wait_for_mode(
            "all_running",

            timeout_seconds=(
                timeout_seconds
            ),
        )
    )

    return {
        "performed": True,

        "reason": None,

        "state": (
            restored_state
        ),

        "command": (
            command_result
        ),
    }

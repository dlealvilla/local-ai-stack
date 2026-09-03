"""Is this SERVER platform-ready?

AI_DEPLOYMENT_HOST_READINESS

A fresh supported Linux/NVIDIA server should become platform-ready from
current product source with one product-owned command. `./ai prepare`
already provisions and reuses the managed runtimes, but it reported
nothing about the host, so an administrator could not tell from its
output whether the machine was actually usable.

This answers only the server question:

    is the host detected, does it have a usable accelerator, and are
    the runtimes this configuration requires present and executable?

It deliberately does NOT consider model selection. On a fresh host
`./ai preflight` reports `Ready: False` solely because no model is
selected, which reads as failure during preparation even though the
server itself is fine. Choosing a model is a later step, not a property
of the machine.

Nothing here detects or installs anything itself: every check is an
existing seam.

    core.hardware              host detection
    core.preflight             command and accelerator checks
    core.runtime_manager       which runtimes are required, and whether
                               each is present and executable

Read-only. Calling this provisions nothing, creates no directories and
mutates no state, so it is safe to run repeatedly.
"""

from core.hardware import inspect_hardware

from core.preflight import (
    check_command,
    check_nvidia_gpu,
    result,
)

from core.runtime_manager import (
    required_runtimes,
    runtime_executable,
    runtime_is_ready,
)


HOST_READINESS_SCHEMA_VERSION = 1


def _host_summary(hardware):
    gpus = hardware.get("gpus") or []

    return {
        "operating_system": hardware.get(
            "operating_system"
        ),

        "architecture": hardware.get(
            "architecture"
        ),

        "cpu_model": hardware.get("cpu_model"),

        "cpu_cores": hardware.get("cpu_cores"),

        "ram_total_gb": hardware.get(
            "ram_total_gb"
        ),

        "accelerators": [
            {
                "vendor": gpu.get("vendor"),
                "name": gpu.get("name"),
                "vram_total_gb": gpu.get(
                    "vram_total_gb"
                ),
            }
            for gpu in gpus
        ],
    }


def evaluate_host_readiness(
    config,
    *,
    hardware=None,
):
    """Report whether this server can host the configured platform.

    Returns the detected host, one check per requirement, and an
    overall verdict. A missing accelerator or an unprovisioned required
    runtime makes the host not ready; an absent model does not, because
    that is not a property of the server.
    """

    if hardware is None:
        hardware = inspect_hardware()

    checks = [
        check_command("python3"),
        check_nvidia_gpu(),
    ]

    #
    # The configuration decides which runtimes matter, so a host with
    # no frontend configured is not penalised for lacking one.
    #
    for name in required_runtimes(config):
        if runtime_is_ready(name):
            checks.append(
                result(
                    f"{name} runtime",
                    "pass",
                    str(runtime_executable(name)),
                )
            )

        else:
            checks.append(
                result(
                    f"{name} runtime",
                    "fail",
                    (
                        "Not provisioned. Run './ai prepare' "
                        "to provision it."
                    ),
                )
            )

    failed = [
        check["name"]
        for check in checks
        if check["status"] != "pass"
    ]

    return {
        "schema_version": (
            HOST_READINESS_SCHEMA_VERSION
        ),

        "host": _host_summary(hardware),

        "checks": checks,

        "ready": not failed,

        "blocking": failed,

        #
        # Stated explicitly so the verdict cannot be mistaken for
        # deployment readiness.
        #
        "scope": (
            "server_and_runtime_only; model selection is not "
            "evaluated"
        ),
    }

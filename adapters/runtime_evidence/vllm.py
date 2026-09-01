"""
vLLM runtime memory evidence.

WORKING / PROVISIONAL:

The current vLLM deployment exposes useful memory diagnostics through
its startup log.

This adapter binds those diagnostics to LIVE EngineCore PIDs before
treating them as evidence.

Historical log entries from processes that no longer exist are never
returned as current-engine evidence.

The startup diagnostics are also kept separate from current live
capacity observations. For example:

    startup_free_device_bytes

is NOT the same concept as:

    current_free_vram_bytes

Current live capacity remains owned by core.capacity_snapshot.

A future vLLM adapter may replace log parsing with structured runtime
metrics or a direct API.
"""


import os
import re
from pathlib import Path


VLLM_RUNTIME_EVIDENCE_SCHEMA_VERSION = 1

GIB = 1024 ** 3


_MEMORY_LINE = re.compile(
    r"\("
    r"EngineCore(?:_DP\d+)?"
    r"\s+pid=(?P<pid>\d+)"
    r"\)"
    r".*?"
    r"Free memory on device "
    r"\("
    r"(?P<startup_free>[0-9.]+)"
    r"/"
    r"(?P<startup_total>[0-9.]+)"
    r"\s+GiB"
    r"\)"
    r"\s+on startup\."
    r".*?"
    r"Desired GPU memory utilization is "
    r"\("
    r"(?P<utilization>[0-9.]+)"
    r",\s*"
    r"(?P<budget>[0-9.]+)"
    r"\s+GiB"
    r"\)"
    r"\."
    r".*?"
    r"Actual usage is "
    r"(?P<weight>[0-9.]+)"
    r"\s+GiB for weight,"
    r"\s*"
    r"(?P<activation>[0-9.]+)"
    r"\s+GiB for peak activation,"
    r"\s*"
    r"(?P<non_torch>[0-9.]+)"
    r"\s+GiB for non-torch memory,"
    r"\s+and\s+"
    r"(?P<cuda_graph>[0-9.]+)"
    r"\s+GiB for CUDAGraph memory\."
    r".*?"
    r"Current kv cache memory in use is "
    r"(?P<kv_cache>\d+)"
    r"\s+bytes\.",
)


def _gib_to_bytes(
    value,
):
    return int(
        round(
            float(
                value
            )
            * GIB
        )
    )


def find_live_vllm_engine_pids():
    """
    Find currently live vLLM EngineCore processes.

    Linux process names may be truncated to 15 characters, therefore
    VLLM::EngineCore commonly appears as VLLM::EngineCor in /proc.
    """

    pids = []


    proc = Path(
        "/proc"
    )


    if not proc.exists():
        return pids


    for entry in proc.iterdir():

        if not entry.name.isdigit():
            continue


        try:
            status_lines = (
                entry
                / "status"
            ).read_text().splitlines()

        except (
            FileNotFoundError,
            PermissionError,
            ProcessLookupError,
            OSError,
        ):
            continue


        process_name = None


        for line in status_lines:

            if line.startswith(
                "Name:"
            ):

                process_name = (
                    line.split(
                        ":",
                        1,
                    )[
                        1
                    ].strip()
                )

                break


        matches_name = (
            process_name is not None
            and process_name.startswith(
                "VLLM::EngineCor"
            )
        )


        matches_cmdline = False


        if not matches_name:

            try:
                cmdline = (
                    entry
                    / "cmdline"
                ).read_bytes().replace(
                    b"\x00",
                    b" ",
                ).decode(
                    "utf-8",
                    errors="replace",
                )

            except (
                FileNotFoundError,
                PermissionError,
                ProcessLookupError,
                OSError,
            ):
                cmdline = ""


            matches_cmdline = (
                "VLLM::EngineCore"
                in cmdline
            )


        if (
            matches_name
            or matches_cmdline
        ):
            pids.append(
                int(
                    entry.name
                )
            )


    return sorted(
        set(
            pids
        )
    )


def parse_runtime_memory_line(
    line,
):
    """
    Parse one vLLM startup memory diagnostic.

    Returns None when the line is not the known supported diagnostic
    format.
    """

    match = _MEMORY_LINE.search(
        line
    )


    if match is None:
        return None


    values = (
        match.groupdict()
    )


    return {
        "schema_version": (
            VLLM_RUNTIME_EVIDENCE_SCHEMA_VERSION
        ),

        "provider": (
            "vllm"
        ),

        "engine_pid": int(
            values[
                "pid"
            ]
        ),

        "time_semantics": (
            "current_engine_startup_evidence"
        ),

        "device_at_startup": {
            "free_bytes": (
                _gib_to_bytes(
                    values[
                        "startup_free"
                    ]
                )
            ),

            "total_bytes": (
                _gib_to_bytes(
                    values[
                        "startup_total"
                    ]
                )
            ),
        },

        "configured_memory": {
            "gpu_memory_utilization": float(
                values[
                    "utilization"
                ]
            ),

            "gpu_budget_bytes": (
                _gib_to_bytes(
                    values[
                        "budget"
                    ]
                )
            ),
        },

        "reported_components": {
            "weight_residency_bytes": (
                _gib_to_bytes(
                    values[
                        "weight"
                    ]
                )
            ),

            "activation_peak_bytes": (
                _gib_to_bytes(
                    values[
                        "activation"
                    ]
                )
            ),

            "non_torch_bytes": (
                _gib_to_bytes(
                    values[
                        "non_torch"
                    ]
                )
            ),

            "cuda_graph_bytes": (
                _gib_to_bytes(
                    values[
                        "cuda_graph"
                    ]
                )
            ),

            #
            # vLLM reports this value directly in bytes.
            #
            "kv_cache_bytes": int(
                values[
                    "kv_cache"
                ]
            ),
        },

        "confidence": (
            "high"
        ),

        "evidence_kind": (
            "runtime_reported_startup_memory"
        ),

        "raw_line": (
            line.rstrip(
                "\n"
            )
        ),
    }


def collect_runtime_memory_evidence(
    *,
    log_path="logs/inference.log",
    live_pids=None,
):
    """
    Return the newest supported memory diagnostic for each live
    EngineCore PID.

    Evidence from dead/historical PIDs is ignored.
    """

    if live_pids is None:

        live_pids = (
            find_live_vllm_engine_pids()
        )


    live_pids = {
        int(
            pid
        )

        for pid in live_pids
    }


    path = Path(
        log_path
    )


    if not path.exists():

        return {
            "schema_version": (
                VLLM_RUNTIME_EVIDENCE_SCHEMA_VERSION
            ),

            "provider": (
                "vllm"
            ),

            "resolved": False,

            "reason": (
                "runtime_log_missing"
            ),

            "live_engine_pids": sorted(
                live_pids
            ),

            "engines": [],
        }


    newest_by_pid = {}


    for line in path.read_text(
        errors="replace"
    ).splitlines():

        parsed = (
            parse_runtime_memory_line(
                line
            )
        )


        if parsed is None:
            continue


        pid = (
            parsed[
                "engine_pid"
            ]
        )


        if pid not in live_pids:
            continue


        #
        # Iterating forward means a later matching line replaces an
        # earlier line for the same live process.
        #
        newest_by_pid[
            pid
        ] = parsed


    engines = [
        newest_by_pid[
            pid
        ]

        for pid in sorted(
            newest_by_pid
        )
    ]


    missing_live_pids = sorted(
        live_pids
        - set(
            newest_by_pid
        )
    )


    return {
        "schema_version": (
            VLLM_RUNTIME_EVIDENCE_SCHEMA_VERSION
        ),

        "provider": (
            "vllm"
        ),

        "resolved": (
            bool(
                engines
            )
            and not missing_live_pids
        ),

        "reason": (
            None
            if (
                engines
                and not missing_live_pids
            )
            else (
                "live_engine_startup_evidence_missing"
            )
        ),

        "live_engine_pids": sorted(
            live_pids
        ),

        "missing_live_engine_pids": (
            missing_live_pids
        ),

        "engines": (
            engines
        ),

        "historical_process_evidence_excluded": (
            True
        ),
    }

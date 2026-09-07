"""Reference serving runtime. Translates a request into a loopback recipe."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
)

IDENTITY = Name("reference-serving")
EXECUTOR_KIND = Name("native-process")
WORKLOAD_MODULE = "kultrun.adapters.runtime.serving_workload"
_IMPORT_ROOT = str(Path(__file__).resolve().parents[3])


class ReferenceServingRuntime:
    """Produces argv for the reference HTTP server. Does not exec."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            runtime=self.identity,
            display_name="Reference serving (lifecycle harness)",
            executor_kind=EXECUTOR_KIND,
            capabilities=("process-lifecycle", "loopback-health", "readiness"),
        )

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        mode = request.mode if request is not None else "healthy"
        instance_id = request.instance_id if request is not None else ""
        bind = request.bind_address if request is not None else "127.0.0.1"
        return RuntimeLaunchSpec(
            runtime=self.identity,
            profile=self.identity,
            executable=sys.executable,
            arguments=("-m", WORKLOAD_MODULE),
            environment=(
                "KULTRUN_REFERENCE_SERVING=1",
                f"KULTRUN_REFERENCE_SERVING_MODE={mode}",
                f"KULTRUN_INSTANCE_ID={instance_id}",
                f"KULTRUN_REFERENCE_BIND={bind}",
                f"PYTHONPATH={_child_pythonpath()}",
            ),
            grace_period_seconds=2.0,
        )


def _child_pythonpath() -> str:
    current = os.environ.get("PYTHONPATH", "")
    if not current:
        return _IMPORT_ROOT
    parts = current.split(os.pathsep)
    if _IMPORT_ROOT in parts:
        return current
    return _IMPORT_ROOT + os.pathsep + current


def build() -> ReferenceServingRuntime:
    return ReferenceServingRuntime()
